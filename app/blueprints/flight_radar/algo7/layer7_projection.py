"""Layer 7 — Trajectory projection (haversine forward).

Given current (lat, lon, heading, speed_ms), project N forward points and
match against the airports DB.
"""
from __future__ import annotations

import json
import logging
import math
import os
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AIRPORTS_PATH = os.path.join(_BASE_DIR, "data", "airports_geo.json")

EARTH_R = 6371.0  # km


@lru_cache(maxsize=1)
def _load_airports() -> list[dict[str, Any]]:
    try:
        with open(_AIRPORTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = rlat2 - rlat1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(rlat2)
    x = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def project_position(lat: float, lon: float, heading_deg: float, distance_km: float) -> tuple[float, float]:
    """Spherical forward Haversine: project a point along bearing for D km."""
    rlat1 = math.radians(lat)
    rlon1 = math.radians(lon)
    rbear = math.radians(heading_deg)
    angular = distance_km / EARTH_R
    rlat2 = math.asin(
        math.sin(rlat1) * math.cos(angular)
        + math.cos(rlat1) * math.sin(angular) * math.cos(rbear)
    )
    rlon2 = rlon1 + math.atan2(
        math.sin(rbear) * math.sin(angular) * math.cos(rlat1),
        math.cos(angular) - math.sin(rlat1) * math.sin(rlat2),
    )
    lat2 = math.degrees(rlat2)
    lon2 = (math.degrees(rlon2) + 540.0) % 360.0 - 180.0
    return lat2, lon2


def project_trajectory(
    lat: float,
    lon: float,
    heading_deg: float,
    speed_ms: float,
    minutes_list: list[int] | None = None,
) -> list[tuple[float, float, int]]:
    """Returns list of (lat, lon, minutes) along the projected trajectory."""
    if minutes_list is None:
        minutes_list = [60, 120, 180, 240, 360]
    speed_kmh = max(0.0, float(speed_ms)) * 3.6
    pts: list[tuple[float, float, int]] = []
    for m in minutes_list:
        d = speed_kmh * (m / 60.0)
        plat, plon = project_position(lat, lon, heading_deg, d)
        pts.append((plat, plon, m))
    return pts


def find_candidate_airports(
    current_lat: float,
    current_lon: float,
    heading_deg: float,
    speed_ms: float,
    aircraft_range_km: float | None = None,
    max_deviation_km: float = 250.0,
    max_candidates: int = 10,
) -> list[dict[str, Any]]:
    """Score every airport in the DB by:
      - distance penalty from any projected trajectory point
      - bearing alignment (closer to current heading = higher score)
      - within aircraft_range_km (if known)
    Returns list of dicts: {icao, iata, name_fr, name_en, country_iso, lat, lon,
                            distance_km, bearing_deg, score, eta_minutes}
    """
    airports = _load_airports()
    if not airports:
        return []

    speed_kmh = max(50.0, float(speed_ms or 0) * 3.6)  # min 50 km/h to avoid div0

    # Build a forward arc set of points (every 30 min up to 8h).
    proj_points = project_trajectory(
        current_lat, current_lon, heading_deg, speed_ms,
        minutes_list=[30, 60, 90, 120, 180, 240, 300, 360, 480],
    )

    candidates: list[dict[str, Any]] = []
    for ap in airports:
        try:
            alat = float(ap["lat"])
            alon = float(ap["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        # Direct distance + bearing from aircraft.
        dist_direct = haversine_km(current_lat, current_lon, alat, alon)

        # Skip airports we've already overflown (distance < 30 km).
        if dist_direct < 30:
            continue

        # Skip beyond aircraft range if known.
        if aircraft_range_km is not None and dist_direct > aircraft_range_km * 1.1:
            continue

        bearing = initial_bearing_deg(current_lat, current_lon, alat, alon)
        bearing_diff = ((bearing - heading_deg + 540.0) % 360.0) - 180.0
        # Reject anything more than 70° off heading.
        if abs(bearing_diff) > 70:
            continue

        # Distance from nearest projection point — measures how close the
        # great-circle path passes the airport.
        min_proj_dist = min(
            haversine_km(plat, plon, alat, alon) for (plat, plon, _) in proj_points
        )

        if min_proj_dist > max_deviation_km:
            continue

        # ETA (minutes) along trajectory at current speed.
        eta_min = (dist_direct / speed_kmh) * 60.0

        # Score:
        #   - bearing alignment 0..1 (1 if perfectly on heading)
        #   - deviation penalty 0..1 (1 if near projection track)
        #   - distance preference: prefer airports between 200..3000 km (typical leg)
        bearing_score = max(0.0, 1.0 - abs(bearing_diff) / 70.0)
        dev_score = max(0.0, 1.0 - min_proj_dist / max_deviation_km)
        if dist_direct < 200:
            dist_score = dist_direct / 200.0
        elif dist_direct < 3000:
            dist_score = 1.0
        else:
            dist_score = max(0.2, 1.0 - (dist_direct - 3000) / 9000.0)

        score = 0.5 * bearing_score + 0.35 * dev_score + 0.15 * dist_score

        candidates.append({
            "icao": ap.get("icao"),
            "iata": ap.get("iata"),
            "name_fr": ap.get("name_fr"),
            "name_en": ap.get("name_en"),
            "country_iso": ap.get("country_iso"),
            "lat": alat,
            "lon": alon,
            "distance_km": round(dist_direct, 1),
            "bearing_deg": round(bearing, 1),
            "min_proj_dist_km": round(min_proj_dist, 1),
            "score": round(score, 4),
            "eta_minutes": round(eta_min),
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:max_candidates]
