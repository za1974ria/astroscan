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



@bp.route("/api/owner-ips", methods=["GET"])
def api_owner_ips_get():
    """Liste les IPs proprietaire (DB + env)."""
    import os
    from app.services.db_visitors import _get_db_visitors
    try:
        conn = _get_db_visitors()
        rows = conn.execute(
            "SELECT id, ip, label, added_at FROM owner_ips ORDER BY added_at DESC"
        ).fetchall()
        conn.close()
        result = [{"id": r[0], "ip": r[1], "label": r[2], "added_at": r[3]} for r in rows]
        env_ips = [x.strip() for x in (os.environ.get("ASTROSCAN_OWNER_IPS") or "").split(",") if x.strip()]
        return jsonify({"db_ips": result, "env_ips": env_ips})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@bp.route("/ready", methods=["GET"])
def ready():
    """Indique si le worker a fini de charger l'app."""
    try:
        from station_web import server_ready
        return jsonify({"ready": bool(server_ready)})
    except Exception:
        return jsonify({"ready": False})



@bp.route("/api/satellites")
def api_satellites():
    """Liste des satellites disponibles."""
    from station_web import list_satellites
    return jsonify({"available": list_satellites()})



@bp.route("/api/accuracy/history")
def api_accuracy_history():
    """Historique et stats de precision des predictions."""
    from station_web import get_accuracy_history, get_accuracy_stats
    return jsonify({
        "items": get_accuracy_history(),
        "stats": get_accuracy_stats(),
    })


# ── PASS 11 — Catalogue + V1 API (Domaines X, Y) ──────────────────────
@bp.route("/api/catalog")
def api_catalog():
    from modules.catalog import search_catalog
    from app.utils.cache import get_cached
    q = request.args.get("q", "")
    t = request.args.get("type", "")
    return jsonify(get_cached("catalog_" + q + t, 86400, lambda: search_catalog(q, t)))


@bp.route("/api/catalog/<obj_id>")
def api_catalog_object(obj_id):
    from modules.catalog import get_object
    obj = get_object(obj_id)
    if obj:
        return jsonify(obj)
    return jsonify({"error": "Objet non trouvé"}), 404


@bp.route("/api/v1/catalog")
def api_v1_catalog():
    from modules.catalog import search_catalog
    from datetime import datetime as _dt
    q = request.args.get("q", "")
    return jsonify({
        "timestamp": _dt.utcnow().isoformat(),
        "query": q,
        "results": search_catalog(q),
        "credit": "AstroScan-Chohra · ORBITAL-CHOHRA",
    })


@bp.route("/api/v1/asteroids")
def api_v1_asteroids():
    from modules.space_alerts import get_asteroid_alerts
    from app.utils.cache import get_cached
    from datetime import datetime as _dt
    data = get_cached("asteroids", 3600, get_asteroid_alerts)
    return jsonify({
        "timestamp": _dt.utcnow().isoformat(),
        "total_today": data.get("total_today", 0) if data else 0,
        "hazardous": data.get("alerts", []) if data else [],
        "source": "NASA NeoWs",
        "credit": "AstroScan-Chohra · ORBITAL-CHOHRA",
    })


@bp.route("/api/v1/iss")
def api_v1_iss():
    from modules.orbit_engine import get_iss_precise, get_iss_crew
    from datetime import datetime as _dt
    data = get_iss_precise()
    if data.get("error"):
        return jsonify({
            "object": "ISS",
            "error": data.get("error"),
            "position": None,
            "crew": [],
            "crew_count": 0,
        }), 503
    crew = get_iss_crew()
    sk = float(data.get("speed_kms", 7.66))
    return jsonify({
        "object": "ISS",
        "timestamp": _dt.utcnow().isoformat(),
        "position": {
            "latitude": data.get("lat", 0),
            "longitude": data.get("lon", 0),
            "altitude_km": data.get("alt_km", 408),
            "speed_kms": sk,
        },
        "velocity_kmh": round(sk * 3600.0, 1),
        "visibility": data.get("visibility", "nominal"),
        "orbits_today_estimate": data.get("orbits_today_estimate"),
        "orbital_period_min_approx": data.get("orbital_period_min_approx", 92),
        "crew": crew,
        "crew_count": len(crew) if isinstance(crew, list) else 0,
        "source": data.get("source", "Skyfield/SGP4"),
        "credit": "AstroScan-Chohra · ORBITAL-CHOHRA — https://astroscan.space",
    })


