"""Daily token budget guard for AstroBrain.

Concurrency model:
    Stored as a tiny JSON file at <project_root>/data/astrobrain_budget.json.
    Read/write are bracketed with fcntl.flock(LOCK_EX) so multi-worker gunicorn
    instances don't race-corrupt the counter.

Budget format::

    {"date": "2026-05-21", "tokens_used": 12345, "tokens_budget": 200000, "requests": 14}

Reset:
    The 'date' key is checked against UTC today on every read. Any mismatch
    triggers a silent reset before returning.

Public API:
    check_budget(estimated_tokens, budget=None) -> (ok: bool, remaining: int, snapshot: dict)
    record_usage(actual_tokens) -> dict
    status() -> dict
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_BUDGET_FILE = _DATA_DIR / "astrobrain_budget.json"

DEFAULT_DAILY_BUDGET = 200_000


def _today_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _resolve_budget(env_value: int | None = None) -> int:
    """Return the configured daily budget. env > arg > default."""
    if env_value is not None:
        return max(0, int(env_value))
    raw = os.environ.get("ASTROBRAIN_DAILY_TOKEN_BUDGET", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            log.warning("[rate_limit] invalid ASTROBRAIN_DAILY_TOKEN_BUDGET=%r, using default", raw)
    return DEFAULT_DAILY_BUDGET


def _ensure_data_dir() -> bool:
    """Try to create data/. Returns False if denied (caller falls back to in-memory)."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except (PermissionError, OSError) as exc:
        log.debug("[rate_limit] data dir not writable (%s); budget will be in-memory", exc)
        return False


# In-memory fallback when filesystem isn't writable (test runners as non-owner)
_in_memory_state: dict = {}


def _empty_state(budget: int) -> dict:
    return {
        "date": _today_utc(),
        "tokens_used": 0,
        "tokens_budget": budget,
        "requests": 0,
    }


def _load_locked(budget: int) -> tuple[dict, object | None]:
    """Open the budget file in r+ with exclusive lock. Returns (state, file_handle).

    If the FS is not writable, returns (in_memory_state, None) — caller must NOT
    try to release a lock on a None handle.
    """
    if not _ensure_data_dir():
        if not _in_memory_state:
            _in_memory_state.update(_empty_state(budget))
        else:
            _maybe_reset(_in_memory_state, budget)
        return _in_memory_state, None

    try:
        # Open r+ (existing file) or create then reopen.
        if not _BUDGET_FILE.exists():
            _BUDGET_FILE.write_text(json.dumps(_empty_state(budget)), encoding="utf-8")
        f = open(_BUDGET_FILE, "r+", encoding="utf-8")
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            raw = f.read()
            f.seek(0)
            state = json.loads(raw) if raw.strip() else _empty_state(budget)
        except json.JSONDecodeError:
            # Corrupt file → reset rather than crash.
            log.warning("[rate_limit] budget file corrupt, resetting")
            state = _empty_state(budget)
        _maybe_reset(state, budget)
        return state, f
    except (PermissionError, OSError) as exc:
        log.debug("[rate_limit] file lock failed (%s); falling back to in-memory", exc)
        if not _in_memory_state:
            _in_memory_state.update(_empty_state(budget))
        else:
            _maybe_reset(_in_memory_state, budget)
        return _in_memory_state, None


def _maybe_reset(state: dict, budget: int) -> None:
    today = _today_utc()
    if state.get("date") != today:
        state["date"] = today
        state["tokens_used"] = 0
        state["requests"] = 0
    # Keep the budget field in sync if env var changed since last write.
    state["tokens_budget"] = budget


def _save_locked(state: dict, f) -> None:
    """Write state JSON and release the file lock. Pass f=None for in-memory mode."""
    if f is None:
        return
    try:
        f.seek(0)
        f.truncate()
        f.write(json.dumps(state, ensure_ascii=False))
        f.flush()
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            f.close()
        except Exception:
            pass


# ─── Public API ─────────────────────────────────────────────────────────────


def check_budget(estimated_tokens: int, budget: int | None = None) -> tuple[bool, int, dict]:
    """Return (ok, remaining, snapshot). Does NOT mutate the counter — call record_usage after."""
    b = _resolve_budget(budget)
    state, f = _load_locked(b)
    remaining = b - int(state.get("tokens_used", 0))
    ok = estimated_tokens <= remaining and b > 0
    snapshot = dict(state)
    _save_locked(state, f)  # Save to refresh the date reset if it just happened.
    return ok, remaining, snapshot


def record_usage(actual_tokens: int, budget: int | None = None) -> dict:
    """Add actual_tokens to the counter atomically. Returns the new state snapshot."""
    b = _resolve_budget(budget)
    state, f = _load_locked(b)
    state["tokens_used"] = int(state.get("tokens_used", 0)) + max(0, int(actual_tokens))
    state["requests"] = int(state.get("requests", 0)) + 1
    snapshot = dict(state)
    _save_locked(state, f)
    return snapshot


def status(budget: int | None = None) -> dict:
    """Read-only snapshot of the current budget state."""
    b = _resolve_budget(budget)
    state, f = _load_locked(b)
    snapshot = dict(state)
    snapshot["remaining"] = max(0, b - int(state.get("tokens_used", 0)))
    _save_locked(state, f)
    return snapshot


def reset_for_tests() -> None:
    """Wipe in-memory state + on-disk file. ONLY for use in tests."""
    global _in_memory_state
    _in_memory_state = {}
    try:
        if _BUDGET_FILE.exists():
            _BUDGET_FILE.unlink()
    except (PermissionError, OSError):
        pass


__all__ = [
    "DEFAULT_DAILY_BUDGET",
    "check_budget",
    "record_usage",
    "reset_for_tests",
    "status",
]
