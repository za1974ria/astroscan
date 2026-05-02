"""Blueprint Analytics — endpoints de tracking visiteurs.

Endpoints :
  - /api/visits             (GET)  : compteur actuel
  - /api/visits/increment   (POST) : incremente et retourne nouvelle valeur
  - /api/visits/reset       (POST) : reset compteur (admin)
  - /api/visits/count       (GET)  : compteur direct via SQLite

Migration depuis station_web.py (CTO Critique 3 - Monolith reduction).
"""

import logging
import sqlite3

from flask import Blueprint, jsonify, redirect, request

log = logging.getLogger(__name__)

bp = Blueprint("analytics_bp", __name__)

DB_PATH = "/root/astro_scan/data/archive_stellaire.db"


@bp.route("/api/visits", methods=["GET"])
def api_visits_get():
    """Retourne le nombre actuel de visites."""
    from station_web import _get_visits_count
    try:
        count = _get_visits_count()
        return jsonify({"count": count})
    except Exception as e:
        log.warning(f"api/visits: {e}")
        return jsonify({"count": 0})


@bp.route("/api/visits/increment", methods=["POST"])
def api_visits_increment():
    """Incremente le compteur et retourne la nouvelle valeur."""
    from station_web import _increment_visits, _get_visits_count
    try:
        count = _increment_visits()
        return jsonify({"count": count})
    except Exception as e:
        log.warning(f"api/visits/increment: {e}")
        return jsonify({"count": _get_visits_count()})


@bp.route("/api/visits/reset", methods=["POST"])
def reset_visits():
    """Reset compteur de visites - admin seulement."""
    try:
        conn = sqlite3.connect(DB_PATH)
        old = conn.execute("SELECT count FROM visits WHERE id=1").fetchone()
        conn.execute("UPDATE visits SET count = 0 WHERE id=1")
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "old_count": old[0] if old else 0, "new_count": 0})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/visits/count")
def get_visits():
    """Retourne le compteur de visites actuel (lecture directe SQLite)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT count FROM visits WHERE id=1").fetchone()
        conn.close()
        return jsonify({"count": row[0] if row else 0})
    except Exception as e:
        return jsonify({"count": 0, "error": str(e)})



@bp.route("/api/visitors/snapshot")
def api_visitors_snapshot():
    """REST one-shot : meme payload que le SSE - polling fallback."""
    from station_web import get_global_stats
    try:
        exclude_my_ip = (request.args.get("exclude_my_ip", "1") or "0").strip().lower() in (
            "1", "true", "yes", "on",
        )
        return jsonify(get_global_stats(exclude_my_ip=exclude_my_ip))
    except Exception as e:
        log.warning("visitors/snapshot: %s", e)
        return jsonify({
            "error": str(e), "total": 0, "online_now": 0, "top_countries": [],
            "last_connections": [], "heatmap": [], "humans_total": 0,
            "bots_total": 0, "humans_today": 0,
        })


@bp.route("/api/visitors/connection-time")
def api_visitors_connection_time_legacy():
    """Redirige 301 vers la version underscore (URL canonique)."""
    return redirect("/api/visitors/connection_time", code=301)
