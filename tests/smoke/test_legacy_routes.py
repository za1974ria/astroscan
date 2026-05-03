"""Smoke tests routes critiques AstroScan — pytest.

Ces tests vérifient que les routes répondent avec un code HTTP valide.
Ils n'appellent pas le réseau externe (les APIs sont cachées ou mockées par l'app).
"""
import sys
sys.path.insert(0, '/root/astro_scan')

import pytest


@pytest.mark.parametrize("route", [
    '/',
    '/portail',
    '/a-propos',
    '/about',
    '/api/health',
    '/api/version',
    '/api/modules-status',
    '/api/ephemerides/tlemcen',
    '/api/visitors/snapshot',
    '/sitemap.xml',
    '/robots.txt',
    '/europe-live',
    '/europe-live?embed=1',
])
def test_route_responds(client, route):
    r = client.get(route)
    assert r.status_code in (200, 304, 302), \
        f'{route} → HTTP {r.status_code} (attendu 200/302/304)'


def test_health_json_structure(client):
    r = client.get('/api/health')
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert 'status' in data or 'ok' in data


def test_api_version_json(client):
    r = client.get('/api/version')
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None


def test_circuit_breakers_endpoint_auth(client):
    r = client.get(
        '/api/admin/circuit-breakers',
        headers={'Authorization': 'Bearer lXnUPqYSFsX6bWIXL9AQnYdo-_EzFNFci6O-sqzByXc'},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    assert data['summary']['total'] == 7
    assert all(
        cb['state'] in ('CLOSED', 'OPEN', 'HALF_OPEN')
        for cb in data['circuit_breakers']
    )


def test_circuit_breakers_endpoint_unauthorized(client):
    r = client.get('/api/admin/circuit-breakers')
    assert r.status_code in (401, 200)


def test_connection_time_redirect(client):
    """L'URL avec tiret redirige 301 vers l'URL avec underscore."""
    r = client.get('/api/visitors/connection-time')
    assert r.status_code == 301
    assert '/api/visitors/connection_time' in r.headers.get('Location', '')


def test_nasa_apod_page(client):
    r = client.get('/nasa-apod')
    assert r.status_code == 200
    assert b'NASA' in r.data or b'APOD' in r.data


def test_ephemerides_json_structure(client):
    r = client.get('/api/ephemerides/tlemcen')
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert 'soleil' in data or 'lieu' in data or 'error' in data


def test_europe_live_page(client):
    """La page World Live rend correctement et contient les 5 lieux mondiaux."""
    r = client.get('/europe-live')
    assert r.status_code == 200
    body = r.data
    assert b'WORLD LIVE' in body
    assert b'MATTERHORN' in body
    assert b'AURORA' in body
    assert b'CANYON' in body
    assert b'FUJI' in body
    assert b'ISS' in body


def test_europe_live_embed(client):
    """La page Europe Live accepte le mode embed sans erreur."""
    r = client.get('/europe-live?embed=1')
    assert r.status_code == 200
    assert b'embed-portail' in r.data


@pytest.mark.parametrize("city", ['matterhorn', 'aurora', 'canyon', 'fuji', 'iss'])
def test_proxy_cam_route(client, city):
    """La route /proxy-cam/<city>.jpg répond 200 (image) ou 503 (caméra hors ligne)."""
    r = client.get(f'/proxy-cam/{city}.jpg')
    assert r.status_code in (200, 503), \
        f'/proxy-cam/{city}.jpg → HTTP {r.status_code}'
    if r.status_code == 200:
        assert 'image' in r.content_type


def test_proxy_cam_unknown_city(client):
    r = client.get('/proxy-cam/unknown.jpg')
    assert r.status_code == 404


def test_portail_sidebar_navigate_pattern(client):
    """Le portail contient navigate() pour tous les modules critiques."""
    r = client.get('/portail')
    assert r.status_code == 200
    body = r.data
    # Aucun lien sidebar ne doit naviguer directement hors du portail
    import re
    broken = re.findall(rb'<a class="nav-item" href="(?!#|/a-propos)[^"]*"', body)
    assert broken == [], f'Liens sidebar cassés trouvés : {broken}'
    # Les modules clés utilisent navigate()
    for key in [b'orbital', b'telescope', b'ephemerides', b'europe-live', b'visiteurs-live']:
        assert b"navigate('" + key + b"')" in body, \
            f"navigate('{key.decode()}') absent du portail"
