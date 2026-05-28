"""SCAN A SIGNAL — flagship signal-acquisition module.

Pivot 2026-05-05: VESSEL TRACKER as the primary module.
  - Satellite tab removed (was Phase 1, deprecated due to UX bugs in iframe).
  - Vessel tab → live AIS via AISStream WebSocket subscriber.
  - Aircraft tab → redirect to /flight-radar (handled in front-end).

The AIS subscriber is started here (once) when the blueprint is imported.
It runs as a daemon thread; if the AISSTREAM_API_KEY env var is missing
or websocket-client is not installed, it stays inert and the API
endpoints simply return empty results.
"""
from __future__ import annotations

import logging
import os

from app.blueprints.scan_signal.routes import scan_signal_bp, get_subscriber

log = logging.getLogger(__name__)


def _bg_threads_enabled() -> bool:
    """Gate aligned with app/bootstrap.py — same env var, same semantics."""
    raw = (os.environ.get("ENABLE_BACKGROUND_THREADS") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


# PHASE B.5D (2026-05-23) — AISStream subscriber gated by ENABLE_BACKGROUND_THREADS.
# Default=1 preserves prod behavior. Test clone uses 0 to keep boot pure.
if _bg_threads_enabled():
    try:
        _sub = get_subscriber()
        _sub.start()
    except Exception as exc:  # pragma: no cover
        log.warning("[scan_signal] could not start AISStream subscriber: %s", exc)
else:
    log.info("[scan_signal] AISStream subscriber SKIPPED (ENABLE_BACKGROUND_THREADS=0)")

__all__ = ["scan_signal_bp"]
