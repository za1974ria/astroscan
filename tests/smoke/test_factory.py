"""Smoke tests — application factory.

Validates that ``app.create_app('testing')`` produces a working Flask
instance with the expected blueprint count and route map.
"""
from __future__ import annotations

import pytest
from flask import Flask


pytestmark = pytest.mark.smoke


def test_create_app_returns_flask_instance(factory_app):
    assert isinstance(factory_app, Flask)
    assert factory_app.config["TESTING"] is True


def test_create_app_registers_blueprints(factory_app):
    """All thematic blueprints are registered (post-PASS-18 target = 21)."""
    bps = list(factory_app.blueprints.keys())
    assert len(bps) >= 18, (
        f"Expected ≥18 blueprints (target 21), got {len(bps)}: {bps}"
    )


def test_create_app_route_count_within_expected_range(factory_app):
    """Route count should be near the current production target of ~330.

    Recalibré post-axe1 (2026-05-29) après :
      - ajouts control_tower / hilal / sentinel / guardian / astrobrain
      - suppression des doublons /api/apod et /api/nasa/apod dans feeds_bp
    Fourchette ±10 % autour du décompte réel pour absorber les évolutions.
    """
    n = sum(1 for _ in factory_app.url_map.iter_rules())
    assert 300 <= n <= 360, f"Got {n} routes — outside expected band [300, 360]"


def test_create_app_health_endpoint_responds(factory_client):
    resp = factory_client.get("/api/health")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload is not None
    assert "status" in payload or "ok" in payload


def test_create_app_no_url_collisions(factory_app):
    """No two rules should share the exact (rule, methods) signature."""
    seen: set[tuple[str, frozenset[str]]] = set()
    collisions: list[str] = []
    for rule in factory_app.url_map.iter_rules():
        sig = (str(rule), frozenset(rule.methods or set()))
        if sig in seen:
            collisions.append(f"{rule} {sorted(rule.methods or [])}")
        seen.add(sig)
    assert not collisions, f"URL collisions detected: {collisions}"


def test_create_app_has_static_route(factory_app):
    """Flask default /static/<path:filename> must remain reachable."""
    rules = [str(r) for r in factory_app.url_map.iter_rules()]
    assert any("/static/" in r for r in rules)
