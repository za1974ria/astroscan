"""Typed audit-event logger.

This is the *only* path through which events are written. Every method
is explicit, schema-checked, and **forbidden** from storing lat/lon —
positions live exclusively on the session row, never on events.
"""
from __future__ import annotations

import logging

from app.blueprints.sentinel import store

log = logging.getLogger("astroscan.sentinel.audit")


def _emit(session_id: str, event_type: str, payload: dict | None = None) -> int:
    # Defensive: strip any lat/lon that may have slipped into payload.
    safe = dict(payload or {})
    for forbidden in ("lat", "lon", "latitude", "longitude"):
        safe.pop(forbidden, None)
    eid = store.add_event(session_id, event_type, safe)
    log.info("[SENTINEL] %s sid=%s", event_type, session_id)
    return eid


def session_created(sid: str, ttl: int, limit: int, has_safe_zone: bool) -> int:
    return _emit(sid, "session_created", {
        "ttl_seconds": ttl,
        "speed_limit_kmh": limit,
        "safe_zone": bool(has_safe_zone),
    })


def driver_accepted(sid: str) -> int:
    return _emit(sid, "driver_accepted")


def over_speed(sid: str, speed_kmh: float, limit_kmh: int, streak_seconds: int) -> int:
    return _emit(sid, "over_speed", {
        "speed_kmh": round(speed_kmh, 1),
        "limit_kmh": limit_kmh,
        "duration_seconds": streak_seconds,
    })


def over_speed_cleared(sid: str, limit_kmh: int) -> int:
    return _emit(sid, "over_speed_cleared", {"limit_kmh": limit_kmh})


def safe_zone_exit(sid: str, distance_m: float, radius_m: int) -> int:
    return _emit(sid, "safe_zone_exit", {
        "distance_m": round(distance_m, 0),
        "radius_m": radius_m,
    })


def safe_zone_return(sid: str) -> int:
    return _emit(sid, "safe_zone_return")


def low_battery(sid: str, battery_pct: int) -> int:
    return _emit(sid, "low_battery", {"battery_pct": battery_pct})


def signal_lost(sid: str, threshold_seconds: int) -> int:
    return _emit(sid, "signal_lost", {"threshold_seconds": threshold_seconds})


def sos_triggered(sid: str) -> int:
    return _emit(sid, "sos_triggered")


def sos_acknowledged(sid: str) -> int:
    return _emit(sid, "sos_acknowledged")


def stop_requested(sid: str, by: str) -> int:
    return _emit(sid, "stop_requested", {"by": by})


def stop_approved(sid: str, by: str) -> int:
    return _emit(sid, "stop_approved", {"by": by})


def session_expired(sid: str) -> int:
    return _emit(sid, "session_expired")


def consent_blocked(sid: str, reason: str) -> int:
    return _emit(sid, "consent_blocked", {"reason": reason})


def anti_cut_blocked(sid: str, reason: str) -> int:
    return _emit(sid, "anti_cut_blocked", {"reason": reason})
