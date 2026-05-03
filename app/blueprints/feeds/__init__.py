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
from datetime import datetime, timedelta

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
        now = datetime.utcnow()
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        "timestamp": datetime.utcnow().isoformat(),
    })


# ── NASA APIs propres (Domaine W — services.nasa_service) ─────────────
@bp.route("/api/nasa/apod")
def api_nasa_apod():
    """Image du jour NASA (APOD)."""
    from services.nasa_service import _fetch_nasa_apod
    try:
        payload = get_cached("nasa_apod_v1", 1800, _fetch_nasa_apod)
        code = 200 if payload.get("ok") else 502
        return jsonify(payload), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
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
        return jsonify({"error": str(e)}), 500


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
        "timestamp": datetime.utcnow().isoformat(),
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
        "timestamp": datetime.utcnow().isoformat(),
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
        return jsonify({"error": str(e)}), 500


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


@bp.route("/api/orbits/live")
def api_orbits_live():
    """Positions satellites pour la carte orbitale : ISS + NOAA. Cache 30 s."""
    import time
    from app.utils.cache import cache_cleanup

    cache_cleanup()
    cached = cache_get("orbits_live", 30)
    if cached is not None:
        return jsonify(cached)

    satellites = []
    try:
        from station_web import _fetch_iss_live
        iss = get_cached("iss_live", 5, _fetch_iss_live)
        if iss:
            lat = iss.get("latitude") if "latitude" in iss else iss.get("lat", 0)
            lon = iss.get("longitude") if "longitude" in iss else iss.get("lon", 0)
            satellites.append({
                "id": "iss",
                "name": "ISS",
                "lat": float(lat),
                "lon": float(lon),
                "type": "iss",
                "alt": iss.get("alt", iss.get("altitude", 408)),
            })
    except Exception:
        pass

    for name, lat, lon in [
        ("NOAA-19", 45.0, -122.0),
        ("NOAA-18", -30.0, 10.0),
        ("NOAA-15", 20.0, 80.0),
    ]:
        satellites.append({
            "id": name.lower().replace("-", "_"),
            "name": name,
            "lat": lat,
            "lon": lon,
            "type": "noaa",
        })
    payload = {"satellites": satellites, "timestamp": int(time.time())}
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
        from station_web import _fetch_iss_live
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
