"""Blueprint System — endpoints de monitoring et statut systeme.

Endpoints :
  - /api/system-status         : statut general
  - /api/system-alerts         : alertes via core.alert_engine
  - /api/system-notifications  : notifications via core.notification_engine

Migration depuis station_web.py (CTO Critique 3 - Monolith reduction).
"""

import logging
import json
import os
import sqlite3
import time

from flask import Blueprint, Response, jsonify, request
from flask import stream_with_context

log = logging.getLogger(__name__)

bp = Blueprint("system_bp", __name__)


@bp.route("/api/system-status")
def api_system_status():
    """Mode demo stable : statut systeme force ONLINE."""
    return jsonify({
        "ok": True,
        "status": "online",
        "master": "ONLINE",
        "aegis": "ACTIVE",
        "modules": "ALL_OPERATIONAL",
    })


@bp.route("/api/system-alerts")
def api_system_alerts():
    """Alertes basees sur le cache systeme uniquement (core/alert_engine)."""
    from station_web import STATION
    try:
        from core import alert_engine as _alerts
        return jsonify(_alerts.analyze_system_alerts(STATION))
    except Exception as e:
        log.warning("api/system-alerts: %s", e)
        return jsonify({
            "alerts": [
                {"level": "critical", "message": "Alert engine failure"},
            ],
            "count": 1,
            "global_status": "unknown",
        }), 500


@bp.route("/api/system-notifications")
def api_system_notifications():
    """Notifications derivees d'alert_engine uniquement (core/notification_engine)."""
    from station_web import STATION
    try:
        from core import notification_engine as _notify
        return jsonify(_notify.check_and_notify(STATION))
    except Exception as e:
        log.warning("api/system-notifications: %s", e)
        return jsonify({"notifications": [], "count": 0, "error": str(e)}), 500



@bp.route("/api/system/server-info")
def server_info():
    """Server infrastructure metadata (Hetzner Hillsboro Oregon US-West)."""
    return jsonify({
        "ip": "5.78.153.17",
        "provider": "Hetzner",
        "status": "ONLINE",
        "zone": "EU",
        "ok": True,
    })



@bp.route("/api/system/diagnostics")
def system_diagnostics():
    """Diagnostics systeme : memoire, CPU, cache - monitoring operationnel."""
    import time
    from station_web import START_TIME
    from services.cache_service import cache_status
    try:
        import psutil
        proc = psutil.Process()
        memory_mb = round(proc.memory_info().rss / 1024 / 1024, 2)
        cpu_percent = psutil.cpu_percent(interval=0.1)
    except Exception:
        memory_mb = 0
        cpu_percent = 0
    return jsonify({
        "system": "Orbital-Chohra",
        "status": "online",
        "uptime": int(time.time() - START_TIME),
        "memory_mb": memory_mb,
        "cpu_percent": cpu_percent,
        "cache_entries": cache_status()["api_cache"]["count"],
    })



@bp.route("/api/system/status")
def api_system_status_orbital():
    """Etat du systeme Orbital-Chohra - sante, heartbeat et uptime."""
    import time
    from station_web import START_TIME
    modules_active = [
        "portail", "observatoire", "galerie", "vision", "scientific", "lab",
        "research", "research_center", "space", "dashboard", "overlord_live",
    ]
    return jsonify({
        "system": "Orbital-Chohra",
        "status": "online",
        "modules": len(modules_active),
        "apis": 10,
        "timestamp": time.time(),
        "uptime": int(time.time() - START_TIME),
        "version": "1.0",
        "modules_list": modules_active,
    })



@bp.route("/api/system-status/cache")
def api_system_status_cache():
    """Etat DSN / Weather / SkyView depuis les snapshots data_core (aucun reseau)."""
    from station_web import STATION
    try:
        from core import system_status_engine as _sysst
        return jsonify(_sysst.build_system_status_cache_payload(STATION))
    except Exception as e:
        log.warning("api/system-status/cache: %s", e)
        return jsonify({
            "dsn": {"status": "fallback", "source": "error", "stale": True},
            "weather": {"status": "fallback", "source": "error", "stale": True},
            "skyview": {"status": "fallback", "source": "error", "stale": True},
            "global_status": "critical",
        }), 500



