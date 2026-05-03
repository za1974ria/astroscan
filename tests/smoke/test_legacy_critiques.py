"""Tests des routes critiques AstroScan — smoke tests."""
import pytest

ROUTES_200 = [
    '/portail',
    '/observatoire',
    '/a-propos',
    '/about',
    '/data',
    '/api/docs',
    '/api/spec.json',
    '/sitemap.xml',
    '/robots.txt',
    '/en/portail',
    '/api/export/visitors.csv',
    '/api/export/visitors.json',
    '/api/export/ephemerides.json',
    '/api/export/observations.json',
    '/api/health',
]

@pytest.mark.parametrize("route", ROUTES_200)
def test_route_returns_200(client, route):
    """Vérifie que chaque route critique retourne 200."""
    resp = client.get(route)
    assert resp.status_code == 200, f"{route} → {resp.status_code}"

def test_sitemap_contient_urls(client):
    resp = client.get('/sitemap.xml')
    assert b'<loc>' in resp.data
    assert resp.data.count(b'<loc>') >= 10

def test_api_spec_json_valide(client):
    import json
    resp = client.get('/api/spec.json')
    data = json.loads(resp.data)
    assert data['openapi'].startswith('3.')
    assert 'paths' in data
    assert len(data['paths']) >= 10

def test_export_visitors_csv_format(client):
    resp = client.get('/api/export/visitors.csv')
    text = resp.data.decode('utf-8')
    assert text.startswith('country,country_code,visits')

def test_export_visitors_json_metadata(client):
    import json
    resp = client.get('/api/export/visitors.json')
    data = json.loads(resp.data)
    assert 'metadata' in data
    assert 'CC BY 4.0' in data['metadata']['license']
    assert 'data' in data

def test_api_docs_swagger_ui(client):
    resp = client.get('/api/docs')
    assert b'swagger' in resp.data.lower()

def test_a_propos_contient_contact(client):
    resp = client.get('/a-propos')
    assert b'zakaria.chohra@gmail.com' in resp.data

def test_set_lang_redirect(client):
    resp = client.get('/set-lang/en')
    assert resp.status_code == 302

def test_en_portail_retourne_200(client):
    resp = client.get('/en/portail')
    assert resp.status_code == 200
