"""Smoke tests prod-safe — frappe le service live via HTTP.

Lance par défaut contre `http://127.0.0.1:5003`. Override possible :
    ASTROSCAN_BASE_URL=https://astroscan.space pytest tests/test_smoke_prod.py

Caractéristiques :
- Lecture seule (GET uniquement, aucune mutation persistante).
- Aucune dépendance hors stdlib (`urllib.request`, `json`, `socket`).
- Timeout court (3s par requête) — l'exécution complète tient sous 15s.
- Auto-skip si le service n'est pas joignable (utile en CI/local sans prod).
- Marker `prod_smoke` pour exécution sélective :
    pytest -m prod_smoke
    pytest -m "not prod_smoke"     # skip en CI sans prod

Critère succès : 0 échec → service sain. Tout échec = signal de rollback.
"""
from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

import pytest

BASE_URL = os.environ.get("ASTROSCAN_BASE_URL", "http://127.0.0.1:5003").rstrip("/")
TIMEOUT_S = float(os.environ.get("ASTROSCAN_SMOKE_TIMEOUT", "3"))

pytestmark = pytest.mark.prod_smoke


# ─── helpers stdlib ──────────────────────────────────────────────────────────


def _http_get(path: str, headers: dict | None = None, timeout: float | None = None):
    """GET path → (status, headers_dict, body_bytes). Raises only on socket-level errors."""
    url = BASE_URL + path
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout or TIMEOUT_S) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), (e.read() if hasattr(e, "read") else b"")


def _service_alive() -> bool:
    try:
        host = BASE_URL.split("://", 1)[1].split("/", 1)[0]
        if ":" in host:
            h, p = host.rsplit(":", 1)
            port = int(p)
        else:
            h, port = host, (443 if BASE_URL.startswith("https") else 80)
        with socket.create_connection((h, port), timeout=1.5):
            return True
    except (OSError, ValueError):
        return False


@pytest.fixture(scope="session", autouse=True)
def _skip_if_no_service():
    if not _service_alive():
        pytest.skip(
            f"ASTROSCAN_BASE_URL={BASE_URL} unreachable — skipping prod smoke suite. "
            "Override with ASTROSCAN_BASE_URL=... if needed."
        )


# ─── tests endpoints publics ──────────────────────────────────────────────────


def test_root_returns_200():
    status, _, _ = _http_get("/")
    assert status == 200, f"GET / → {status}"


def test_portail_returns_200():
    status, _, _ = _http_get("/portail")
    assert status == 200, f"GET /portail → {status}"


def test_analytics_returns_200():
    status, _, _ = _http_get("/analytics")
    assert status == 200, f"GET /analytics → {status}"


# ─── tests health ─────────────────────────────────────────────────────────────


def test_health_returns_200_with_ok():
    status, _, body = _http_get("/health")
    assert status == 200, f"GET /health → {status}"
    data = json.loads(body)
    # /health expose status:'ok' ET ok n'est pas direct ; on tolère les deux schémas.
    assert data.get("status") == "ok" or data.get("ok") is True, (
        f"health payload missing status/ok: {data}"
    )


def test_api_health_returns_200_with_status_ok():
    status, _, body = _http_get("/api/health")
    assert status == 200, f"GET /api/health → {status}"
    data = json.loads(body)
    op = data.get("operational") or {}
    assert op.get("status") == "ok" or data.get("ok") is True, (
        f"/api/health not OK: status={op.get('status')} ok={data.get('ok')}"
    )
    # SQLite explicitement OK est non-négociable.
    if "sqlite" in op:
        assert op["sqlite"] == "ok", f"/api/health.operational.sqlite != ok ({op['sqlite']})"


# ─── test visiteurs ───────────────────────────────────────────────────────────


def test_api_visits_returns_valid_json_with_count():
    status, _, body = _http_get("/api/visits")
    assert status == 200, f"GET /api/visits → {status}"
    data = json.loads(body)
    assert "count" in data, f"/api/visits missing 'count': {data}"
    assert isinstance(data["count"], int) and data["count"] >= 0


# ─── test sécurité admin (CRITIQUE — jamais 200 sans auth) ────────────────────


def test_admin_circuit_breakers_requires_auth():
    status, _, _ = _http_get("/api/admin/circuit-breakers")
    assert status in (401, 503), (
        f"SECURITY REGRESSION: /api/admin/circuit-breakers without auth → {status} "
        "(expected 401 if token configured, 503 if not). Endpoint must NEVER be 200 unauth."
    )


def test_admin_circuit_breakers_rejects_bad_token():
    status, _, _ = _http_get(
        "/api/admin/circuit-breakers",
        headers={"Authorization": "Bearer obviously-wrong-token-xxx"},
    )
    assert status in (401, 503), (
        f"SECURITY REGRESSION: bad token → {status} (expected 401/503)"
    )


# ─── test guardian (singleton + discipline) ───────────────────────────────────


def test_guardian_health_valid():
    status, _, body = _http_get("/api/guardian/health")
    # /api/guardian/* sont @require_localhost — accessible depuis 127.0.0.1.
    if status == 403:
        pytest.skip("Guardian endpoints require localhost — test base URL not local")
    assert status == 200, f"GET /api/guardian/health → {status}"
    data = json.loads(body)
    assert data.get("ok") is True
    assert data.get("module") == "guardian"
    # Champs singleton CHANTIER 5B exposés ; tolère versions antérieures.
    if "is_leader" in data:
        assert isinstance(data["is_leader"], bool)
        assert "worker_pid" in data
        assert "lock_path" in data
        if data.get("started"):
            assert data.get("thread_alive") is True


def test_guardian_leader_pid_consistent():
    """Sur plusieurs appels (workers distincts gunicorn), le leader_pid annoncé
    doit être stable (cross-worker singleton)."""
    leader_pids = set()
    seen_leader = False
    for _ in range(8):
        status, _, body = _http_get("/api/guardian/health")
        if status != 200:
            pytest.skip(f"guardian unreachable status={status}")
        d = json.loads(body)
        if "leader_pid" in d and d["leader_pid"] is not None:
            leader_pids.add(d["leader_pid"])
        if d.get("is_leader"):
            seen_leader = True
    # Si exposé, doit être unique sur l'horizon de test.
    if leader_pids:
        assert len(leader_pids) == 1, (
            f"SINGLETON REGRESSION: multiple leader_pids observed: {leader_pids}"
        )


# ─── tests headers sécurité ───────────────────────────────────────────────────


def test_html_response_has_csp_and_nosniff():
    _, headers, _ = _http_get("/analytics")
    headers_low = {k.lower(): v for k, v in headers.items()}
    assert "content-security-policy" in headers_low, "CSP header missing on HTML"
    assert headers_low.get("x-content-type-options", "").lower() == "nosniff"


def test_session_cookie_is_httponly():
    _, headers, _ = _http_get("/")
    sc = headers.get("Set-Cookie") or headers.get("set-cookie") or ""
    if "astroscan_sid" not in sc:
        pytest.skip("no astroscan_sid cookie set — endpoint may bypass session hook")
    assert "HttpOnly" in sc, f"cookie missing HttpOnly: {sc}"
    assert "SameSite=Lax" in sc, f"cookie missing SameSite=Lax: {sc}"
