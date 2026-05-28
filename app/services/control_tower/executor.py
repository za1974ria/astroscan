"""AstroScan Control Tower — Phase 4C.1 controlled executor.

Real-execution layer for **exactly two** whitelisted actions:

  proc_gunicorn → sudo -n systemctl restart astroscan.service
  proc_nginx    → sudo -n systemctl restart nginx.service

Every other input is refused at the whitelist gate. The executor is:
  - subprocess-only (no os.system, no popen, no shell=True)
  - timeout-protected (hard wall-clock cap)
  - rate-limited (per-target cooldown + global storm lock)
  - operator-overridable (kill switch and maintenance flag files)
  - fully audited (append-only TSV log)
  - cross-worker safe via audit-log scanning (cooldown + storm)

Safety review checklist — verifiable by AST grep on this file:
  - imports subprocess only with shell=False explicit calls
  - never uses os.system / os.popen / shutil.rm* / os.kill
  - whitelist is a constant module-level dict (no dynamic mutation)
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timezone

# ── Configuration constants ──────────────────────────────────────────
KILL_SWITCH_PATH = "/opt/astroscan/runtime/remediation.disabled"
MAINTENANCE_FLAG_PATH = "/opt/astroscan/runtime/maintenance.flag"
AUDIT_LOG_PATH = "/opt/astroscan/logs/remediation.log"

COOLDOWN_SECONDS = 600           # per-target lockout window
STORM_WINDOW_SECONDS = 900       # 15-minute global window
STORM_MAX_ACTIONS = 3            # ≥ this many attempts in window → freeze
COMMAND_TIMEOUT_SECONDS = 15     # hard wall-clock cap for subprocess
AUDIT_TAIL_BYTES = 65536         # tail read window of audit log

# ── Strict whitelist ─────────────────────────────────────────────────
# target_id → immutable argv tuple. The argv is built ONCE here, never
# templated, never composed from external input. Any other target_id is
# rejected at gate 1 (whitelist check).
_WHITELIST: dict[str, tuple[str, ...]] = {
    "proc_gunicorn": (
        "/usr/bin/sudo", "-n",
        "/usr/bin/systemctl", "restart", "astroscan.service",
    ),
    "proc_nginx": (
        "/usr/bin/sudo", "-n",
        "/usr/bin/systemctl", "restart", "nginx.service",
    ),
}

# Per-target serialization. Prevents two threads of the SAME worker from
# launching the same restart simultaneously. Cross-worker contention is
# handled by the audit-log cooldown read.
_target_locks: dict[str, threading.Lock] = {
    k: threading.Lock() for k in _WHITELIST
}

logger = logging.getLogger("astroscan.control_tower.executor")


# ── Time helpers ─────────────────────────────────────────────────────
def _now_ts() -> float:
    return time.time()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Audit log: append-only TSV ───────────────────────────────────────
# Format per line (tab-separated, 5 fields):
#   <iso8601-utc>\t<target_id>\t<decision>\t<result>\t<reason>
#
# decision ∈ {executing, executed, skipped}
# result   ∈ {ok, failed, blocked, started}
def _audit_write(target_id: str, decision: str, result: str, reason: str) -> None:
    """Best-effort append. NEVER raises."""
    line = (
        f"{_now_iso()}\t{target_id}\t{decision}\t{result}\t"
        f"{(reason or '').replace(chr(10), ' ').replace(chr(9), ' ')[:400]}\n"
    )
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:  # noqa: BLE001 — audit must not break the snapshot
        logger.error("audit write failed (%s) for line=%r", exc, line)


def _audit_read_recent_starts(window_seconds: float) -> list[tuple[float, str]]:
    """Return list of (ts, target_id) for "executing" entries in window.

    Used by cooldown and storm gates so they survive across gunicorn
    workers. Reads only the audit log tail (last AUDIT_TAIL_BYTES) to
    bound the scan cost. Defensive: any I/O issue returns [] (fail-open
    on gates is acceptable because subsequent gates and the whitelist
    still apply; we'd rather attempt a legitimate restart than freeze
    forever on a corrupt log)."""
    cutoff = _now_ts() - window_seconds
    out: list[tuple[float, str]] = []
    if not os.path.exists(AUDIT_LOG_PATH):
        return out
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            try:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - AUDIT_TAIL_BYTES), os.SEEK_SET)
                if size > AUDIT_TAIL_BYTES:
                    f.readline()  # discard partial line
            except OSError:
                f.seek(0)
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 5:
                    continue
                ts_iso, tid, decision, result, _reason = parts[:5]
                if decision != "executing":
                    continue
                try:
                    ts = datetime.fromisoformat(ts_iso).timestamp()
                except (ValueError, TypeError):
                    continue
                if ts < cutoff:
                    continue
                out.append((ts, tid))
    except OSError:
        return []
    return out


# ── Safety gates ─────────────────────────────────────────────────────
def _gate_whitelist(target_id: str) -> tuple[bool, str]:
    if target_id not in _WHITELIST:
        return False, f"target {target_id!r} not in whitelist"
    return True, ""


def _gate_kill_switch() -> tuple[bool, str]:
    if os.path.exists(KILL_SWITCH_PATH):
        return False, f"kill switch active: {KILL_SWITCH_PATH}"
    return True, ""


def _gate_maintenance() -> tuple[bool, str]:
    if os.path.exists(MAINTENANCE_FLAG_PATH):
        return False, f"maintenance flag active: {MAINTENANCE_FLAG_PATH}"
    return True, ""


def _gate_cooldown(target_id: str) -> tuple[bool, str]:
    recent = _audit_read_recent_starts(COOLDOWN_SECONDS)
    same = [ts for ts, tid in recent if tid == target_id]
    if not same:
        return True, ""
    last = max(same)
    remaining = int(COOLDOWN_SECONDS - (_now_ts() - last))
    return False, f"cooldown active ({remaining}s remaining)"


def _gate_storm() -> tuple[bool, str]:
    recent = _audit_read_recent_starts(STORM_WINDOW_SECONDS)
    count = len(recent)
    if count >= STORM_MAX_ACTIONS:
        return False, (
            f"storm lock: {count} actions in last {STORM_WINDOW_SECONDS}s "
            f"(>= {STORM_MAX_ACTIONS})"
        )
    return True, ""


def _run_all_gates(target_id: str) -> tuple[bool, str]:
    for gate in (
        lambda: _gate_whitelist(target_id),
        _gate_kill_switch,
        _gate_maintenance,
        _gate_storm,
        lambda: _gate_cooldown(target_id),
    ):
        ok, why = gate()
        if not ok:
            return False, why
    return True, ""


# ── Public API ───────────────────────────────────────────────────────
def execute_remediation(target_id: str, reason: str = "") -> dict:
    """Execute the whitelisted restart for `target_id`.

    NEVER raises. Always returns a structured outcome dict. Every code
    path either logs an audit line OR is reached after one has been
    written, so post-mortem reconstruction is always possible from
    AUDIT_LOG_PATH alone.

    Outcome dict shape:
        target_id      : str
        decision       : "executed" | "skipped"
        result         : "ok" | "failed" | "blocked"
        reason         : str
        command        : list[str] | None
        stdout         : str (capped 1 KiB)
        stderr         : str (capped 1 KiB)
        exit_code      : int | None
        started_at     : iso8601
        duration_ms    : int
    """
    started_iso = _now_iso()
    started_ts = _now_ts()

    def _make_outcome(decision, result, reason_str, cmd, stdout, stderr, exit_code):
        return {
            "target_id": target_id,
            "decision": decision,
            "result": result,
            "reason": reason_str,
            "command": list(cmd) if cmd else None,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "started_at": started_iso,
            "duration_ms": int((_now_ts() - started_ts) * 1000),
        }

    # Gates (whitelist FIRST, then kill switch, maintenance, storm, cooldown).
    allowed, gate_reason = _run_all_gates(target_id)
    if not allowed:
        _audit_write(target_id, "skipped", "blocked", gate_reason)
        cmd = _WHITELIST.get(target_id)
        return _make_outcome("skipped", "blocked", gate_reason, cmd, "", "", None)

    cmd = _WHITELIST[target_id]
    lock = _target_locks[target_id]

    # Per-target lock prevents two threads in the SAME worker firing
    # the same restart concurrently. If we can't acquire it instantly,
    # another thread is already executing → skip.
    if not lock.acquire(blocking=False):
        msg = "another thread is already executing this target"
        _audit_write(target_id, "skipped", "blocked", msg)
        return _make_outcome("skipped", "blocked", msg, cmd, "", "", None)

    try:
        # PRE-event: persist intent BEFORE subprocess. This is the
        # entry that future cooldown/storm gates count on. If the
        # worker dies mid-restart, this line remains as evidence.
        _audit_write(target_id, "executing", "started",
                     f"reason={reason!r}")

        try:
            proc = subprocess.run(
                list(cmd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=COMMAND_TIMEOUT_SECONDS,
                shell=False,
                check=False,
            )
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace")[:1024]
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace")[:1024]
            ok = (proc.returncode == 0)
            outcome_result = "ok" if ok else "failed"
            audit_msg = (
                f"reason={reason!r} exit={proc.returncode} "
                f"stderr={stderr[:200]!r}"
            )
            _audit_write(target_id, "executed", outcome_result, audit_msg)
            return _make_outcome(
                "executed", outcome_result,
                reason or "policy-triggered",
                cmd, stdout, stderr, proc.returncode,
            )

        except subprocess.TimeoutExpired:
            msg = f"timeout after {COMMAND_TIMEOUT_SECONDS}s"
            _audit_write(target_id, "executed", "failed", msg)
            return _make_outcome("executed", "failed", msg, cmd, "", "", None)

        except FileNotFoundError as e:
            msg = f"executable not found: {e}"
            _audit_write(target_id, "executed", "failed", msg)
            return _make_outcome("executed", "failed", msg, cmd, "", "", None)

        except Exception as exc:  # noqa: BLE001 — final guard
            msg = f"unexpected error: {str(exc)[:120]}"
            _audit_write(target_id, "executed", "failed", msg)
            return _make_outcome("executed", "failed", msg, cmd, "", "", None)

    finally:
        lock.release()


def execution_status() -> dict:
    """Read-only debug introspection. Safe for future /api exposure."""
    recent_starts = _audit_read_recent_starts(STORM_WINDOW_SECONDS)
    return {
        "kill_switch_path": KILL_SWITCH_PATH,
        "maintenance_flag_path": MAINTENANCE_FLAG_PATH,
        "audit_log_path": AUDIT_LOG_PATH,
        "kill_switch_active": os.path.exists(KILL_SWITCH_PATH),
        "maintenance_active": os.path.exists(MAINTENANCE_FLAG_PATH),
        "whitelist": sorted(_WHITELIST.keys()),
        "cooldown_seconds": COOLDOWN_SECONDS,
        "storm_window_seconds": STORM_WINDOW_SECONDS,
        "storm_max_actions": STORM_MAX_ACTIONS,
        "command_timeout_seconds": COMMAND_TIMEOUT_SECONDS,
        "recent_starts_in_window": [
            {"ts": ts, "target_id": tid} for ts, tid in recent_starts
        ],
        "storm_locked": len(recent_starts) >= STORM_MAX_ACTIONS,
    }