@bp.route("/api/system-heal", methods=["POST"])
def api_system_heal():
    """Auto-healing controle : refresh cache DSN / meteo / SkyView (core/auto_heal_engine)."""
    from station_web import STATION
    try:
        from core import auto_heal_engine as _heal
        return jsonify(_heal.run_auto_heal(STATION))
    except Exception as e:
        log.warning("api/system-heal: %s", e)
        return jsonify({"actions": [], "count": 0, "error": str(e)}), 500


# ─── PASS 4 : Health / System simple ────────────────────────────────────────

@bp.route('/health', methods=['GET'])
def health_check():
    """Liveness enrichi : uptime, mémoire, disque, circuit-breakers, APIs actives."""
    import psutil
    import shutil
    from datetime import datetime, timezone
    import station_web as _sw

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        d = _sw._build_status_payload_dict(now_iso, include_external=False)
        uptime_seconds = int(d.get("uptime_seconds") or 0)
        production_mode = d.get("production_mode")
        tle_backend = d.get("tle_backend_status")
        data_freshness = d.get("data_freshness")
        tle_count = d.get("tle_count")
        overall_status = d.get("status") or "ok"
    except Exception as ex:
        log.warning("health_check: %s", ex)
        uptime_seconds = int(time.time() - _sw.START_TIME)
        production_mode = "OFFLINE"
        tle_backend = None
        data_freshness = "unknown"
        tle_count = 0
        overall_status = "degraded"

    try:
        proc = psutil.Process()
        mem_mb = round(proc.memory_info().rss / 1024 / 1024, 1)
        mem_pct = round(psutil.virtual_memory().percent, 1)
        memory_usage = {"process_mb": mem_mb, "system_pct": mem_pct}
    except Exception:
        memory_usage = {}

    try:
        disk = shutil.disk_usage("/")
        disk_usage = {
            "total_gb": round(disk.total / 1e9, 1),
            "used_gb":  round(disk.used  / 1e9, 1),
            "free_gb":  round(disk.free  / 1e9, 1),
            "pct":      round(disk.used / disk.total * 100, 1),
        }
    except Exception:
        disk_usage = {}

    try:
        from services.circuit_breaker import all_status as _cb_all_status
        cb_statuses = _cb_all_status()
        active_apis = {s["name"]: s["state"] for s in cb_statuses}
        open_count = sum(1 for s in cb_statuses if s["state"] == "OPEN")
        if open_count > 0 and overall_status == "ok":
            overall_status = "degraded"
    except Exception:
        active_apis = {}

    return jsonify({
        "status":         overall_status,
        "service":        "astroscan",
        "uptime":         uptime_seconds,
        "uptime_sec":     uptime_seconds,
        "mode":           production_mode,
        "tle_status":     tle_backend,
        "data_freshness": data_freshness,
        "tle_count":      tle_count,
        "memory_usage":   memory_usage,
        "disk_usage":     disk_usage,
        "active_apis":    active_apis,
        "timestamp":      now_iso,
    })


@bp.route('/selftest', methods=['GET'])
def selftest():
    """Auto-contrôle structurel (clés fusion) — JSON toujours valide."""
    try:
        import station_web as _sw
        status = _sw.get_status_data()
        validation = _sw.validate_system_state(status)
        return jsonify({
            "selftest": "ok" if validation["valid"] else "fail",
            "details": validation,
        })
    except Exception as e:
        log.warning("selftest: %s", e)
        try:
            import station_web as _sw
            _sw.struct_log(
                logging.ERROR,
                category="validation",
                event="selftest_exception",
                error=str(e)[:400],
            )
        except Exception:
            pass
        return jsonify({
            "selftest": "fail",
            "error": str(e),
            "details": {"valid": False, "errors": ["selftest_exception"]},
        })


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


# ─── PASS 4 : API System (G) ─────────────────────────────────────────────────

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


# ─── PASS 4 : Accuracy export (J) ────────────────────────────────────────────

