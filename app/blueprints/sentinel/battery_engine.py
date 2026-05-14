"""Low-battery one-shot detector.

A single event is fired per session when the driver's battery first
drops at or below ``LOW_BATTERY_THRESHOLD_PCT``. Subsequent updates do
not re-fire.
"""
from __future__ import annotations

LOW_BATTERY_THRESHOLD_PCT = 15


def should_fire(battery_pct: int | None, already_fired: bool) -> bool:
    if battery_pct is None or already_fired:
        return False
    return battery_pct <= LOW_BATTERY_THRESHOLD_PCT
