"""FLIGHT RADAR — premium NASA-grade ATC module.

Backend: OpenSky OAuth2 (4000 req/day) with anonymous fallback.
Frontend: Leaflet DARK/SAT toggle, ATC-style HUD, live ADS-B effects.

The poll loop is started lazily on first request to /api/flight-radar/*
endpoints (so blueprint import stays cheap). One background thread fetches
/api/states/all every 30 s, populates Redis (`as:fr:aircraft` hash), and
maintains per-aircraft history (`as:fr:aircraft_history:<icao24>`).
"""
from __future__ import annotations

import logging
import os

from app.blueprints.flight_radar.routes import flight_radar_bp, ensure_service_started

log = logging.getLogger(__name__)


def _bg_threads_enabled() -> bool:
    """Gate aligned with app/bootstrap.py — same env var, same semantics."""
    raw = (os.environ.get("ENABLE_BACKGROUND_THREADS") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


# PHASE B.5D (2026-05-23) — Poll loop gated by ENABLE_BACKGROUND_THREADS.
# Default=1 preserves prod behavior. Test clone uses 0 to keep boot pure.
if _bg_threads_enabled():
    try:
        ensure_service_started()
    except Exception as exc:  # pragma: no cover
        log.warning("[flight_radar] could not start poll loop: %s", exc)
else:
    log.info("[flight_radar] poll loop SKIPPED (ENABLE_BACKGROUND_THREADS=0)")

__all__ = ["flight_radar_bp"]
