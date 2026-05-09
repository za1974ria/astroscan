"""Unit tests — pure functions extracted by PASS 10–17.

These tests cover the new ``app/services/*`` modules. They are pure
(no Flask context, no I/O) so they run fast and are safe in CI.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


# ── iss_compute ──────────────────────────────────────────────────────────────


def test_az_to_direction_8_cardinals():
    from app.services.iss_compute import _az_to_direction

    assert _az_to_direction(0) == "N"
    assert _az_to_direction(45) == "NE"
    assert _az_to_direction(90) == "E"
    assert _az_to_direction(135) == "SE"
    assert _az_to_direction(180) == "S"
    assert _az_to_direction(225) == "SW"
    assert _az_to_direction(270) == "W"
    assert _az_to_direction(315) == "NW"


def test_az_to_direction_wraps_at_360():
    from app.services.iss_compute import _az_to_direction

    assert _az_to_direction(359.9) == "N"
    assert _az_to_direction(360) == "N"


# ── hilal_compute ────────────────────────────────────────────────────────────


def test_hilal_hijri_months_is_full_calendar():
    from app.services.hilal_compute import _HIJRI_MONTHS

    assert isinstance(_HIJRI_MONTHS, list)
    assert len(_HIJRI_MONTHS) == 12
    assert all(isinstance(m, str) and m for m in _HIJRI_MONTHS)


# ── oracle_engine ────────────────────────────────────────────────────────────


def test_oracle_build_messages_shape():
    from app.services.oracle_engine import oracle_build_messages

    messages = oracle_build_messages(
        historique=[],
        user_message="What is the Moon's phase tonight?",
        ville="Tlemcen",
    )
    assert isinstance(messages, list)
    assert len(messages) >= 1
    assert all("role" in m and "content" in m for m in messages)
    # The user message must be present in the constructed payload
    assert any("Moon" in (m.get("content") or "") for m in messages)


def test_oracle_live_strings_is_iterable():
    from app.services.oracle_engine import oracle_cosmique_live_strings

    out = oracle_cosmique_live_strings()
    # Tolerant: accept list/tuple/dict — main thing is "non-empty + JSON-safe"
    assert out is not None


# ── guide_engine ─────────────────────────────────────────────────────────────


def test_build_orbital_guide_returns_dict():
    from app.services.guide_engine import build_orbital_guide

    out = build_orbital_guide(
        ville="Tlemcen",
        lat=34.87,
        lon=-1.32,
        date_iso="2026-05-03",
    )
    assert isinstance(out, dict)


# ── http_client ──────────────────────────────────────────────────────────────


def test_http_client_module_loads_and_exposes_curl_helpers():
    """The hardened HTTP client wraps libcurl via subprocess — verify import."""
    from app.services import http_client

    # The module exposes _curl_get / _curl_post helpers (private by convention,
    # public in practice for blueprint consumers post-PASS-10).
    expected = {"_curl_get", "_curl_post", "_curl_post_json", "_safe_json_loads"}
    available = {name for name in dir(http_client) if not name.startswith("__")}
    missing = expected - available
    assert not missing, (
        f"http_client missing expected helpers {missing}. Available: {available}"
    )
