"""FLIGHT RADAR — Flask routes (premium NASA-grade ATC edition).

Public UI:
  GET /flight-radar

Public JSON API:
  GET /api/flight-radar/aircraft               filtered live snapshot
  GET /api/flight-radar/aircraft/<icao24>      detailed state + track
  GET /api/flight-radar/aircraft/<icao24>/track recent positions only
  GET /api/flight-radar/airports               50 major airports (static)
  GET /api/flight-radar/health                 backend health snapshot
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from app.blueprints.flight_radar.services.flight_service import FlightService
from app.blueprints.flight_radar.services.opensky_client import get_client
from app.blueprints.flight_radar.algo7 import Algo7DestinationEngine

log = logging.getLogger(__name__)

flight_radar_bp = Blueprint("flight_radar", __name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_AIRPORTS_PATH = os.path.join(_BASE_DIR, "data", "airports_geo.json")


# ──────────────────────────────────────────────────────────────────────
# Shared dependencies (Redis + service singleton)
# ──────────────────────────────────────────────────────────────────────

try:
    import redis as _redis
    _REDIS = _redis.Redis(decode_responses=True)
    _REDIS.ping()
    _REDIS_OK = True
except Exception:  # pragma: no cover
    _REDIS = None
    _REDIS_OK = False
    log.warning("[flight_radar] Redis unavailable — using in-memory cache only")

_service: FlightService | None = None
_algo7: Algo7DestinationEngine | None = None


def get_service() -> FlightService:
    global _service
    if _service is None:
        _service = FlightService(_REDIS if _REDIS_OK else None, get_client())
    return _service


def get_algo7() -> Algo7DestinationEngine:
    global _algo7
    if _algo7 is None:
        _algo7 = Algo7DestinationEngine(redis_client=_REDIS if _REDIS_OK else None)
    return _algo7


def ensure_service_started() -> None:
    get_service().start()


# ──────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────

@flight_radar_bp.route("/flight-radar")
def flight_radar_page() -> Any:
    try:
        from app.blueprints.i18n import get_lang
        lang = get_lang()
    except Exception:
        lang = "fr"
    return render_template("flight_radar.html", lang=lang)


# ──────────────────────────────────────────────────────────────────────
# API
# ──────────────────────────────────────────────────────────────────────

def _f(arg: str | None) -> float | None:
    if arg is None or arg == "":
        return None
    try:
        return float(arg)
    except (TypeError, ValueError):
        return None


@flight_radar_bp.route("/api/flight-radar/aircraft")
def api_aircraft_list() -> Any:
    ensure_service_started()
    svc = get_service()
    mode = request.args.get("mode")  # "fly" | "gnd" | None
    country = request.args.get("country") or None
    alt_min = _f(request.args.get("alt_min"))
    alt_max = _f(request.args.get("alt_max"))
    limit = int(request.args.get("limit") or 800)
    payload = svc.get_aircraft_list(
        country_iso=country,
        on_ground=mode,
        alt_min=alt_min,
        alt_max=alt_max,
        limit=limit,
    )
    return jsonify(payload)


@flight_radar_bp.route("/api/flight-radar/aircraft/<icao24>")
def api_aircraft_detail(icao24: str) -> Any:
    ensure_service_started()
    svc = get_service()
    st = svc.get_aircraft_state(icao24)
    if st is None:
        return jsonify({"ok": False, "error": "aircraft not found"}), 404
    # Enrich with ALGO-7 destination prediction.
    try:
        algo = get_algo7().predict(st)
        st["algo7"] = algo.to_dict()
    except Exception as exc:  # pragma: no cover
        log.warning("[flight_radar] algo7 predict failed for %s: %s", icao24, exc)
        st["algo7"] = None
    return jsonify({"ok": True, "aircraft": st})


@flight_radar_bp.route("/api/flight-radar/aircraft/<icao24>/track")
def api_aircraft_track(icao24: str) -> Any:
    ensure_service_started()
    svc = get_service()
    track = svc.get_track(icao24, limit=30)
    return jsonify({"ok": True, "icao24": icao24, "track": track})


@flight_radar_bp.route("/api/flight-radar/airport/<iata>/details")
def api_airport_details(iata: str) -> Any:
    ensure_service_started()
    svc = get_service()
    details = svc.get_airport_details(iata)
    if details is None:
        return jsonify({"ok": False, "error": "airport not found"}), 404
    return jsonify({"ok": True, **details})


@flight_radar_bp.route("/api/flight-radar/airports")
def api_airports() -> Any:
    try:
        with open(_AIRPORTS_PATH, "r", encoding="utf-8") as f:
            airports = json.load(f)
    except FileNotFoundError:
        airports = []
    return jsonify({"airports": airports, "count": len(airports)})


@flight_radar_bp.route("/api/flight-radar/health")
def api_health() -> Any:
    ensure_service_started()
    svc = get_service()
    return jsonify(svc.health())
