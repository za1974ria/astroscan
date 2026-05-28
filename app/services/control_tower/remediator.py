"""AstroScan Control Tower — Remediator (Phase 4A, DRY-RUN ONLY).

Computes informational suggestions from the current snapshot's classified
services. **NEVER executes anything.** Verifiable by grep:

  $ grep -E 'subprocess|os\\.system|systemctl|nginx|os\\.kill' remediator.py
  (no matches expected)

Public API:
  compute_suggestions(services: list[dict]) -> list[dict]

Each emitted suggestion has the shape:
  {
    "policy_id"                  : str,
    "target"                     : str (human-readable service label),
    "target_id"                  : str (stable target id),
    "reason"                     : str,
    "suggested_action"           : str,
    "executable"                 : False,            # hard-coded
    "risk_level"                 : "low|medium|high",
    "requires_human_confirmation": True,             # hard-coded
    "cooldown_seconds"           : int,
    "state"                      : "red|orange",
    "suggested_at"               : ISO-8601 UTC timestamp
  }

Cooldown:
  Per-(policy_id, target_id) suppression for COOLDOWN_SECONDS to avoid
  re-emitting the same suggestion on every 10s snapshot tick.

  Storage is process-local (dict + threading.Lock). In a 4-worker
  Gunicorn deployment this means at most 4 duplicate suggestions per
  cooldown window — acceptable for dry-run informational mode. Moving
  to a shared store (sqlite / redis) is deferred to Phase 4B.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from app.services.control_tower.policies import POLICIES, COOLDOWN_SECONDS


# Process-local cooldown state. Never serialized, never persisted.
# Keyed by (policy_id, target_id). Value: monotonic-ish wall-clock seconds.
_LAST_SUGGESTED: dict[tuple[str, str], float] = {}
_LAST_LOCK = threading.Lock()


def _is_in_cooldown(policy_id: str, target_id: str, now_ts: float) -> bool:
    with _LAST_LOCK:
        last = _LAST_SUGGESTED.get((policy_id, target_id))
        if last is None:
            return False
        return (now_ts - last) < COOLDOWN_SECONDS


def _mark_suggested(policy_id: str, target_id: str, now_ts: float) -> None:
    with _LAST_LOCK:
        _LAST_SUGGESTED[(policy_id, target_id)] = now_ts


def _format_reason(policy: dict, service: dict) -> str:
    detail = service.get("reason") or service.get("error") or ""
    name = service.get("label") or service.get("id") or "?"
    try:
        return policy["reason_tpl"].format(detail=detail, name=name)
    except Exception:
        # Defensive: never let a malformed template break the snapshot.
        return policy.get("reason_tpl", "policy fired")


def _build_suggestion(policy: dict, service: dict, now_iso: str) -> dict:
    # PHASE 4C.1: only policies that explicitly opt in are executable.
    # `executor.py` independently enforces the same whitelist as a second
    # line of defence — flipping `allow_execution` to True here is NOT
    # sufficient on its own to run anything.
    is_executable = bool(policy.get("allow_execution", False))
    return {
        "policy_id": policy["policy_id"],
        "target": service.get("label") or service.get("id") or "?",
        "target_id": service.get("id", "?"),
        "reason": _format_reason(policy, service),
        "suggested_action": policy["suggested_action"],
        "executable": is_executable,
        "risk_level": policy["risk_level"],
        # Operators must still confirm any execution outcome by reading
        # the audit log; the remediator does not assume autonomy.
        "requires_human_confirmation": True,
        "cooldown_seconds": COOLDOWN_SECONDS,
        "state": service.get("state", "grey"),
        "suggested_at": now_iso,
    }


def compute_suggestions(services: list[dict]) -> list[dict]:
    """Match every policy against the classified services list and return
    a deterministic, cooldown-filtered list of dry-run suggestions.

    Side-effects (all DRY-RUN):
      - updates _LAST_SUGGESTED in-memory map for cooldown tracking.
      - emits no logs, no network calls, no filesystem writes.

    Args:
        services: internal classified service dicts produced by
                  snapshot._run_one() — each must contain at minimum
                  `id`, `state`, and ideally `label`/`reason`.

    Returns:
        list of suggestion dicts, in policy declaration order. Empty
        list when every monitored target is healthy or cooled-down.
    """
    if not services:
        return []
    now_ts = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()
    by_id = {s.get("id"): s for s in services if s.get("id")}

    suggestions: list[dict] = []
    for policy in POLICIES:
        svc = by_id.get(policy["target_id"])
        if svc is None:
            continue
        if svc.get("state") not in policy["states"]:
            continue
        if _is_in_cooldown(policy["policy_id"], policy["target_id"], now_ts):
            continue
        suggestion = _build_suggestion(policy, svc, now_iso)

        # PHASE 4C.1: invoke controlled executor for whitelisted policies.
        # The executor independently re-enforces the whitelist + 5 safety
        # gates (kill switch, maintenance, storm, cooldown, target lock).
        # It NEVER raises; the worst case is a "blocked"/"failed" outcome
        # which we just attach to the suggestion.
        if suggestion["executable"]:
            from app.services.control_tower.executor import execute_remediation
            exec_outcome = execute_remediation(
                target_id=policy["target_id"],
                reason=suggestion["reason"],
            )
            suggestion["execution"] = {
                "decision":   exec_outcome["decision"],
                "result":     exec_outcome["result"],
                "reason":     exec_outcome["reason"],
                "exit_code":  exec_outcome["exit_code"],
                "duration_ms": exec_outcome["duration_ms"],
                "started_at": exec_outcome["started_at"],
            }

        suggestions.append(suggestion)
        _mark_suggested(policy["policy_id"], policy["target_id"], now_ts)
    return suggestions


def cooldown_snapshot() -> dict:
    """Debug helper: returns a copy of the cooldown map. Used by tests
    and the future /api/control-tower/remediator-debug endpoint (4B).
    Never called from snapshot.py."""
    with _LAST_LOCK:
        return {f"{k[0]}::{k[1]}": v for k, v in _LAST_SUGGESTED.items()}
