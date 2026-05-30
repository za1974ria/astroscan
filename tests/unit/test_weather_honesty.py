"""Unit tests — /api/weather honesty (static source check).

The /api/weather route in app/blueprints/weather/__init__.py issues a SINGLE
call to api.open-meteo.com (no &models= parameter, no second source, no
validation). It therefore must NOT claim ECMWF nor a multi-source validation
in the JSON envelope.

These tests are static (read the source file) so they pass even when the
factory_app fixture skips for environmental reasons (e.g. data/ not writable
locally). They complement the integration assertion in
tests/smoke/test_critical_endpoints.py::test_weather_payload_is_honestly_labelled.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


WEATHER_BP = (
    Path(__file__).resolve().parents[2]
    / "app" / "blueprints" / "weather" / "__init__.py"
)


def _extract_api_weather_function_source() -> str:
    """Return the source of the api_weather_alias function (route /api/weather)."""
    tree = ast.parse(WEATHER_BP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "api_weather_alias":
            return ast.get_source_segment(WEATHER_BP.read_text(encoding="utf-8"), node) or ""
    pytest.fail("api_weather_alias not found in weather blueprint")


def test_weather_blueprint_file_exists():
    assert WEATHER_BP.is_file(), f"missing {WEATHER_BP}"


def test_api_weather_does_not_claim_ecmwf():
    """The function body must not embed an "ECMWF" source label."""
    body = _extract_api_weather_function_source()
    # Allow "ECMWF" to appear nowhere in the function body of api_weather_alias.
    # (Other functions in the same file may legitimately list ECMWF in a PDF
    # bulletin that documents Open-Meteo's underlying global models.)
    assert "ECMWF" not in body, (
        "api_weather_alias still references ECMWF in its payload while only "
        "Open-Meteo is queried (single source). Found in:\n" + body
    )


def test_api_weather_mode_is_single_source():
    """The function body must not claim multi-source validation."""
    body = _extract_api_weather_function_source()
    forbidden = [
        "multi-source validated",
        "multi-source",
        "multi_source",
        "cross-validated",
        "cross_validated",
    ]
    for needle in forbidden:
        assert needle not in body, (
            f"api_weather_alias still claims {needle!r} in its payload — "
            "no cross-source validation actually happens"
        )


def test_api_weather_emits_required_envelope_keys():
    """Relabel must NOT change the shape of the JSON envelope.

    Both the success block (~l.248) and the fallback block (~l.273) build a
    jsonify({...}) call that must include the keys consumers may depend on.
    """
    body = _extract_api_weather_function_source()
    expected_keys = [
        '"ok"', '"temp"', '"wind"', '"humidity"', '"pressure"', '"condition"',
        '"source"', '"mode"', '"timestamp"', '"valid"',
    ]
    for key in expected_keys:
        # Each key must appear at least TWICE — once in the success block,
        # once in the fallback block.
        assert body.count(key) >= 2, (
            f"key {key} appears {body.count(key)}x in api_weather_alias — "
            "expected >= 2 (success block + fallback block)"
        )


def test_api_weather_url_is_still_single_open_meteo_call():
    """Defensive: confirm that the route still hits exactly ONE Open-Meteo URL.

    If a future patch adds a real second source, this test will fail and the
    relabel above should be reconsidered (lifted, not extended).
    """
    body = _extract_api_weather_function_source()
    open_meteo_hits = len(re.findall(r"api\.open-meteo\.com", body))
    assert open_meteo_hits == 1, (
        f"api_weather_alias now contains {open_meteo_hits} Open-Meteo URLs. "
        "If a second source was wired, lift the single-source label."
    )
    # And no other HTTP host is referenced inside the function body.
    other_http = re.findall(r"https?://(?!api\.open-meteo\.com)[^\s\"']+", body)
    assert other_http == [], (
        f"api_weather_alias references non-Open-Meteo URLs: {other_http} — "
        "if these are real sources, relabel honestly."
    )
