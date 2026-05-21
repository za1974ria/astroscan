"""Integration tests — Guardian HTTP routes."""
from __future__ import annotations

import pytest

from app.blueprints.guardian import agent, audit_log

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setenv("LLM_DRY_RUN", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    audit_log.reset_for_tests()
    yield
    agent.stop_agent(timeout=2.0)
    audit_log.reset_for_tests()


def _local_env():
    return {"REMOTE_ADDR": "127.0.0.1"}


def _external_env():
    return {"REMOTE_ADDR": "1.2.3.4"}


# ─── /api/guardian/health ───────────────────────────────────────────────────


def test_health_localhost_returns_200(factory_client):
    resp = factory_client.get("/api/guardian/health", environ_overrides=_local_env())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["module"] == "guardian"
    assert "poll_interval_s" in body


def test_health_external_returns_403(factory_client):
    resp = factory_client.get("/api/guardian/health", environ_overrides=_external_env())
    assert resp.status_code == 403


def test_health_x_forwarded_for_blocked(factory_client):
    resp = factory_client.get(
        "/api/guardian/health",
        environ_overrides=_local_env(),
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert resp.status_code == 403


# ─── /api/guardian/status ───────────────────────────────────────────────────


def test_status_localhost_returns_200(factory_client):
    resp = factory_client.get("/api/guardian/status", environ_overrides=_local_env())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "snapshots" in body
    assert isinstance(body["snapshots"], list)


def test_status_external_403(factory_client):
    resp = factory_client.get("/api/guardian/status", environ_overrides=_external_env())
    assert resp.status_code == 403


# ─── /api/guardian/incidents ────────────────────────────────────────────────


def test_incidents_default_since_1h(factory_client):
    resp = factory_client.get("/api/guardian/incidents", environ_overrides=_local_env())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["since"] == "1h"
    assert isinstance(body["incidents"], list)
    assert body["count"] == len(body["incidents"])


def test_incidents_valid_since_values(factory_client):
    for since in ("15m", "1h", "6h", "24h"):
        resp = factory_client.get(
            f"/api/guardian/incidents?since={since}",
            environ_overrides=_local_env(),
        )
        assert resp.status_code == 200
        assert resp.get_json()["since"] == since


def test_incidents_invalid_since_returns_400(factory_client):
    resp = factory_client.get(
        "/api/guardian/incidents?since=99x",
        environ_overrides=_local_env(),
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "invalid_since"


def test_incidents_external_returns_403(factory_client):
    resp = factory_client.get("/api/guardian/incidents", environ_overrides=_external_env())
    assert resp.status_code == 403


def test_incidents_returned_after_writing(factory_client):
    audit_log.write_incident({
        "ts": "2026-05-21T20:00:00+00:00",
        "rule": "test_rule", "severity": "warn",
        "metric": "x.y", "operator": ">", "threshold": 1,
        "actual": 99, "cooldown_until": "2026-05-21T20:30:00+00:00",
    })
    resp = factory_client.get("/api/guardian/incidents?since=24h",
                              environ_overrides=_local_env())
    body = resp.get_json()
    rules = [i["rule"] for i in body["incidents"]]
    assert "test_rule" in rules
