"""Unit tests — app.blueprints.sentinel.tokens (signed timed tokens)."""

from __future__ import annotations

import time

import pytest
from flask import Flask

from app.blueprints.sentinel import tokens

pytestmark = pytest.mark.unit


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "axe1-test-secret-key"
    with app.app_context():
        yield app


def test_make_tokens_two_distinct_strings(flask_app):
    p, d = tokens.make_tokens("session-001")
    assert isinstance(p, str)
    assert isinstance(d, str)
    assert p != d


def test_load_token_roundtrip_parent(flask_app):
    p, _ = tokens.make_tokens("session-002")
    payload = tokens.load_token(p, max_age_seconds=3600)
    assert payload["sid"] == "session-002"
    assert payload["role"] == "parent"


def test_load_token_roundtrip_driver(flask_app):
    _, d = tokens.make_tokens("session-003")
    payload = tokens.load_token(d, max_age_seconds=3600)
    assert payload["role"] == "driver"


def test_load_token_expected_role_match(flask_app):
    _, d = tokens.make_tokens("session-004")
    payload = tokens.load_token(d, max_age_seconds=3600, expected_role="driver")
    assert payload["role"] == "driver"


def test_load_token_wrong_role(flask_app):
    _, d = tokens.make_tokens("session-005")
    with pytest.raises(tokens.TokenError, match="wrong_role"):
        tokens.load_token(d, max_age_seconds=3600, expected_role="parent")


def test_load_token_invalid(flask_app):
    with pytest.raises(tokens.TokenError, match="invalid"):
        tokens.load_token("garbage", max_age_seconds=3600)


def test_load_token_signed_with_wrong_key(flask_app):
    """A token from a different key must fail signature validation."""
    other = Flask(__name__)
    other.config["SECRET_KEY"] = "other-secret"
    with other.app_context():
        p, _ = tokens.make_tokens("sxx")
    with pytest.raises(tokens.TokenError):
        tokens.load_token(p, max_age_seconds=3600)


def test_load_token_expired(flask_app):
    p, _ = tokens.make_tokens("session-007")
    # Wait 2 seconds then validate with max_age=1
    time.sleep(2.1)
    with pytest.raises(tokens.TokenError, match="expired"):
        tokens.load_token(p, max_age_seconds=1)


def test_sentinel_secret_key_takes_precedence(flask_app, monkeypatch):
    monkeypatch.setenv("SENTINEL_SECRET_KEY", "isolated-sentinel-key")
    p1, _ = tokens.make_tokens("session-iso")
    # A token minted with the isolated key must validate while env var is set
    payload = tokens.load_token(p1, max_age_seconds=3600)
    assert payload["sid"] == "session-iso"

    # If we clear the env var, the same token must NOT validate with the
    # Flask SECRET_KEY (different secret).
    monkeypatch.delenv("SENTINEL_SECRET_KEY", raising=False)
    with pytest.raises(tokens.TokenError):
        tokens.load_token(p1, max_age_seconds=3600)
