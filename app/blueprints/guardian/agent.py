"""Guardian monitoring agent — daemon thread.

Polls every GUARDIAN_POLL_INTERVAL seconds (default 60):
    1. Run collect_all() — snapshot of all probes.
    2. Evaluate rules.yaml against the snapshot.
    3. For each fired incident, write to audit_log + log.warning.
    4. (Optional) For 'critical' incidents, call AstroBrainService.summarize_health()
       to attach a human-readable narrative — but only when OPENAI_API_KEY is
       present AND LLM_DRY_RUN=0, and at most once per incident.

Design choices:
    - One singleton thread per process (gunicorn worker). Started lazily on
      the first request that imports this module via app/__init__.py.
    - Hard-coded ceiling on consecutive errors before backoff to avoid log
      spam if everything is broken.
    - The thread is daemon=True → does NOT block gunicorn graceful shutdown.
    - State is held module-level: it survives across requests within the
      same worker process but is NOT shared between workers (acceptable for
      monitoring, which is naturally idempotent).

CHANTIER 5 (2026-05-23) — Discipline pass:
    - Restart grace window: 90s after agent boot, suppress availability rules
      (service_down/http_root_down/nginx_down/sentinel_health_down) to avoid
      spurious alerts during gunicorn warmup.
    - Confirmation gate: LLM narrative skipped on first occurrence — require
      ≥2 consecutive fires of the same rule (still within cooldown window) to
      escalate. Blocks transient blips from burning OpenAI budget.
    - LLM rate-limit window 15 min process-local (in addition to 20/day cap).
    - Per-rule incident counter exposed via health() for observability.
"""
from __future__ import annotations

import errno
import fcntl
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.blueprints.guardian import audit_log, collectors, rules

log = logging.getLogger(__name__)


DEFAULT_POLL_INTERVAL_S = 60
MIN_POLL_INTERVAL_S = 5  # safety floor
MAX_CONSECUTIVE_ERRORS_BEFORE_BACKOFF = 5

# CHANTIER 5 — Discipline constants.
RESTART_GRACE_SECONDS = 90
LLM_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
LLM_DAILY_CAP = 20
CONFIRMATION_MIN_FIRES = 2
AVAILABILITY_RULES = frozenset({
    "service_down", "http_root_down", "nginx_down", "sentinel_health_down",
})

# CHANTIER 5B — Cross-worker singleton via fcntl file lock.
# Each gunicorn worker imports routes.py which calls start_agent(). Without
# this lock, every worker spawns its own polling daemon → N× polling and
# N× LLM calls. We hold an OS-level exclusive non-blocking lock on a tmpfile
# for the lifetime of the leader worker. When the leader dies (graceful
# restart, --max-requests recycle, crash), the kernel releases the lock and
# the next worker to call start_agent() becomes leader.
_DEFAULT_LOCK_PATH = "/tmp/astroscan_guardian.lock"
_SINGLETON_LOCK_FD = None  # holds the open fd → must not be GC'd
_SINGLETON_LEADER_PID: int | None = None


def _lock_path() -> str:
    raw = (os.environ.get("GUARDIAN_LOCK_PATH") or "").strip()
    return raw or _DEFAULT_LOCK_PATH


def _allow_multi_workers() -> bool:
    """Debug escape hatch — disable singleton enforcement."""
    return (os.environ.get("GUARDIAN_ALLOW_MULTI") or "").strip() in (
        "1", "true", "True", "yes", "on",
    )


def _acquire_singleton_lock() -> bool:
    """Acquire the cross-worker singleton lock. Non-blocking.

    Returns:
        True if this worker is now (or was already) the singleton leader.
        False if another worker holds the lock — caller must no-op.

    Side effect:
        On success, stores the file descriptor in module global so the OS
        keeps the lock alive for the worker's lifetime. The PID is written
        into the file for observability (cat /tmp/astroscan_guardian.lock).
    """
    global _SINGLETON_LOCK_FD, _SINGLETON_LEADER_PID

    if _allow_multi_workers():
        return True
    if _SINGLETON_LOCK_FD is not None:
        return True  # already holding in this process

    path = _lock_path()
    fd = None
    try:
        fd = open(path, "a+")
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            err = getattr(exc, "errno", None)
            if err in (errno.EAGAIN, errno.EWOULDBLOCK):
                fd.close()
                return False
            log.warning("[guardian] flock failed unexpectedly on %s: %s", path, exc)
            fd.close()
            return False
        # Lock obtained → write our pid for observability.
        try:
            fd.seek(0)
            fd.truncate()
            fd.write(f"{os.getpid()}\n")
            fd.flush()
        except OSError:
            pass  # observability is best-effort
        _SINGLETON_LOCK_FD = fd
        _SINGLETON_LEADER_PID = os.getpid()
        return True
    except OSError as exc:
        log.warning("[guardian] singleton lock open failed on %s: %s", path, exc)
        if fd is not None:
            try:
                fd.close()
            except OSError:
                pass
        return False


