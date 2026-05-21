"""Unit tests — guardian.agent thread lifecycle + health()."""
from __future__ import annotations

import time

import pytest

from app.blueprints.guardian import agent, audit_log

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _cleanup_agent_state():
    """Each test starts with a stopped agent + empty incident buffer."""
    agent.stop_agent(timeout=2.0)
    audit_log.reset_for_tests()
    yield
    agent.stop_agent(timeout=2.0)
    audit_log.reset_for_tests()


def test_health_when_not_started():
    h = agent.health()
    assert h["ok"] is True
    assert h["module"] == "guardian"
    assert h["thread_alive"] is False
    assert h["started"] is False


def test_start_agent_idempotent(monkeypatch):
    monkeypatch.setenv("GUARDIAN_ENABLED", "1")
    monkeypatch.setenv("GUARDIAN_POLL_INTERVAL", "300")  # avoid actual ticks during test
    first = agent.start_agent()
    second = agent.start_agent()
    assert first is True
    assert second is False  # already running
    h = agent.health()
    assert h["started"] is True


def test_start_agent_disabled(monkeypatch):
    monkeypatch.setenv("GUARDIAN_ENABLED", "0")
    started = agent.start_agent()
    assert started is False
    assert agent.health()["thread_alive"] is False


def test_stop_agent_when_not_running():
    # Should be idempotent / safe
    result = agent.stop_agent()
    assert result is True


def test_start_does_not_block_caller(monkeypatch):
    """A slow tick must not delay the caller of start_agent()."""
    monkeypatch.setenv("GUARDIAN_ENABLED", "1")
    monkeypatch.setenv("GUARDIAN_POLL_INTERVAL", "300")

    t0 = time.monotonic()
    agent.start_agent()
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, f"start_agent took {elapsed:.2f}s — should be near-instant"


def test_thread_runs_at_least_one_tick(monkeypatch):
    """With a tight interval the loop must produce >=1 tick within ~1.5s."""
    monkeypatch.setenv("GUARDIAN_ENABLED", "1")
    monkeypatch.setenv("GUARDIAN_POLL_INTERVAL", "5")  # min interval is 5s
    # Replace collect_all with a tiny no-op for speed
    from app.blueprints.guardian import collectors

    monkeypatch.setattr(collectors, "collect_all", lambda: [])
    agent.start_agent()
    # First tick is immediate
    time.sleep(0.5)
    h = agent.health()
    assert h["ticks_total"] >= 1


def test_llm_summarize_skipped_in_dry_run(monkeypatch):
    monkeypatch.setenv("LLM_DRY_RUN", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    res = agent._maybe_llm_summarize(
        {"severity": "critical"}, snapshot_map={}
    )
    assert res is None


def test_llm_summarize_skipped_when_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_DRY_RUN", "0")
    res = agent._maybe_llm_summarize(
        {"severity": "critical"}, snapshot_map={}
    )
    assert res is None


def test_llm_summarize_skipped_when_severity_not_critical(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_DRY_RUN", "0")
    res = agent._maybe_llm_summarize(
        {"severity": "warn"}, snapshot_map={}
    )
    assert res is None


def test_poll_interval_default(monkeypatch):
    monkeypatch.delenv("GUARDIAN_POLL_INTERVAL", raising=False)
    assert agent._poll_interval() == float(agent.DEFAULT_POLL_INTERVAL_S)


def test_poll_interval_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("GUARDIAN_POLL_INTERVAL", "garbage")
    assert agent._poll_interval() == float(agent.DEFAULT_POLL_INTERVAL_S)


def test_poll_interval_floor_enforced(monkeypatch):
    monkeypatch.setenv("GUARDIAN_POLL_INTERVAL", "1")
    assert agent._poll_interval() == float(agent.MIN_POLL_INTERVAL_S)
