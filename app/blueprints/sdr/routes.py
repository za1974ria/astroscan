"""Blueprint SDR — routes /api/sdr/status, /api/sdr/stations,
/orbital-radio, /api/sdr/passes

Extrait de station_web.py lors de la PHASE 2B / Étape B2 (2026-05-02).

La route /api/sdr/captures reste dans station_web.py car elle dépend
de get_db() (helper monolithe). À migrer dans une étape ultérieure
(B-db) après extraction du module DB.
"""
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from flask import Blueprint, jsonify, render_template
from app.routes.sdr import api_sdr_passes_impl

sdr_bp = Blueprint('sdr', __name__)
log = logging.getLogger(__name__)

# Constante hardcodée — cohérence avec station_web.py L.167
# TODO B-config futur : centraliser dans app/config.py
_STATION = '/root/astro_scan'
# Doublon documenté avec station_web.py L.429 — à centraliser en B-config
_SDR_F = os.path.join(_STATION, 'data', 'sdr_status.json')


@sdr_bp.route('/api/sdr/status')
def api_sdr_status():
    if Path(_SDR_F).exists():
        try:
            return jsonify(json.load(open(_SDR_F)))
        except Exception:
            pass
    return jsonify({'ok': True, 'status': 'standby', 'last_capture': None})


@sdr_bp.route('/api/sdr/stations')
def api_sdr_stations():
    return jsonify({'ok': True, 'stations': [
        {'name': 'Univ. Twente',   'country': 'Pays-Bas', 'flag': '🇳🇱', 'status': 'online', 'freq': '137MHz'},
        {'name': 'Rome IK0SMG',    'country': 'Italie',   'flag': '🇮🇹', 'status': 'online', 'freq': '137MHz'},
        {'name': 'Bordeaux F5SWN', 'country': 'France',   'flag': '🇫🇷', 'status': 'online', 'freq': '137MHz'},
        {'name': 'Madrid EA4RCU',  'country': 'Espagne',  'flag': '🇪🇸', 'status': 'online', 'freq': '137MHz'},
    ]})


@sdr_bp.route('/orbital-radio')
def orbital_radio():
    return render_template('orbital_radio.html')


@sdr_bp.route('/api/sdr/passes')
def api_sdr_passes():
    return api_sdr_passes_impl(
        jsonify=jsonify,
        STATION=_STATION,
        Path=Path,
        json_module=json,
        time_module=time,
        subprocess_module=subprocess,
        log=log,
    )


# ── PASS 14 — SDR captures (différé PASS 2B levé — DB extraite via app.utils.db) ──
@sdr_bp.route("/api/sdr/captures")
def api_sdr_captures():
    """Liste des captures SDR/NOAA depuis la DB d'observations."""
    try:
        from app.utils.db import get_db
        conn = get_db()
        rows = conn.execute(
            "SELECT id, timestamp, source, COALESCE(title,'') as title "
            "FROM observations WHERE source LIKE '%SDR%' OR source LIKE '%NOAA%' "
            "ORDER BY id DESC LIMIT 10"
        ).fetchall()
        return jsonify({"ok": True, "captures": [dict(r) for r in rows]})
    except Exception as e:
        log.warning("api/sdr/captures: %s", e)
        return jsonify({"ok": False, "captures": []})
