"""Unit tests — /api/aegis/status configuration flags.

The status endpoint must reflect REAL env-key presence (same pattern as
groq_configured) instead of hardcoding False. Covers both the success block
and the except block of api_aegis_status (app/blueprints/ai/__init__.py).

Two layers:
 1. Static (always run, no fixtures) — assert the route source body never
    returns False for gemini/grok, and references the canonical env vars.
 2. Integration (factory_client) — exercise the endpoint with monkeypatched
    env vars. Skipped when the factory fixture itself skips (data/ not
    writable locally), runs in CI.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


AI_BLUEPRINT = (
    Path(__file__).resolve().parents[2]
    / "app" / "blueprints" / "ai" / "__init__.py"
)


def _extract_status_function_source() -> str:
    text = AI_BLUEPRINT.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "api_aegis_status":
            return ast.get_source_segment(text, node) or ""
    pytest.fail("api_aegis_status not found in ai blueprint")


# ─── Static tests (always run, pytest.mark.unit) ─────────────────────────────


@pytest.mark.unit
def test_status_source_does_not_hardcode_gemini_false():
    """gemini_configured must NEVER be a literal `False`."""
    body = _extract_status_function_source()
    # Any literal "gemini_configured": False is a regression.
    assert not re.search(r'"gemini_configured"\s*:\s*False\b', body), (
        "api_aegis_status still hardcodes gemini_configured: False — "
        "this is the lie this fix targets."
    )


@pytest.mark.unit
def test_status_source_does_not_hardcode_grok_false():
    """grok_configured must NEVER be a literal `False`."""
    body = _extract_status_function_source()
    assert not re.search(r'"grok_configured"\s*:\s*False\b', body), (
        "api_aegis_status still hardcodes grok_configured: False — "
        "this is the lie this fix targets."
    )


@pytest.mark.unit
def test_status_source_reads_gemini_api_key():
    body = _extract_status_function_source()
    assert "GEMINI_API_KEY" in body, (
        "api_aegis_status does not read GEMINI_API_KEY — gemini_configured "
        "cannot be honest without it."
    )


@pytest.mark.unit
def test_status_source_reads_xai_api_key_for_grok():
    """grok_configured must read XAI_API_KEY (the env name used by the
    upstream call in app/services/ai_translate.py::_call_xai_grok)."""
    body = _extract_status_function_source()
    assert "XAI_API_KEY" in body, (
        "api_aegis_status does not read XAI_API_KEY — grok_configured "
        "must mirror what _call_xai_grok actually consumes."
    )


@pytest.mark.unit
def test_status_source_both_blocks_patched():
    """Both the success block AND the except block must use the same
    real env-read pattern — not a placeholder in either."""
    body = _extract_status_function_source()
    # The pattern bool(os.environ.get("GEMINI_API_KEY"...)) must appear
    # in at least 2 places (success + except blocks).
    gemini_reads = len(re.findall(
        r'os\.environ\.get\(\s*["\']GEMINI_API_KEY["\']', body
    ))
    grok_reads = len(re.findall(
        r'os\.environ\.get\(\s*["\']XAI_API_KEY["\']', body
    ))
    assert gemini_reads >= 2, (
        f"GEMINI_API_KEY only read {gemini_reads}x in api_aegis_status; "
        "must be in both success block and except block."
    )
    assert grok_reads >= 2, (
        f"XAI_API_KEY only read {grok_reads}x in api_aegis_status; "
        "must be in both success block and except block."
    )


# ─── Integration tests (require factory_client) ───────────────────────────────


_EXPECTED_KEYS = {
    "ok",
    "gemini_configured",
    "grok_configured",
    "grok_ok",
    "grok_error",
    "groq_configured",
    "groq_ok",
    "groq_error",
    "claude_calls",
    "claude_limit",
    "groq_calls",
    "collector_last_run",
    "timestamp",
}


@pytest.fixture
def aegis_client(factory_client):
    return factory_client


def test_gemini_configured_true_when_key_set(monkeypatch, aegis_client):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    resp = aegis_client.get("/api/aegis/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None
    assert data["gemini_configured"] is True
    assert data["grok_configured"] is False
    assert data["groq_configured"] is False


def test_gemini_configured_false_when_key_absent(monkeypatch, aegis_client):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    resp = aegis_client.get("/api/aegis/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["gemini_configured"] is False


def test_gemini_configured_false_when_key_blank(monkeypatch, aegis_client):
    """Whitespace-only key counts as not-configured (same as groq pattern)."""
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    resp = aegis_client.get("/api/aegis/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["gemini_configured"] is False


def test_grok_configured_reads_xai_api_key(monkeypatch, aegis_client):
    """grok_configured must reflect XAI_API_KEY (xAI service env name),
    matching what app/services/ai_translate.py:_call_xai_grok reads."""
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    resp = aegis_client.get("/api/aegis/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["grok_configured"] is True
    assert data["gemini_configured"] is False


def test_payload_shape_unchanged(monkeypatch, aegis_client):
    """Relabel must not change the JSON envelope keys consumers depend on."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("XAI_API_KEY", "y")
    monkeypatch.setenv("GROQ_API_KEY", "z")
    resp = aegis_client.get("/api/aegis/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == _EXPECTED_KEYS, (
        f"missing: {_EXPECTED_KEYS - set(data.keys())}, "
        f"extra: {set(data.keys()) - _EXPECTED_KEYS}"
    )
