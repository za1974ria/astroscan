"""Tests de la nouvelle Application Factory + Blueprints."""

import json
import os
import sys
from pathlib import Path as _Path
from pathlib import Path as _Path_helper

import pytest

# PASS 2D fix (2026-05-07) — skip data-dependent tests if SQLite DBs are absent (e.g. CI).
_DATA_DIR = _Path_helper(__file__).resolve().parent.parent.parent / "data"


def _skip_if_db_missing(db_name):
    """Skip the current test if the SQLite DB file is not present in data/."""
    db_path = _DATA_DIR / db_name
    if not db_path.exists():
        pytest.skip(f"{db_path} not present (CI environment) — requires integration data")


sys.path.insert(0, str(_Path(__file__).resolve().parent.parent.parent))


@pytest.fixture(scope="module")
def new_app():
    os.environ["TESTING"] = "1"
    os.environ["SENTRY_DSN"] = ""
    try:
        from app import create_app
    except (PermissionError, OSError) as exc:
        pytest.skip(f"create_app could not load: {exc}")
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


def _data_dir_writable():
    """Visitor logging in request hooks writes to data/*.db. In dev where
    data/ is root-owned, route tests cannot run. In CI/prod (fresh checkout
    or root) they pass normally."""
    return os.access(_DATA_DIR, os.W_OK)


@pytest.fixture(autouse=True)
def _skip_if_db_readonly(request):
    if request.node.name not in ("test_factory_cree_app", "test_blueprints_enregistres"):
        if not _data_dir_writable():
            pytest.skip("data/ not writable by current user (visitor DB logger requires write)")


@pytest.fixture(scope="module")
def new_client(new_app):
    return new_app.test_client()


def test_factory_cree_app(new_app):
    assert new_app is not None
    assert new_app.config["TESTING"] is True


def test_blueprints_enregistres(new_app):
    blueprints = list(new_app.blueprints.keys())
    print("Blueprints:", blueprints)
    assert len(blueprints) >= 4


def test_sitemap_blueprint(new_client):
    resp = new_client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert b"<urlset" in resp.data
    count = resp.data.count(b"<loc>")
    assert count >= 15, f"Seulement {count} URLs dans le sitemap"


def test_set_lang_blueprint(new_client):
    resp = new_client.get("/set-lang/en")
    assert resp.status_code == 302
    cookie = resp.headers.get("Set-Cookie", "")
    assert "lang=en" in cookie


def test_a_propos_blueprint(new_client):
    resp = new_client.get("/a-propos")
    assert resp.status_code == 200


def test_about_alias_blueprint(new_client):
    resp = new_client.get("/about")
    assert resp.status_code == 200


def test_data_portal_blueprint(new_client):
    resp = new_client.get("/data")
    assert resp.status_code == 200


def test_api_spec_blueprint(new_client):
    resp = new_client.get("/api/spec.json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["openapi"].startswith("3.")
    assert len(data["paths"]) >= 10
    assert len(data["tags"]) >= 6


def test_api_docs_blueprint(new_client):
    resp = new_client.get("/api/docs")
    assert resp.status_code == 200
    assert b"swagger" in resp.data.lower()


def test_export_visitors_csv_blueprint(new_client):
    _skip_if_db_missing("visitors.db")
    resp = new_client.get("/api/export/visitors.csv")
    assert resp.status_code == 200
    text = resp.data.decode("utf-8")
    assert text.startswith("country,country_code")


def test_export_visitors_json_blueprint(new_client):
    _skip_if_db_missing("visitors.db")
    resp = new_client.get("/api/export/visitors.json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "metadata" in data
    assert "CC BY 4.0" in data["metadata"]["license"]


def test_export_observations_blueprint(new_client):
    _skip_if_db_missing("astroscan.db")
    resp = new_client.get("/api/export/observations.json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["metadata"]["count"] > 0


def test_robots_txt_blueprint(new_client):
    resp = new_client.get("/robots.txt")
    assert resp.status_code == 200


def test_methodology_page_smoke(new_client):
    """Axe 1 — /methodology must render with ESA-relevant keywords.

    The page is the public engineering narrative for ESA / NASA / CNES
    reviewers; the content is locked at the SEO meta layer."""
    resp = new_client.get("/methodology")
    assert resp.status_code == 200
    body = resp.data.lower()
    assert b"methodology" in body


def test_sentinel_health_smoke(new_client):
    """Axe 1 — /api/sentinel/health returns the public health envelope."""
    resp = new_client.get("/api/sentinel/health")
    assert resp.status_code in (200, 503)
    data = json.loads(resp.data)
    if resp.status_code == 200:
        assert data.get("ok") is True
        assert data.get("module") == "astroscan_sentinel"
        assert "max_ttl_seconds" in data
