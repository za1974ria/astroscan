"""Blueprint Archive — observations CRUD, anomalies, classification, shield, MAST.

PASS 6 (2026-05-03) — Création :
  /api/archive/{reports,objects,discoveries},
  /api/microobservatory (statique),
  /api/classification/stats, /api/mast/targets, /api/shield.

Différé : /api/microobservatory/{images,preview} (helpers >100 lignes
  + conversion FITS+JPG → PASS 13).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from flask import Blueprint, request, jsonify

from app.config import SHIELD_F

log = logging.getLogger(__name__)

bp = Blueprint("archive", __name__)


# ── Archive CRUD (Domaine H — observations CRUD) ──────────────────────
@bp.route("/api/archive/reports", methods=["GET", "POST"])
def api_archive_reports():
    try:
        from modules.science_archive_engine import (
            save_report, list_reports, get_archive_index,
        )
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            report_data = data.get("report", data)
            source = data.get("source", "digital_lab")
            result = save_report(report_data, source=source)
            return jsonify({"ok": True, "saved": result})
        limit = request.args.get("limit", 50, type=int)
        reports = list_reports(limit=min(limit, 200))
        index = get_archive_index()
        return jsonify({"reports": reports, "index": index})
    except Exception as e:
        log.warning("api/archive/reports: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/archive/objects", methods=["GET", "POST"])
def api_archive_objects():
    try:
        from modules.science_archive_engine import (
            save_objects, list_objects, get_archive_index,
        )
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            objects = data.get("objects", data.get("objects_list", []))
            if isinstance(objects, dict):
                objects = [objects]
            source = data.get("source", "archive_api")
            result = save_objects(objects, source=source)
            return jsonify({"ok": True, "saved": result})
        limit = request.args.get("limit", 100, type=int)
        objects = list_objects(limit=min(limit, 500))
        index = get_archive_index()
        return jsonify({"objects": objects, "index": index})
    except Exception as e:
        log.warning("api/archive/objects: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/archive/discoveries", methods=["GET", "POST"])
def api_archive_discoveries():
    try:
        from modules.science_archive_engine import (
            save_discovery, list_discoveries, get_archive_index,
        )
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            source = data.get("source", "archive_api")
            entry = {k: v for k, v in data.items() if k != "source"}
            result = save_discovery(entry, source=source)
            return jsonify({"ok": True, "saved": result})
        limit = request.args.get("limit", 50, type=int)
        discoveries = list_discoveries(limit=min(limit, 200))
        index = get_archive_index()
        return jsonify({"discoveries": discoveries, "index": index})
    except Exception as e:
        log.warning("api/archive/discoveries: %s", e)
        return jsonify({"error": str(e)}), 500


# ── MicroObservatory (Domaine F — galerie statique seulement) ─────────
@bp.route("/api/microobservatory")
def api_microobservatory():
    targets = [
        {"name": "M42 — Nébuleuse d'Orion", "ra": "05:35:17", "dec": "-05:23:28", "exposure": "60s"},
        {"name": "M31 — Andromède", "ra": "00:42:44", "dec": "+41:16:09", "exposure": "120s"},
        {"name": "M13 — Amas Hercule", "ra": "16:41:41", "dec": "+36:27:41", "exposure": "30s"},
        {"name": "M57 — Nébuleuse Lyre", "ra": "18:53:35", "dec": "+33:01:45", "exposure": "90s"},
    ]
    return jsonify({
        "service": "MicroObservatory NASA — Harvard CfA",
        "url": "https://mo-www.cfa.harvard.edu/OWN/",
        "targets": targets,
        "instructions": "Connectez-vous sur MicroObservatory pour soumettre vos observations",
        "credit": "AstroScan-Chohra · ORBITAL-CHOHRA",
    })


# ── Classification stats (Domaine I — anomalies) ──────────────────────
@bp.route("/api/classification/stats")
def api_classification_stats():
    try:
        from app.utils.db import get_db
        conn = get_db()
        rows = conn.execute(
            "SELECT COALESCE(objets_detectes,'inconnu') as type, COUNT(*) as n "
            "FROM observations GROUP BY objets_detectes ORDER BY n DESC"
        ).fetchall()
        return jsonify({"ok": True, "stats": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ── MAST targets (Domaine H — observations Hubble/JWST) ───────────────
@bp.route("/api/mast/targets")
def api_mast_targets():
    try:
        from app.utils.db import get_db
        conn = get_db()
        rows = conn.execute(
            "SELECT id, COALESCE(title, objets_detectes, 'Unknown') as name, "
            "source, timestamp FROM observations "
            "WHERE source LIKE '%MAST%' OR source LIKE '%Hubble%' OR source LIKE '%JWST%' "
            "ORDER BY id DESC LIMIT 20"
        ).fetchall()
        return jsonify({"ok": True, "targets": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"ok": False, "targets": [], "error": str(e)})


# ── Shield status (Domaine I — anomalies / sécurité) ──────────────────
@bp.route("/api/shield")
def api_shield():
    if Path(SHIELD_F).exists():
        try:
            with open(SHIELD_F) as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify({"ok": True, "status": "active", "uptime": "—"})