@bp.route('/api/accuracy/export.csv')
def api_accuracy_export_csv():
    """Export CSV historique de précision ISS."""
    from app.services.accuracy_history import get_accuracy_history
    rows = get_accuracy_history()
    lines = ["ts,distance_km"]
    for row in rows:
        ts = row.get("ts", "")
        distance = row.get("distance_km", "")
        lines.append(f"{ts},{distance}")
    csv_payload = "\n".join(lines) + "\n"
    return Response(
        csv_payload,
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="accuracy_history.csv"'},
    )


# ─── PASS 4 : Status/Health étendu (AC) ──────────────────────────────────────

@bp.route('/api/health')
def api_health():
    """Health check enrichi : DB, services, uptime, opérationnel."""
    from datetime import datetime, timezone
    total, anom, sources = 0, 0, []
    uptime_str = '—'
    try:
        import station_web as _sw
        conn = sqlite3.connect(_sw.DB_PATH, timeout=10.0)
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anom  = conn.execute("SELECT COUNT(*) FROM observations WHERE anomalie=1").fetchone()[0]
        rows  = conn.execute(
            "SELECT DISTINCT source FROM observations WHERE timestamp > datetime('now','-7 days')"
        ).fetchall()
        sources = [r[0] for r in rows]
        conn.close()
    except Exception:
        pass
    try:
        uptime_str = open('/proc/uptime').read().split()[0]
        s = int(float(uptime_str))
        uptime_str = f"{s//3600}h {(s%3600)//60}m"
    except Exception:
        pass
    payload = {
        'ok': True, 'station': 'ORBITAL-CHOHRA',
        'ip': '5.78.153.17', 'location': 'Tlemcen, Algérie',
        'director': 'Zakaria Chohra — Tlemcen, Algérie',
        'time_utc': datetime.now(timezone.utc).isoformat(),
        'uptime': uptime_str,
        'db': {'total': total, 'anomalies': anom, 'sources': sources},
        'services': {
            'gemini': 'active' if os.environ.get('GEMINI_API_KEY') else 'missing',
            'grok':   'inactive',
            'groq':   'active' if os.environ.get('GROQ_API_KEY')   else 'missing',
            'nasa':   'active' if os.environ.get('NASA_API_KEY')    else 'missing',
            'aegis': 'active', 'sdr': 'active', 'iss': 'active',
        },
        'coordinates': {'lat': 34.87, 'lon': 1.32, 'alt_m': 800, 'timezone': 'Africa/Algiers'},
    }
    try:
        import station_web as _sw
        if _sw._core_status_engine is not None:
            payload['operational'] = _sw._core_status_engine.build_operational_health(
                _sw.STATION, _sw.DB_PATH, _sw.TLE_CACHE, _sw.TLE_CACHE_FILE,
                ws_present=True, sse_present=True,
            )
            payload['data_credibility'] = _sw._core_status_engine.data_credibility_stub(
                _sw.TLE_CACHE, _sw.TLE_CACHE_FILE
            )
    except Exception as ex:
        log.debug("api_health operational: %s", ex)
        try:
            from datetime import datetime, timezone
            payload['operational'] = {
                'status': 'unknown',
                'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'error': 'probe_partial',
            }
        except Exception:
            pass
    return jsonify(payload)


@bp.route('/status')
def api_status():
    """Snapshot JSON stable pour badges UI / monitoring."""
    import station_web as _sw
    return jsonify(_sw.build_status_snapshot_dict())


@bp.route('/stream/status')
def stream_status_sse():
    """Flux SSE : même snapshot que /status, toutes les ~3 s."""
    import station_web as _sw

    def _gen():
        while True:
            try:
                snap = _sw.build_status_snapshot_dict()
                yield "data: " + json.dumps(snap, default=str) + "\n\n"
            except Exception as ex:
                try:
                    yield "data: " + json.dumps({"error": str(ex)[:200], "stream": "status"}) + "\n\n"
                except Exception:
                    pass
            time.sleep(3)

    return Response(
        stream_with_context(_gen()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
