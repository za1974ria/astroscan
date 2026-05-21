"""Unit tests — sentinel pure engines (state_machine, speed, battery,
anti_cut, geo). All pure logic, no I/O, no DB."""
from __future__ import annotations

import math

import pytest

from app.blueprints.sentinel import (
    battery_engine,
    geo_engine,
    speed_engine,
    state_machine as fsm,
)
from app.blueprints.sentinel.anti_cut_engine import (
    AntiCutViolation,
    assert_no_silent_deletion,
    assert_no_unilateral_termination,
)


pytestmark = pytest.mark.unit


# ── state_machine ────────────────────────────────────────────────────────────


def test_live_set_membership():
    assert fsm.ACTIVE in fsm.LIVE
    assert fsm.STOP_PENDING_PARENT in fsm.LIVE
    assert fsm.STOP_PENDING_DRIVER in fsm.LIVE
    assert fsm.ENDED not in fsm.LIVE


def test_terminal_set_membership():
    assert fsm.ENDED in fsm.TERMINAL
    assert fsm.EXPIRED in fsm.TERMINAL
    assert fsm.ACTIVE not in fsm.TERMINAL


def test_can_driver_update_active():
    assert fsm.can_driver_update(fsm.ACTIVE)
    assert fsm.can_driver_update(fsm.STOP_PENDING_PARENT)
    assert not fsm.can_driver_update(fsm.ENDED)
    assert not fsm.can_driver_update(fsm.PENDING_DRIVER)


def test_can_request_stop_active_only():
    assert fsm.can_request_stop(fsm.ACTIVE, "parent")
    assert fsm.can_request_stop(fsm.ACTIVE, "driver")
    assert not fsm.can_request_stop(fsm.ACTIVE, "stranger")
    assert not fsm.can_request_stop(fsm.STOP_PENDING_PARENT, "parent")


def test_state_after_request():
    assert fsm.state_after_request("parent") == fsm.STOP_PENDING_PARENT
    assert fsm.state_after_request("driver") == fsm.STOP_PENDING_DRIVER


def test_approver_for():
    assert fsm.approver_for(fsm.STOP_PENDING_PARENT) == "driver"
    assert fsm.approver_for(fsm.STOP_PENDING_DRIVER) == "parent"
    assert fsm.approver_for(fsm.ACTIVE) is None


# ── speed_engine ─────────────────────────────────────────────────────────────


def test_speed_below_limit_no_event():
    out = speed_engine.evaluate(
        speed_kmh=80, limit_kmh=90, now_ts=1000,
        streak_started_at=None, over_speed_active=False,
    )
    assert out["event"] is None
    assert out["over_speed_active"] is False
    assert out["streak_started_at"] is None


def test_speed_just_above_starts_streak():
    out = speed_engine.evaluate(
        speed_kmh=95, limit_kmh=90, now_ts=1000,
        streak_started_at=None, over_speed_active=False,
    )
    assert out["event"] is None
    assert out["streak_started_at"] == 1000


def test_speed_streak_too_short_no_alert():
    out = speed_engine.evaluate(
        speed_kmh=95, limit_kmh=90, now_ts=1005,
        streak_started_at=1000, over_speed_active=False,
    )
    assert out["event"] is None
    assert out["streak_started_at"] == 1000


def test_speed_streak_completes_fires_alert():
    streak_start = 1000
    now = streak_start + speed_engine.STREAK_REQUIRED_SECONDS
    out = speed_engine.evaluate(
        speed_kmh=95, limit_kmh=90, now_ts=now,
        streak_started_at=streak_start, over_speed_active=False,
    )
    assert out["event"] == "over_speed"
    assert out["over_speed_active"] is True


def test_speed_drops_resets_streak():
    out = speed_engine.evaluate(
        speed_kmh=80, limit_kmh=90, now_ts=1010,
        streak_started_at=1000, over_speed_active=False,
    )
    assert out["streak_started_at"] is None


def test_speed_clears_after_alert_via_hysteresis():
    out = speed_engine.evaluate(
        speed_kmh=85, limit_kmh=90, now_ts=2000,
        streak_started_at=1000, over_speed_active=True,
    )
    assert out["event"] == "over_speed_cleared"
    assert out["over_speed_active"] is False


def test_speed_does_not_clear_within_margin():
    out = speed_engine.evaluate(
        speed_kmh=87, limit_kmh=90, now_ts=2000,
        streak_started_at=1000, over_speed_active=True,
    )
    # 87 > 90-5 (clear) → still active
    assert out["event"] is None
    assert out["over_speed_active"] is True


def test_running_stats_update():
    mx, sm, n = speed_engine.update_running_stats(
        speed_kmh=60.0, max_so_far=50.0, sum_so_far=100.0, samples_so_far=2,
    )
    assert mx == 60.0
    assert sm == 160.0
    assert n == 3


def test_running_stats_max_preserved():
    mx, *_ = speed_engine.update_running_stats(
        speed_kmh=40.0, max_so_far=80.0, sum_so_far=0.0, samples_so_far=0,
    )
    assert mx == 80.0


def test_avg_from_normal():
    assert speed_engine.avg_from(150.0, 3) == 50.0


def test_avg_from_zero_samples():
    assert speed_engine.avg_from(0.0, 0) == 0.0


# ── battery_engine ───────────────────────────────────────────────────────────


def test_battery_should_fire_at_threshold():
    assert battery_engine.should_fire(15, already_fired=False) is True


def test_battery_should_fire_below_threshold():
    assert battery_engine.should_fire(5, already_fired=False) is True


def test_battery_should_not_fire_above_threshold():
    assert battery_engine.should_fire(20, already_fired=False) is False