def _is_singleton_leader() -> bool:
    return _SINGLETON_LOCK_FD is not None and _SINGLETON_LEADER_PID == os.getpid()


def _poll_interval() -> float:
    raw = (os.environ.get("GUARDIAN_POLL_INTERVAL") or "").strip()
    if not raw:
        return float(DEFAULT_POLL_INTERVAL_S)
    try:
        return max(MIN_POLL_INTERVAL_S, float(raw))
    except ValueError:
        log.warning("[guardian] invalid GUARDIAN_POLL_INTERVAL=%r, using default", raw)
        return float(DEFAULT_POLL_INTERVAL_S)


def _enabled() -> bool:
    return (os.environ.get("GUARDIAN_ENABLED") or "1").strip() in ("1", "true", "True", "yes")


def _restart_grace_seconds() -> float:
    raw = (os.environ.get("GUARDIAN_RESTART_GRACE_S") or "").strip()
    if not raw:
        return float(RESTART_GRACE_SECONDS)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(RESTART_GRACE_SECONDS)


@dataclass
class AgentState:
    thread: threading.Thread | None = None
    started: bool = False
    stop_event: threading.Event = field(default_factory=threading.Event)
    last_tick_ts: float = 0.0
    ticks_total: int = 0
    last_snapshots: list[dict] = field(default_factory=list)
    cooldowns: dict[str, datetime] = field(default_factory=dict)
    rules_cache: list[rules.Rule] = field(default_factory=list)
    consecutive_errors: int = 0
    llm_summaries_today: int = 0
    llm_summaries_date: str = ""
    # CHANTIER 5 additions.
    boot_ts: float = 0.0
    last_llm_ts: float = 0.0
    incident_counters: dict[str, int] = field(default_factory=dict)
    suppressed_grace_count: int = 0


_STATE = AgentState()
_STATE_LOCK = threading.Lock()


def _in_restart_grace(state: AgentState, now_ts: float | None = None) -> bool:
    """True if we're still within the post-boot grace window."""
    grace = _restart_grace_seconds()
    if grace <= 0.0 or state.boot_ts <= 0.0:
        return False
    now_ts = now_ts if now_ts is not None else time.time()
    return (now_ts - state.boot_ts) < grace


def _filter_grace_incidents(incidents: list, state: AgentState) -> list:
    """Drop availability-class incidents during the restart grace window.
    Returns the filtered incidents list and increments the suppression counter."""
    if not incidents or not _in_restart_grace(state):
        return incidents
    kept: list = []
    dropped = 0
    for inc in incidents:
        if inc.rule in AVAILABILITY_RULES:
            dropped += 1
            continue
        kept.append(inc)
    if dropped:
        state.suppressed_grace_count += dropped
        log.info(
            "[guardian] restart grace active — suppressed %d availability incidents "
            "(grace_remaining=%.1fs)",
            dropped, _restart_grace_seconds() - (time.time() - state.boot_ts),
        )
    return kept


