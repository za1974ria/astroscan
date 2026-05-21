"""Unit tests — services.circuit_breaker.

Mocks Redis via monkeypatching _get_redis to avoid network. Verifies the
state machine: CLOSED → OPEN → HALF_OPEN → CLOSED.
"""

from __future__ import annotations

import time

import pytest

from services import circuit_breaker as cb_mod

pytestmark = pytest.mark.unit


class FakeRedis:
    """In-memory stub of redis.Redis with just the methods CircuitBreaker uses."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v):
        self.store[k] = str(v)

    def setex(self, k, ttl, v):
        self.store[k] = str(v)

    def incr(self, k):
        n = int(self.store.get(k, "0")) + 1
        self.store[k] = str(n)
        return n

    def expire(self, k, ttl):
        return True

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def ping(self):
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr(cb_mod, "_redis_client", None)
    monkeypatch.setattr(cb_mod, "_get_redis", lambda: fr)
    return fr


# ── State machine ────────────────────────────────────────────────────────────


def test_breaker_starts_closed(fake_redis):
    cb = cb_mod.CircuitBreaker("TEST_CLOSED", failure_threshold=3, recovery_timeout=10)
    assert cb.state == "CLOSED"


def test_breaker_call_returns_result_on_success(fake_redis):
    cb = cb_mod.CircuitBreaker("TEST_OK", failure_threshold=3, recovery_timeout=10)
    result = cb.call(lambda: 42)
    assert result == 42


def test_breaker_opens_after_threshold_failures(fake_redis):
    cb = cb_mod.CircuitBreaker("TEST_OPEN", failure_threshold=3, recovery_timeout=60)

    def boom():
        raise ValueError("fail")

    for _ in range(3):
        cb.call(boom, fallback="FB")
    assert cb._get_state_raw() == "OPEN"


def test_breaker_returns_fallback_when_open(fake_redis):
    cb = cb_mod.CircuitBreaker("TEST_FB", failure_threshold=2, recovery_timeout=60)

    def boom():
        raise ValueError("x")

    for _ in range(2):
        cb.call(boom, fallback={"err": "open"})

    assert cb._get_state_raw() == "OPEN"
    # Subsequent calls return fallback without invoking fn
    called = {"n": 0}

    def fn():
        called["n"] += 1
        return "ok"

    result = cb.call(fn, fallback="FALLBACK")
    assert result == "FALLBACK"
    assert called["n"] == 0


def test_breaker_recovers_to_half_open_after_timeout(fake_redis):
    cb = cb_mod.CircuitBreaker("TEST_HALF", failure_threshold=1, recovery_timeout=1)

    def boom():
        raise RuntimeError("x")

    cb.call(boom, fallback=None)
    assert cb._get_state_raw() == "OPEN"
    time.sleep(1.05)
    # Reading state triggers recovery transition.
    assert cb.state == "HALF_OPEN"


def test_breaker_closes_after_successful_half_open_call(fake_redis):
    cb = cb_mod.CircuitBreaker("TEST_RECOVER", failure_threshold=1, recovery_timeout=1)

    def boom():
        raise RuntimeError("x")

    cb.call(boom, fallback=None)
    time.sleep(1.05)
    # Trigger state read → HALF_OPEN
    _ = cb.state
    # Successful call must close the breaker
    cb.call(lambda: "ok")
    assert cb._get_state_raw() == "CLOSED"


def test_breaker_reset(fake_redis):
    cb = cb_mod.CircuitBreaker("TEST_RESET", failure_threshold=1, recovery_timeout=60)

    def boom():
        raise RuntimeError("x")

    cb.call(boom, fallback=None)
    cb.reset()
    assert cb._get_state_raw() == "CLOSED"
    assert cb._get_failures() == 0


def test_breaker_status_shape(fake_redis):
    cb = cb_mod.CircuitBreaker("TEST_STATUS", failure_threshold=5, recovery_timeout=30)
    s = cb.status()
    assert s["name"] == "TEST_STATUS"
    assert s["state"] in ("CLOSED", "HALF_OPEN", "OPEN")
    assert s["failure_threshold"] == 5
    assert s["recovery_timeout_s"] == 30
    assert "failures" in s


# ── Redis-unavailable fallback path ─────────────────────────────────────────


def test_breaker_works_without_redis(monkeypatch):
    monkeypatch.setattr(cb_mod, "_redis_client", None)
    monkeypatch.setattr(cb_mod, "_get_redis", lambda: None)
    cb = cb_mod.CircuitBreaker("NO_REDIS", failure_threshold=2, recovery_timeout=10)
    # All operations must degrade gracefully.
    assert cb.state == "CLOSED"
    assert cb._get_failures() == 0
    cb._set_state("OPEN")  # no-op
    cb._set_last_fail(time.time())  # no-op
    cb._incr_failures()  # returns 0
    cb._reset_failures()  # no-op
    cb.reset()
    # call() with no Redis: fn runs normally
    assert cb.call(lambda: "ok") == "ok"


# ── Module-level breakers / all_status ──────────────────────────────────────


def test_predefined_breakers_exist():
    for name in ("CB_NASA", "CB_N2YO", "CB_NOAA", "CB_ISS", "CB_METEO", "CB_TLE", "CB_GROQ"):
        assert hasattr(cb_mod, name)
        assert isinstance(getattr(cb_mod, name), cb_mod.CircuitBreaker)


def test_all_breakers_list_has_all_seven():
    assert len(cb_mod.ALL_BREAKERS) == 7


def test_all_status_returns_list_of_dicts():
    statuses = cb_mod.all_status()
    assert isinstance(statuses, list)
    assert len(statuses) == 7
    for s in statuses:
        assert "name" in s
        assert "state" in s
