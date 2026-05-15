"""Input validation (stdlib only, no pydantic dep)."""
from __future__ import annotations


class ValidationError(ValueError):
    pass


# Acte 1 UX v2 (2026-05-15) — TTL passe du whitelist fixe à une plage
# 1 min ≤ ttl ≤ 12 h. Les anciens presets (1800/3600/5400) restent dans
# la plage et donc valides ; les nouveaux (10800/21600/43200) aussi.
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 720 * 60   # 12 hours
SPEED_LIMIT_MIN = 30
SPEED_LIMIT_MAX = 200
DEFAULT_DURATION = 60 * 60
DEFAULT_SPEED_LIMIT = 90
SAFE_ZONE_RADIUS_MIN = 50
SAFE_ZONE_RADIUS_MAX = 50_000   # 50 km hard cap


def validate_create(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("body_must_be_object")

    # Duration — range check (Acte 1 UX v2 : 1 min ≤ ttl ≤ 12 h).
    ttl = payload.get("ttl_seconds")
    try:
        ttl = int(ttl) if ttl is not None else DEFAULT_DURATION
    except (TypeError, ValueError):
        raise ValidationError("ttl_invalid")
    if not (MIN_TTL_SECONDS <= ttl <= MAX_TTL_SECONDS):
        raise ValidationError("ttl_out_of_range")

    # Speed limit
    limit = payload.get("speed_limit_kmh")
    try:
        limit = int(limit) if limit is not None else DEFAULT_SPEED_LIMIT
    except (TypeError, ValueError):
        raise ValidationError("speed_limit_invalid")
    if not (SPEED_LIMIT_MIN <= limit <= SPEED_LIMIT_MAX):
        raise ValidationError("speed_limit_out_of_range")

    # Driver label
    label = payload.get("driver_label")
    if label is not None:
        label = str(label).strip()
        if len(label) == 0:
            label = None
        elif len(label) > 24:
            raise ValidationError("driver_label_too_long")

    # Optional safe zone
    safe_zone = payload.get("safe_zone")
    sz_lat = sz_lon = sz_radius = None
    if safe_zone is not None:
        if not isinstance(safe_zone, dict):
            raise ValidationError("safe_zone_invalid")
        try:
            sz_lat = float(safe_zone["lat"])
            sz_lon = float(safe_zone["lon"])
            sz_radius = int(safe_zone["radius_m"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("safe_zone_invalid")
        if not (-90.0 <= sz_lat <= 90.0) or not (-180.0 <= sz_lon <= 180.0):
            raise ValidationError("safe_zone_out_of_range")
        if not (SAFE_ZONE_RADIUS_MIN <= sz_radius <= SAFE_ZONE_RADIUS_MAX):
            raise ValidationError("safe_zone_radius_out_of_range")

    return {
        "ttl_seconds": ttl,
        "speed_limit_kmh": limit,
        "driver_label": label,
        "safe_zone_lat": sz_lat,
        "safe_zone_lon": sz_lon,
        "safe_zone_radius_m": sz_radius,
    }


def validate_position(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("body_must_be_object")
    try:
        lat = float(payload["lat"])
        lon = float(payload["lon"])
    except (KeyError, TypeError, ValueError):
        raise ValidationError("lat_lon_required_numeric")
    if not (-90.0 <= lat <= 90.0):
        raise ValidationError("lat_out_of_range")
    if not (-180.0 <= lon <= 180.0):
        raise ValidationError("lon_out_of_range")

    def _opt_float(key, lo, hi):
        v = payload.get(key)
        if v is None or v == "":
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValidationError(f"{key}_invalid")
        if not (lo <= v <= hi):
            raise ValidationError(f"{key}_out_of_range")
        return v

    accuracy = _opt_float("accuracy", 0.0, 100_000.0)
    speed_kmh = _opt_float("speed_kmh", 0.0, 500.0)
    heading_deg = _opt_float("heading_deg", 0.0, 360.0)

    battery = payload.get("battery_pct")
    if battery is None or battery == "":
        battery = None
    else:
        try:
            battery = int(battery)
        except (TypeError, ValueError):
            raise ValidationError("battery_pct_invalid")
        if not (0 <= battery <= 100):
            raise ValidationError("battery_pct_out_of_range")

    return {
        "lat": lat,
        "lon": lon,
        "accuracy": accuracy if accuracy is not None else 0.0,
        "speed_kmh": speed_kmh if speed_kmh is not None else 0.0,
        "heading_deg": heading_deg,
        "battery_pct": battery,
    }


def validate_push_register(payload: dict) -> tuple[str, str]:
    """Returns (fcm_token, platform)."""
    if not isinstance(payload, dict):
        raise ValidationError("body_must_be_object")
    fcm = payload.get("fcm_token")
    if not isinstance(fcm, str) or not fcm.strip():
        raise ValidationError("fcm_token_required")
    fcm = fcm.strip()
    if len(fcm) > 4096:
        raise ValidationError("fcm_token_too_long")
    platform = (payload.get("platform") or "").strip().lower()
    if platform not in ("android",):
        raise ValidationError("platform_must_be_android")
    return fcm, platform


def validate_batch(payload: dict) -> list[dict]:
    """Returns a list of validated position dicts, ordered as received."""
    if not isinstance(payload, dict):
        raise ValidationError("body_must_be_object")
    positions = payload.get("positions")
    if not isinstance(positions, list) or not positions:
        raise ValidationError("positions_required")
    if len(positions) > 50:
        raise ValidationError("batch_too_large")
    return [validate_position(p) for p in positions]
