"""Integration tests — AstroBrain HTTP routes via factory_app fixture.

Uses LLM_DRY_RUN=1 so no API call. Requires the conftest.py monkey-patch
on builtins.open to swallow PermissionError on .env (already in place
from Axe 1).
"""

from __future__ import annotations

import pytest

from app.blueprints.astrobrain import rate_limit

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setenv("LLM_DRY_RUN", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rate_limit.reset_for_tests()
    yield
    rate_limit.reset_for_tests()


def _local_env():
    return {"REMOTE_ADDR": "127.0.0.1"}


def _external_env():
    return {"REMOTE_ADDR": "1.2.3.4"}


# ─── /api/astrobrain/health ─────────────────────────────────────────────────


def test_health_localhost_returns_200(factory_client):
    resp = factory_client.get("/api/astrobrain/health", environ_overrides=_local_env())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["module"] == "astrobrain"
    assert body["dry_run"] is True
    assert "model_default" in body
    assert "budget" in body


def test_health_external_returns_403(factory_client):
    resp = factory_client.get("/api/astrobrain/health", environ_overrides=_external_env())
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "localhost_only"


def test_health_x_forwarded_for_returns_403(factory_client):
    resp = factory_client.get(
        "/api/astrobrain/health",
        environ_overrides=_local_env(),
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert resp.status_code == 403


# ─── /api/astrobrain/ask ────────────────────────────────────────────────────


def test_ask_localhost_dry_run_returns_200(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/ask",
        json={"question": "What is the orbital period of the ISS?"},
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["dry_run"] is True
    assert "DRY_RUN" in (body["answer"] or "")


def test_ask_external_returns_403(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/ask",
        json={"question": "x"},
        environ_overrides=_external_env(),
    )
    assert resp.status_code == 403


def test_ask_missing_question_returns_400(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/ask",
        json={},
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 400


def test_ask_empty_question_returns_400(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/ask",
        json={"question": ""},
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 400


def test_ask_too_long_question_returns_413(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/ask",
        json={"question": "x" * 5000},
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 413


def test_ask_with_context(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/ask",
        json={
            "question": "Interpret this Kp value",
            "context": {"kp": 5.7, "ts": "2026-05-21T20:00Z"},
        },
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 200


def test_ask_invalid_context_type(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/ask",
        json={"question": "x", "context": "should be object"},
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 400


# ─── /api/astrobrain/explain-telemetry ──────────────────────────────────────


def test_explain_telemetry_localhost_ok(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/explain-telemetry",
        json={"telemetry": {"iss": {"alt_km": 408, "lat": 12.3}}},
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_explain_telemetry_external_403(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/explain-telemetry",
        json={"telemetry": {"x": 1}},
        environ_overrides=_external_env(),
    )
    assert resp.status_code == 403


def test_explain_telemetry_missing_payload(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/explain-telemetry",
        json={},
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 400


def test_explain_telemetry_with_focus(factory_client):
    resp = factory_client.post(
        "/api/astrobrain/explain-telemetry",
        json={"telemetry": {"kp": 6.0}, "focus": "geomagnetic storm risk"},
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 200


def test_budget_exceeded_returns_429(factory_client, monkeypatch):
    monkeypatch.setenv("ASTROBRAIN_DAILY_TOKEN_BUDGET", "1")
    rate_limit.reset_for_tests()
    resp = factory_client.post(
        "/api/astrobrain/ask",
        json={"question": "A question that will exceed a budget of 1 token easily"},
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 429
    assert resp.get_json()["error"] == "daily_token_budget_exceeded"
