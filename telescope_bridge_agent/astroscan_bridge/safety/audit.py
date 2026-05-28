"""Local audit log — append-only JSONL at ~/.astroscan/agent.jsonl.

Every adapter operation (discover, read_device, error) emits one line.
The log is local-only in TB-3 (no cloud transmission). Rotation is
deferred to TB-4."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


_LOG_PATH_ENV = "ASTROSCAN_AGENT_LOG"


def _default_log_path() -> Path:
    home = Path.home()
    return home / ".astroscan" / "agent.jsonl"


def _log_path() -> Path:
    override = os.environ.get(_LOG_PATH_ENV)
    return Path(override) if override else _default_log_path()


def audit(event: str, **fields) -> None:
    """Best-effort append. NEVER raises into the caller's flow."""
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    payload.update(fields)
    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        # Never let auditing break a probe.
        pass
