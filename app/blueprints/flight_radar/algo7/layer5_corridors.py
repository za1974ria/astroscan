"""Layer 5 — Airway corridors.

Bounding-box matching of (lat, lon, FL) against airways_geo.json. When the
aircraft sits inside a known corridor, that corridor's typical destinations
get a score boost.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AIRWAYS_PATH = os.path.join(_BASE_DIR, "data", "airways_geo.json")


@lru_cache(maxsize=1)
def _load_airways() -> list[dict[str, Any]]:
    try:
        with open(_AIRWAYS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.warning("[algo7.layer5] airways_geo.json missing")
        return []


def detect_corridor(
    lat: float,
    lon: float,
    altitude_m: float | None,
    heading_deg: float | None = None,
) -> dict[str, Any] | None:
    """Return the first matching corridor or None."""
    fl = None
    if altitude_m is not None and altitude_m > 0:
        fl = (altitude_m * 3.28084) / 100.0  # meters → flight level

    for aw in _load_airways():
        try:
            if not (aw["lat_min"] <= lat <= aw["lat_max"]):
                continue
            # Longitude wrap (e.g. PACOTS spans +/-180).
            lon_min = aw["lon_min"]
            lon_max = aw["lon_max"]
            if lon_min <= lon_max:
                if not (lon_min <= lon <= lon_max):
                    continue
            else:  # wraps around 180
                if not (lon >= lon_min or lon <= lon_max):
                    continue
            if fl is not None:
                if not (aw["alt_min_fl"] <= fl <= aw["alt_max_fl"] + 30):
                    continue
        except KeyError:
            continue
        return {
            "name": aw["name"],
            "type": aw["type"],
            "typical_origins": list(aw.get("typical_origins") or []),
            "typical_destinations": list(aw.get("typical_destinations") or []),
        }
    return None


def score_destination_in_corridor(corridor: dict[str, Any] | None, candidate_icao: str) -> float:
    """0..1 — how well a destination ICAO matches the corridor's known endpoints."""
    if not corridor:
        return 0.0
    candidate_icao = (candidate_icao or "").upper()
    if candidate_icao in corridor.get("typical_destinations", []):
        return 1.0
    if candidate_icao in corridor.get("typical_origins", []):
        return 0.15  # could be a return leg
    return 0.0
