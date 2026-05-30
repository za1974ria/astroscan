"""Unit tests — Gemini API key MUST live in headers, never in URL or argv.

Security regression test : the prod incident traced GEMINI_API_KEY visible in
`ps -ef` / `systemctl status` because the previous `_call_gemini` shipped the
key inside a `curl` argv (`?key=...` in the URL passed to subprocess.run).
This file enforces:

  - No `?key=` ever appears in Gemini URLs in app/services/ai_translate.py.
  - No subprocess/curl call references a Gemini endpoint.
  - All Gemini call sites set the `x-goog-api-key` header.
  - Live `_call_gemini` puts the key in the header, not the URL (mocked).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


pytestmark = pytest.mark.unit


AI_TRANSLATE = (
    Path(__file__).resolve().parents[2]
    / "app" / "services" / "ai_translate.py"
)


def _source() -> str:
    return AI_TRANSLATE.read_text(encoding="utf-8")


# ─── Static guards ───────────────────────────────────────────────────────────


def test_no_key_query_param_in_gemini_urls():
    """Aucune URL Gemini ne doit contenir `?key=` (toutes variantes)."""
    text = _source()
    # Find lines mentioning generativelanguage and assert none carries ?key=.
    offenders = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "generativelanguage" in line and "key=" in line:
            offenders.append((lineno, line.strip()))
    assert not offenders, (
        "URLs Gemini avec ?key= encore presentes — fuite ps/log :\n"
        + "\n".join(f"  l.{n}: {l}" for n, l in offenders)
    )


def test_no_subprocess_curl_targets_generativelanguage():
    """Aucun subprocess.run([..., 'curl', ...]) ne doit appeler generativelanguage.

    Le mecanisme curl-en-subprocess est ce qui exposait la cle dans argv via
    /proc/<pid>/cmdline (visible par ps, systemctl status, etc.). Pour Gemini,
    on est passe a requests/urllib avec header.
    """
    text = _source()
    tree = ast.parse(text)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match subprocess.run(...) and check if any string arg contains the URL.
        is_subproc_run = (
            isinstance(func, ast.Attribute)
            and func.attr == "run"
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
        )
        if not is_subproc_run:
            continue
        # First positional arg is the command list — walk it for any string literal
        # mentioning the Gemini host.
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                if "generativelanguage" in child.value:
                    offenders.append(child.lineno)
            # Also catch f-strings with the Gemini host (JoinedStr).
            if isinstance(child, ast.JoinedStr):
                for v in child.values:
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        if "generativelanguage" in v.value:
                            offenders.append(child.lineno)
    assert not offenders, (
        f"subprocess.run targets generativelanguage at lines {offenders} — "
        "use requests/urllib with x-goog-api-key header instead."
    )


def test_every_gemini_url_has_companion_x_goog_header():
    """Chaque bloc qui construit une URL Gemini doit aussi declarer le
    header x-goog-api-key. On compte les occurrences pour valider le pairing.
    """
    text = _source()
    gemini_urls = text.count("generativelanguage.googleapis.com")
    header_uses = len(re.findall(r'["\']x-goog-api-key["\']', text))
    assert gemini_urls >= 4, (
        f"Attendu >=4 sites Gemini, vu {gemini_urls} — quelqu'un a supprime un site ?"
    )
    assert header_uses >= gemini_urls, (
        f"{gemini_urls} URLs Gemini mais seulement {header_uses} headers "
        "x-goog-api-key — un site est passe sans header."
    )


# ─── Live behavior of _call_gemini ────────────────────────────────────────────


def test_call_gemini_puts_key_in_header_not_url(monkeypatch):
    """L'appel reel _call_gemini doit passer la cle UNIQUEMENT en header.

    On mock requests.post pour intercepter url/headers/json sans toucher au
    reseau. Le test echoue si la cle apparait dans l'URL.
    """
    from app.services import ai_translate

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-NEVER-IN-ARGV-OR-URL")
    # Reset rotation throttle so the call goes through immediately.
    ai_translate._key_usage = {}

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "Bonjour"}]}}
        ]
    }

    with patch("app.services.ai_translate.requests.post",
               return_value=fake_response) as mock_post:
        text, err = ai_translate._call_gemini("Hello")

    assert err is None
    assert text == "Bonjour"
    assert mock_post.called

    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    headers = call_args.kwargs.get("headers", {})

    assert "key=" not in url, (
        f"GEMINI URL CONTAINS KEY (fuite): {url!r}"
    )
    assert "test-key-NEVER-IN-ARGV-OR-URL" not in url, (
        f"GEMINI key value leaked into URL: {url!r}"
    )
    assert headers.get("x-goog-api-key") == "test-key-NEVER-IN-ARGV-OR-URL", (
        f"x-goog-api-key header missing or wrong: {headers!r}"
    )
    assert headers.get("Content-Type") == "application/json"


def test_call_gemini_returns_unconfigured_when_no_key(monkeypatch):
    """Si aucune cle GEMINI_* n'est dans l'env, l'appel doit echouer
    proprement sans toucher au reseau (etat honnete, pas de crash)."""
    from app.services import ai_translate

    for var in ("GEMINI_API_KEY", "GEMINI_API_KEY_BACKUP", "GEMINI_API_KEY_3"):
        monkeypatch.delenv(var, raising=False)
    ai_translate._key_usage = {}

    with patch("app.services.ai_translate.requests.post") as mock_post:
        text, err = ai_translate._call_gemini("Hello")

    assert text is None
    assert err is not None
    assert "non configur" in err.lower()
    assert not mock_post.called, "Aucun appel reseau ne doit partir sans cle."