def _maybe_llm_summarize(incident: dict, snapshot_map: dict[str, dict]) -> str | None:
    """If conditions allow, ask AstroBrain to summarize the incident. Best-effort.

    Gates (cumulative):
      - LLM_DRY_RUN != truthy
      - OPENAI_API_KEY present
      - severity == "critical"
      - rule has fired >= CONFIRMATION_MIN_FIRES (confirmation gate)
      - time since last LLM call >= LLM_RATE_LIMIT_WINDOW_SECONDS
      - daily count < LLM_DAILY_CAP
    """
    if (os.environ.get("LLM_DRY_RUN") or "").strip() in ("1", "true", "True", "yes"):
        return None
    if not (os.environ.get("OPENAI_API_KEY") or "").strip():
        return None
    if incident.get("severity") != "critical":
        return None

    rule_name = str(incident.get("rule") or "")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    now_ts = time.time()

    with _STATE_LOCK:
        # Reset daily counter on date rollover.
        if _STATE.llm_summaries_date != today:
            _STATE.llm_summaries_date = today
            _STATE.llm_summaries_today = 0

        # Confirmation gate: require N>=2 fires for this rule before escalating.
        fires = _STATE.incident_counters.get(rule_name, 0)
        if fires < CONFIRMATION_MIN_FIRES:
            log.debug(
                "[guardian] LLM gated (confirmation): rule=%s fires=%d need=%d",
                rule_name, fires, CONFIRMATION_MIN_FIRES,
            )
            return None

        # Rate-limit window (in addition to daily cap).
        elapsed = now_ts - _STATE.last_llm_ts
        if _STATE.last_llm_ts > 0 and elapsed < LLM_RATE_LIMIT_WINDOW_SECONDS:
            log.info(
                "[guardian] LLM rate-limited: %.0fs since last call (window=%ds)",
                elapsed, LLM_RATE_LIMIT_WINDOW_SECONDS,
            )
            return None

        # Daily budget cap.
        if _STATE.llm_summaries_today >= LLM_DAILY_CAP:
            log.info(
                "[guardian] LLM daily cap reached (%d) — skipping for rule=%s",
                LLM_DAILY_CAP, rule_name,
            )
            return None

        _STATE.llm_summaries_today += 1
        _STATE.last_llm_ts = now_ts

    try:
        from app.blueprints.astrobrain.service import AstroBrainService

        svc = AstroBrainService()
        payload = {"incident": incident, "subsystem_snapshot": snapshot_map}
        result = svc.summarize_health(payload)
        if result.get("ok"):
            return result.get("answer")
    except Exception as exc:  # noqa: BLE001
        log.debug("[guardian] LLM summarize_health failed: %s", exc)
    return None


def _tick(state: AgentState) -> None:
    """One iteration of the monitoring loop."""
    state.last_tick_ts = time.time()
    state.ticks_total += 1

    try:
        snapshots = collectors.collect_all()
        state.last_snapshots = snapshots
    except Exception as exc:  # noqa: BLE001
        log.warning("[guardian] collectors.collect_all crashed: %s", exc)
        snapshots = []

    incidents, new_cooldowns = rules.evaluate(
        state.rules_cache, snapshots, cooldown_state=state.cooldowns,
    )
    state.cooldowns = new_cooldowns

    # CHANTIER 5 — Suppress availability alerts during restart grace.
    incidents = _filter_grace_incidents(incidents, state)

    if not incidents:
        return

    snap_map = {s.get("name", ""): s for s in snapshots}
    for inc in incidents:
        # CHANTIER 5 — Track per-rule fire counter for confirmation gate.
        with _STATE_LOCK:
            state.incident_counters[inc.rule] = state.incident_counters.get(inc.rule, 0) + 1
            fires_now = state.incident_counters[inc.rule]

        record = {
            "ts": inc.ts,
            "rule": inc.rule,
            "severity": inc.severity,
            "metric": inc.metric,
            "operator": inc.operator,
            "threshold": inc.threshold,
            "actual": inc.actual,
            "cooldown_until": inc.cooldown_until,
            "fire_count": fires_now,
        }
        # CHANTIER 5 — Local first: write incident + warning BEFORE any remote call.
        audit_log.write_incident(record)
        log.warning(
            "[guardian] incident rule=%s severity=%s metric=%s actual=%s "
            "threshold=%s fires=%d",
            inc.rule, inc.severity, inc.metric, inc.actual, inc.threshold, fires_now,
        )
        # LLM call gated by _maybe_llm_summarize (confirmation + rate-limit + cap).
        narrative = _maybe_llm_summarize(record, snap_map)
        if narrative:
            record["narrative"] = narrative
            # Persist again with narrative attached (append-only log keeps both).
            audit_log.write_incident({"rule": inc.rule, "narrative": narrative,
                                       "ts": inc.ts, "kind": "narrative"})


def _run_loop(state: AgentState) -> None:
    """Body of the daemon thread. Exits cleanly on stop_event."""
    log.info(
        "[guardian] agent loop started (interval=%.1fs, rules=%d, "
        "restart_grace=%.0fs, llm_window=%ds)",
        _poll_interval(), len(state.rules_cache),
        _restart_grace_seconds(), LLM_RATE_LIMIT_WINDOW_SECONDS,
    )
    interval = _poll_interval()
    while not state.stop_event.is_set():
        try:
            _tick(state)
            state.consecutive_errors = 0
        except Exception as exc:  # noqa: BLE001
            state.consecutive_errors += 1
            log.warning("[guardian] tick failed (%d): %s", state.consecutive_errors, exc)
            if state.consecutive_errors >= MAX_CONSECUTIVE_ERRORS_BEFORE_BACKOFF:
                # Exponential backoff cap when broken state persists
                interval = min(interval * 2, 600.0)
                state.consecutive_errors = 0
                log.warning("[guardian] backing off to %.0fs", interval)
            else:
                interval = _poll_interval()
        if state.stop_event.wait(interval):
            break
    log.info("[guardian] agent loop stopped")


