"""Unit tests — app.blueprints.sentinel.schemas (input validation)."""
from __future__ import annotations

import pytest

from app.blueprints.sentinel import schemas


pytestmark = pytest.mark.unit


# ── validate_create ──────────────────────────────────────────────────────────


def test_create_defaults_when_empty_payload():
    out = schemas.validate_create({})
    assert out["ttl_seconds"] == schemas.DEFAULT_DURATION
    assert out["speed_limit_kmh"] == schemas.DEFAULT_SPEED_LIMIT
    assert out["driver_label"] is None
    assert out["safe_zone_lat"] is None


def test_create_rejects_non_dict():
    with pytest.raises(schemas.ValidationError):
        schemas.validate_create("nope")  # type: ignore[arg-type]


def test_create_ttl_below_min():
    with pytest.raises(schemas.ValidationError, match="ttl_out_of_range"):
        schemas.validate_create({"ttl_seconds": 30})


def test_create_ttl_above_max():
    with pytest.raises(schemas.ValidationError, match="ttl_out_of_range"):
        schemas.validate_create({"ttl_seconds": 999_999})


def test_create_ttl_non_numeric():
    with pytest.raises(schemas.ValidationError, match="ttl_invalid"):
        schemas.validate_create({"ttl_seconds": "abc"})


def test_create_speed_limit_below_min():
    with pytest.raises(schemas.ValidationError, match="speed_limit_out_of_range"):
        schemas.validate_create({"speed_limit_kmh": 10})


def test_create_speed_limit_above_max():
    with pytest.raises(schemas.ValidationError, match="speed_limit_out_of_range"):
        schemas.validate_create({"speed_limit_kmh": 500})


def test_create_speed_limit_non_numeric():
    with pytest.raises(schemas.ValidationError, match="speed_limit_invalid"):
        schemas.validate_create({"speed_limit_kmh": "fast"})


def test_create_driver_label_strips():
    out = schemas.validate_create({"driver_label": "   Ali   "})
    assert out["driver_label"] == "Ali"


def test_create_driver_label_empty_becomes_none():
    out = schemas.validate_create({"driver_label": "   "})
    assert out["driver_label"] is None


def test_create_driver_label_too_long():
    with pytest.raises(schemas.ValidationError, match="driver_label_too_long"):
        schemas.validate_create({"driver_label": "x" * 25})


def test_create_safe_zone_complete():
    out = schemas.validate_create({
        "safe_zone": {"lat": 34.8, "lon": -1.3, "radius_m": 500}
    })
    assert out["safe_zone_lat"] == 34.8
    assert out["safe_zone_lon"] == -1.3
    assert out["safe_zone_radius_m"] == 500


def test_create_safe_zone_missing_field():
    with pytest.raises(schemas.ValidationError, match="safe_zone_invalid"):
        schemas.validate_create({"safe_zone": {"lat": 34.8, "lon": -1.3}})


def test_create_safe_zone_not_dict():
    with pytest.raises(schemas.ValidationError, match="safe_zone_invalid"):
        schemas.validate_create({"safe_zone": "nope"})


def test_create_safe_zone_lat_out_of_range():
    with pytest.raises(schemas.ValidationError, match="safe_zone_out_of_range"):
        schemas.validate_create({"safe_zone": {"lat": 95.0, "lon": 0.0, "radius_m": 500}})


def test_create_safe_zone_lon_out_of_range():
    with pytest.raises(schemas.ValidationError, match="safe_zone_out_of_range"):
        schemas.validate_create({"safe_zone": {"lat": 0.0, "lon": -200.0, "radius_m": 500}})


def test_create_safe_zone_radius_too_small():
    with pytest.raises(schemas.ValidationError, match="safe_zone_radius_out_of_range"):
        schemas.validate_create({"safe_zone": {"lat": 0.0, "lon": 0.0, "radius_m": 10}})


def test_create_safe_zone_radius_too_large():
    with pytest.raises(schemas.ValidationError, match="safe_zone_radius_out_of_range"):
        schemas.validate_create({"safe_zone": {"lat": 0.0, "lon": 0.0, "radius_m": 100_000}})


# ── validate_position ────────────────────────────────────────────────────────


def test_position_minimal_ok():
    out = schemas.validate_position({"lat": 34.8, "lon": -1.3})
    assert out["lat"] == 34.8
    assert out["lon"] == -1.3
    assert out["accuracy"] == 0.0
    assert out["speed_kmh"] == 0.0
    assert out["heading_deg"] is None
    assert out["battery_pct"] is None


