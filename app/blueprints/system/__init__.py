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
