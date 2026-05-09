"""Blueprint ISS — routes simples sans TLE_CACHE

Extrait de station_web.py lors de la PHASE 2B / Étape B3b (2026-05-02).

SCOPE B3b (5 routes) :
- /iss-tracker  : render_template
- /orbital      : render_template
- /orbital-map  : render_template + CESIUM_TOKEN
- /api/tle/sample, /api/tle/catalog : JSON hardcodés

Les autres routes ISS/TLE restent dans station_web.py jusqu'à
B3b-bis (lazy imports), B3c (TLE_CACHE accesseur), B-cache (services/cache_service),
et B-state (refonte fetch_tle_from_celestrak global TLE_CACHE).
"""
import os
import logging
from flask import Blueprint, jsonify, render_template

iss_bp = Blueprint('iss', __name__)
log = logging.getLogger(__name__)

# CESIUM_TOKEN — recalculé à l'appel pour cohérence avec station_web.py L.458
def _cesium_token():
    return os.getenv("CESIUM_TOKEN", "")


@iss_bp.route('/iss-tracker')
def iss_tracker_page():
    return render_template('iss_tracker.html')


@iss_bp.route('/orbital')
def orbital_dashboard():
    return render_template('orbital_dashboard.html')


@iss_bp.route('/orbital-map')
def orbital_map_page():
    return render_template('orbital_map.html', cesium_token=_cesium_token())


@iss_bp.route("/api/tle/sample")
def tle_sample():
    satellites = [
        {
            "name": "Hubble",
            "tle1": "1 20580U 90037B   24100.47588426  .00000856  00000+0  43078-4 0  9993",
            "tle2": "2 20580  28.4694  45.2957 0002837  48.3533 311.7862 15.09100244430766"
        },
        {
            "name": "NOAA 19",
            "tle1": "1 33591U 09005A   24100.17364847  .00000077  00000+0  66203-4 0  9996",
            "tle2": "2 33591  99.1954  60.9022 0014193 183.3210 176.7778 14.12414904786721"
        }
    ]
    return jsonify({"satellites": satellites})


@iss_bp.route("/api/tle/catalog")
def tle_catalog():
    """Catalog of satellites with TLE data; frontend may limit display count."""
    satellites = [
        {
            "name": "Hubble",
            "tle1": "1 20580U 90037B   24100.47588426  .00000856  00000+0  43078-4 0  9993",
            "tle2": "2 20580  28.4694  45.2957 0002837  48.3533 311.7862 15.09100244430766"
        },
        {
            "name": "NOAA 19",
            "tle1": "1 33591U 09005A   24100.17364847  .00000077  00000+0  66203-4 0  9996",
            "tle2": "2 33591  99.1954  60.9022 0014193 183.3210 176.7778 14.12414904786721"
        }
    ]
    return jsonify({"satellites": satellites})


# ── PASS 11 — Extensions ISS (Domaine I) ──────────────────────────────
@iss_bp.route("/api/iss/crew")
def api_iss_crew():
    """Équipage ISS — noms (open-notify / fallback), format UI iss_tracker."""
    from flask import jsonify as _jsonify
    try:
        from modules.orbit_engine import get_iss_crew
        raw = get_iss_crew()
        crew = []
        for c in raw or []:
            if isinstance(c, str):
                crew.append({"name": c, "photo_url": ""})
            elif isinstance(c, dict):
                crew.append({
                    "name": c.get("name") or "?",
                    "photo_url": c.get("photo_url") or "",
                })
        return _jsonify({"ok": True, "crew": crew})
    except Exception as e:
        log.warning("api/iss/crew: %s", e)
        return _jsonify({"ok": False, "crew": [], "error": str(e)})


