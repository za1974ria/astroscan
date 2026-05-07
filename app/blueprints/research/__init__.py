"""Blueprint Research — Research Center + Science + Space Intelligence.

PASS 13 (2026-05-03) — Création :
  /research-center (page),
  /api/research/{summary,events,logs},
  /api/science/analyze-image,
  /api/space/intelligence (GET, POST).
"""
from __future__ import annotations

import json
import logging
import os
import uuid

from flask import Blueprint, render_template, request, jsonify

from app.config import STATION
from app.utils.cache import get_cached

log = logging.getLogger(__name__)

bp = Blueprint("research", __name__)


# ── Research Center page (Domaine AB) ─────────────────────────────────
@bp.route("/research-center")
def research_center_page():
    """Research Center dashboard: Space Weather, NEO, Solar Activity, Reports."""
    return render_template("research_center.html")


# ── Research API (modules.research_center) ────────────────────────────
@bp.route("/api/research/summary", methods=["GET"])
def api_research_summary():
    try:
        from modules.research_center import get_research_summary
        data = get_research_summary()
        return jsonify(data)
    except Exception as e:
        log.warning("api/research/summary: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/research/events", methods=["GET"])
def api_research_events():
    try:
        from modules.research_center import get_research_events
        limit = request.args.get("limit", 50, type=int)
        events = get_research_events(limit=min(limit, 200))
        return jsonify({"events": events})
    except Exception as e:
        log.warning("api/research/events: %s", e)
        return jsonify({"error": str(e), "events": []}), 500


@bp.route("/api/research/logs", methods=["GET"])
def api_research_logs():
    try:
        from modules.research_center import list_logs
        limit = request.args.get("limit", 50, type=int)
        logs = list_logs(limit=min(limit, 200))
        return jsonify({"logs": logs})
    except Exception as e:
        log.warning("api/research/logs: %s", e)
        return jsonify({"error": str(e), "logs": []}), 500


# ── Science : analyse d'image scientifique ────────────────────────────
@bp.route("/api/science/analyze-image", methods=["POST"])
def api_science_analyze_image():
    """Analyse d'image spatiale via image_science_engine."""
    from station_web import LAB_UPLOADS
    try:
        from modules.image_science_engine import analyze_space_image
        f = request.files.get("image")
        if f and f.filename:
            ext = os.path.splitext(f.filename)[1] or ".png"
            name = str(uuid.uuid4()) + ext
            path = os.path.join(LAB_UPLOADS, name)
            os.makedirs(LAB_UPLOADS, exist_ok=True)
            f.save(path)
            result = analyze_space_image(path)
            return jsonify(result)
        path = request.form.get("path") or (request.get_json(silent=True) or {}).get("path")
        if path:
            full = path if os.path.isabs(path) else os.path.join(STATION, path)
            result = analyze_space_image(full)
            return jsonify(result)
        return jsonify({"error": "Aucune image fournie (fichier ou path)"}), 400
    except Exception as e:
        log.warning("api/science/analyze-image: %s", e)
        return jsonify({
            "error": str(e),
            "stars": 0, "galaxies": 0, "nebula": False, "anomalies": [],
        }), 500


# ── Space Intelligence (Domaine AH) ───────────────────────────────────
@bp.route("/api/space/intelligence", methods=["GET", "POST"])
def api_space_intelligence():
    """Analyse spatiale : alertes, événements, niveau de risque."""
    from app.services.iss_live import _fetch_iss_live
    try:
        from modules.space_intelligence_engine import detect_space_event
        data = {}
        if request.method == "POST" and request.get_json(silent=True):
            data = request.get_json(silent=True) or {}
        else:
            iss = get_cached("iss_live", 5, _fetch_iss_live)
            if iss:
                data["iss"] = iss
            try:
                with open(f"{STATION}/static/space_weather.json", "r", encoding="utf-8") as f:
                    data["solar"] = json.load(f)
            except Exception:
                data["solar"] = {}
            try:
                with open(f"{STATION}/static/voyager_live.json", "r", encoding="utf-8") as f:
                    data["voyager"] = json.load(f)
            except Exception:
                data["voyager"] = {}
        out = detect_space_event(data)
        return jsonify(out)
    except Exception as e:
        log.warning("api/space/intelligence: %s", e)
        return jsonify({
            "alerts": [], "events": [], "risk_level": "medium",
            "error": str(e),
        })
