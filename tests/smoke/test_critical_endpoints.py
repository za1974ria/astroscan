"""Smoke tests — the 11 critical production endpoints.

Mirrors the post-deploy smoke test in ``DEPLOYMENT.md §7``. Every endpoint
listed here MUST return HTTP 200 against the factory app — a single failure
is the ops trigger for a Level 1 rollback in production.
"""
from __future__ import annotations

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.integration]


CRITICAL_ENDPOINTS_200 = [
    "/",
    "/api/iss",
    "/api/health",
    "/portail",
    "/dashboard",
    "/api/apod",
    "/sitemap.xml",
    "/robots.txt",
    "/api/weather",
    "/api/satellites",
    "/api/system-status",
]


@pytest.mark.parametrize("route", CRITICAL_ENDPOINTS_200)
def test_critical_endpoint_returns_200(factory_client, route):
    resp = factory_client.get(route)
    # 304 (not-modified) is also acceptable on cacheable responses;
    # 302 only on legitimate redirects (none expected here).
    assert resp.status_code in (200, 304), (
        f"{route} → HTTP {resp.status_code} (expected 200/304)"
    )


def test_health_payload_has_status_field(factory_client):
    resp = factory_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None
    assert "status" in data or "ok" in data


def test_sitemap_contains_urls(factory_client):
    resp = factory_client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert b"<urlset" in resp.data
    assert resp.data.count(b"<loc>") >= 10


def test_robots_txt_is_text(factory_client):
    resp = factory_client.get("/robots.txt")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore").lower()
    assert "user-agent" in body or "sitemap" in body


def test_weather_payload_is_honestly_labelled(factory_client):
    """`/api/weather` is a single Open-Meteo call. The payload must NOT
    claim a multi-source / ECMWF validation that does not happen.

    Covers BOTH the success block and the fallback block (both build the
    same envelope with `source` and `mode`).
    """
    resp = factory_client.get("/api/weather")
    assert resp.status_code == 200, f"/api/weather -> HTTP {resp.status_code}"
    data = resp.get_json()
    assert data is not None, "/api/weather returned non-JSON body"

    # Envelope keys consumers rely on (relabel must NOT change the shape).
    for required_key in ("ok", "temp", "wind", "humidity", "pressure",
                         "condition", "source", "mode", "timestamp", "valid"):
        assert required_key in data, f"missing key {required_key!r} in /api/weather payload"

    # Honesty: no second source actually queried -> ECMWF must NOT be claimed.
    src = (data.get("source") or "").upper()
    assert "ECMWF" not in src, (
        f"/api/weather still claims ECMWF in source={data.get('source')!r} "
        "while only one Open-Meteo call is made"
    )

    # Honesty: no cross-validation actually performed.
    mode = (data.get("mode") or "").lower()
    assert "multi-source validated" not in mode, (
        f"/api/weather still labelled mode={data.get('mode')!r} "
        "while no cross-source validation happens"
    )
    assert "multi" not in mode, (
        f"/api/weather mode={data.get('mode')!r} still implies multiple sources"
    )
