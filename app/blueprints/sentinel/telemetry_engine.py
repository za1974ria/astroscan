"""Telemetry composer.

Takes a row from the store + recent events and shapes the public state
payload returned to either party. This is the single source of truth
for what a token-bearer can see — keep all field-shaping here so the
contract with the frontend stays consistent.
"""
from __future__ import annotations

import time

from app.blueprints.sentinel import speed_engine, store


def public_state(sid: str, role: str) -> dict | None:
    row = store.get_session(sid)
    if row is None:
        return None
    events = store.list_events(sid, limit=30)
    now = int(time.time())
    expires_at = int(row["expires_at"])

    return {
        "session_id": row["session_id"],
        "role": role,
        "state": row["state"],
        "driver_label": row["driver_label"],
        "speed_limit_kmh": row["speed_limit_kmh"],
        "safe_zone": (
            {
                "lat": row["safe_zone_lat"],
                "lon": row["safe_zone_lon"],
                "radius_m": row["safe_zone_radius_m"],
            }
            if row["safe_zone_radius_m"] is not None
            else None
        ),
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "expires_at": expires_at,
        "ended_at": row["ended_at"],
        "last_update_at": row["last_update_at"],
        "last_lat": row["last_lat"],
        "last_lon": row["last_lon"],
        "last_accuracy": row["last_accuracy"],
        "last_signal": row["last_signal"],
        "last_speed_kmh": row["last_speed_kmh"],
        "last_heading_deg": row["last_heading_deg"],
        "last_battery_pct": row["last_battery_pct"],
        "max_speed_kmh": row["max_speed_kmh"],
        "avg_speed_kmh": speed_engine.avg_from(
            row["avg_speed_sum"], row["avg_speed_samples"]
        ),
        "updates_count": row["updates_count"],
        "over_speed_active": bool(row["over_speed_active"]),
        "safe_zone_exit_active": bool(row["safe_zone_exit_active"]),
        "signal_lost_active": bool(row["signal_lost_active"]),
        "sos_active": bool(row["sos_active"]),
        "sos_ack_at": row["sos_ack_at"],
        "stop_requested_by": row["stop_requested_by"],
        "stop_requested_at": row["stop_requested_at"],
        "events": events,
        "server_time": now,
        "time_remaining": max(0, expires_at - now),
    }
