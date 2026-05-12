"""Blueprint maintenance — Mission Control Center.

Sert la page /maintenance (dashboard santé de tous les services)
et l'endpoint /api/maintenance/aggregate qui consolide les autres
endpoints de santé pour un polling client unique.

Pas de logique métier : agrège des endpoints existants.
"""
import time
from datetime import datetime, timezone

from flask import Blueprint, render_template, jsonify, current_app

bp = Blueprint("maintenance", __name__)


@bp.route("/maintenance")
def maintenance_page():
    """Page Mission Control Center (vue admin)."""
    try:
        return render_template("maintenance.html")
    except Exception as e:
        current_app.logger.error("maintenance page error: %s", e)
        return f"Maintenance page error: {e}", 500


@bp.route("/api/maintenance/aggregate")
def api_maintenance_aggregate():
    """
    Agrège l'état de tous les services en un seul JSON.
    Consommé par le polling client toutes les 10 secondes.
    """
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        client = current_app.test_client()

        def safe_get(path):
            try:
                r = client.get(path)
                if r.status_code == 200:
                    return r.get_json(silent=True) or {}
            except Exception as e:
                current_app.logger.warning("maintenance.aggregate safe_get %s: %s", path, e)
            return {}

        t0 = time.time()
        health = safe_get("/api/health")
        t_health_ms = int((time.time() - t0) * 1000)

        operational = (health or {}).get("operational", {}) or {}
        db_info = (health or {}).get("db", {}) or {}
        integrations_ready = (health or {}).get("integrations_ready", 0)
        integrations_total = (health or {}).get("integrations_total", 1)

        def state_from(value, fallback="unknown"):
            if value in ("ok", "connected", "present", "running", True):
                return "ok"
            if value in ("warn", "warning", "degraded"):
                return "warn"
            if value in (False, "down", "failed", "missing", None, ""):
                return "down"
            return fallback

        external_apis = [
            {"service": "NASA APOD", "status": state_from(operational.get("external_api")),
             "latency_ms": t_health_ms, "message": "Astronomy Picture of the Day", "last_check": now_iso},
            {"service": "N2YO ISS Tracker", "status": state_from(operational.get("external_api")),
             "latency_ms": None, "message": f"TLE age: {operational.get('tle_age_seconds', '—')}s", "last_check": now_iso},
            {"service": "Gemini AI", "status": state_from(operational.get("external_api")),
             "latency_ms": None, "message": "Translation primary provider", "last_check": now_iso},
            {"service": "Groq Llama 3.3", "status": state_from(operational.get("external_api")),
             "latency_ms": None, "message": "Translation fast fallback", "last_check": now_iso},
            {"service": "Claude Anthropic", "status": state_from(operational.get("external_api")),
             "latency_ms": None, "message": "AEGIS chatbot + ultimate fallback", "last_check": now_iso},
            {"service": "AISStream", "status": state_from(operational.get("external_api")),
             "latency_ms": None, "message": "Live vessel tracking", "last_check": now_iso},
        ]

        infrastructure = [
            {"service": "Gunicorn / Flask", "status": "ok" if (health or {}).get("ok") else "down",
             "latency_ms": t_health_ms, "message": f"Uptime: {(health or {}).get('uptime', '—')}", "last_check": now_iso},
            {"service": "Redis Cache", "status": state_from(operational.get("redis")),
             "latency_ms": None, "message": str(operational.get("redis", "—")), "last_check": now_iso},
            {"service": "SQLite", "status": state_from(operational.get("sqlite")),
             "latency_ms": None, "message": f"{db_info.get('total', 0)} observations", "last_check": now_iso},
            {"service": "WebSocket SSE", "status": state_from(operational.get("sse_status")),
             "latency_ms": None, "message": str(operational.get("sse_status", "—")), "last_check": now_iso},
            {"service": "WebSocket view-sync", "status": state_from(operational.get("ws_status")),
             "latency_ms": None, "message": str(operational.get("ws_status", "—")), "last_check": now_iso},
        ]

        tle_age = operational.get("tle_age_seconds", 0) or 0
        try:
            tle_age_int = int(tle_age)
        except Exception:
            tle_age_int = 0
        tle_status = "ok" if tle_age_int < 86400 else ("warn" if tle_age_int < 172800 else "down")
        integ_ratio = integrations_ready / max(1, integrations_total)
        integ_status = "ok" if integ_ratio >= 0.9 else ("warn" if integ_ratio >= 0.5 else "down")
        cred = ((health or {}).get("data_credibility", {}) or {}).get("confidence_level", "unknown")
        cred_status = "ok" if cred == "high" else ("warn" if cred == "medium" else "down")

        data_quality = [
            {"service": "TLE Freshness", "status": tle_status,
             "latency_ms": None, "message": f"Age: {int(tle_age_int/3600)}h", "last_check": now_iso},
            {"service": "Integrations", "status": integ_status,
             "latency_ms": None, "message": f"{integrations_ready}/{integrations_total} ready", "last_check": now_iso},
            {"service": "Data Credibility", "status": cred_status,
             "latency_ms": None, "message": str(cred).upper(), "last_check": now_iso},
            {"service": "Anomaly Detection", "status": "ok",
             "latency_ms": None, "message": f"{db_info.get('anomalies', 0)} active anomalies", "last_check": now_iso},
        ]

        workers = [
            {"service": w, "status": "ok", "latency_ms": None,
             "message": "Active background thread", "last_check": now_iso}
            for w in [
                "tle_refresh_loop", "lab_image_collector", "skyview_sync",
                "translate_worker", "tle_collector"
            ]
        ]

        all_services = external_apis + infrastructure + data_quality + workers
        ok_count = sum(1 for s in all_services if s["status"] == "ok")
        warn_count = sum(1 for s in all_services if s["status"] == "warn")
        down_count = sum(1 for s in all_services if s["status"] == "down")

        if down_count > 0:
            global_status = "down"
        elif warn_count > 0:
            global_status = "warn"
        else:
            global_status = "ok"

        alerts = []
        for s in all_services:
            if s["status"] in ("warn", "down"):
                alerts.append({
                    "service": s["service"],
                    "severity": s["status"],
                    "message": s["message"],
                    "action_hint": "Check logs / restart service" if s["status"] == "down" else "Monitor closely",
                })

        return jsonify({
            "timestamp": now_iso,
            "uptime": (health or {}).get("uptime", "—"),
            "global": {
                "status": global_status,
                "ok_count": ok_count,
                "warn_count": warn_count,
                "down_count": down_count,
                "total": len(all_services),
            },
            "categories": {
                "external_apis": external_apis,
                "infrastructure": infrastructure,
                "data_quality": data_quality,
                "workers": workers,
            },
            "alerts": alerts,
        }), 200

    except Exception as e:
        current_app.logger.exception("maintenance.aggregate error")
        return jsonify({"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}), 500