def test_position_full_payload():
    out = schemas.validate_position({
        "lat": 34.0, "lon": -1.0,
        "accuracy": 12.5, "speed_kmh": 60.0,
        "heading_deg": 180.0, "battery_pct": 75,
    })
    assert out["accuracy"] == 12.5
    assert out["speed_kmh"] == 60.0
    assert out["heading_deg"] == 180.0
    assert out["battery_pct"] == 75


def test_position_missing_lat_lon():
    with pytest.raises(schemas.ValidationError, match="lat_lon_required_numeric"):
        schemas.validate_position({})


def test_position_non_numeric():
    with pytest.raises(schemas.ValidationError, match="lat_lon_required_numeric"):
        schemas.validate_position({"lat": "abc", "lon": 0.0})


def test_position_lat_out_of_range():
    with pytest.raises(schemas.ValidationError, match="lat_out_of_range"):
        schemas.validate_position({"lat": 95.0, "lon": 0.0})


def test_position_lon_out_of_range():
    with pytest.raises(schemas.ValidationError, match="lon_out_of_range"):
        schemas.validate_position({"lat": 0.0, "lon": -200.0})


def test_position_battery_out_of_range():
    with pytest.raises(schemas.ValidationError, match="battery_pct_out_of_range"):
        schemas.validate_position({"lat": 0.0, "lon": 0.0, "battery_pct": 150})


def test_position_battery_non_numeric():
    with pytest.raises(schemas.ValidationError, match="battery_pct_invalid"):
        schemas.validate_position({"lat": 0.0, "lon": 0.0, "battery_pct": "full"})


def test_position_accuracy_out_of_range():
    with pytest.raises(schemas.ValidationError, match="accuracy_out_of_range"):
        schemas.validate_position({"lat": 0.0, "lon": 0.0, "accuracy": 999_999})


def test_position_speed_out_of_range():
    with pytest.raises(schemas.ValidationError, match="speed_kmh_out_of_range"):
        schemas.validate_position({"lat": 0.0, "lon": 0.0, "speed_kmh": 999})


def test_position_not_dict():
    with pytest.raises(schemas.ValidationError, match="body_must_be_object"):
        schemas.validate_position("nope")  # type: ignore[arg-type]


def test_position_empty_string_optional_treated_as_none():
    out = schemas.validate_position({"lat": 0.0, "lon": 0.0, "speed_kmh": ""})
    assert out["speed_kmh"] == 0.0


# ── validate_push_register ───────────────────────────────────────────────────


def test_push_register_ok():
    fcm, platform = schemas.validate_push_register(
        {"fcm_token": "abc123", "platform": "android"}
    )
    assert fcm == "abc123"
    assert platform == "android"


def test_push_register_missing_token():
    with pytest.raises(schemas.ValidationError, match="fcm_token_required"):
        schemas.validate_push_register({"platform": "android"})


def test_push_register_empty_token():
    with pytest.raises(schemas.ValidationError, match="fcm_token_required"):
        schemas.validate_push_register({"fcm_token": "  ", "platform": "android"})


def test_push_register_token_too_long():
    with pytest.raises(schemas.ValidationError, match="fcm_token_too_long"):
        schemas.validate_push_register({"fcm_token": "x" * 5000, "platform": "android"})


def test_push_register_wrong_platform():
    with pytest.raises(schemas.ValidationError, match="platform_must_be_android"):
        schemas.validate_push_register({"fcm_token": "abc", "platform": "ios"})


def test_push_register_not_dict():
    with pytest.raises(schemas.ValidationError, match="body_must_be_object"):
        schemas.validate_push_register("nope")  # type: ignore[arg-type]


# ── validate_batch ───────────────────────────────────────────────────────────


def test_batch_ok():
    out = schemas.validate_batch({
        "positions": [
            {"lat": 1.0, "lon": 2.0},
            {"lat": 3.0, "lon": 4.0},
        ]
    })
    assert len(out) == 2
    assert out[0]["lat"] == 1.0
    assert out[1]["lon"] == 4.0


def test_batch_missing_positions():
    with pytest.raises(schemas.ValidationError, match="positions_required"):
        schemas.validate_batch({})


def test_batch_empty_positions():
    with pytest.raises(schemas.ValidationError, match="positions_required"):
        schemas.validate_batch({"positions": []})


def test_batch_too_large():
    with pytest.raises(schemas.ValidationError, match="batch_too_large"):
        schemas.validate_batch({"positions": [{"lat": 0.0, "lon": 0.0}] * 51})


def test_batch_not_dict():
    with pytest.raises(schemas.ValidationError, match="body_must_be_object"):
        schemas.validate_batch("nope")  # type: ignore[arg-type]


def test_batch_invalid_position_bubbles_up():
    with pytest.raises(schemas.ValidationError):
        schemas.validate_batch({"positions": [{"lat": 999, "lon": 0}]})
