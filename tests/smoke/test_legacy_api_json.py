"""Tests des endpoints API JSON."""
import pytest
import json

def test_ephemerides_tlemcen(client):
    resp = client.get('/api/ephemerides/tlemcen')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert 'soleil' in data or 'error' in data

def test_visitors_snapshot(client):
    resp = client.get('/api/visitors/snapshot')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert 'total' in data
    assert 'top_countries' in data

def test_api_health(client):
    resp = client.get('/api/health')
    assert resp.status_code == 200

def test_observations_export_count(client):
    resp = client.get('/api/export/observations.json')
    data = json.loads(resp.data)
    assert data['metadata']['count'] > 0
