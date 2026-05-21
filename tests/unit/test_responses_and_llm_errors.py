"""Unit tests — app.utils.responses + app.utils.llm_errors."""

from __future__ import annotations

import json

import pytest
from flask import Flask

from app.utils import llm_errors, responses

pytestmark = pytest.mark.unit


# ── responses ────────────────────────────────────────────────────────────────


def _flask_ctx():
    return Flask(__name__).app_context()


def test_api_ok_envelope_shape():
    with _flask_ctx():
        resp = responses.api_ok({"a": 1})
        body = json.loads(resp.get_data(as_text=True))
    assert body["ok"] is True
    assert body["data"] == {"a": 1}
    assert "timestamp" in body


def test_api_ok_no_data_is_none():
    with _flask_ctx():
        resp = responses.api_ok()
        body = json.loads(resp.get_data(as_text=True))
    assert body["ok"] is True
    assert body["data"] is None


def test_api_ok_extra_fields_merged():
    with _flask_ctx():
        resp = responses.api_ok({"x": 1}, count=5, source="cache")
        body = json.loads(resp.get_data(as_text=True))
    assert body["count"] == 5
    assert body["source"] == "cache"


def test_api_error_envelope_shape():
    with _flask_ctx():
        resp, code = responses.api_error("bad thing")
        body = json.loads(resp.get_data(as_text=True))
    assert code == 400
    assert body["ok"] is False
    assert body["error"] == "bad thing"
    assert "timestamp" in body


def test_api_error_custom_code():
    with _flask_ctx():
        resp, code = responses.api_error("not found", code=404)
    assert code == 404


def test_api_error_extra_fields():
    with _flask_ctx():
        resp, code = responses.api_error("oops", code=500, detail="db down", field="x")
        body = json.loads(resp.get_data(as_text=True))
    assert body["detail"] == "db down"
    assert body["field"] == "x"


# ── llm_errors.classify_error ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "msg, expected",
    [
        ("credit balance is too low", "unavailable"),
        ("Your quota has been exceeded", "unavailable"),
        ("Billing issue", "unavailable"),
        ("insufficient_quota", "unavailable"),
        ("Payment required", "unavailable"),
        ("rate limit exceeded", "rate_limit"),
        ("Too many requests", "rate_limit"),
        ("HTTP 429", "rate_limit"),
        ("Request timeout", "timeout"),
        ("400 Bad Request", "invalid_input"),
        ("invalid_request_error", "invalid_input"),
        ("401 Unauthorized", "unavailable"),
        ("403 Forbidden", "unavailable"),
        ("invalid api key", "unavailable"),
        ("authentication failed", "unavailable"),
        ("500 internal server error", "unavailable"),
        ("503 service unavailable", "unavailable"),
        ("502 bad gateway", "unavailable"),
        ("504 gateway timeout", "timeout"),  # 'timeout' substring wins via heuristic order
        ("unknown weird thing", "generic"),
    ],
)
def test_classify_error_strings(msg, expected):
    assert llm_errors.classify_error(msg) == expected


def test_classify_error_none_is_generic():
    assert llm_errors.classify_error(None) == "generic"


def test_classify_error_exception_with_message():
    exc = ValueError("rate limit exceeded")
    assert llm_errors.classify_error(exc) == "rate_limit"


def test_classify_error_exception_class_name_signal():
    class TimedOutError(Exception):
        pass

    assert llm_errors.classify_error(TimedOutError("…")) == "timeout"


# ── llm_errors.friendly_message ──────────────────────────────────────────────


def test_friendly_message_fr_default():
    msg = llm_errors.friendly_message("rate limit", lang="fr")
    assert "Le service IA" in msg


def test_friendly_message_en():
    msg = llm_errors.friendly_message("rate limit", lang="en")
    assert "AI service" in msg


def test_friendly_message_unknown_lang_falls_back_to_fr():
    msg = llm_errors.friendly_message("timeout", lang="zz")
    # Unknown lang → _get_lang() called, returns 'fr' fallback
    assert "IA" in msg or "Service" in msg


def test_friendly_message_for_credit_balance_does_not_leak_raw():
    raw = "Your credit balance is too low — request_id req_abc"
    msg = llm_errors.friendly_message(raw, lang="en")
    assert "credit balance" not in msg
    assert "req_abc" not in msg


# ── llm_errors.llm_error_response ───────────────────────────────────────────


def test_llm_error_response_shape_unavailable():
    with _flask_ctx():
        resp, code = llm_errors.llm_error_response("credit balance too low", provider="Anthropic")
        body = json.loads(resp.get_data(as_text=True))
    assert code == 503
    assert body["ok"] is False
    assert body["service_status"] == "unavailable"
    assert "credit balance" not in body["error"]


def test_llm_error_response_shape_rate_limit():
    with _flask_ctx():
        resp, code = llm_errors.llm_error_response("429 too many", provider="Groq")
        body = json.loads(resp.get_data(as_text=True))
    assert body["service_status"] == "unavailable"


def test_llm_error_response_shape_generic():
    with _flask_ctx():
        resp, code = llm_errors.llm_error_response("weird", provider="X")
        body = json.loads(resp.get_data(as_text=True))
    assert body["service_status"] == "error"


def test_llm_error_response_with_exception():
    with _flask_ctx():
        exc = TimeoutError("upstream timed out")
        resp, code = llm_errors.llm_error_response(exc, provider="Anthropic")
        body = json.loads(resp.get_data(as_text=True))
    assert code == 503
    assert body["ok"] is False


def test_llm_error_response_custom_status():
    with _flask_ctx():
        resp, code = llm_errors.llm_error_response("x", provider="X", http_status=502)
    assert code == 502