@iss_bp.route("/api/iss/orbit")
def api_iss_orbit():
    """Trajectoire ISS future sur 90 minutes (pas 60s) via SGP4."""
    from flask import jsonify as _jsonify
    try:
        import math as _math
        import datetime as _dt
        from sgp4.api import Satrec, jday
        from modules.iss_passes import fetch_iss_tle

        try:
            _name, tle1, tle2 = fetch_iss_tle()
        except Exception:
            tle1 = tle2 = None

        if not tle1 or not tle2:
            return _jsonify({"ok": False, "message": "TLE ISS indisponible", "points": [], "count": 0})

        sat = Satrec.twoline2rv(tle1, tle2)
        now = _dt.datetime.now(_dt.timezone.utc)
        points = []

        for sec in range(0, 90 * 60 + 1, 60):
            t = now + _dt.timedelta(seconds=sec)
            jd, fr = jday(
                t.year, t.month, t.day,
                t.hour, t.minute, t.second + t.microsecond / 1e6,
            )
            err, r, _v = sat.sgp4(jd, fr)
            if err != 0:
                continue
            rx, ry, rz = r[0], r[1], r[2]
            lon = _math.degrees(_math.atan2(ry, rx))
            hyp = _math.sqrt(rx * rx + ry * ry)
            lat = _math.degrees(_math.atan2(rz, hyp))
            alt = _math.sqrt(rx * rx + ry * ry + rz * rz) - 6371.0
            if not (_math.isfinite(lat) and _math.isfinite(lon) and _math.isfinite(alt)):
                continue
            points.append({
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "alt": round(alt, 2),
            })
        return _jsonify({"ok": True, "points": points, "count": len(points)})
    except Exception as e:
        log.warning("api/iss/orbit: %s", e)
        return _jsonify({"ok": False, "message": str(e), "points": [], "count": 0})


@iss_bp.route("/api/iss/stream")
def iss_stream():
    """Stream ISS position via SSE — mise à jour toutes les 3s."""
    from flask import Response

    def generate():
        import time as _t
        import json as _json
        import requests as _r
        while True:
            try:
                resp = _r.get(
                    "https://api.wheretheiss.at/v1/satellites/25544",
                    timeout=4,
                )
                d = resp.json()
                payload = _json.dumps({
                    "lat": round(d["latitude"], 4),
                    "lon": round(d["longitude"], 4),
                    "alt": round(d["altitude"], 1),
                    "vel": round(d["velocity"], 1),
                    "ts": int(d["timestamp"]),
                    "vis": d.get("visibility", "unknown"),
                })
                yield f"data: {payload}\n\n"
            except Exception as e:
                yield 'data: {"error": "' + str(e) + '"}\n\n'
            _t.sleep(3)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@iss_bp.route("/api/iss-passes")
