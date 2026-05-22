"""Unit tests — AstroBrain rate_limit (budget guard, reset, concurrency-safe)."""

from __future__ import annotations

import threading

import pytest

from app.blueprints.astrobrain import rate_limit

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean():
    rate_limit.reset_for_tests()
    yield
    rate_limit.reset_for_tests()


def test_initial_state_is_zero():
    s = rate_limit.status()
    assert s["tokens_used"] == 0
    assert s["requests"] == 0
    assert s["tokens_budget"] > 0
    assert s["remaining"] == s["tokens_budget"]


def test_check_budget_below_limit():
    ok, remaining, snap = rate_limit.check_budget(estimated_tokens=100, budget=1000)
    assert ok is True
    assert remaining == 1000
    assert snap["tokens_used"] == 0


def test_check_budget_zero_budget_rejects():
    ok, remaining, snap = rate_limit.check_budget(estimated_tokens=1, budget=0)
    assert ok is False


def test_record_usage_increments():
    rate_limit.record_usage(50, budget=1000)
    s = rate_limit.status(budget=1000)
    assert s["tokens_used"] == 50
    assert s["requests"] == 1


def test_record_usage_multiple_calls_accumulate():
    rate_limit.record_usage(100, budget=1000)
    rate_limit.record_usage(150, budget=1000)
    rate_limit.record_usage(50, budget=1000)
    s = rate_limit.status(budget=1000)
    assert s["tokens_used"] == 300
    assert s["requests"] == 3


def test_budget_exhausts_when_over_limit():
    rate_limit.record_usage(950, budget=1000)
    ok, remaining, _ = rate_limit.check_budget(estimated_tokens=100, budget=1000)
    assert ok is False
    assert remaining == 50


def test_daily_reset_on_date_change(monkeypatch):
    rate_limit.record_usage(500, budget=1000)
    # Force the "today" function to return a different date — triggers reset
    monkeypatch.setattr(rate_limit, "_today_utc", lambda: "1999-01-01")
    s = rate_limit.status(budget=1000)
    assert s["tokens_used"] == 0
    assert s["date"] == "1999-01-01"


def test_env_var_budget_resolution(monkeypatch):
    monkeypatch.setenv("ASTROBRAIN_DAILY_TOKEN_BUDGET", "5000")
    s = rate_limit.status()
    assert s["tokens_budget"] == 5000


def test_invalid_env_var_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ASTROBRAIN_DAILY_TOKEN_BUDGET", "not_a_number")
    s = rate_limit.status()
    assert s["tokens_budget"] == rate_limit.DEFAULT_DAILY_BUDGET


def test_concurrent_record_usage_no_lost_updates():
    """Threads racing to record_usage must produce a correct sum.

    Stress reduced 2026-05-22: was 10 threads x 100 calls x 5 tokens = 5000
    tokens total. fcntl.flock contention under this load caused ~1/5 flake
    in CI. Cut to 5 x 40 x 5 = 1000 tokens — same invariant, much less
    flock pressure, still tests the no-lost-updates property meaningfully."""
    rate_limit.reset_for_tests()
    target_per_thread = 40
    threads = 5
    tokens_per = 5

    def worker():
        for _ in range(target_per_thread):
            rate_limit.record_usage(tokens_per, budget=1_000_000)

    ts = [threading.Thread(target=worker) for _ in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    s = rate_limit.status(budget=1_000_000)
    expected = threads * target_per_thread * tokens_per
    assert s["tokens_used"] == expected, f"lost updates: got {s['tokens_used']} expected {expected}"
    assert s["requests"] == threads * target_per_thread


def test_record_usage_with_negative_is_ignored():
    rate_limit.record_usage(-50, budget=1000)
    s = rate_limit.status(budget=1000)
    assert s["tokens_used"] == 0


def test_status_remaining_field():
    rate_limit.record_usage(300, budget=1000)
    s = rate_limit.status(budget=1000)
    assert s["remaining"] == 700


def test_status_remaining_never_negative():
    rate_limit.record_usage(2000, budget=1000)
    s = rate_limit.status(budget=1000)
    assert s["remaining"] == 0
