"""Blueprint System — endpoints de monitoring et statut systeme.

Endpoints :
  - /api/system-status         : statut general
  - /api/system-alerts         : alertes via core.alert_engine
  - /api/system-notifications  : notifications via core.notification_engine

Migration depuis station_web.py (CTO Critique 3 - Monolith reduction).
"""

import logging

from flask import Blueprint, jsonify

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
