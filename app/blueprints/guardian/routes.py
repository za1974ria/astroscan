"""Guardian HTTP routes — localhost-only admin endpoints.

Routes:
    GET /api/guardian/status     — latest snapshot from the monitoring thread
    GET /api/guardian/incidents  — recent incidents (?since=15m|1h|6h|24h)
    GET /api/guardian/health     — agent self-status

The url_prefix '/api/guardian' is applied at registration (app/__init__.py).
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from app.blueprints.astrobrain.security import require_localhost
from app.blueprints.guardian import agent, audit_log

log = logging.getLogger(__name__)

bp = Blueprint("guardian", __name__)

# Ensure the agent thread is started on first import (factory-managed).
# Safe to call repeatedly — start_agent() is idempotent.
try:
    agent.start_agent()
except Exception as exc:  # noqa: BLE001 — never break factory boot
    log.warning("[guardian] start_agent failed at import: %s", exc)


_SINCE_TO_SECONDS = {
    "15m": 15 * 60,
    "1h": 3600,
    "6h": 6 * 3600,
    "24h": 24 * 3600,
}


@bp.route("/status", methods=["GET"])
@require_localhost
def api_status():
    snap = agent.status()
    return jsonify(snap), 200


@bp.route("/incidents", methods=["GET"])
@require_localhost
def api_incidents():
    since = (request.args.get("since") or "1h").strip().lower()
    if since not in _SINCE_TO_SECONDS:
        return jsonify({"ok": False, "error": "invalid_since",
                        "allowed": list(_SINCE_TO_SECONDS)}), 400
    seconds = _SINCE_TO_SECONDS[since]
    items = audit_log.recent(since_seconds=seconds)
    return jsonify({"ok": True, "since": since, "count": len(items), "incidents": items}), 200


@bp.route("/health", methods=["GET"])
@require_localhost
def api_health():
    return jsonify(agent.health()), 200
