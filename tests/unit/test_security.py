"""Tests unitaires — décorateurs require_admin + rate_limit_ip.

PASS 28.SEC (2026-05-09).

Construit une mini-app Flask isolée pour tester les décorateurs sans
dépendre de `factory_app` (qui exige .env). Réinitialise systématiquement
le compteur global `_API_RATE_HITS` entre les tests.
"""
from __future__ import annotations

import time

import pytest
from flask import Blueprint, Flask, jsonify

from app.services import security as sec_mod
from app.services.security import (
    _API_RATE_HITS,
    rate_limit_ip,
    require_admin,
)


# ── Helpers ────────────────────────────────────────────────────────────

def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    bp = Blueprint("t", __name__)

    @bp.route("/admin/ping", methods=["POST"])
    @require_admin
    def admin_ping():
        return jsonify({"ok": True, "msg": "admin"})

    @bp.route("/rl", methods=["POST"])
    @rate_limit_ip(max_per_minute=3, key_prefix="t.rl")
    def rl():
        return jsonify({"ok": True, "msg": "rl"})

    app.register_blueprint(bp)
    return app


@pytest.fixture(autouse=True)
def _reset_rate_state(monkeypatch):
    """Vide le compteur global avant chaque test + retire ADMIN_TOKEN env."""
    _API_RATE_HITS.clear()
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ASTROSCAN_ADMIN_TOKEN", raising=False)
    yield
    _API_RATE_HITS.clear()


@pytest.fixture
def app():
    return _build_app()


@pytest.fixture
def client(app):
    return app.test_client()


# ── require_admin ──────────────────────────────────────────────────────

def test_require_admin_fail_closed_when_token_unset(client):
    """ADMIN_TOKEN absent → 503 (fail-closed), pas 200."""
    rv = client.post("/admin/ping")
    assert rv.status_code == 503
    body = rv.get_json()
    assert body["ok"] is False
    assert "ADMIN_TOKEN" in body["error"]


def test_require_admin_401_without_header(monkeypatch, client):
    monkeypatch.setenv("ADMIN_TOKEN", "secret123")
    rv = client.post("/admin/ping")
    assert rv.status_code == 401
    assert rv.get_json()["ok"] is False


def test_require_admin_401_with_wrong_token(monkeypatch, client):
    monkeypatch.setenv("ADMIN_TOKEN", "secret123")
    rv = client.post("/admin/ping", headers={"X-Admin-Token": "bad"})
    assert rv.status_code == 401


def test_require_admin_200_with_correct_x_admin_token(monkeypatch, client):
    monkeypatch.setenv("ADMIN_TOKEN", "secret123")
    rv = client.post("/admin/ping", headers={"X-Admin-Token": "secret123"})
    assert rv.status_code == 200
    assert rv.get_json()["msg"] == "admin"


def test_require_admin_200_with_authorization_bearer_fallback(monkeypatch, client):
    """Compat avec le pattern legacy Authorization: Bearer."""
    monkeypatch.setenv("ADMIN_TOKEN", "secret123")
    rv = client.post("/admin/ping", headers={"Authorization": "Bearer secret123"})
    assert rv.status_code == 200


def test_require_admin_uses_legacy_astroscan_admin_token(monkeypatch, client):
    """ASTROSCAN_ADMIN_TOKEN est utilisé si ADMIN_TOKEN absent (compat prod)."""
    monkeypatch.setenv("ASTROSCAN_ADMIN_TOKEN", "legacy")
    rv = client.post("/admin/ping", headers={"X-Admin-Token": "legacy"})
    assert rv.status_code == 200


# ── rate_limit_ip ──────────────────────────────────────────────────────

def test_rate_limit_passes_below_limit(client):
    for _ in range(3):
        rv = client.post("/rl")
        assert rv.status_code == 200


def test_rate_limit_blocks_above_limit(client):
    for _ in range(3):
        client.post("/rl")
    rv = client.post("/rl")
    assert rv.status_code == 429
    body = rv.get_json()
    assert body["ok"] is False
    assert body["limit"] == 3
    assert body["window_sec"] == 60
    assert body["retry_after"] >= 1


def test_rate_limit_headers_present_on_success(client):
    rv = client.post("/rl")
    assert rv.status_code == 200
    assert rv.headers.get("X-RateLimit-Limit") == "3"
    # Premier hit ⇒ 2 restants.
    assert rv.headers.get("X-RateLimit-Remaining") == "2"
    assert rv.headers.get("X-RateLimit-Reset") == "60"


def test_rate_limit_headers_present_on_429(client):
    for _ in range(3):
        client.post("/rl")
    rv = client.post("/rl")
    assert rv.status_code == 429
    assert rv.headers.get("Retry-After") is not None
    assert rv.headers.get("X-RateLimit-Limit") == "3"
    assert rv.headers.get("X-RateLimit-Remaining") == "0"


def test_rate_limit_per_ip_isolation(client):
    # 3 hits depuis IP A — saturé.
    for _ in range(3):
        client.post("/rl", environ_overrides={"REMOTE_ADDR": "10.0.0.1"})
    blocked = client.post("/rl", environ_overrides={"REMOTE_ADDR": "10.0.0.1"})
    assert blocked.status_code == 429

    # IP B doit passer.
    rv = client.post("/rl", environ_overrides={"REMOTE_ADDR": "10.0.0.2"})
    assert rv.status_code == 200


def test_rate_limit_sliding_window_60s(monkeypatch, client):
    """Fenêtre glissante : après simulation d'un saut > 60s, le compteur se réinitialise."""
    fake_clock = {"t": 1000.0}

    def _fake_time():
        return fake_clock["t"]

    monkeypatch.setattr(sec_mod.time, "time", _fake_time)

    for _ in range(3):
        rv = client.post("/rl")
        assert rv.status_code == 200

    # Sous la limite : 4e bloqué.
    rv = client.post("/rl")
    assert rv.status_code == 429

    # On avance de 61s → la fenêtre glissante doit avoir évacué les hits.
    fake_clock["t"] += 61
    rv = client.post("/rl")
    assert rv.status_code == 200


def test_rate_limit_x_forwarded_for_used_for_keying(client):
    """X-Forwarded-For prioritaire : 2 IPs distinctes derrière le même remote_addr ⇒ pas de fuite."""
    for _ in range(3):
        client.post("/rl", headers={"X-Forwarded-For": "1.1.1.1"})
    blocked = client.post("/rl", headers={"X-Forwarded-For": "1.1.1.1"})
    assert blocked.status_code == 429

    rv = client.post("/rl", headers={"X-Forwarded-For": "2.2.2.2"})
    assert rv.status_code == 200
