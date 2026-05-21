"""Unit tests — @require_localhost decorator (security)."""

from __future__ import annotations

import pytest
from flask import Flask, jsonify

from app.blueprints.astrobrain.security import (
    is_localhost_request,
    require_localhost,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def app():
    app = Flask(__name__)

    @app.route("/probe")
    @require_localhost
    def probe():
        return jsonify({"ok": True})

    return app


def test_loopback_v4_allowed(app):
    client = app.test_client()
    resp = client.get("/probe", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_loopback_v6_allowed(app):
    client = app.test_client()
    resp = client.get("/probe", environ_overrides={"REMOTE_ADDR": "::1"})
    assert resp.status_code == 200


def test_localhost_string_allowed(app):
    client = app.test_client()
    resp = client.get("/probe", environ_overrides={"REMOTE_ADDR": "localhost"})
    assert resp.status_code == 200


def test_non_loopback_refused(app):
    client = app.test_client()
    resp = client.get("/probe", environ_overrides={"REMOTE_ADDR": "1.2.3.4"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "localhost_only"


def test_private_lan_refused(app):
    client = app.test_client()
    resp = client.get("/probe", environ_overrides={"REMOTE_ADDR": "192.168.1.50"})
    assert resp.status_code == 403


def test_x_forwarded_for_blocks_even_from_loopback(app):
    """Even if the socket peer is loopback, an X-Forwarded-For header means
    we came via Nginx — block to avoid public exposure."""
    client = app.test_client()
    resp = client.get(
        "/probe",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert resp.status_code == 403


def test_x_real_ip_blocks_even_from_loopback(app):
    client = app.test_client()
    resp = client.get(
        "/probe",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Real-IP": "1.2.3.4"},
    )
    assert resp.status_code == 403


def test_empty_remote_addr_refused(app):
    client = app.test_client()
    resp = client.get("/probe", environ_overrides={"REMOTE_ADDR": ""})
    assert resp.status_code == 403


def test_is_localhost_request_pure(app):
    """The bare predicate without the decorator wrapper."""
    with app.test_request_context("/", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}):
        ok, reason = is_localhost_request()
        assert ok is True
        assert reason == "ok"

    with app.test_request_context("/", environ_overrides={"REMOTE_ADDR": "8.8.8.8"}):
        ok, reason = is_localhost_request()
        assert ok is False
        assert "non_loopback_peer" in reason