def test_battery_should_not_fire_when_already_fired():
    assert battery_engine.should_fire(5, already_fired=True) is False


def test_battery_should_not_fire_when_none():
    assert battery_engine.should_fire(None, already_fired=False) is False


# ── geo_engine.haversine + signal_quality ────────────────────────────────────


def test_haversine_zero_distance():
    d = geo_engine.haversine_m(34.8, -1.3, 34.8, -1.3)
    assert d == pytest.approx(0.0, abs=1.0)


def test_haversine_one_degree_latitude_about_111km():
    d = geo_engine.haversine_m(34.0, 0.0, 35.0, 0.0)
    assert 110_000 < d < 112_000


def test_haversine_symmetric():
    d1 = geo_engine.haversine_m(34.8, -1.3, 35.5, -1.0)
    d2 = geo_engine.haversine_m(35.5, -1.0, 34.8, -1.3)
    assert d1 == pytest.approx(d2)


def test_signal_quality_buckets():
    assert geo_engine.signal_quality(10) == "excellent"
    assert geo_engine.signal_quality(30) == "good"
    assert geo_engine.signal_quality(70) == "fair"
    assert geo_engine.signal_quality(200) == "poor"
    assert geo_engine.signal_quality(None) == "unknown"


# ── geo_engine.evaluate_safe_zone ────────────────────────────────────────────


def test_safe_zone_disabled_when_no_config():
    out = geo_engine.evaluate_safe_zone(
        lat=0.0, lon=0.0,
        sz_lat=None, sz_lon=None, sz_radius_m=None,
        now_ts=1000, outside_streak_start=None, safe_zone_exit_active=False,
    )
    assert out["event"] is None
    assert out["safe_zone_exit_active"] is False
    assert out["distance_m"] is None


def test_safe_zone_inside_no_event():
    out = geo_engine.evaluate_safe_zone(
        lat=34.8, lon=-1.3,
        sz_lat=34.8, sz_lon=-1.3, sz_radius_m=500,
        now_ts=1000, outside_streak_start=None, safe_zone_exit_active=False,
    )
    assert out["event"] is None
    assert out["distance_m"] == pytest.approx(0.0, abs=1.0)


def test_safe_zone_outside_starts_streak():
    out = geo_engine.evaluate_safe_zone(
        lat=35.0, lon=-1.3,  # ~22km from origin
        sz_lat=34.8, sz_lon=-1.3, sz_radius_m=500,
        now_ts=1000, outside_streak_start=None, safe_zone_exit_active=False,
    )
    assert out["event"] is None
    assert out["outside_streak_start"] == 1000


def test_safe_zone_exit_fires_after_streak():
    streak_start = 1000
    now = streak_start + geo_engine.SAFE_ZONE_STREAK_SECONDS
    out = geo_engine.evaluate_safe_zone(
        lat=35.0, lon=-1.3,
        sz_lat=34.8, sz_lon=-1.3, sz_radius_m=500,
        now_ts=now, outside_streak_start=streak_start, safe_zone_exit_active=False,
    )
    assert out["event"] == "safe_zone_exit"
    assert out["safe_zone_exit_active"] is True


def test_safe_zone_return_immediate():
    out = geo_engine.evaluate_safe_zone(
        lat=34.8, lon=-1.3,
        sz_lat=34.8, sz_lon=-1.3, sz_radius_m=500,
        now_ts=2000, outside_streak_start=1000, safe_zone_exit_active=True,
    )
    assert out["event"] == "safe_zone_return"
    assert out["safe_zone_exit_active"] is False


def test_safe_zone_re_entry_resets_streak():
    out = geo_engine.evaluate_safe_zone(
        lat=34.8, lon=-1.3,
        sz_lat=34.8, sz_lon=-1.3, sz_radius_m=500,
        now_ts=1100, outside_streak_start=1000, safe_zone_exit_active=False,
    )
    assert out["event"] is None
    assert out["outside_streak_start"] is None


# ── anti_cut_engine ──────────────────────────────────────────────────────────


@pytest.fixture
def _stub_audit_logger(monkeypatch):
    """anti_cut_engine.audit_logger.anti_cut_blocked writes to sentinel.db.
    Stub it so the policy assertions can be tested in isolation."""
    from app.blueprints.sentinel import audit_logger as al

    calls = []
    monkeypatch.setattr(al, "anti_cut_blocked", lambda sid, reason: calls.append((sid, reason)) or 1)
    return calls


def test_anti_cut_unknown_requester_raises(_stub_audit_logger):
    with pytest.raises(AntiCutViolation, match="unknown_requester"):
        assert_no_unilateral_termination("sid-1", fsm.ACTIVE, "stranger")
    assert len(_stub_audit_logger) == 1


def test_anti_cut_valid_requester_passes(_stub_audit_logger):
    assert_no_unilateral_termination("sid-2", fsm.ACTIVE, "parent")
    assert_no_unilateral_termination("sid-3", fsm.ACTIVE, "driver")
    assert _stub_audit_logger == []


def test_anti_cut_terminal_state_silent(_stub_audit_logger):
    assert_no_unilateral_termination("sid-4", fsm.ENDED, "parent")
    assert _stub_audit_logger == []


def test_anti_cut_no_silent_deletion_live_blocked(_stub_audit_logger):
    with pytest.raises(AntiCutViolation, match="cannot_delete_live_session"):
        assert_no_silent_deletion("sid-5", fsm.ACTIVE)
    assert len(_stub_audit_logger) == 1


def test_anti_cut_no_silent_deletion_terminal_allowed(_stub_audit_logger):
    assert_no_silent_deletion("sid-6", fsm.ENDED)
    assert_no_silent_deletion("sid-7", fsm.EXPIRED)
    assert _stub_audit_logger == []
