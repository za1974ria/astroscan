"""Blueprint maintenance — Mission Control Center (i18n FR/EN).

Sert /maintenance (dashboard) et /api/maintenance/aggregate (JSON
agrégé pour le polling client). Tous les noms de service et messages
sont localisés selon get_lang() (priorité ?lang= > cookie > Accept-Language).
"""
import time
from datetime import datetime, timezone

from flask import Blueprint, render_template, jsonify, current_app

from app.blueprints.i18n import get_lang

bp = Blueprint("maintenance", __name__)


# ── i18n catalog ────────────────────────────────────────────────────
SERVICES_I18N = {
    # External APIs
    "NASA APOD": {
        "fr": ("NASA APOD", "Image astronomique du jour"),
        "en": ("NASA APOD", "Astronomy Picture of the Day"),
    },
    "N2YO ISS Tracker": {
        "fr": ("N2YO Traceur ISS", "Âge TLE : {tle_age}s"),
        "en": ("N2YO ISS Tracker", "TLE age: {tle_age}s"),
    },
    "Gemini AI": {
        "fr": ("Gemini AI", "Fournisseur traduction principal"),
        "en": ("Gemini AI", "Translation primary provider"),
    },
    "Groq Llama 3.3": {
        "fr": ("Groq Llama 3.3", "Fallback traduction rapide"),
        "en": ("Groq Llama 3.3", "Translation fast fallback"),
    },
    "Claude Anthropic": {
        "fr": ("Claude Anthropic", "Chatbot AEGIS + fallback ultime"),
        "en": ("Claude Anthropic", "AEGIS chatbot + ultimate fallback"),
    },
    "AISStream": {
        "fr": ("AISStream", "Suivi navires en direct"),
        "en": ("AISStream", "Live vessel tracking"),
    },
    # Infrastructure
    "Gunicorn / Flask": {
        "fr": ("Gunicorn / Flask", "Disponibilité : {uptime}"),
        "en": ("Gunicorn / Flask", "Uptime: {uptime}"),
    },
    "Redis Cache": {
        "fr": ("Cache Redis", "{value}"),
        "en": ("Redis Cache", "{value}"),
    },
    "SQLite": {
        "fr": ("SQLite", "{count} observations"),
        "en": ("SQLite", "{count} observations"),
    },
    "WebSocket SSE": {
        "fr": ("WebSocket SSE", "{value}"),
        "en": ("WebSocket SSE", "{value}"),
    },
    "WebSocket view-sync": {
        "fr": ("WebSocket view-sync", "{value}"),
        "en": ("WebSocket view-sync", "{value}"),
    },
    # Data Quality
    "TLE Freshness": {
        "fr": ("Fraîcheur TLE", "Âge : {hours}h"),
        "en": ("TLE Freshness", "Age: {hours}h"),
    },
    "Integrations": {
        "fr": ("Intégrations", "{ready}/{total} prêtes"),
        "en": ("Integrations", "{ready}/{total} ready"),
    },
    "Data Credibility": {
        "fr": ("Crédibilité des données", "{level}"),
        "en": ("Data Credibility", "{level}"),
    },
    "Anomaly Detection": {
        "fr": ("Détection d'anomalies", "{count} anomalies actives"),
        "en": ("Anomaly Detection", "{count} active anomalies"),
    },
    # Workers
    "tle_refresh_loop": {
        "fr": ("Rafraîchissement TLE", "Thread d'arrière-plan actif"),
        "en": ("TLE refresh loop", "Active background thread"),
    },
    "lab_image_collector": {
        "fr": ("Collecteur images Lab", "Thread d'arrière-plan actif"),
        "en": ("Lab image collector", "Active background thread"),
    },
    "skyview_sync": {
        "fr": ("Synchronisation SkyView", "Thread d'arrière-plan actif"),
        "en": ("SkyView sync", "Active background thread"),
    },
    "translate_worker": {
        "fr": ("Worker traduction", "Thread d'arrière-plan actif"),
        "en": ("Translate worker", "Active background thread"),
    },
    "tle_collector": {
        "fr": ("Collecteur TLE", "Thread d'arrière-plan actif"),
        "en": ("TLE collector", "Active background thread"),
    },
}

ACTION_HINTS_I18N = {
    "down": {
        "fr": "Vérifier les logs / redémarrer le service",
        "en": "Check logs / restart service",
    },
    "warn": {
        "fr": "Surveiller de près",
        "en": "Monitor closely",
    },
}

