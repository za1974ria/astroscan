"""Unit tests — Groq + xAI Grok API keys MUST live in headers, never in argv.

Continuation security regression test : the prior Gemini fix migrated 4 sites
to requests + x-goog-api-key header. This file enforces the same invariant
for the remaining curl-via-subprocess offenders (Groq and xAI Grok).

The vector is identical : `subprocess.run([..., "-H", f"Authorization: Bearer
{api_key}", ...])` interpolates the key into argv → /proc/<pid>/cmdline → ps
-ef → systemctl status → any system user reads the key.

Enforced :
  - No subprocess.run([..., "curl", ...]) anywhere in ai_translate.py.
  - No `Authorization: Bearer` literal embedded in an argv-style list.
  - _call_groq sends the key in headers Authorization, not in URL/argv.
  - _call_xai_grok same.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.unit


AI_TRANSLATE = (
    Path(__file__).resolve().parents[2]
    / "app" / "services" / "ai_translate.py"
)


def _source() -> str:
    return AI_TRANSLATE.read_text(encoding="utf-8")


# ─── Static guards ───────────────────────────────────────────────────────────


def test_no_subprocess_run_anywhere_in_ai_translate():
    """ai_translate.py ne doit plus appeler subprocess.run sur curl ou autre.

    Le fix Gemini + ce fix Groq/xAI eliminent tous les subprocess.run.
    Si un futur appel reapparait, le test forcera a relire la justification
    securite avant de le merger.
    """
    text = _source()
    tree = ast.parse(text)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute)
                and func.attr == "run"
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"):
            offenders.append(node.lineno)
    assert not offenders, (
        f"subprocess.run trouve aux lignes {offenders} dans ai_translate.py — "
        "doit etre remplace par requests + header (Authorization / x-goog-api-key)."
    )


def test_no_curl_literal_in_ai_translate():
    """Aucune liste argv ne doit contenir la chaine 'curl' (canari).

    Si quelqu'un re-introduit un subprocess.run(['curl', ...]), ce test
    le repere immediatement, meme avant que le code ne tourne.
    """
    text = _source()
    tree = ast.parse(text)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "curl":
            offenders.append(node.lineno)
    assert not offenders, (
        f'Le litteral "curl" est present aux lignes {offenders} dans '
        "ai_translate.py — argv literal, fuite ps. Migrer vers requests."
    )


def test_no_authorization_bearer_in_argv_style_list():
    """Aucune liste Python ne doit contenir un litteral 'Authorization: Bearer ...'.

    Les seules occurrences acceptables de 'Authorization' sont dans des dicts
    headers={...} passes a requests (ou similaires), pas dans des List[str]
    destines a subprocess.run.
    """
    text = _source()
    tree = ast.parse(text)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        for elt in node.elts:
            if (isinstance(elt, ast.Constant)
                    and isinstance(elt.value, str)
                    and "Authorization" in elt.value
                    and "Bearer" in elt.value):
                offenders.append((node.lineno, elt.value[:40]))
            # f-string interpolation case
            if isinstance(elt, ast.JoinedStr):
                joined = "".join(
                    v.value for v in elt.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                )
                if "Authorization" in joined and "Bearer" in joined:
                    offenders.append((node.lineno, joined[:40]))
    assert not offenders, (
        "Authorization: Bearer trouve dans une liste argv-style aux lignes "
        f"{offenders} — fuite ps via subprocess. Mettre dans headers={{}}."
    )


def test_groq_url_unchanged():
    text = _source()
    assert "https://api.groq.com/openai/v1/chat/completions" in text


def test_xai_default_url_unchanged():
    text = _source()
    assert "https://api.x.ai/v1/chat/completions" in text


# ─── Live behavior — Groq ─────────────────────────────────────────────────────


def test_call_groq_puts_key_in_authorization_header(monkeypatch):
    """_call_groq doit poser la cle dans le header Authorization Bearer.

    Mock requests.post pour intercepter url/headers/json. Aucune cle ne
    doit apparaitre dans l'URL.
    """
    from app.services import ai_translate

    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-NEVER-IN-ARGV-OR-URL")

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "Bonjour"}}]
    }

    with patch("app.services.ai_translate.requests.post",
               return_value=fake_response) as mock_post:
        text, err = ai_translate._call_groq("Hello")

    assert err is None
    assert text == "Bonjour"
    assert mock_post.called

    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    headers = call_args.kwargs.get("headers", {})

    assert "gsk-test-NEVER-IN-ARGV-OR-URL" not in url, (
        f"GROQ key value leaked into URL: {url!r}"
    )
    assert headers.get("Authorization") == "Bearer gsk-test-NEVER-IN-ARGV-OR-URL", (
        f"Authorization header missing or wrong: {headers!r}"
    )
    assert headers.get("Content-Type") == "application/json"


def test_call_groq_returns_unconfigured_when_no_key(monkeypatch):
    from app.services import ai_translate

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with patch("app.services.ai_translate.requests.post") as mock_post:
        text, err = ai_translate._call_groq("Hello")
    assert text is None
    assert err is not None
    assert "non configur" in err.lower()
    assert not mock_post.called


# ─── Live behavior — xAI Grok ────────────────────────────────────────────────


def test_call_xai_grok_puts_key_in_authorization_header(monkeypatch):
    """_call_xai_grok doit poser la cle dans le header Authorization Bearer."""
    from app.services import ai_translate

    monkeypatch.setenv("XAI_API_KEY", "xai-test-NEVER-IN-ARGV-OR-URL")
    monkeypatch.delenv("XAI_MODEL", raising=False)
    monkeypatch.delenv("XAI_CHAT_COMPLETIONS_URL", raising=False)

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "Bonjour"}}]
    }

    with patch("app.services.ai_translate.requests.post",
               return_value=fake_response) as mock_post:
        text, err = ai_translate._call_xai_grok("Hello")

    assert err is None
    assert text == "Bonjour"
    assert mock_post.called

    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    headers = call_args.kwargs.get("headers", {})

    # URL defaults must be respected.
    assert url == "https://api.x.ai/v1/chat/completions"
    assert "xai-test-NEVER-IN-ARGV-OR-URL" not in url
    assert headers.get("Authorization") == "Bearer xai-test-NEVER-IN-ARGV-OR-URL"
    assert headers.get("Content-Type") == "application/json"


def test_call_xai_grok_honors_url_override(monkeypatch):
    """Le passage cle->header ne doit pas casser la possibilite d'override
    de l'URL via XAI_CHAT_COMPLETIONS_URL (pattern pre-existant)."""
    from app.services import ai_translate

    monkeypatch.setenv("XAI_API_KEY", "k")
    monkeypatch.setenv("XAI_CHAT_COMPLETIONS_URL", "https://override.example/v1/chat")

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "x"}}]
    }
    with patch("app.services.ai_translate.requests.post",
               return_value=fake_response) as mock_post:
        ai_translate._call_xai_grok("hi")
    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    assert url == "https://override.example/v1/chat"


def test_call_xai_grok_returns_unconfigured_when_no_key(monkeypatch):
    from app.services import ai_translate

    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with patch("app.services.ai_translate.requests.post") as mock_post:
        text, err = ai_translate._call_xai_grok("Hello")
    assert text is None
    assert err is not None
    assert "non configur" in err.lower()
    assert not mock_post.called
