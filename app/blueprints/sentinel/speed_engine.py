"""Over-speed detector.

Product rule (V1, locked): an over-speed alert fires only when the
driver's speed exceeds the configured limit **continuously for
``STREAK_REQUIRED_SECONDS`` (15s)**. GPS-noise blips do not fire.

Hysteresis on clear: alert stays raised until speed falls below
``limit - CLEAR_MARGIN_KMH`` — prevents flapping at the boundary.
"""
from __future__ import annotations

STREAK_REQUIRED_SECONDS = 15
CLEAR_MARGIN_KMH = 5


def evaluate(
    speed_kmh: float,
    limit_kmh: int,
    now_ts: int,
    streak_started_at: int | None,
    over_speed_active: bool,
) -> dict:
    above = speed_kmh > float(limit_kmh)
    below_clear = speed_kmh <= float(limit_kmh - CLEAR_MARGIN_KMH)

    next_streak = streak_started_at
    next_active = over_speed_active
    event: str | None = None

    if over_speed_active:
        if below_clear:
            next_active = False
            next_streak = None
            event = "over_speed_cleared"
    else:
        if above:
            if next_streak is None:
                next_streak = now_ts
            elif now_ts - next_streak >= STREAK_REQUIRED_SECONDS:
                next_active = True
                event = "over_speed"
        else:
            next_streak = None

    return {
        "streak_started_at": next_streak,
        "over_speed_active": next_active,
        "event": event,
    }


def update_running_stats(
    speed_kmh: float,
    max_so_far: float,
    sum_so_far: float,
    samples_so_far: int,
) -> tuple[float, float, int]:
    return (
        max(max_so_far, speed_kmh),
        sum_so_far + speed_kmh,
        samples_so_far + 1,
    )


def avg_from(sum_v: float, n: int) -> float:
    return (sum_v / float(n)) if n > 0 else 0.0
