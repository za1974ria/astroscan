"""Tests des endpoints API JSON."""
import json
import sqlite3

import pytest  # noqa: F401  — kept for parity with existing markers


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
    """End-to-end: insert one observation, export, verify it surfaces.

    Avant fix_obs_test, le test assertait ``count > 0`` en présupposant que
    la DB contenait déjà des observations seed-loaded — vrai sur la DB de
    dev, faux en CI sur une DB vierge (after fix_dbinit la table existe mais
    elle est vide). Le test est désormais autonome : il insère un sentinelle
    via le même DB_PATH que l'endpoint, vérifie le bout-en-bout
    (insertion → export → présence dans le JSON), puis nettoie.
    """
    from app.services.paths import DB_PATH

    sentinel = "test_observations_export_count_sentinel"
    sentinel_ts = "2026-05-29T11:11:11Z"

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO observations (timestamp, source, title, objets_detectes,"
            " anomalie, score_confiance, analyse_gemini)"
            " VALUES (?,?,?,?,?,?,?)",
            (sentinel_ts, sentinel, sentinel, "n/a", 0, 0.0, "n/a"),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        resp = client.get('/api/export/observations.json')
        assert resp.status_code == 200
        data = json.loads(resp.data)

        # API shape contract (independent of pre-existing rows).
        assert isinstance(data, dict)
        assert 'metadata' in data and 'data' in data
        meta = data['metadata']
        assert isinstance(meta, dict)
        assert 'count' in meta and isinstance(meta['count'], int)
        assert meta['count'] == len(data['data'])
        assert meta['source'] == 'AstroScan-Chohra'
        assert 'license' in meta and 'generated_at' in meta

        # End-to-end proof: the row we just inserted surfaces in the export.
        rows = data['data']
        assert meta['count'] >= 1
        sentinel_rows = [r for r in rows if r.get('source') == sentinel]
        assert sentinel_rows, "inserted sentinel observation not surfaced by export"
        s = sentinel_rows[0]
        for required in (
            'id', 'timestamp', 'source', 'objects_detected',
            'anomaly', 'confidence_score', 'ai_analysis',
        ):
            assert required in s, f"export schema missing key: {required}"
        assert s['timestamp'] == sentinel_ts
    finally:
        # Cleanup: avoid polluting the dev DB across runs.
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                "DELETE FROM observations WHERE source = ? AND timestamp = ?",
                (sentinel, sentinel_ts),
            )
            conn.commit()
        finally:
            conn.close()
