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

from app.blueprints.flight_radar.routes import flight_radar_bp, ensure_service_started

log = logging.getLogger(__name__)

# Start the poll loop as soon as the blueprint is imported.
try:
    ensure_service_started()
except Exception as exc:  # pragma: no cover
    log.warning("[flight_radar] could not start poll loop: %s", exc)

__all__ = ["flight_radar_bp"]
