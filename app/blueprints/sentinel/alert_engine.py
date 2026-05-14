"""Alert engine — orchestrates per-update alert evaluation.

Single entry point ``evaluate_update`` takes a fresh telemetry payload
plus the current session row, runs every alert detector (over-speed,
safe-zone, low-battery), persists the resulting state via the store,
and emits typed audit events. The route layer never calls detectors
directly — it goes through here.
"""
from __future__ import annotations

import time

from app.blueprints.sentinel import (
    audit_logger,
    battery_engine,
    geo_engine,
    push_engine,
    speed_engine,
    store,
)


def evaluate_update(session_id: str, row: dict, pos: dict) -> dict:
    """Apply all alert detectors. Persists the result. Returns a small
    summary the route can return to the client.
    """
    now = int(time.time())

    # Stats
    new_max, new_sum, new_n = speed_engine.update_running_stats(
        pos["speed_kmh"], row["max_speed_kmh"],
        row["avg_speed_sum"], row["avg_speed_samples"],
    )

    # Over-speed FSM (15 s continuous + hysteresis)
    sp = speed_engine.evaluate(
        speed_kmh=pos["speed_kmh"],
        limit_kmh=row["speed_limit_kmh"],
        now_ts=now,
        streak_started_at=row["over_speed_streak_start"],
        over_speed_active=bool(row["over_speed_active"]),
    )

    # Safe-zone (optional)
    sz = geo_engine.evaluate_safe_zone(
        lat=pos["lat"], lon=pos["lon"],
        sz_lat=row["safe_zone_lat"], sz_lon=row["safe_zone_lon"],
        sz_radius_m=row["safe_zone_radius_m"],
        now_ts=now,
        outside_streak_start=row["safe_zone_outside_start"],
        safe_zone_exit_active=bool(row["safe_zone_exit_active"]),
    )

    signal_label = geo_engine.signal_quality(pos["accuracy"])

    store.write_telemetry(
        session_id=session_id,
        pos=pos,
        signal_label=signal_label,
        new_max=new_max,
        new_avg_sum=new_sum,
        new_avg_n=new_n,
        over_speed_active=sp["over_speed_active"],
        over_speed_streak_start=sp["streak_started_at"],
        safe_zone_exit_active=sz["safe_zone_exit_active"],
        safe_zone_outside_start=sz["outside_streak_start"],
    )

    fired: list[str] = []

    if sp["event"] == "over_speed":
        audit_logger.over_speed(
            session_id,
            pos["speed_kmh"],
            row["speed_limit_kmh"],
            speed_engine.STREAK_REQUIRED_SECONDS,
        )
        push_engine.notify(session_id, "parent", "over_speed", {
            "speed_kmh": round(pos["speed_kmh"], 1),
            "limit_kmh": row["speed_limit_kmh"],
        })
        fired.append("over_speed")
    elif sp["event"] == "over_speed_cleared":
        audit_logger.over_speed_cleared(session_id, row["speed_limit_kmh"])
        fired.append("over_speed_cleared")

    if sz["event"] == "safe_zone_exit":
        audit_logger.safe_zone_exit(
            session_id, sz["distance_m"] or 0.0, row["safe_zone_radius_m"]
        )
        push_engine.notify(session_id, "parent", "safe_zone_exit", {
            "distance_m": round(sz["distance_m"] or 0.0, 0),
        })
        fired.append("safe_zone_exit")
    elif sz["event"] == "safe_zone_return":
        audit_logger.safe_zone_return(session_id)
        fired.append("safe_zone_return")

    if battery_engine.should_fire(
        pos["battery_pct"], bool(row["low_battery_fired"])
    ):
        if store.fire_low_battery_once(session_id):
            audit_logger.low_battery(session_id, pos["battery_pct"])
            push_engine.notify(session_id, "parent", "low_battery", {
                "battery_pct": pos["battery_pct"],
            })
            fired.append("low_battery")

    return {
        "signal": signal_label,
        "fired": fired,
        "distance_to_safe_zone_m": sz["distance_m"],
    }
