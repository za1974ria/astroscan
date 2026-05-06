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

from app.blueprints.scan_signal.routes import scan_signal_bp, get_subscriber

log = logging.getLogger(__name__)

# Start the AISStream subscriber as soon as the blueprint loads.
try:
    _sub = get_subscriber()
    _sub.start()
except Exception as exc:  # pragma: no cover
    log.warning("[scan_signal] could not start AISStream subscriber: %s", exc)

__all__ = ["scan_signal_bp"]
