"""Unit tests — app.routes.iss freshness + Null-Island anti-mensonge."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes import iss as iss_module

pytestmark = pytest.mark.unit


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


# ─── _compute_meta : freshness ladder ──────────────────────────────────────


def test_compute_meta_fresh_sgp4_is_live_high():
    now = datetime.now(timezone.utc)
    meta = iss_module._compute_meta(
        _iso(now), "SGP4", "2026-05-28T18:00:00Z", datetime, timezone,
    )
    assert meta["status"] == "live"
    assert meta["confidence"] == "high"
    assert meta["age_seconds"] == 0
    assert "warning" not in meta


def test_compute_meta_60s_old_is_stale_medium():
    now = datetime.now(timezone.utc)
    meta = iss_module._compute_meta(
        _iso(now - timedelta(seconds=60)), "SGP4", None, datetime, timezone,
    )
    assert meta["status"] == "stale"
    assert meta["confidence"] == "medium"
    assert meta["age_seconds"] >= 60
    assert "warning" in meta


def test_compute_meta_47min_old_is_stale_low():
    now = datetime.now(timezone.utc)
    meta = iss_module._compute_meta(
        _iso(now - timedelta(minutes=47)), "SGP4", None, datetime, timezone,
    )
    assert meta["status"] == "stale"
    assert meta["confidence"] == "low"
    assert "outdated" in meta["warning"]


def test_compute_meta_fallback_never_high_even_when_fresh():
    now = datetime.now(timezone.utc)
    meta = iss_module._compute_meta(
        _iso(now), "fallback", None, datetime, timezone,
    )
    assert meta["status"] == "fallback"
    assert meta["confidence"] in ("medium", "low")
    assert meta["confidence"] != "high"


def test_compute_meta_missing_timestamp_is_stale_low():
    meta = iss_module._compute_meta(None, "SGP4", None, datetime, timezone)
    assert meta["status"] == "stale"
    assert meta["confidence"] == "low"
    assert meta["age_seconds"] is None


# ─── _position_is_invalid : Null-Island sentinel detection ─────────────────


@pytest.mark.parametrize(
    "lat,lon",
    [
        (0, 0),
        (0.0, 0.0),
        (None, None),
        (None, 12.3),
        (45.0, None),
        ("nan", 0),
        ([0], [0]),
    ],
)
def test_position_invalid_detected(lat, lon):
    assert iss_module._position_is_invalid(lat, lon) is True


@pytest.mark.parametrize(
    "lat,lon",
    [
        (51.0, 13.0),
        (-12.5, 144.2),
        (0.0001, 0.0001),  # NEAR Null Island but not exactly zero
        (1.0, 0.0),        # On the equator, NOT at the prime meridian
        (0.0, 1.0),        # On the prime meridian, NOT at the equator
    ],
)
def test_position_valid_passes(lat, lon):
    assert iss_module._position_is_invalid(lat, lon) is False


def test_position_nan_detected():
    nan = float("nan")
    assert iss_module._position_is_invalid(nan, 12.0) is True
    assert iss_module._position_is_invalid(12.0, nan) is True


# ─── _force_unavailable_meta : caps status/confidence ──────────────────────


def test_force_unavailable_overrides_live_high():
    fresh_meta = {
        "status": "live",
        "confidence": "high",
        "age_seconds": 0,
        "source": "SGP4",
        "last_updated": _iso(datetime.now(timezone.utc)),
    }
    forced = iss_module._force_unavailable_meta(fresh_meta)
    assert forced["status"] == "unavailable"
    assert forced["confidence"] == "none"
    assert forced["confidence"] not in ("high", "medium", "low")
    assert "warning" in forced
    assert "unavailable" in forced["warning"].lower()


def test_force_unavailable_preserves_age_seconds():
    forced = iss_module._force_unavailable_meta(
        {"status": "live", "confidence": "high", "age_seconds": 12}
    )
    assert forced["age_seconds"] == 12
    # ... but observability of age does not confer trust:
    assert forced["status"] == "unavailable"
    assert forced["confidence"] == "none"


# ─── Anti-mensonge invariant: position (0,0) ⇒ NEVER live/high/medium ─────


@pytest.mark.parametrize(
    "lat,lon",
    [(0.0, 0.0), (None, None), ("garbage", 12.0)],
)
def test_invalid_position_meta_never_live_or_trusted(lat, lon):
    """The hard contract: any invalid ground-track must downgrade the meta
    so that no client can ever read status='live' or confidence in
    ('high', 'medium') on a payload whose lat/lon are sentinel/missing."""
    assert iss_module._position_is_invalid(lat, lon) is True
    # Even a perfectly fresh SGP4 meta must be capped:
    fresh_meta = iss_module._compute_meta(
        _iso(datetime.now(timezone.utc)),
        "SGP4",
        "2026-05-28T18:00:00Z",
        datetime, timezone,
    )
    assert fresh_meta["status"] == "live"
    assert fresh_meta["confidence"] == "high"
    forced = iss_module._force_unavailable_meta(fresh_meta)
    assert forced["status"] != "live"
    assert forced["confidence"] not in ("high", "medium")