# ─── Public lifecycle ───────────────────────────────────────────────────────


def start_agent() -> bool:
    """Start the daemon thread if not already running. Idempotent.

    Returns True if a fresh thread was spawned, False if disabled or already running.
    """
    with _STATE_LOCK:
        if not _enabled():
            log.info("[guardian] agent disabled via GUARDIAN_ENABLED=0")
            return False
        if _STATE.started and _STATE.thread and _STATE.thread.is_alive():
            return False
        # CHANTIER 5B — Cross-worker singleton gate. Only one worker (the
        # one that wins the flock) runs the polling loop; others no-op.
        if not _acquire_singleton_lock():
            log.info(
                "[guardian] singleton lock held by another worker (lock=%s) — "
                "agent no-op in this worker (pid=%d)",
                _lock_path(), os.getpid(),
            )
            return False
        _STATE.rules_cache = rules.load_rules()
        _STATE.stop_event = threading.Event()
        # CHANTIER 5 — Mark boot timestamp for restart grace window.
        _STATE.boot_ts = time.time()
        _STATE.incident_counters = {}
        _STATE.suppressed_grace_count = 0
        _STATE.thread = threading.Thread(
            target=_run_loop, args=(_STATE,),
            name="guardian-agent", daemon=True,
        )
        _STATE.thread.start()
        _STATE.started = True
        log.info(
            "[guardian] singleton leader acquired (pid=%d, lock=%s)",
            os.getpid(), _lock_path(),
        )
    return True


def stop_agent(timeout: float = 5.0) -> bool:
    """Signal the loop to exit and join. Used in tests, not in normal shutdown
    (daemon thread exits with the process)."""
    with _STATE_LOCK:
        if not _STATE.started:
            return True
        _STATE.stop_event.set()
        thread = _STATE.thread
    if thread:
        thread.join(timeout=timeout)
    with _STATE_LOCK:
        _STATE.started = False
        _STATE.thread = None
        _STATE.consecutive_errors = 0
    return True


def health() -> dict[str, Any]:
    """Return a small dict describing the agent's own state. Cheap & safe to call."""
    with _STATE_LOCK:
        thread = _STATE.thread
        last = _STATE.last_tick_ts
        ticks = _STATE.ticks_total
        started = _STATE.started
        llm_count = _STATE.llm_summaries_today
        rules_count = len(_STATE.rules_cache)
        boot_ts = _STATE.boot_ts
        last_llm = _STATE.last_llm_ts
        counters = dict(_STATE.incident_counters)
        suppressed = _STATE.suppressed_grace_count
    alive = bool(thread and thread.is_alive())
    last_age = (time.time() - last) if last else None
    now = time.time()
    # CHANTIER 5B — Read leader pid from lockfile (observability across workers).
    leader_pid_in_file = None
    try:
        with open(_lock_path()) as fh:
            content = fh.read().strip()
            leader_pid_in_file = int(content) if content.isdigit() else None
    except OSError:
        pass
    return {
        "ok": True,
        "module": "guardian",
        "version": "1.2.0",
        "enabled": _enabled(),
        "started": started,
        "thread_alive": alive,
        "last_tick_ago_s": int(last_age) if last_age is not None else None,
        "ticks_total": ticks,
        "rules_loaded": rules_count,
        "poll_interval_s": _poll_interval(),
        "llm_summaries_today": llm_count,
        "uptime_s": int(now - boot_ts) if boot_ts > 0 else None,
        "in_restart_grace": _in_restart_grace(_STATE, now),
        "restart_grace_s": int(_restart_grace_seconds()),
        "last_llm_ago_s": int(now - last_llm) if last_llm > 0 else None,
        "llm_rate_limit_window_s": LLM_RATE_LIMIT_WINDOW_SECONDS,
        "incident_counters": counters,
        "suppressed_grace_total": suppressed,
        "worker_pid": os.getpid(),
        "is_leader": _is_singleton_leader(),
        "leader_pid": leader_pid_in_file,
        "lock_path": _lock_path(),
        "allow_multi_workers": _allow_multi_workers(),
    }


def status() -> dict:
    """Latest snapshots dict for the /status endpoint."""
    with _STATE_LOCK:
        snapshots = list(_STATE.last_snapshots)
        last = _STATE.last_tick_ts
    return {
        "ok": True,
        "last_tick_ts": last,
        "snapshots": snapshots,
    }


__all__ = ["health", "start_agent", "status", "stop_agent"]
