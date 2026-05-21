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
"""
from __future__ import annotations

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


_STATE = AgentState()
_STATE_LOCK = threading.Lock()


def _maybe_llm_summarize(incident: dict, snapshot_map: dict[str, dict]) -> str | None:
    """If conditions allow, ask AstroBrain to summarize the incident. Best-effort."""
    if (os.environ.get("LLM_DRY_RUN") or "").strip() in ("1", "true", "True", "yes"):
        return None
    if not (os.environ.get("OPENAI_API_KEY") or "").strip():
        return None
    if incident.get("severity") != "critical":
        return None

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    with _STATE_LOCK:
        if _STATE.llm_summaries_date != today:
            _STATE.llm_summaries_date = today
            _STATE.llm_summaries_today = 0
        # Hard cap: at most 20 LLM summaries per day (budget guard).
        if _STATE.llm_summaries_today >= 20:
            return None
        _STATE.llm_summaries_today += 1

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

    if not incidents:
        return

    snap_map = {s.get("name", ""): s for s in snapshots}
    for inc in incidents:
        record = {
            "ts": inc.ts,
            "rule": inc.rule,
            "severity": inc.severity,
            "metric": inc.metric,
            "operator": inc.operator,
            "threshold": inc.threshold,
            "actual": inc.actual,
            "cooldown_until": inc.cooldown_until,
        }
        narrative = _maybe_llm_summarize(record, snap_map)
        if narrative:
            record["narrative"] = narrative

        audit_log.write_incident(record)
        log.warning(
            "[guardian] incident rule=%s severity=%s metric=%s actual=%s threshold=%s",
            inc.rule, inc.severity, inc.metric, inc.actual, inc.threshold,
        )


def _run_loop(state: AgentState) -> None:
    """Body of the daemon thread. Exits cleanly on stop_event."""
    log.info("[guardian] agent loop started (interval=%.1fs, rules=%d)",
             _poll_interval(), len(state.rules_cache))
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
        _STATE.rules_cache = rules.load_rules()
        _STATE.stop_event = threading.Event()
        _STATE.thread = threading.Thread(
            target=_run_loop, args=(_STATE,),
            name="guardian-agent", daemon=True,
        )
        _STATE.thread.start()
        _STATE.started = True
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
    alive = bool(thread and thread.is_alive())
    last_age = (time.time() - last) if last else None
    return {
        "ok": True,
        "module": "guardian",
        "version": "1.0.0",
        "enabled": _enabled(),
        "started": started,
        "thread_alive": alive,
        "last_tick_ago_s": int(last_age) if last_age is not None else None,
        "ticks_total": ticks,
        "rules_loaded": rules_count,
        "poll_interval_s": _poll_interval(),
        "llm_summaries_today": llm_count,
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
