"""Layer 4 — Aircraft type / range inference.

We don't ship a 50 MB ICAO24 → aircraft-type DB. Instead we estimate
range from a coarse category derived from current cruise altitude + speed:
  - light  (regional/turboprop)  → 2 000 km
  - medium (single-aisle jet)    → 5 000 km
  - heavy  (twin-aisle jet)      → 12 000 km
  - super  (A380)                → 14 000 km

Cache: as:fr:aircrafttype:<icao24> TTL 7 days (in case we later add a
real DB). For now the cache simply memoizes the heuristic result.
"""
from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

CACHE_TTL = 7 * 24 * 3600

CATEGORY_RANGE_KM = {
    "light": 2000,
    "medium": 5000,
    "heavy": 12000,
    "super": 14000,
}


def _classify_by_kinematics(
    baro_altitude: float | None,
    velocity: float | None,
    on_ground: bool,
) -> str:
    """Coarse classification from cruise behaviour."""
    if on_ground:
        return "medium"  # neutral default; we'll likely never run on ground
    alt = float(baro_altitude or 0)
    spd = float(velocity or 0)  # m/s
    # Long-haul cruise: high altitude AND high speed.
    if alt > 10500 and spd > 230:
        # Could be heavy or super; we have no way to know without a real DB.
        return "heavy"
    # Mid-haul / single-aisle: typical cruise FL340-FL380, mach 0.78.
    if alt > 8500 and spd > 180:
        return "medium"
    # Regional / turboprop: lower altitude or slower.
    if alt < 6000 or spd < 150:
        return "light"
    return "medium"


def decode_aircraft_type(
    icao24: str,
    baro_altitude: float | None,
    velocity: float | None,
    on_ground: bool,
    redis_client: Any | None = None,
) -> dict[str, Any]:
    """Returns {icao_type, manufacturer, model, range_km, category}.

    Currently inferred from kinematics. Hook for a future ICAO24 DB.
    """
    icao24 = (icao24 or "").lower().strip()
    cache_key = f"as:fr:aircrafttype:{icao24}"

    if redis_client is not None and icao24:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    category = _classify_by_kinematics(baro_altitude, velocity, on_ground)
    range_km = CATEGORY_RANGE_KM.get(category, 5000)

    result = {
        "icao_type": None,
        "manufacturer": None,
        "model": None,
        "category": category,
        "range_km": range_km,
        "source": "kinematic_heuristic",
    }

    if redis_client is not None and icao24:
        try:
            redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))
        except Exception:
            pass
    return result


def is_destination_compatible(aircraft_type: dict[str, Any], distance_km: float) -> bool:
    rng = float(aircraft_type.get("range_km") or 0)
    return distance_km <= rng * 1.05  # 5% tolerance


def score_destination_for_type(aircraft_type: dict[str, Any], distance_km: float) -> float:
    """0..1 — how appropriate the destination is for this aircraft."""
    rng = float(aircraft_type.get("range_km") or 5000)
    if distance_km <= 0:
        return 0.0
    if distance_km > rng * 1.1:
        return 0.0
    # Sweet spot: 30%-90% of range (typical operations).
    pct = distance_km / rng
    if 0.30 <= pct <= 0.90:
        return 1.0
    if pct < 0.30:
        return 0.6 + (pct / 0.30) * 0.4
    # 0.9 < pct ≤ 1.1 → tail penalty
    return max(0.0, 1.0 - (pct - 0.90) / 0.20)
