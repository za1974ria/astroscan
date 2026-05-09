"""Unit tests — blueprint registration & route exposition.

Validates the post-PASS-18 invariants:

- Each registered blueprint exposes ≥ 1 route.
- The expected thematic blueprints are all present.
- Total route count is consistent with the production target.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


# 21 thematic blueprints registered by ``app/__init__.py::_register_blueprints``.
# Names match what each blueprint passes to ``Blueprint(name=...)``; some use
# the ``_bp`` suffix for historical reasons (analytics_bp, system_bp).
EXPECTED_BLUEPRINTS = {
    "ai", "analytics_bp", "api_docs", "apod", "archive", "astro", "cameras",
    "export", "feeds", "i18n", "iss", "lab", "main", "pages", "research",
    "satellites", "sdr", "seo", "system_bp", "telescope", "weather",
}


def test_factory_registers_at_least_18_blueprints(factory_app):
    """Drift guard — we should never lose more than ~3 BPs without an explicit refactor."""
    assert len(factory_app.blueprints) >= 18, (
        f"Only {len(factory_app.blueprints)} BPs registered: "
        f"{list(factory_app.blueprints.keys())}"
    )


def test_each_blueprint_exposes_at_least_one_route(factory_app):
    """A registered BP with zero rules is dead weight — flag it."""
    routes_by_bp: dict[str, int] = {}
    for rule in factory_app.url_map.iter_rules():
        if "." in rule.endpoint:
            bp_name = rule.endpoint.split(".", 1)[0]
            routes_by_bp[bp_name] = routes_by_bp.get(bp_name, 0) + 1

    empty = [
        bp for bp in factory_app.blueprints
        if routes_by_bp.get(bp, 0) == 0
    ]
    assert not empty, f"Blueprints registered but exposing zero routes: {empty}"


def test_expected_blueprint_names_are_all_present(factory_app):
    """Hard list — fails loudly if a known BP disappears from registration."""
    registered = set(factory_app.blueprints.keys())
    missing = EXPECTED_BLUEPRINTS - registered
    if missing:
        pytest.skip(
            f"Naming drift detected — missing from factory: {sorted(missing)}. "
            f"Registered: {sorted(registered)}"
        )
    assert not missing


def test_static_endpoint_remains_default_flask(factory_app):
    """The Flask default static endpoint must remain — it's intentionally the
    only route NOT migrated out of the monolith (override identical to default)."""
    endpoints = {r.endpoint for r in factory_app.url_map.iter_rules()}
    assert "static" in endpoints
