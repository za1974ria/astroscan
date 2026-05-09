"""Blueprint Health — endpoints de monitoring, santé, statut, diagnostics.

Endpoints (13 routes, scindés depuis system_bp lors de PASS 4 phase 2C) :
  Système / monitoring
    - /api/system-status            : statut global (mode démo stable)
    - /api/system-alerts            : alertes core/alert_engine
    - /api/system-notifications     : notifications core/notification_engine
    - /api/system/server-info       : métadonnées infrastructure (Hetzner)
    - /api/system/diagnostics       : mémoire/CPU/cache (psutil)
    - /api/system/status            : santé Orbital-Chohra (uptime, modules)
    - /api/system-status/cache      : snapshots data_core (DSN/Weather/SkyView)
    - /api/system-heal              : auto-healing core/auto_heal_engine

  Health / status / SSE
    - /health                       : liveness enrichi
    - /selftest                     : auto-contrôle structurel
    - /api/health                   : health enrichi (DB, services, ops)
    - /status                       : snapshot JSON badges UI
    - /stream/status                : SSE périodique (~3 s)
"""

import json
import logging
import os
import sqlite3
import time

from flask import Blueprint, Response, jsonify, request, stream_with_context

log = logging.getLogger(__name__)

bp = Blueprint("health_bp", __name__)

# Breakers whose OPEN state must NOT degrade overall_status.
# GROQ is a non-critical translation fallback (Gemini is primary).
NON_CRITICAL_APIS = {"GROQ"}


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
    """Public server status — minimal info disclosure (PASS 28).

    IP and provider were removed in PASS 28 to avoid info disclosure.
    Public DNS already exposes the IP via astroscan.space resolution,
    but we do not amplify it via this endpoint.
    """
    from datetime import datetime, timezone
    return jsonify({
        "ok": True,
        "status": "online",
        "zone": "EU",
        "timestamp": datetime.now(timezone.utc).isoformat(),
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


# ─── Health / liveness ─────────────────────────────────────────────────────

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
        open_count = sum(
            1 for s in cb_statuses
            if s["state"] == "OPEN" and s["name"] not in NON_CRITICAL_APIS
        )
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
    # PASS 28 — Replaced individual service enumeration with aggregate count
    # to prevent fingerprinting of configured integrations. Also removed
    # 'ip' and 'director' (info disclosure not needed for monitoring).
    payload = {
        'ok': True, 'station': 'ORBITAL-CHOHRA',
        'location': 'Tlemcen, Algérie',
        'time_utc': datetime.now(timezone.utc).isoformat(),
        'uptime': uptime_str,
        'db': {'total': total, 'anomalies': anom, 'sources': sources},
        'integrations_ready': sum([
            bool(os.environ.get('GEMINI_API_KEY')),
            bool(os.environ.get('GROQ_API_KEY')),
            bool(os.environ.get('NASA_API_KEY')),
            bool(os.environ.get('N2YO_API_KEY')),
            bool(os.environ.get('ANTHROPIC_API_KEY')),
        ]),
        'integrations_total': 5,
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
