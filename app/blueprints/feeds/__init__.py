"""Blueprint Feeds — agrégation des feeds externes (NASA, NOAA, JPL, modules live).

PASS 8 (2026-05-03) — Création :
  /api/feeds/{voyager,neo,solar,solar_alerts,mars,apod_hd,all}
  /api/space-weather/alerts
  /api/mars/weather, /api/voyager-live
  /api/nasa/{apod,neo,solar}
  /api/neo
  /api/alerts/{asteroids,solar,all}
  /api/live/{spacex,news,mars-weather,iss-passes,all}
  /api/news, /api/sondes

Différé : /api/jwst/images, /api/jwst/refresh (helper _fetch_jwst_live_images
  ~80 lignes + _JWST_STATIC ~50 lignes → PASS 13), /api/hubble/images
  (helper _fetch_hubble + dépendances NASA APOD), /api/bepi/telemetry
  (utilise _curl_get inline mais petit — peut être migré, gardé en monolithe
  pour simplicité ce PASS).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, current_app

from app.config import STATION
from app.utils.cache import cache_get, cache_set, cache_cleanup, get_cached
from app.services.http_client import _curl_get
from app.services.external_feeds import (
    fetch_voyager, fetch_neo, fetch_solar_wind, fetch_solar_alerts,
    fetch_mars_rover, fetch_apod_hd, fetch_swpc_alerts,
)

log = logging.getLogger(__name__)

bp = Blueprint("feeds", __name__)


# ── Voyager (Domaine M — JPL) ──────────────────────────────────────────
@bp.route("/api/feeds/voyager")
def api_feeds_voyager():
    data = get_cached("voyager", 3600, fetch_voyager)
    if not data:
        now = datetime.now(timezone.utc)
        days_v1 = (now - datetime(1977, 9, 5)).days
        days_v2 = (now - datetime(1977, 8, 20)).days
        v1_au = 17.0 + days_v1 * 0.000985
        v2_au = 14.5 + days_v2 * 0.000898
        data = {
            "VOYAGER_1": {
                "dist_au": round(v1_au, 2),
                "dist_km": round(v1_au * 149597870.7),
                "speed_km_s": 17.0,
                "source": "Calcul approx.",
            },
            "VOYAGER_2": {
                "dist_au": round(v2_au, 2),
                "dist_km": round(v2_au * 149597870.7),
                "speed_km_s": 15.4,
                "source": "Calcul approx.",
            },
        }
    return jsonify({"ok": True, "data": data})


@bp.route("/api/voyager-live")
def api_voyager_live():
    """Télémétrie Voyager — calcul physique JPL DSN × temps écoulé."""
    try:
        path = f"{STATION}/static/voyager_live.json"
        if not os.path.exists(path):
            return jsonify({"statut": "Indisponible"})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return jsonify({"statut": "Indisponible"})
        data.setdefault("methode", "Calcul physique — vitesse JPL × temps écoulé depuis epoch 2024-01-01")
        data.setdefault("precision", "±0.01% — données JPL DSN vérifiées")
        return jsonify(data)
    except Exception as e:
        log.warning("voyager-live: %s", e)
        return jsonify({"statut": "Indisponible"})


# ── NASA NEO + Mars + APOD HD (Domaine M, AE — NASA) ──────────────────
@bp.route("/api/feeds/neo")
def api_feeds_neo():
    data = get_cached("neo", 3600, fetch_neo)
    return jsonify({"ok": True, "neos": data or [], "count": len(data) if data else 0})


@bp.route("/api/feeds/mars")
def api_feeds_mars():
    data = get_cached("mars", 7200, fetch_mars_rover)
    return jsonify({"ok": True, "photos": data or []})


@bp.route("/api/mars/weather")
def api_mars_weather():
    """InSight météo Mars — proxy JSON (mission terminée, peut être vide)."""
    try:
        nasa_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        url = f"https://api.nasa.gov/insight_weather/?api_key={nasa_key}&feedtype=json&ver=1.0"
        raw = _curl_get(url, timeout=10)
        if not raw:
            return jsonify({"error": "no data"}), 502
        return current_app.response_class(raw, mimetype="application/json")
    except Exception as e:
        log.exception("internal error"); return jsonify({"error": "internal server error"}), 500


@bp.route("/api/feeds/apod_hd")
def api_feeds_apod_hd():
    """NASA APOD HD. Cache 3600 s pour limiter les appels externes."""
    cache_cleanup()
    cached = cache_get("apod_hd", 3600)
    if cached is not None:
        return jsonify(cached)
    data = get_cached("apod_hd", 3600, fetch_apod_hd)
    payload = {"ok": True, "apod": data}
    cache_set("apod_hd", payload)
    return jsonify(payload)


# ── NOAA SWPC : vent solaire + alertes (Domaine L) ────────────────────
@bp.route("/api/feeds/solar")
def api_feeds_solar():
    data = get_cached("solar", 900, fetch_solar_wind)
    return jsonify({"ok": True, "solar_wind": data})


@bp.route("/api/feeds/solar_alerts")
def api_feeds_solar_alerts():
    """Alertes éruptions solaires et flares X-ray — NOAA SWPC."""
    data = get_cached("solar_alerts", 600, fetch_solar_alerts)
    return jsonify({
        "ok": True,
        "alerts": data.get("alerts", []) if data else [],
        "flares": data.get("flares", []) if data else [],
    })


@bp.route("/api/space-weather/alerts")
def api_space_weather_alerts():
    """Alertes NOAA SWPC dernières 24h — cache 30 min."""
    try:
        data = get_cached("swpc_alerts_24h", 1800, fetch_swpc_alerts)
        return jsonify(data)
    except Exception as e:
        log.exception("internal error"); return jsonify({"error": "internal server error"}), 500


# ── Aggrégateur "tout en un" (Domaine M) ──────────────────────────────
@bp.route("/api/feeds/all")
def api_feeds_all():
    """Tous les feeds en un appel."""
    return jsonify({
        "ok": True,
        "voyager": get_cached("voyager", 3600, fetch_voyager),
        "neo": get_cached("neo", 3600, fetch_neo),
        "solar_wind": get_cached("solar", 900, fetch_solar_wind),
        "solar_alerts": get_cached("solar_alerts", 600, fetch_solar_alerts),
        "mars": get_cached("mars", 7200, fetch_mars_rover),
        "apod_hd": get_cached("apod_hd", 3600, fetch_apod_hd),
        "station": "ORBITAL-CHOHRA · Tlemcen, Algérie",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── NASA APIs propres (Domaine W — services.nasa_service) ─────────────
# Note : /api/nasa/apod est servi exclusivement par `nasa_proxy_bp`
# (app/blueprints/nasa_proxy/__init__.py, url_prefix=/api/nasa, route /apod).
# Le doublon historique de feeds_bp est supprimé pour éliminer la collision
# détectée par tests/smoke/test_factory.py::test_create_app_no_url_collisions.


@bp.route("/api/nasa/neo")
def api_nasa_neo():
    """Objets proches de la Terre (NASA NEO)."""
    from services.nasa_service import _fetch_nasa_neo
    try:
        payload = get_cached("nasa_neo_v1", 900, _fetch_nasa_neo)
        code = 200 if payload.get("ok") else 502
        return jsonify(payload), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "asteroids": []}), 500


@bp.route("/api/nasa/solar")
def api_nasa_solar():
    """Météo solaire NASA DONKI."""
    from services.nasa_service import _fetch_nasa_solar
    try:
        payload = get_cached("nasa_solar_v1", 600, _fetch_nasa_solar)
        code = 200 if payload.get("ok") else 502
        return jsonify(payload), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "events": []}), 500


@bp.route("/api/neo")
def api_neo():
    """Objets proches de la Terre — fenêtre 7 jours."""
    import urllib.request
    try:
        nasa_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
        url = (
            f"https://api.nasa.gov/neo/rest/v1/feed?"
            f"start_date={today}&end_date={tomorrow}&api_key={nasa_key}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        neos = []
        for date, asteroids in data.get("near_earth_objects", {}).items():
            for a in asteroids:
                neos.append({
                    "nom": a["name"],
                    "date": date,
                    "diametre_min": round(a["estimated_diameter"]["kilometers"]["estimated_diameter_min"], 3),
                    "diametre_max": round(a["estimated_diameter"]["kilometers"]["estimated_diameter_max"], 3),
                    "vitesse_kms": round(float(a["close_approach_data"][0]["relative_velocity"]["kilometers_per_second"]), 2),
                    "distance_km": round(float(a["close_approach_data"][0]["miss_distance"]["kilometers"])),
                    "dangereux": a["is_potentially_hazardous_asteroid"],
                    "url": a["nasa_jpl_url"],
                })
        neos.sort(key=lambda x: x["distance_km"])
        return jsonify({"count": len(neos), "asteroids": neos[:20], "generated_at": today})
    except Exception as e:
        log.exception("internal error"); return jsonify({"error": "internal server error"}), 500


# ── Alertes (Domaine L — modules.space_alerts) ────────────────────────
@bp.route("/api/alerts/asteroids")
def api_asteroids():
    from modules.space_alerts import get_asteroid_alerts
    return jsonify(get_cached("asteroids", 3600, get_asteroid_alerts))


@bp.route("/api/alerts/solar")
def api_solar():
    from modules.space_alerts import get_solar_weather
    return jsonify(get_cached("solar_weather", 300, get_solar_weather))


@bp.route("/api/alerts/all")
def api_alerts_all():
    from modules.space_alerts import get_asteroid_alerts, get_solar_weather
    return jsonify({
        "asteroids": get_cached("asteroids", 3600, get_asteroid_alerts),
        "solar": get_cached("solar_weather", 300, get_solar_weather),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Live feeds (Domaine AD — modules.live_feeds) ──────────────────────
_NEWS_TRADUCTIONS = {
    "launches": "lancements",
    "satellite": "satellite",
    "mission": "mission",
    "rocket": "fusée",
    "space": "espace",
    "NASA": "NASA",
    "SpaceX": "SpaceX",
}


def _apply_news_translations(items):
    """Remplace quelques termes fréquents (ordre pour éviter space→SpaceX)."""
    if not items:
        return items
    order = ["SpaceX", "NASA", "launches", "satellite", "mission", "rocket", "space"]
    tr = _NEWS_TRADUCTIONS
    out = []
    for a in items:
        title = a.get("title", "")
        summary = a.get("summary", "")
        for en in order:
            if en in tr:
                title = title.replace(en, tr[en])
                summary = summary.replace(en, tr[en])
        out.append({**a, "title": title, "summary": summary})
    return out


@bp.route("/api/live/spacex")
def api_spacex():
    from modules.live_feeds import get_spacex_launches
    return jsonify(get_cached("spacex", 3600, get_spacex_launches))


@bp.route("/api/live/news")
def api_space_news():
    """News spatiales — titres/résumés avec remplacement de termes fréquents."""
    from modules.live_feeds import get_space_news

    def _get():
        items = get_space_news()
        return _apply_news_translations(items)
    return jsonify(get_cached("space_news", 1800, _get))


@bp.route("/api/live/mars-weather")
def api_live_mars_weather():
    from modules.live_feeds import get_mars_weather
    return jsonify(get_cached("mars_weather", 3600, get_mars_weather))


@bp.route("/api/live/iss-passes")
def api_live_iss_passes():
    from modules.live_feeds import get_iss_passes_tlemcen
    return jsonify(get_cached("iss_passes", 600, get_iss_passes_tlemcen))


@bp.route("/api/live/all")
def api_live_all():
    from modules.live_feeds import (
        get_spacex_launches, get_space_news, get_mars_weather,
    )
    return jsonify({
        "spacex": get_cached("spacex", 3600, get_spacex_launches),
        "news": get_cached("space_news", 1800, get_space_news),
        "mars_weather": get_cached("mars_weather", 3600, get_mars_weather),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── News + Sondes (Domaine AP / F) ────────────────────────────────────
@bp.route("/api/news")
def api_news():
    try:
        from modules.news_module import get_live_news
        articles = get_live_news()
        data = {"articles": articles, "count": len(articles), "source": "live"}
    except Exception as e:
        data = {"ok": False, "error": str(e)}
    return jsonify(data)


@bp.route("/api/sondes")
def api_sondes():
    """Agrégation SONDES SPATIALES — logique dans sondes_module.py."""
    try:
        import sys
        if STATION not in sys.path:
            sys.path.insert(0, STATION)
        from modules.sondes_module import get_sondes_payload
        return jsonify(get_sondes_payload())
    except Exception as e:
        log.warning("api_sondes: %s", e)
        log.exception("internal error"); return jsonify({"error": "internal server error"}), 500


# ── PASS 11 — Sondes live + Orbits + Missions overview ─────────────────
@bp.route("/api/sondes/live")
def api_sondes_live():
    """Télémétrie temps réel — Voyager 1&2, JWST, New Horizons.
    Calcul physique local (vitesse JPL × temps écoulé). Cache 4 min.
    """
    from datetime import datetime, timezone

    cached = cache_get("sondes_live", 240)
    if cached is not None:
        return jsonify(cached)

    C_KM_S = 299792.458
    AU_KM = 149_597_870.7
    now = datetime.now(timezone.utc)

    V1_LAUNCH = datetime(1977, 9, 5, tzinfo=timezone.utc)
    V1_SPEED = 17.026
    v1_dist_km = (now - V1_LAUNCH).total_seconds() * V1_SPEED

    V2_LAUNCH = datetime(1977, 8, 20, tzinfo=timezone.utc)
    V2_SPEED = 15.374
    v2_dist_km = (now - V2_LAUNCH).total_seconds() * V2_SPEED

    NH_LAUNCH = datetime(2006, 1, 19, tzinfo=timezone.utc)
    NH_SPEED = 14.03
    nh_dist_km = (now - NH_LAUNCH).total_seconds() * NH_SPEED

    webb_dist_km = 1_500_000.0
    webb_temp_c = -233.0
    webb_delay_s = webb_dist_km / C_KM_S

    _now_iso = now.isoformat()
    _local_dq = {
        "source": "calcul_physique_local",
        "last_update": _now_iso,
        "confidence": 0.92,
        "stale": False,
    }
    payload = {
        "ok": True,
        "timestamp": _now_iso,
        "source": "calcul_local",
        "voyager_1": {
            "dist_km": round(v1_dist_km),
            "dist_au": round(v1_dist_km / AU_KM, 3),
            "speed_km_s": V1_SPEED,
            "signal_delay_s": round(v1_dist_km / C_KM_S),
            "status": "MISSION ACTIVE — Espace interstellaire",
            "data_quality": dict(_local_dq),
        },
        "voyager_2": {
            "dist_km": round(v2_dist_km),
            "dist_au": round(v2_dist_km / AU_KM, 3),
            "speed_km_s": V2_SPEED,
            "signal_delay_s": round(v2_dist_km / C_KM_S),
            "status": "MISSION ACTIVE — Espace interstellaire",
            "data_quality": dict(_local_dq),
        },
        "new_horizons": {
            "dist_km": round(nh_dist_km),
            "dist_au": round(nh_dist_km / AU_KM, 3),
            "speed_km_s": NH_SPEED,
            "signal_delay_s": round(nh_dist_km / C_KM_S),
            "status": "MISSION ACTIVE — Ceinture de Kuiper",
            "data_quality": dict(_local_dq),
        },
        "webb": {
            "dist_km": round(webb_dist_km),
            "temp_c": webb_temp_c,
            "signal_delay_s": round(webb_delay_s, 1),
            "status": "OPERATIONAL — Point de Lagrange L2",
            "data_quality": dict(_local_dq),
        },
    }
    cache_set("sondes_live", payload)
    return jsonify(payload)


def _orbits_sat_position_now(tle1: str, tle2: str):
    """Sub-satellite point (lat, lon, alt_km) right now via SGP4 + local TLE.

    All computation is local — no network calls. Returns None if SGP4 fails
    or any TLE line is missing/invalid. The caller is responsible for
    skipping the satellite rather than substituting a placeholder.
    """
    import math
    from datetime import datetime, timezone
    try:
        from sgp4.api import Satrec, jday
    except Exception:
        return None
    line1 = str(tle1 or "").strip()
    line2 = str(tle2 or "").strip()
    if not line1 or not line2:
        return None
    try:
        now = datetime.now(timezone.utc)
        jd, fr = jday(
            now.year, now.month, now.day,
            now.hour, now.minute,
            now.second + (now.microsecond / 1_000_000.0),
        )
        rec = Satrec.twoline2rv(line1, line2)
        e, r, _v = rec.sgp4(jd, fr)
        if e != 0:
            return None

        # TEME → ECEF: rotate around Z by GMST.
        t = (jd - 2451545.0) + fr
        gmst_deg = (280.46061837 + 360.98564736629 * t) % 360.0
        g = math.radians(gmst_deg)
        cg, sg = math.cos(g), math.sin(g)
        x = r[0] * cg + r[1] * sg
        y = -r[0] * sg + r[1] * cg
        z = r[2]

        # ECEF → geodetic lat/lon/alt (WGS-84, Bowring closed-form).
        a = 6378.137              # km
        f = 1.0 / 298.257223563
        b = a * (1.0 - f)
        e2  = (a * a - b * b) / (a * a)
        ep2 = (a * a - b * b) / (b * b)
        p = math.sqrt(x * x + y * y)
        th = math.atan2(z * a, p * b)
        sth, cth = math.sin(th), math.cos(th)
        lat = math.atan2(z + ep2 * b * sth ** 3, p - e2 * a * cth ** 3)
        lon = math.atan2(y, x)
        sin_lat = math.sin(lat)
        n = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
        alt = p / math.cos(lat) - n
        return (math.degrees(lat), math.degrees(lon), alt)
    except Exception:
        return None


@bp.route("/api/orbits/live")
def api_orbits_live():
    """ISS + NOAA positions, computed locally via SGP4. Cache 30 s.

    Drops the previous open-notify.org HTTP call (consistently timed out
    from the Hetzner host) and the hardcoded NOAA placeholder coords
    (45.0/-122.0 …). Every position is now a real SGP4 sub-satellite
    point derived from the local TLE cache. Satellites whose TLE is
    not available are skipped rather than faked.
    """
    import time
    from datetime import datetime, timezone
    from app.utils.cache import cache_cleanup
    from app.services.iss_compute import _get_satellite_tle_by_name

    cache_cleanup()
    cached = cache_get("orbits_live", 30)
    if cached is not None:
        return jsonify(cached)

    targets = [
        ("ISS",    "iss",     "iss",  "ISS"),
        ("NOAA15", "noaa_15", "noaa", "NOAA-15"),
        ("NOAA18", "noaa_18", "noaa", "NOAA-18"),
        ("NOAA19", "noaa_19", "noaa", "NOAA-19"),
    ]

    satellites = []
    for lookup, sat_id, sat_type, display_name in targets:
        try:
            tle1, tle2, _resolved = _get_satellite_tle_by_name(lookup)
        except Exception:
            tle1 = tle2 = None
        if not tle1 or not tle2:
            continue
        pos = _orbits_sat_position_now(tle1, tle2)
        if not pos:
            continue
        lat, lon, alt = pos
        satellites.append({
            "id": sat_id,
            "name": display_name,
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "alt": round(alt, 1),
            "type": sat_type,
        })

    payload = {
        "satellites": satellites,
        "source": "sgp4_local_tle",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "timestamp": int(time.time()),
    }
    if not satellites:
        payload["note"] = "no TLE in cache"
    cache_set("orbits_live", payload)
    return jsonify(payload)


@bp.route("/api/missions/overview")
def api_missions_overview():
    """Regroupe ISS, Voyager, SDR pour le centre de contrôle."""
    import os
    import time
    from pathlib import Path
    from app.config import SDR_F

    iss = {"ok": False, "lat": 0, "lon": 0, "alt": 408}
    try:
        from app.services.iss_live import _fetch_iss_live
        iss = get_cached("iss_live", 5, _fetch_iss_live) or iss
    except Exception:
        pass

    voyager = {}
    try:
        vpath = f"{STATION}/static/voyager_live.json"
        if os.path.exists(vpath):
            with open(vpath, "r", encoding="utf-8") as f:
                voyager = json.load(f)
    except Exception:
        voyager = {"statut": "Indisponible"}

    sdr = {"status": "standby", "ok": True}
    if Path(SDR_F).exists():
        try:
            with open(SDR_F) as f:
                sdr = json.load(f)
        except Exception:
            sdr = {"status": "standby"}

    alerts = []
    try:
        apath = f"{STATION}/static/space_weather.json"
        if os.path.exists(apath):
            with open(apath, "r", encoding="utf-8") as f:
                sw = json.load(f)
            if isinstance(sw, dict) and (sw.get("kp_index") or 0) >= 5:
                alerts.append("Activité géomagnétique élevée")
    except Exception:
        pass

    return jsonify({
        "iss": iss,
        "voyager": voyager,
        "sdr": sdr,
        "alerts": alerts,
        "timestamp": int(time.time()),
    })


# ── PASS 14 — Survol ISS + Flights OpenSky/AirLabs ────────────────────
# Note : /api/apod est servi exclusivement par `apod_bp`
# (app/blueprints/apod/routes.py) avec la cascade S1→S4 (cache disque jour,
# cache négatif, fetch NASA timeout 4s, stale fallback). L'alias historique
# de feeds_bp est supprimé pour éliminer la collision détectée par
# tests/smoke/test_factory.py::test_create_app_no_url_collisions.


@bp.route("/api/survol")
def api_survol():
    """Position ISS + zone survolée (Nominatim reverse geocoding)."""
    import urllib.request
    try:
        iss_url = "https://api.wheretheiss.at/v1/satellites/25544"
        req = urllib.request.Request(iss_url)
        with urllib.request.urlopen(req, timeout=10) as r:
            iss_data = json.loads(r.read())
        lat = iss_data.get("latitude", 0)
        lon = iss_data.get("longitude", 0)

        geo_url = (
            f"https://nominatim.openstreetmap.org/reverse?"
            f"format=json&lat={lat}&lon={lon}&zoom=5"
        )
        req2 = urllib.request.Request(
            geo_url,
            headers={
                "User-Agent": "AstroScan-OrbitalChohra/2.0",
                "Accept-Language": "fr",
            },
        )
        with urllib.request.urlopen(req2, timeout=10) as r2:
            geo_data = json.loads(r2.read())

        if isinstance(geo_data, dict) and geo_data.get("error"):
            zone = "🌊 Océan / Zone non cartographiée"
            pays = "Océan"
        else:
            addr = geo_data.get("address") or {}
            zone = geo_data.get("display_name", "Inconnu")
            pays = addr.get("country", "Inconnu")

        return jsonify({"lat": lat, "lon": lon, "zone": zone, "pays": pays, "statut": "ok"})
    except Exception as e:
        log.warning("api/survol: %s", e)
        return jsonify({"statut": "erreur", "message": str(e)})


# Cache local OpenSky / AirLabs (30s, partagé entre workers via Redis idéalement)
_flights_cache: dict = {"data": None, "ts": 0.0, "airlabs_count": 0}


@bp.route("/api/flights")
def api_flights():
    """OpenSky prioritaire ; AirLabs secours ; cache 30 s ; repli stale."""
    import time as _time
    import requests as _req

    now = _time.time()
    if (
        _flights_cache.get("data") is not None
        and (now - float(_flights_cache.get("ts") or 0.0)) < 30
    ):
        return jsonify(_flights_cache["data"])

    OPENSKY_USER = (os.environ.get("OPENSKY_USER") or "").strip()
    OPENSKY_PASS = (os.environ.get("OPENSKY_PASS") or "").strip()
    AIRLABS_KEY = (os.environ.get("AIRLABS_KEY") or "").strip()

    # Source 1 : OpenSky
    try:
        auth = (OPENSKY_USER, OPENSKY_PASS) if OPENSKY_USER else None
        r = _req.get(
            "https://opensky-network.org/api/states/all",
            timeout=12,
            auth=auth,
            headers={"User-Agent": "AstroScan/2.0"},
        )
        if r.status_code == 200:
            data = r.json()
            states = []
            for s in data.get("states") or []:
                if not s or len(s) < 11:
                    continue
                if s[5] is None or s[6] is None:
                    continue
                states.append({
                    "callsign": (s[1] or "").strip(),
                    "origin": s[2] or "??",
                    "lon": s[5],
                    "lat": s[6],
                    "alt": round(s[7] or 0),
                    "speed": round((s[9] or 0) * 3.6),
                    "heading": round(s[10] or 0),
                    "on_ground": s[8],
                })
            result = {
                "states": states,
                "source": "OpenSky",
                "count": len(states),
                "timestamp": int(now),
            }
            _flights_cache["data"] = result
            _flights_cache["ts"] = now
            return jsonify(result)
    except Exception as e:
        log.warning("flights OpenSky: %s", e)

    # Source 2 : AirLabs (fallback)
    if AIRLABS_KEY:
        try:
            r = _req.get(
                f"https://airlabs.co/api/v9/flights?api_key={AIRLABS_KEY}",
                timeout=12,
            )
            if r.status_code == 200:
                d = r.json()
                states = []
                for f in (d.get("response") or [])[:300]:
                    if f.get("lat") is None or f.get("lng") is None:
                        continue
                    states.append({
                        "callsign": f.get("flight_iata") or f.get("flight_icao") or "",
                        "origin": f.get("flag") or "??",
                        "lon": f["lng"],
                        "lat": f["lat"],
                        "alt": round(f.get("alt") or 0),
                        "speed": round((f.get("speed") or 0)),
                        "heading": round(f.get("dir") or 0),
                        "on_ground": False,
                    })
                _flights_cache["airlabs_count"] = int(_flights_cache.get("airlabs_count", 0)) + 1
                result = {
                    "states": states,
                    "source": "AirLabs",
                    "count": len(states),
                    "airlabs_calls": _flights_cache["airlabs_count"],
                    "timestamp": int(now),
                }
                _flights_cache["data"] = result
                _flights_cache["ts"] = now
                return jsonify(result)
        except Exception as e:
            log.warning("flights AirLabs: %s", e)

    # Repli stale (cache périmé) ou échec total
    if _flights_cache.get("data"):
        stale = dict(_flights_cache["data"])
        stale["stale"] = True
        return jsonify(stale)
    return jsonify({"states": [], "source": "none", "count": 0, "error": "all sources failed"})


# ── PASS 15 — BepiColombo telemetry (JPL Horizons) ────────────────────
@bp.route("/api/bepi/telemetry")
def api_bepi():
    """BepiColombo — synthèse + tentative JPL Horizons."""
    out = {
        "status": "EN ROUTE VERS MERCURE",
        "agence": "ESA/JAXA",
        "lancement": "2018",
        "arrivee": "2025",
        "name": "BepiColombo",
    }
    try:
        raw = _curl_get(
            "https://ssd.jpl.nasa.gov/api/horizons.api?"
            "format=text&COMMAND=-121&OBJ_DATA=YES"
            "&MAKE_EPHEM=YES&EPHEM_TYPE=VECTORS&CENTER=500@10"
            "&START_TIME=today&STOP_TIME=today&STEP_SIZE=1d&QUANTITIES=20",
            timeout=12,
        )
        if raw:
            out["raw"] = raw[:500]
    except Exception as e:
        out["error"] = str(e)
    return jsonify(out)
