"""Guardian append-only incident log writer.

Writes JSON Lines to logs/guardian/incidents.jsonl. Best-effort: if the
filesystem isn't writable, falls back silently to an in-memory deque so
the rest of the agent loop doesn't break.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any

log = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_INCIDENTS_FILE = _PROJECT_ROOT / "logs" / "guardian" / "incidents.jsonl"

# In-memory ring buffer used as fallback + as the read source for /api/guardian/incidents
_MEM_BUFFER: deque[dict] = deque(maxlen=500)
_MEM_LOCK = Lock()


def _ensure_dir() -> bool:
    try:
        _INCIDENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        return True
    except (PermissionError, OSError) as exc:
        log.debug("[guardian] incidents dir not writable: %s", exc)
        return False


def write_incident(incident: dict[str, Any]) -> None:
    """Append the incident dict to the JSONL file AND to the in-memory deque."""
    with _MEM_LOCK:
        _MEM_BUFFER.append(dict(incident))

    if not _ensure_dir():
        return
    try:
        line = json.dumps(incident, default=str, ensure_ascii=False)
        with open(_INCIDENTS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except (PermissionError, OSError) as exc:
        log.debug("[guardian] incident write failed: %s", exc)


def recent(since_seconds: int = 3600) -> list[dict]:
    """Return incidents from the in-memory deque newer than now - since_seconds."""
    import time

    cutoff = time.time() - max(0, int(since_seconds))
    with _MEM_LOCK:
        snapshot = list(_MEM_BUFFER)

    out: list[dict] = []
    for inc in snapshot:
        ts = inc.get("ts")
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.timestamp() >= cutoff:
                out.append(inc)
        except (ValueError, TypeError):
            out.append(inc)  # keep if unparsable, better than dropping
    return out


def count() -> int:
    with _MEM_LOCK:
        return len(_MEM_BUFFER)


def reset_for_tests() -> None:
    with _MEM_LOCK:
        _MEM_BUFFER.clear()


__all__ = ["count", "recent", "reset_for_tests", "write_incident"]
