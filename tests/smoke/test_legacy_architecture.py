"""Tests de la nouvelle Application Factory + Blueprints."""
import pytest
import json
import sys
import os
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent.parent))


@pytest.fixture(scope='module')
def new_app():
    os.environ['TESTING'] = '1'
    os.environ['SENTRY_DSN'] = ''
    from app import create_app
    app = create_app("testing")
    app.config['TESTING'] = True
    return app


@pytest.fixture(scope='module')
def new_client(new_app):
    return new_app.test_client()


def test_factory_cree_app(new_app):
    assert new_app is not None
    assert new_app.config['TESTING'] is True


def test_blueprints_enregistres(new_app):
    blueprints = list(new_app.blueprints.keys())
    print("Blueprints:", blueprints)
    assert len(blueprints) >= 4


def test_sitemap_blueprint(new_client):
    resp = new_client.get('/sitemap.xml')
    assert resp.status_code == 200
    assert b'<urlset' in resp.data
    count = resp.data.count(b'<loc>')
    assert count >= 15, f"Seulement {count} URLs dans le sitemap"


def test_set_lang_blueprint(new_client):
    resp = new_client.get('/set-lang/en')
    assert resp.status_code == 302
    cookie = resp.headers.get('Set-Cookie', '')
    assert 'lang=en' in cookie


def test_a_propos_blueprint(new_client):
    resp = new_client.get('/a-propos')
    assert resp.status_code == 200


def test_about_alias_blueprint(new_client):
    resp = new_client.get('/about')
    assert resp.status_code == 200


def test_data_portal_blueprint(new_client):
    resp = new_client.get('/data')
    assert resp.status_code == 200


def test_api_spec_blueprint(new_client):
    resp = new_client.get('/api/spec.json')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['openapi'].startswith('3.')
    assert len(data['paths']) >= 10
    assert len(data['tags']) >= 6


def test_api_docs_blueprint(new_client):
    resp = new_client.get('/api/docs')
    assert resp.status_code == 200
    assert b'swagger' in resp.data.lower()


def test_export_visitors_csv_blueprint(new_client):
    resp = new_client.get('/api/export/visitors.csv')
    assert resp.status_code == 200
    text = resp.data.decode('utf-8')
    assert text.startswith('country,country_code')


def test_export_visitors_json_blueprint(new_client):
    resp = new_client.get('/api/export/visitors.json')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert 'metadata' in data
    assert 'CC BY 4.0' in data['metadata']['license']


def test_export_observations_blueprint(new_client):
    resp = new_client.get('/api/export/observations.json')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['metadata']['count'] > 0


def test_robots_txt_blueprint(new_client):
    resp = new_client.get('/robots.txt')
    assert resp.status_code == 200
