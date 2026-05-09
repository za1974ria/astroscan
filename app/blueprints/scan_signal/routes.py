"""SCAN A SIGNAL — Flask routes (VESSEL TRACKER edition).

Public UI:
  GET /scan-signal

Public JSON API:
  GET  /api/scan-signal/vessel/search?q=<query>
  GET  /api/scan-signal/vessel/recent?limit=20
  GET  /api/scan-signal/vessel/<mmsi>
  POST /api/scan-signal/ping
  GET  /api/scan-signal/stats
  GET  /api/scan-signal/health

The satellite endpoints were retired in this build; the satellite tab in
the UI is gone. Aircraft tracking remains a redirect to /flight-radar.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from app.blueprints.scan_signal.services.aisstream_subscriber import AISStreamSubscriber
from app.blueprints.scan_signal.services.vessel_service import VesselService

log = logging.getLogger(__name__)

scan_signal_bp = Blueprint("scan_signal", __name__)


# ──────────────────────────────────────────────────────────────────────
# Shared dependencies (Redis + services)
# ──────────────────────────────────────────────────────────────────────

try:
    import redis as _redis
    _REDIS = _redis.Redis(decode_responses=True)
    _REDIS.ping()
    _REDIS_OK = True
except Exception:  # pragma: no cover
    _REDIS = None
    _REDIS_OK = False
    log.warning("[scan_signal] raw redis unavailable — counters + vessel cache disabled")

# Vessel service reads from the Redis cache populated by the subscriber.
_vessel_service = VesselService(_REDIS) if _REDIS_OK else VesselService(None)

# AISStream subscriber — kept as a module-level singleton so the
# blueprint __init__ can start it once and the health endpoint can
# query its state.
_ais_subscriber: AISStreamSubscriber | None = None


def get_subscriber() -> AISStreamSubscriber:
    """Return (lazily creating) the AISStream subscriber singleton."""
    global _ais_subscriber
    if _ais_subscriber is None:
        _ais_subscriber = AISStreamSubscriber(_REDIS) if _REDIS_OK else AISStreamSubscriber(None)
    return _ais_subscriber


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _seconds_until_midnight_utc() -> int:
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return max(60, int((midnight - now).total_seconds()) + 1)


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


# ──────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────

@scan_signal_bp.route("/scan-signal")
def scan_signal_page():
    """Public page — no auth, embeddable via ?embed=1."""
    embed = (request.args.get("embed") or "") == "1"
    try:
        from app.blueprints.i18n import get_lang
        lang = get_lang()
    except Exception:
        lang = "fr"
    return render_template("scan_signal.html", embed=embed, lang=lang)


# ──────────────────────────────────────────────────────────────────────
# API — vessel search
# ──────────────────────────────────────────────────────────────────────

@scan_signal_bp.route("/api/scan-signal/vessel/search")
def api_vessel_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"query": "", "matches": [], "total_found": 0, "showing": 0})
    try:
        return jsonify(_vessel_service.search(q))
    except Exception as exc:
        log.exception("[scan_signal] /vessel/search failed for %r", q)
        return jsonify({"error": "internal_error", "message": str(exc),
                        "query": q, "matches": [], "total_found": 0, "showing": 0}), 500


# ──────────────────────────────────────────────────────────────────────
# API — vessel recent (replaces "popular satellites")
# ──────────────────────────────────────────────────────────────────────

@scan_signal_bp.route("/api/scan-signal/vessel/recent")
def api_vessel_recent():
    try:
        limit = int(request.args.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(50, limit))
    try:
        return jsonify(_vessel_service.recent(limit=limit))
    except Exception as exc:
        log.exception("[scan_signal] /vessel/recent failed")
        return jsonify({"error": "internal_error", "message": str(exc), "items": []}), 500


# ──────────────────────────────────────────────────────────────────────
# API — vessel state
# ──────────────────────────────────────────────────────────────────────

@scan_signal_bp.route("/api/scan-signal/vessel/<mmsi>")
def api_vessel_state(mmsi: str):
    try:
        from app.blueprints.i18n import get_lang
        lang = get_lang()
    except Exception:
        lang = "fr"
    try:
        state = _vessel_service.get_state(mmsi, lang=lang)
    except Exception as exc:
        log.exception("[scan_signal] /vessel/%s failed", mmsi)
        return jsonify({"error": "internal_error", "message": str(exc),
                        "mmsi": mmsi}), 500
    if not state:
        return jsonify({"error": "not_found", "mmsi": mmsi}), 404
    return jsonify(state)


# ──────────────────────────────────────────────────────────────────────
# API — historical track (vessel trail)
# ──────────────────────────────────────────────────────────────────────

@scan_signal_bp.route("/api/scan-signal/vessel/<mmsi>/track")
def api_vessel_track(mmsi: str):
    """Return last 10 historical positions, oldest→newest, for trail rendering."""
    try:
        track = _vessel_service.get_track(mmsi, limit=10)
        return jsonify({"mmsi": mmsi, "track": track, "count": len(track)})
    except Exception as exc:
        log.exception("[scan_signal] /vessel/%s/track failed", mmsi)
        return jsonify({"error": "internal_error", "message": str(exc),
                        "mmsi": mmsi, "track": [], "count": 0}), 500


# ──────────────────────────────────────────────────────────────────────
# API — major ports (static reference list)
# ──────────────────────────────────────────────────────────────────────

_PORTS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "ports_geo.json",
)
_PORTS_CACHE: list[dict] | None = None


@scan_signal_bp.route("/api/scan-signal/ports")
def api_ports():
    """Return major ports with coordinates for map display (cached at boot)."""
    global _PORTS_CACHE
    try:
        if _PORTS_CACHE is None:
            with open(_PORTS_PATH, "r", encoding="utf-8") as f:
                _PORTS_CACHE = json.load(f)
        return jsonify({"ports": _PORTS_CACHE, "count": len(_PORTS_CACHE)})
    except Exception as exc:
        log.exception("[scan_signal] /ports failed")
        return jsonify({"error": "internal_error", "message": str(exc),
                        "ports": [], "count": 0}), 500


# ──────────────────────────────────────────────────────────────────────
# API — anonymous activity counters
# ──────────────────────────────────────────────────────────────────────

@scan_signal_bp.route("/api/scan-signal/ping", methods=["POST"])
def api_ping():
    """Increment anonymous counters. NO IP, NO target stored."""
    try:
        body = request.get_json(silent=True) or {}
        kind = (body.get("type") or "vessel").strip().lower()
        if kind not in ("satellite", "vessel", "aircraft"):
            kind = "vessel"
    except Exception:
        kind = "vessel"

    today = _today_key()
    today_count = 0
    active_now = 0

    if _REDIS_OK and _REDIS is not None:
        try:
            today_key = f"as:scan:counter:{kind}:today:{today}"
            active_key = f"as:scan:counter:{kind}:active"
            today_count = int(_REDIS.incr(today_key))
            _REDIS.expire(today_key, _seconds_until_midnight_utc())
            active_now = int(_REDIS.incr(active_key))
            _REDIS.expire(active_key, 60)
        except Exception as exc:
            log.warning("[scan_signal] ping counter failed: %s", exc)

    return jsonify({
        "today_count": today_count,
        "active_now": active_now,
        "type": kind,
    })


@scan_signal_bp.route("/api/scan-signal/stats")
def api_stats():
    today = _today_key()
    out: dict[str, Any] = {"today": {}, "active_now": {}}
    if _REDIS_OK and _REDIS is not None:
        try:
            for kind in ("satellite", "vessel", "aircraft"):
                t = _REDIS.get(f"as:scan:counter:{kind}:today:{today}")
                a = _REDIS.get(f"as:scan:counter:{kind}:active")
                out["today"][kind] = int(t) if t else 0
                out["active_now"][kind] = int(a) if a else 0
        except Exception as exc:
            log.warning("[scan_signal] stats failed: %s", exc)
    return jsonify(out)


# ──────────────────────────────────────────────────────────────────────
# API — health
# ──────────────────────────────────────────────────────────────────────

@scan_signal_bp.route("/api/scan-signal/health")
def api_health():
    try:
        sub = get_subscriber()
        cache_size = 0
        if _REDIS_OK and _REDIS is not None:
            try:
                cache_size = int(_REDIS.hlen("as:scan:vessels") or 0)
            except Exception:
                cache_size = 0
        return jsonify({
            "status": "ok" if _REDIS_OK else "degraded",
            "redis": _REDIS_OK,
            "observatories": len(_vessel_service._observatories),
            "vessel_cache_size": cache_size,
            "aisstream": sub.get_health(),
        })
    except Exception as exc:
        log.exception("[scan_signal] /health failed")
        return jsonify({"status": "error", "message": str(exc)}), 500
