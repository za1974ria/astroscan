"""Ground Assets — Flask routes.

Public UI:
  GET /ground-assets

Public JSON API:
  GET /api/ground-assets/network
  GET /api/ground-assets/asset/<asset_id>
  GET /api/ground-assets/events
  GET /api/ground-assets/health

All endpoints are wrapped in try/except and degrade gracefully.
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, render_template, request

from app.blueprints.ground_assets.services import GroundAssetsService

log = logging.getLogger(__name__)

ground_assets_bp = Blueprint("ground_assets", __name__)
_service = GroundAssetsService()


# ──────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────

@ground_assets_bp.route("/ground-assets")
def ground_assets_page():
    """Public page — no auth, embeddable via ?embed=1."""
    embed = (request.args.get("embed") or "") == "1"
    try:
        from app.blueprints.i18n import get_lang
        lang = get_lang()
    except Exception:
        lang = "fr"
    return render_template(
        "ground_assets.html",
        embed=embed,
        lang=lang,
    )


# ──────────────────────────────────────────────────────────────────────
# API
# ──────────────────────────────────────────────────────────────────────

@ground_assets_bp.route("/api/ground-assets/network")
def api_network():
    try:
        return jsonify(_service.get_network_state())
    except Exception as exc:
        log.exception("[ground_assets] /network failed")
        return jsonify({
            "error": "internal_error",
            "message": str(exc),
            "observatories": [],
            "missions": [],
            "balloons": [],
            "antennas": [],
            "stats": {},
        }), 500


@ground_assets_bp.route("/api/ground-assets/asset/<asset_id>")
def api_asset_detail(asset_id: str):
    try:
        detail = _service.get_asset_detail(asset_id)
        if detail is None:
            return jsonify({"error": "not_found", "asset_id": asset_id}), 404
        return jsonify(detail)
    except Exception as exc:
        log.exception("[ground_assets] /asset/%s failed", asset_id)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@ground_assets_bp.route("/api/ground-assets/events")
def api_events():
    try:
        limit = max(1, min(200, int(request.args.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    try:
        events = _service.get_recent_events(limit=limit)
        return jsonify({"events": events, "count": len(events)})
    except Exception as exc:
        log.exception("[ground_assets] /events failed")
        return jsonify({"error": "internal_error", "message": str(exc), "events": []}), 500


@ground_assets_bp.route("/api/ground-assets/health")
def api_health():
    try:
        return jsonify(_service.get_health())
    except Exception as exc:
        log.exception("[ground_assets] /health failed")
        return jsonify({
            "status": "error",
            "message": str(exc),
            "data_sources": {},
        }), 500
