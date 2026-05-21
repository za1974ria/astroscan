"""Unit tests for services.llm_client (AstroBrain LLM wrapper)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from services.llm_client import (
    LLMClient,
    LLMClientError,
    LLMResponse,
    _safe_error_message,
    make_default_client,
)

pytestmark = pytest.mark.unit


# ─── Dry-run mode ───────────────────────────────────────────────────────────


def test_dry_run_default_when_no_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_DRY_RUN", raising=False)
    c = LLMClient()
    assert c.dry_run is True


def test_dry_run_explicit_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("LLM_DRY_RUN", "0")
    c = LLMClient(dry_run=True)
    assert c.dry_run is True


def test_dry_run_env_var_true(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("LLM_DRY_RUN", "1")
    c = LLMClient()
    assert c.dry_run is True


def test_dry_run_response_shape():
    c = LLMClient(api_key="dummy", dry_run=True)
    resp = c.chat(
        [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}],
        model="gpt-5-mini",
    )
    assert resp.ok is True
    assert resp.dry_run is True
    assert "DRY_RUN" in resp.text
    assert resp.model.endswith("-dry-run")
    assert resp.tokens_in > 0
    assert resp.tokens_out > 0


def test_dry_run_does_not_call_openai():
    c = LLMClient(api_key="dummy", dry_run=True)
    with patch.object(c, "_get_openai") as get_openai:
        c.chat([{"role": "user", "content": "x"}], model="gpt-5")
        get_openai.assert_not_called()


# ─── Misconfiguration ───────────────────────────────────────────────────────


def test_raises_when_no_key_and_not_dry_run(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMClientError):
        LLMClient(dry_run=False)


# ─── Retry behavior — mocked client ─────────────────────────────────────────


def _fake_openai_client(responses=None, raise_seq=None):
    """Build a MagicMock that mimics openai.OpenAI minimally.

    Either ``responses`` is a list of successful response objects to return in
    order, or ``raise_seq`` is a list of exceptions to raise in order.
    """
    fake = MagicMock()
    chat = MagicMock()
    completions = MagicMock()
    fake.chat = chat
    chat.completions = completions

    side_effects: list = []
    if raise_seq:
        side_effects.extend(raise_seq)
    if responses:
        side_effects.extend(responses)
    completions.create.side_effect = side_effects
    return fake


def _success_response(text="ok", tokens_in=10, tokens_out=20, model="gpt-5-mini"):
    r = MagicMock()
    r.choices = [MagicMock()]
    r.choices[0].message = MagicMock()
    r.choices[0].message.content = text
    r.usage = MagicMock()
    r.usage.prompt_tokens = tokens_in
    r.usage.completion_tokens = tokens_out
    r.model = model
    return r


def test_retry_on_rate_limit_then_success(monkeypatch):
    from openai import RateLimitError

    rl = RateLimitError("rate limited", response=MagicMock(status_code=429), body=None)
    success = _success_response()

    c = LLMClient(api_key="sk-test", dry_run=False)
    # IMPORTANT: build the fake ONCE so its side_effect iterator persists
    # across calls (a fresh fake each call would always start at index 0).
    fake = _fake_openai_client(responses=[success], raise_seq=[rl])
    monkeypatch.setattr(c, "_get_openai", lambda: fake)
    monkeypatch.setattr("services.llm_client.time.sleep", lambda *_: None)

    resp = c.chat([{"role": "user", "content": "x"}], model="gpt-5-mini")
    assert resp.ok is True
    assert resp.attempts == 2
    assert resp.text == "ok"


def test_retry_exhausted_returns_fallback(monkeypatch):
    from openai import APITimeoutError

    to = APITimeoutError(MagicMock())
    c = LLMClient(api_key="sk-test", dry_run=False)
    fake = _fake_openai_client(raise_seq=[to, to, to])
    monkeypatch.setattr(c, "_get_openai", lambda: fake)
    monkeypatch.setattr("services.llm_client.time.sleep", lambda *_: None)

    resp = c.chat([{"role": "user", "content": "x"}], model="gpt-5-mini")
    assert resp.ok is False
    assert resp.fallback is True
    assert resp.attempts == LLMClient.MAX_ATTEMPTS
    assert resp.error == "timeout"


def test_no_retry_on_authentication_error(monkeypatch):
    from openai import AuthenticationError

    err = AuthenticationError("invalid", response=MagicMock(status_code=401), body=None)
    c = LLMClient(api_key="sk-bad", dry_run=False)
    fake = _fake_openai_client(raise_seq=[err, err, err])
    monkeypatch.setattr(c, "_get_openai", lambda: fake)
    monkeypatch.setattr("services.llm_client.time.sleep", lambda *_: None)

    resp = c.chat([{"role": "user", "content": "x"}], model="gpt-5-mini")
    assert resp.ok is False
    assert resp.attempts == 1  # NOT retried
    assert resp.error == "auth_error"


def test_no_retry_on_bad_request(monkeypatch):
    from openai import BadRequestError

    err = BadRequestError("bad", response=MagicMock(status_code=400), body=None)
    c = LLMClient(api_key="sk-test", dry_run=False)
    fake = _fake_openai_client(raise_seq=[err])
    monkeypatch.setattr(c, "_get_openai", lambda: fake)
    resp = c.chat([{"role": "user", "content": "x"}], model="gpt-5-mini")
    assert resp.ok is False
    assert resp.attempts == 1
    assert resp.error == "bad_request"


# ─── Logging — no secret leakage ────────────────────────────────────────────


def test_chat_logs_no_api_key(monkeypatch, tmp_path):
    """The structured log MUST NOT contain the API key in any field."""
    secret = "sk-DO-NOT-LEAK-ME-XYZ123ABC456"
    log_file = tmp_path / "llm_client.log"
    monkeypatch.setattr("services.llm_client._LOG_FILE", log_file)
    monkeypatch.setattr("services.llm_client._LOG_DIR", tmp_path)

    c = LLMClient(api_key=secret, dry_run=True)
    c.chat([{"role": "user", "content": "x"}], model="gpt-5-mini")
    # Dry-run doesn't write to file by current design — force a real call path test:
    # we use a fake openai client that raises a non-retriable error so logging happens.
    from openai import BadRequestError

    err = BadRequestError("bad", response=MagicMock(status_code=400), body=None)
    c2 = LLMClient(api_key=secret, dry_run=False)
    fake2 = _fake_openai_client(raise_seq=[err])
    monkeypatch.setattr(c2, "_get_openai", lambda: fake2)
    c2.chat([{"role": "user", "content": "x"}], model="gpt-5-mini")

    if log_file.exists():
        content = log_file.read_text(encoding="utf-8")
        assert secret not in content, "API key leaked into log!"


# ─── _safe_error_message — classification ───────────────────────────────────


def test_safe_error_message_known_classes():
    from openai import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        RateLimitError,
    )

    assert _safe_error_message(RateLimitError("x", response=MagicMock(status_code=429), body=None)) == "rate_limited"
    assert _safe_error_message(APIConnectionError(request=MagicMock())) == "connection_error"
    assert _safe_error_message(APITimeoutError(MagicMock())) == "timeout"
    assert _safe_error_message(AuthenticationError("x", response=MagicMock(status_code=401), body=None)) == "auth_error"
    assert _safe_error_message(BadRequestError("x", response=MagicMock(status_code=400), body=None)) == "bad_request"


def test_safe_error_message_none_returns_unknown():
    assert _safe_error_message(None) == "unknown_error"


def test_safe_error_message_unknown_class_returns_upstream_error():
    assert _safe_error_message(RuntimeError("weird")) == "upstream_error"


# ─── Factory ────────────────────────────────────────────────────────────────


def test_make_default_client_uses_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    monkeypatch.setenv("LLM_DRY_RUN", "1")
    c = make_default_client()
    assert c.api_key == "sk-from-env"
    assert c.dry_run is True


def test_llm_response_dataclass_defaults():
    r = LLMResponse(ok=True, text="hi", model="gpt-5-mini")
    assert r.tokens_in == 0
    assert r.tokens_out == 0
    assert r.fallback is False
    assert r.dry_run is False
    assert r.meta == {}
