"""Geo helpers: haversine + safe-zone evaluation.

Safe-zone alert rule:
  - "Outside" requires being outside the radius continuously for
    ``SAFE_ZONE_STREAK_SECONDS`` to avoid GPS noise false positives.
  - "Cleared" is immediate on first sample back inside (entry is a
    deliberate act; exit drift is the noise risk).
"""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0
SAFE_ZONE_STREAK_SECONDS = 60


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def signal_quality(accuracy_m: float | None) -> str:
    if accuracy_m is None:
        return "unknown"
    if accuracy_m < 20:
        return "excellent"
    if accuracy_m < 50:
        return "good"
    if accuracy_m < 100:
        return "fair"
    return "poor"


def evaluate_safe_zone(
    lat: float,
    lon: float,
    sz_lat: float | None,
    sz_lon: float | None,
    sz_radius_m: int | None,
    now_ts: int,
    outside_streak_start: int | None,
    safe_zone_exit_active: bool,
) -> dict:
    """Returns next state + event (None | safe_zone_exit | safe_zone_return)."""
    if sz_lat is None or sz_lon is None or sz_radius_m is None:
        return {
            "outside_streak_start": None,
            "safe_zone_exit_active": False,
            "event": None,
            "distance_m": None,
        }

    distance_m = haversine_m(lat, lon, sz_lat, sz_lon)
    outside = distance_m > float(sz_radius_m)

    next_streak = outside_streak_start
    next_active = safe_zone_exit_active
    event: str | None = None

    if safe_zone_exit_active:
        if not outside:
            next_active = False
            next_streak = None
            event = "safe_zone_return"
    else:
        if outside:
            if next_streak is None:
                next_streak = now_ts
            elif now_ts - next_streak >= SAFE_ZONE_STREAK_SECONDS:
                next_active = True
                event = "safe_zone_exit"
        else:
            next_streak = None

    return {
        "outside_streak_start": next_streak,
        "safe_zone_exit_active": next_active,
        "event": event,
        "distance_m": distance_m,
    }