CRED_LABELS_I18N = {
    "high":    {"fr": "ÉLEVÉE",     "en": "HIGH"},
    "medium":  {"fr": "MOYENNE",    "en": "MEDIUM"},
    "low":     {"fr": "FAIBLE",     "en": "LOW"},
    "unknown": {"fr": "INCONNUE",   "en": "UNKNOWN"},
}


def _t(key: str, lang: str, fmt: dict | None = None) -> tuple[str, str]:
    """Return (localized_name, localized_message) for a service key."""
    entry = SERVICES_I18N.get(key)
    if not entry:
        return key, ""
    name, msg_tpl = entry.get(lang) or entry.get("en") or (key, "")
    try:
        return name, msg_tpl.format(**(fmt or {}))
    except Exception:
        return name, msg_tpl


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
    Agrège l'état de tous les services. Localise les noms et messages
    selon get_lang() (?lang= prioritaire pour permettre au frontend de
    forcer une langue côté fetch).
    """
    try:
        lang = get_lang()
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
        uptime_val = (health or {}).get("uptime", "—")

        def state_from(value, fallback="unknown"):
            if value in ("ok", "connected", "present", "running", True):
                return "ok"
            if value in ("warn", "warning", "degraded"):
                return "warn"
            if value in (False, "down", "failed", "missing", None, ""):
                return "down"
            return fallback

        def build(key, status, latency_ms=None, fmt=None):
            name, msg = _t(key, lang, fmt)
            return {
                "service": name,
                "status": status,
                "latency_ms": latency_ms,
                "message": msg,
                "last_check": now_iso,
            }

        ext_api_status = state_from(operational.get("external_api"))
        external_apis = [
            build("NASA APOD",         ext_api_status, latency_ms=t_health_ms),
            build("N2YO ISS Tracker",  ext_api_status, fmt={"tle_age": operational.get("tle_age_seconds", "—")}),
            build("Gemini AI",         ext_api_status),
            build("Groq Llama 3.3",    ext_api_status),
            build("Claude Anthropic",  ext_api_status),
            build("AISStream",         ext_api_status),
        ]

        infrastructure = [
            build("Gunicorn / Flask",   "ok" if (health or {}).get("ok") else "down",
                  latency_ms=t_health_ms, fmt={"uptime": uptime_val}),
            build("Redis Cache",        state_from(operational.get("redis")),
                  fmt={"value": str(operational.get("redis", "—"))}),
            build("SQLite",             state_from(operational.get("sqlite")),
                  fmt={"count": db_info.get("total", 0)}),
            build("WebSocket SSE",      state_from(operational.get("sse_status")),
                  fmt={"value": str(operational.get("sse_status", "—"))}),
            build("WebSocket view-sync", state_from(operational.get("ws_status")),
                  fmt={"value": str(operational.get("ws_status", "—"))}),
        ]

        tle_age = operational.get("tle_age_seconds", 0) or 0
        try:
            tle_age_int = int(tle_age)
        except Exception:
            tle_age_int = 0
        tle_status = "ok" if tle_age_int < 86400 else ("warn" if tle_age_int < 172800 else "down")
        integ_ratio = integrations_ready / max(1, integrations_total)
        integ_status = "ok" if integ_ratio >= 0.9 else ("warn" if integ_ratio >= 0.5 else "down")
        cred_raw = ((health or {}).get("data_credibility", {}) or {}).get("confidence_level", "unknown")
        cred_status = "ok" if cred_raw == "high" else ("warn" if cred_raw == "medium" else "down")
        cred_label = CRED_LABELS_I18N.get(cred_raw, CRED_LABELS_I18N["unknown"]).get(lang, cred_raw)

        data_quality = [
            build("TLE Freshness",      tle_status,    fmt={"hours": int(tle_age_int / 3600)}),
            build("Integrations",       integ_status,  fmt={"ready": integrations_ready, "total": integrations_total}),
            build("Data Credibility",   cred_status,   fmt={"level": cred_label}),
            build("Anomaly Detection",  "ok",          fmt={"count": db_info.get("anomalies", 0)}),
        ]

        workers = [
            build(w, "ok") for w in [
                "tle_refresh_loop", "lab_image_collector", "skyview_sync",
                "translate_worker", "tle_collector",
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
                    "action_hint": ACTION_HINTS_I18N[s["status"]].get(lang, ACTION_HINTS_I18N[s["status"]]["en"]),
                })

        return jsonify({
            "lang": lang,
            "timestamp": now_iso,
            "uptime": uptime_val,
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