def api_iss_passes_n2yo():
    """Prochains passages ISS via N2YO (lat/lon, défaut Tlemcen)."""
    import os as _os
    import urllib.request
    from flask import jsonify as _jsonify, request as _req
    from app.services.http_client import _safe_json_loads
    try:
        from services.circuit_breaker import CB_N2YO
    except ImportError:
        CB_N2YO = None

    try:
        lat = _req.args.get("lat", "34.8")
        lon = _req.args.get("lon", "1.3")
        key = _os.environ.get("N2YO_API_KEY", "DEMO")
        url = (
            f"https://api.n2yo.com/rest/v1/satellite/visualpasses/25544/"
            f"{lat}/{lon}/0/7/300/&apiKey={key}"
        )

        def _fetch_n2yo():
            req = urllib.request.Request(url, headers={"User-Agent": "AstroScan/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return _safe_json_loads(r.read().decode("utf-8"), "n2yo_iss_passes")

        if CB_N2YO is not None:
            data = CB_N2YO.call(_fetch_n2yo, fallback=None)
        else:
            try:
                data = _fetch_n2yo()
            except Exception:
                data = None
        if data is None:
            return _jsonify({
                "passes": [], "count": 0,
                "source": "fallback (N2YO circuit ouvert)",
            })
        if not isinstance(data, dict):
            return _jsonify({"passes": [], "count": 0, "error": "invalid_response"})
        passes = []
        for p in data.get("passes", []):
            passes.append({
                "startUTC": p["startUTC"],
                "startAzCompass": p.get("startAzCompass", ""),
                "maxEl": p.get("maxEl", 0),
                "duration": p.get("duration", 0),
                "mag": p.get("mag", 0),
            })
        return _jsonify({"passes": passes, "count": len(passes)})
    except Exception as e:
        return _jsonify({"error": str(e)}), 500


@iss_bp.route("/api/passages-iss")
def api_passages_iss():
    """Prochains passages ISS — lecture directe du fichier static/passages_iss.json."""
    import os as _os
    from flask import jsonify as _jsonify
    from app.config import PASSAGES_ISS_JSON

    log.info("passages-iss: GET /api/passages-iss")
    path = PASSAGES_ISS_JSON
    try:
        if not _os.path.isfile(path):
            log.warning("passages-iss: fichier manquant")
            return _jsonify({
                "error": "not_found",
                "message": "passages_iss.json introuvable",
                "prochains_passages": [],
            }), 404
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        import json as _json
        data = _json.loads(raw) if raw else {"prochains_passages": []}
        return _jsonify(data)
    except Exception as e:
        log.warning("passages-iss: %s", e)
        return _jsonify({
            "error": "read_error",
            "message": str(e),
            "prochains_passages": [],
        }), 500


# ── PASS 14 — ISS compute (SGP4 ground-track + passes) ───────────────
@iss_bp.route("/api/iss/ground-track")
def api_iss_ground_track():
    """Orbite projetée au sol pour la carte ISS Tracker (cache 5 min)."""
    from flask import jsonify as _jsonify
    from app.utils.cache import get_cached
    from app.services.iss_compute import compute_iss_ground_track
    try:
        data = get_cached("iss_ground_track_v1", 300, compute_iss_ground_track)
        return _jsonify(data if isinstance(data, dict) else {"track": []})
    except Exception as e:
        log.warning("api/iss/ground-track: %s", e)
        return _jsonify({"track": [], "error": str(e)})


@iss_bp.route("/api/iss/passes")
def api_iss_passes_tlemcen():
    """Prochains passages ISS sur Tlemcen — SGP4 local, cache 2h."""
    from flask import jsonify as _jsonify
    from app.utils.cache import get_cached
    from app.services.iss_compute import compute_iss_passes_tlemcen
    try:
        data = get_cached("iss_passes_rich", 7200, compute_iss_passes_tlemcen)
        return _jsonify(data)
    except Exception as e:
        log.warning("api/iss/passes: %s", e)
        return _jsonify({"error": str(e)}), 500


@iss_bp.route("/api/iss/passes/<float:lat>/<float:lon>")
def api_iss_passes_observer(lat, lon):
    """Prochains passages pour coordonnées (ville) — même moteur que Tlemcen."""
    from flask import jsonify as _jsonify
    from app.utils.cache import get_cached
    from app.services.iss_compute import compute_iss_passes_for_observer
    if abs(lat) > 90 or abs(lon) > 180:
        return _jsonify({
            "ok": False, "passes": [], "error": "coordonnées invalides",
        }), 400
    cache_key = "iss_passes_obs_{:.4f}_{:.4f}".format(lat, lon)

    def _fn():
        return compute_iss_passes_for_observer(lat, lon)

    try:
        data = get_cached(cache_key, 7200, _fn)
        return _jsonify({"ok": True, "passes": data if isinstance(data, list) else []})
    except Exception as e:
        log.warning("api/iss/passes/observer: %s", e)
        return _jsonify({"ok": False, "passes": [], "error": str(e)}), 500


# ── PASS 16 — /api/iss canonique (DI 16 args via lazy-import) ──────────
@iss_bp.route("/api/iss")
def api_iss():
    """Endpoint canonique ISS — délègue à app/routes/iss.api_iss_impl avec DI."""
    import os as _os
    import time as _time
    from datetime import datetime as _datetime, timezone as _timezone
    from flask import jsonify as _jsonify
    from app.routes.iss import api_iss_impl
    from app.utils.cache import (
        cache_cleanup as _cache_cleanup,
        cache_get as _cache_get,
        cache_set as _cache_set,
        get_cached as _get_cached,
    )
    # Helpers + globals encore en monolithe — lazy import depuis station_web
    from station_web import (
        system_log,
        _fetch_iss_live, _get_iss_crew,
        propagate_tle_debug,
        TLE_CACHE, TLE_ACTIVE_PATH,
        _parse_tle_file, _emit_diag_json,
    )
    return api_iss_impl(
        cache_cleanup=_cache_cleanup,
        system_log=system_log,
        cache_get=_cache_get,
        jsonify=_jsonify,
        _cached=_get_cached,
        _fetch_iss_live=_fetch_iss_live,
        _get_iss_crew=_get_iss_crew,
        cache_set=_cache_set,
        time_module=_time,
        propagate_tle_debug=propagate_tle_debug,
        datetime_cls=_datetime,
        timezone_cls=_timezone,
        TLE_CACHE=TLE_CACHE,
        TLE_ACTIVE_PATH=TLE_ACTIVE_PATH,
        _parse_tle_file=_parse_tle_file,
        _emit_diag_json=_emit_diag_json,
        os_module=_os,
    )