@bp.route("/api/v1/planets")
def api_v1_planets():
    """Positions héliocentriques temps réel via astropy. Cache 10 min."""
    from datetime import datetime as _dt, timezone as _tz
    from app.utils.cache import cache_get, cache_set
    cached = cache_get("v1_planets", 600)
    if cached is not None:
        return jsonify(cached)
    _PLANET_META = {
        "mercury": {"name": "Mercure", "diameter_km": 4879, "moons": 0, "type": "Tellurique"},
        "venus":   {"name": "Vénus",   "diameter_km": 12104, "moons": 0, "type": "Tellurique"},
        "earth":   {"name": "Terre",   "diameter_km": 12742, "moons": 1, "type": "Tellurique"},
        "mars":    {"name": "Mars",    "diameter_km": 6779,  "moons": 2, "type": "Tellurique"},
        "jupiter": {"name": "Jupiter", "diameter_km": 139820, "moons": 95, "type": "Gazeuse"},
        "saturn":  {"name": "Saturne", "diameter_km": 116460, "moons": 146, "type": "Gazeuse"},
        "uranus":  {"name": "Uranus",  "diameter_km": 50724,  "moons": 28, "type": "Gazeuse"},
        "neptune": {"name": "Neptune", "diameter_km": 49244,  "moons": 16, "type": "Gazeuse"},
    }
    try:
        from astropy.coordinates import get_body_barycentric
        from astropy.time import Time
        import astropy.units as u
        t = Time.now()
        planets = []
        for body_key, meta in _PLANET_META.items():
            try:
                pos = get_body_barycentric(body_key, t)
                dist_au = float(pos.norm().to(u.au).value)
                x = float(pos.x.to(u.au).value)
                y = float(pos.y.to(u.au).value)
                z = float(pos.z.to(u.au).value)
            except Exception:
                dist_au = None
                x = y = z = None
            row = dict(meta)
            row["distance_au"] = round(dist_au, 4) if dist_au is not None else None
            row["x_au"] = round(x, 4) if x is not None else None
            row["y_au"] = round(y, 4) if y is not None else None
            row["z_au"] = round(z, 4) if z is not None else None
            row["realtime"] = True
            planets.append(row)
        payload = {
            "timestamp": _dt.now(_tz.utc).isoformat(),
            "source": "astropy · DE432 ephemeris",
            "planets": planets,
            "credit": "AstroScan-Chohra · ORBITAL-CHOHRA",
        }
        cache_set("v1_planets", payload)
        return jsonify(payload)
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning("api_v1_planets astropy: %s", e)
        fallback = {
            "timestamp": _dt.now(_tz.utc).isoformat(),
            "source": "fallback_static",
            "planets": [
                {"name": "Mercure", "distance_au": 0.39, "diameter_km": 4879, "moons": 0, "type": "Tellurique", "realtime": False},
                {"name": "Vénus", "distance_au": 0.72, "diameter_km": 12104, "moons": 0, "type": "Tellurique", "realtime": False},
                {"name": "Terre", "distance_au": 1.0, "diameter_km": 12742, "moons": 1, "type": "Tellurique", "realtime": False},
                {"name": "Mars", "distance_au": 1.52, "diameter_km": 6779, "moons": 2, "type": "Tellurique", "realtime": False},
                {"name": "Jupiter", "distance_au": 5.2, "diameter_km": 139820, "moons": 95, "type": "Gazeuse", "realtime": False},
                {"name": "Saturne", "distance_au": 9.58, "diameter_km": 116460, "moons": 146, "type": "Gazeuse", "realtime": False},
                {"name": "Uranus", "distance_au": 19.2, "diameter_km": 50724, "moons": 28, "type": "Gazeuse", "realtime": False},
                {"name": "Neptune", "distance_au": 30.05, "diameter_km": 49244, "moons": 16, "type": "Gazeuse", "realtime": False},
            ],
            "credit": "AstroScan-Chohra · ORBITAL-CHOHRA",
        }
        return jsonify(fallback)
