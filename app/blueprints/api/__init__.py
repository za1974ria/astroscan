"""Blueprint API — documentation Swagger + spec OpenAPI."""
from flask import Blueprint, render_template, jsonify
from services.cache_service import cache_status
from services.circuit_breaker import all_status as cb_all_status
import os
from flask import request

bp = Blueprint("api_docs", __name__)

API_SPEC = {
    "openapi": "3.0.0",
    "info": {
        "title": "AstroScan-Chohra API",
        "version": "2.0.0",
        "description": (
            "API publique de la station d'observation spatiale AstroScan-Chohra. "
            "Données en temps réel : ISS, météo spatiale, éphémérides Tlemcen, APOD NASA. "
            "Usage scientifique et éducatif libre."
        ),
        "contact": {
            "name": "Zakaria Chohra",
            "email": "zakaria.chohra@gmail.com",
            "url": "https://astroscan.space/a-propos",
        },
        "license": {
            "name": "Open Data — CC BY 4.0",
            "url": "https://astroscan.space/data",
        },
    },
    "servers": [{"url": "https://astroscan.space", "description": "Production"}],
    "tags": [
        {"name": "ISS", "description": "Station Spatiale Internationale"},
        {"name": "Astronomie", "description": "Éphémérides et données astronomiques"},
        {"name": "NASA", "description": "Données officielles NASA"},
        {"name": "Météo Spatiale", "description": "NOAA, Kp-index, aurores"},
        {"name": "Export", "description": "Téléchargement CSV/JSON — CC BY 4.0"},
        {"name": "Analytics", "description": "Statistiques plateforme"},
        {"name": "Système", "description": "Health checks"},
    ],
    "paths": {
        "/api/ephemerides/tlemcen": {"get": {
            "summary": "Éphémérides Tlemcen",
            "tags": ["Astronomie"],
            "responses": {"200": {"description": "JSON éphémérides complètes"}},
        }},
        "/api/iss": {"get": {
            "summary": "Position ISS temps réel",
            "tags": ["ISS"],
            "responses": {"200": {"description": "JSON position ISS"}},
        }},
        "/api/apod": {"get": {
            "summary": "APOD NASA du jour",
            "tags": ["NASA"],
            "responses": {"200": {"description": "JSON APOD + traduction FR"}},
        }},
        "/api/meteo-spatiale": {"get": {
            "summary": "Météo spatiale NOAA",
            "tags": ["Météo Spatiale"],
            "responses": {"200": {"description": "JSON Kp, alertes, vent solaire"}},
        }},
        "/api/visitors/snapshot": {"get": {
            "summary": "Statistiques visiteurs",
            "tags": ["Analytics"],
            "responses": {"200": {"description": "JSON stats visiteurs"}},
        }},
        "/api/export/visitors.csv": {"get": {
            "summary": "Export visiteurs CSV",
            "tags": ["Export"],
            "responses": {"200": {"description": "CSV anonymisé"}},
        }},
        "/api/export/visitors.json": {"get": {
            "summary": "Export visiteurs JSON",
            "tags": ["Export"],
            "responses": {"200": {"description": "JSON avec metadata CC BY 4.0"}},
        }},
        "/api/export/observations.json": {"get": {
            "summary": "Export observations stellaires",
            "tags": ["Export"],
            "responses": {"200": {"description": "500 observations avec analyse IA"}},
        }},
        "/api/export/ephemerides.json": {"get": {
            "summary": "Export éphémérides JSON",
            "tags": ["Export"],
            "responses": {"200": {"description": "JSON scientifique avec metadata"}},
        }},
        "/api/health": {"get": {
            "summary": "Santé de l'API",
            "tags": ["Système"],
            "responses": {"200": {"description": "JSON health check"}},
        }},
    },
}


@bp.route("/api/docs")
def api_docs():
    return render_template("api_docs.html")


@bp.route("/api/spec.json")
def api_spec_json():
    return jsonify(API_SPEC)


@bp.route("/api/cache/status")
def api_cache_status():
    """Etat actuel du cache Redis : entrees, TTL, backend (admin/monitoring)."""
    return jsonify(cache_status())


@bp.route("/api/admin/circuit-breakers")
def api_admin_circuit_breakers():
    """Etat des circuit breakers - Bearer token requis (ASTROSCAN_ADMIN_TOKEN)."""
    auth = request.headers.get("Authorization", "")
    expected = (os.environ.get("ASTROSCAN_ADMIN_TOKEN") or "").strip()
    if expected and auth != f"Bearer {expected}":
        return jsonify({"error": "Unauthorized"}), 401
    statuses = cb_all_status()
    return jsonify({
        "ok": True,
        "circuit_breakers": statuses,
        "summary": {
            "total": len(statuses),
            "open": sum(1 for s in statuses if s["state"] == "OPEN"),
            "half_open": sum(1 for s in statuses if s["state"] == "HALF_OPEN"),
            "closed": sum(1 for s in statuses if s["state"] == "CLOSED"),
        },
    })



@bp.route("/api/version")
def api_version():
    """Version metadata for AstroScan."""
    from datetime import datetime
    return jsonify({
        "ok": True,
        "name": "AstroScan",
        "version": "1.0.0",
        "status": "production-ready",
        "timestamp": datetime.utcnow().isoformat(),
    })



@bp.route("/api/tle/status", methods=["GET"])
def api_tle_status():
    """Retourne l'etat actuel du cache TLE connecte/cache/simulation."""
    from station_web import TLE_CACHE
    try:
        return jsonify({
            "status": TLE_CACHE.get("status"),
            "source": TLE_CACHE.get("source"),
            "last_refresh_iso": TLE_CACHE.get("last_refresh_iso"),
            "count": TLE_CACHE.get("count"),
            "error": TLE_CACHE.get("error"),
        })
    except Exception as e:
        log.warning(f"/api/tle/status: {e}")
        return jsonify({
            "status": "error",
            "source": None,
            "last_refresh_iso": None,
            "count": 0,
            "error": str(e),
        })


@bp.route("/api/tle/active", methods=["GET"])
def api_tle_active():
    """Retourne les TLE actifs depuis le cache connecte/disque/simulation."""
    from station_web import TLE_CACHE
    try:
        return jsonify({
            "status": TLE_CACHE.get("status"),
            "source": TLE_CACHE.get("source"),
            "last_refresh_iso": TLE_CACHE.get("last_refresh_iso"),
            "count": TLE_CACHE.get("count"),
            "items": TLE_CACHE.get("items") or [],
            "error": TLE_CACHE.get("error"),
        })
    except Exception as e:
        log.warning(f"/api/tle/active: {e}")
        return jsonify({
            "status": "error",
            "source": None,
            "last_refresh_iso": None,
            "count": 0,
            "items": [],
            "error": str(e),
        })



@bp.route("/api/tle/full")
def api_tle_full():
    """Catalogue TLE complet (parsed depuis data/tle/active.tle)."""
    from station_web import _parse_tle_file, TLE_ACTIVE_PATH
    try:
        satellites = _parse_tle_file(TLE_ACTIVE_PATH)
        return jsonify({"satellites": satellites})
    except Exception as e:
        log.warning("api/tle/full: %s", e)
        return jsonify({"satellites": []})


@bp.route("/api/modules-status")
def api_modules_status():
    """Etat statique des modules AstroScan."""
    try:
        return jsonify({
            "ok": True,
            "modules": {
                "iss": True,
                "orbit": True,
                "dsn": True,
                "aurores": True,
                "apod": True,
                "aegis": True,
                "passages": True,
                "weather": True,
                "oracle": True,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
