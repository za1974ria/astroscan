"""Unit tests — AstroBrainService business layer (uses LLM_DRY_RUN)."""
from __future__ import annotations

import pytest

from app.blueprints.astrobrain import rate_limit
from app.blueprints.astrobrain.service import AstroBrainService
from services.llm_client import LLMClient

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_budget(monkeypatch):
    monkeypatch.setenv("LLM_DRY_RUN", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rate_limit.reset_for_tests()
    yield
    rate_limit.reset_for_tests()


@pytest.fixture
def svc():
    return AstroBrainService(client=LLMClient(api_key="dummy", dry_run=True))


# ─── ask ────────────────────────────────────────────────────────────────────


def test_ask_returns_dict_envelope(svc):
    r = svc.ask("What is the ISS orbital period?")
    assert isinstance(r, dict)
    assert r["ok"] is True
    assert r["dry_run"] is True
    assert "answer" in r and r["answer"]
    assert r["tokens"]["in"] > 0


def test_ask_with_context(svc):
    r = svc.ask("Why is Kp high?", context={"kp_index": 7.3, "ts": "2026-05-21T20:00Z"})
    assert r["ok"] is True
    assert r["method"] == "ask"


def test_ask_rejects_empty_question(svc):
    r = svc.ask("")
    assert r["ok"] is False
    assert r["error"] == "question_required"


def test_ask_rejects_non_string_question(svc):
    r = svc.ask(None)  # type: ignore[arg-type]
    assert r["ok"] is False


# ─── explain_telemetry ──────────────────────────────────────────────────────


def test_explain_telemetry_ok(svc):
    r = svc.explain_telemetry({"iss": {"lat": 12.3, "lon": -45.6, "alt_km": 408}})
    assert r["ok"] is True
    assert r["method"] == "explain_telemetry"


def test_explain_telemetry_with_focus(svc):
    r = svc.explain_telemetry({"kp": 6.0}, focus="solar storm risk")
    assert r["ok"] is True


def test_explain_telemetry_rejects_empty(svc):
    r = svc.explain_telemetry({})
    assert r["ok"] is False
    assert r["error"] == "telemetry_required"


def test_explain_telemetry_rejects_non_dict(svc):
    r = svc.explain_telemetry("nope")  # type: ignore[arg-type]
    assert r["ok"] is False


# ─── summarize_health ───────────────────────────────────────────────────────


def test_summarize_health_ok(svc):
    r = svc.summarize_health({"systemd": "active", "disk_pct": 45})
    assert r["ok"] is True
    assert r["method"] == "summarize_health"


def test_summarize_health_rejects_empty(svc):
    r = svc.summarize_health({})
    assert r["ok"] is False
    assert r["error"] == "health_data_required"


# ─── analyze_anomaly ────────────────────────────────────────────────────────


def test_analyze_anomaly_with_logs_and_metrics(svc):
    r = svc.analyze_anomaly("ERROR 500 at 20:42 on /api/iss/pos", metrics={"err_count": 12})
    assert r["ok"] is True
    assert r["method"] == "analyze_anomaly"


def test_analyze_anomaly_empty_logs_ok(svc):
    # The analyzer can accept empty logs and report insufficient_data on its own
    r = svc.analyze_anomaly("")
    assert r["ok"] is True


# ─── Model selection ───────────────────────────────────────────────────────


def test_ask_uses_default_model(svc, monkeypatch):
    monkeypatch.setenv("ASTROBRAIN_MODEL_DEFAULT", "gpt-5-mini")
    r = svc.ask("test")
    assert "gpt-5-mini" in r["model"]


def test_explain_telemetry_uses_premium_model(svc, monkeypatch):
    monkeypatch.setenv("ASTROBRAIN_MODEL_PREMIUM", "gpt-5")
    r = svc.explain_telemetry({"x": 1})
    assert "gpt-5" in r["model"]


# ─── Budget gate ────────────────────────────────────────────────────────────


def test_budget_exceeded_blocks_call(svc, monkeypatch):
    # Set a tiny daily budget so the first call exceeds it.
    monkeypatch.setenv("ASTROBRAIN_DAILY_TOKEN_BUDGET", "1")
    rate_limit.reset_for_tests()
    r = svc.ask("A relatively long question that should exceed a 1-token budget")
    assert r["ok"] is False
    assert r["error"] == "daily_token_budget_exceeded"


def test_budget_records_usage_after_call(svc):
    rate_limit.reset_for_tests()
    before = rate_limit.status()["tokens_used"]
    svc.ask("hello")
    after = rate_limit.status()["tokens_used"]
    assert after > before
