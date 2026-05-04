"""Blueprint System — admin / sync / data système (slim post-PASS 4 phase 2C).

Routes (6, après split health → app/blueprints/health/) :
  - /api/tle/refresh         : refresh TLE manuel
  - /api/latest              : dernières observations
  - /api/sync/state (GET)    : lecture source télescope partagée
  - /api/sync/state (POST)   : écriture source télescope partagée
  - /api/telescope/sources   : liste sources sélectionnables
  - /api/dsn                 : DSN NASA (snapshot data_core)

Les routes health/monitoring (/health, /api/health, /selftest, /status,
/stream/status, /api/system-*) ont été déplacées vers health_bp.
La route /api/accuracy/export.csv a été déplacée vers export_bp (bp_global).
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("system_bp", __name__)


@bp.route('/api/tle/refresh', methods=['POST'])
def api_tle_refresh():
    """Déclenche un rafraîchissement manuel des TLE."""
    try:
        import station_web as _sw
        ok = _sw.fetch_tle_from_celestrak()
        return jsonify({
            "ok": bool(ok),
            "status": _sw.TLE_CACHE.get("status"),
            "count": _sw.TLE_CACHE.get("count"),
            "last_refresh_iso": _sw.TLE_CACHE.get("last_refresh_iso"),
            "error": _sw.TLE_CACHE.get("error"),
        })
    except Exception as e:
        log.warning("/api/tle/refresh: %s", e)
        return jsonify({"ok": False, "error": str(e)})


@bp.route('/api/latest')
def api_latest():
    """Dernières observations — liste paginable avec support i18n."""
    lang = request.args.get('lang', 'fr').lower()
    try:
        import station_web as _sw
        conn = _sw.get_db()
        cur = conn.cursor()
        total     = cur.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anomalies = cur.execute("SELECT COUNT(*) FROM observations WHERE anomalie=1").fetchone()[0]
        sources   = cur.execute("SELECT COUNT(DISTINCT source) FROM observations").fetchone()[0]
        try:
            req_j = cur.execute(
                "SELECT COUNT(*) FROM observations WHERE date(timestamp)=date('now')"
            ).fetchone()[0]
        except Exception:
            req_j = 0
        try:
            limit_arg = request.args.get('limit', '20')
            limit = min(200, max(1, int(limit_arg))) if str(limit_arg).isdigit() else 20
        except Exception:
            limit = 20
        try:
            rows = cur.execute(
                "SELECT id, timestamp, source, analyse_gemini, analyse_gemini as rapport_gemini, "
                "COALESCE(rapport_fr,'') as rapport_fr, objets_detectes, anomalie, "
                "COALESCE(title,'') as title, COALESCE(objets_detectes,'') as type_objet, "
                "COALESCE(score_confiance,0.0) as confidence "
                "FROM observations ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        except Exception:
            rows = cur.execute(
                "SELECT id, timestamp, source, analyse_gemini, analyse_gemini as rapport_gemini, "
                "'' as rapport_fr, objets_detectes, anomalie, "
                "'' as title, '' as type_objet, 0.0 as confidence "
                "FROM observations ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        conn.close()
        obs_list = []
        for row in rows:
            r = dict(row)
            raw = r.get('rapport_gemini') or r.get('analyse_gemini') or ''
            if lang == 'fr':
                fr = (r.get('rapport_fr') or '').strip()
                r['rapport_gemini'] = fr if fr else raw
            else:
                r['rapport_gemini'] = raw
            r['rapport_display'] = r['rapport_gemini']
            obs_list.append(r)
        return jsonify({
            'ok': True, 'total': total, 'anomalies': anomalies,
            'sources': sources, 'telescopes': 9, 'req_jour': req_j,
            'observations': obs_list,
            'notice': 'Analyses AEGIS',
        })
    except Exception as e:
        log.error("api_latest: %s", e)
        return jsonify({'ok': False, 'error': str(e), 'total': 0, 'observations': []})


@bp.route('/api/sync/state', methods=['GET'])
def api_sync_state_get():
    """État canonique partagé (PC + Android) : source télescope affichée."""
    import station_web as _sw
    return jsonify({'ok': True, 'source': _sw._sync_state_read()})


@bp.route('/api/sync/state', methods=['POST'])
def api_sync_state_post():
    """Met à jour l'état partagé (quand un client change la source)."""
    import station_web as _sw
    try:
        data = request.get_json(force=True, silent=True) or {}
        source = data.get('source') or request.form.get('source') or 'live'
    except Exception:
        source = 'live'
    s = _sw._sync_state_write(source)
    return jsonify({'ok': True, 'source': s})


@bp.route('/api/telescope/sources')
def api_telescope_sources():
    """Liste des sources live sélectionnables."""
    return jsonify({
        'ok': True,
        'sources': [
            {'id': 'live',         'name': 'Flux principal',      'desc': 'Dernière image du pipeline (feeder)',     'icon': '📡'},
            {'id': 'apod',         'name': 'NASA APOD',            'desc': 'Image du jour — temps 0',                 'icon': '🔭'},
            {'id': 'hubble',       'name': 'ESA Hubble',           'desc': 'Archives Hubble — temps 0',               'icon': '🌌'},
            {'id': 'apod_archive', 'name': 'NASA APOD (archive)',  'desc': 'Image aléatoire 2015–2024',               'icon': '📁'},
        ]
    })


# ── PASS 11 — DSN (Deep Space Network NASA) ───────────────────────────
@bp.route("/api/dsn")
def api_dsn():
    """DSN : fetch NASA + snapshot data_core/dsn/ + fallback."""
    from app.config import STATION as _STATION
    try:
        from core import dsn_engine_safe as _dsn
        return jsonify(_dsn.get_dsn_safe(_STATION))
    except Exception as e:
        log.warning("api/dsn: %s", e)
        try:
            from core import dsn_engine_safe as _dsn
            return jsonify(_dsn.build_dsn_fallback_payload())
        except Exception:
            return jsonify({
                "stations": [
                    {"friendlyName": "Goldstone (USA)", "name": "GDS", "dishes": []},
                    {"friendlyName": "Madrid (Spain)", "name": "MDS", "dishes": []},
                    {"friendlyName": "Canberra (Australia)", "name": "CDS", "dishes": []},
                ],
                "status": "fallback",
            })
