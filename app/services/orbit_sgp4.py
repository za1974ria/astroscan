from datetime import datetime, timezone


def propagate_tle_debug(tle1: str, tle2: str):
    """Debug helper: returns (payload, reason). payload is None on failure."""
    try:
        from sgp4.api import Satrec, jday
    except Exception as e:
        return None, f"import_error:{e}"

    try:
        line1 = str(tle1 or "").strip()
        line2 = str(tle2 or "").strip()
        if not line1 or not line2:
            return None, "missing_tle_lines"

        now = datetime.now(timezone.utc)
        jd, fr = jday(
            now.year,
            now.month,
            now.day,
            now.hour,
            now.minute,
            now.second + (now.microsecond / 1_000_000.0),
        )
        sat = Satrec.twoline2rv(line1, line2)
        error_code, position, velocity = sat.sgp4(jd, fr)
        if error_code != 0:
            return None, f"sgp4_error_code:{error_code}"

        return {
            "position_km": {
                "x": float(position[0]),
                "y": float(position[1]),
                "z": float(position[2]),
            },
            "velocity_km_s": {
                "x": float(velocity[0]),
                "y": float(velocity[1]),
                "z": float(velocity[2]),
            },
            "timestamp": now.isoformat().replace("+00:00", "Z"),
        }, "ok"
    except Exception as e:
        return None, f"runtime_error:{e}"


def propagate_tle(tle1: str, tle2: str):
    """Compatibility wrapper: preserve existing fallback behavior.

    Delegates to propagate_tle_debug() for SGP4 propagation.
    Returns None on any error (route fallback behavior preserved).
    """
    payload, _reason = propagate_tle_debug(tle1, tle2)
    return payload
