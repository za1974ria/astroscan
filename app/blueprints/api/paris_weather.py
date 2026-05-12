"""Paris weather endpoint with in-memory 10-min cache (v2.6.0).

Backs the Paris gallery widget on /europe-live with live data:
- Temperature in °C (forced — wttr.in defaults to °F)
- Conditions (sky description in FR)
- Humidity, wind
- Cached 10 minutes to avoid DDoSing wttr.in
"""
import time
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, current_app

paris_weather_bp = Blueprint("paris_weather", __name__)

_CACHE = {"data": None, "ts": 0.0}
_CACHE_TTL = 600  # 10 minutes


def _fetch_paris_weather():
    """Fetch from wttr.in with °C units (m flag forces metric)."""
    url = "https://wttr.in/Paris?format=j1&m"
    r = requests.get(url, timeout=6)
    r.raise_for_status()
    j = r.json()
    cur = j["current_condition"][0]
    return {
        "city": "Paris",
        "temp_c": int(cur.get("temp_C", 0)),
        "feels_like_c": int(cur.get("FeelsLikeC", cur.get("temp_C", 0))),
        "humidity": int(cur.get("humidity", 0)),
        "wind_kmh": int(cur.get("windspeedKmph", 0)),
        "conditions": (cur.get("weatherDesc") or [{"value": "—"}])[0].get("value", "—"),
        "icon_code": cur.get("weatherCode", "113"),
        "observed_utc": datetime.now(timezone.utc).isoformat(),
    }


@paris_weather_bp.route("/api/paris/weather")
def api_paris_weather():
    """Return current Paris weather, cached 10 minutes."""
    now = time.time()
    if _CACHE["data"] and (now - _CACHE["ts"] < _CACHE_TTL):
        cached = dict(_CACHE["data"])
        cached["from_cache"] = True
        cached["cache_age_s"] = int(now - _CACHE["ts"])
        return jsonify(cached), 200

    try:
        data = _fetch_paris_weather()
        _CACHE["data"] = data
        _CACHE["ts"] = now
        data["from_cache"] = False
        data["cache_age_s"] = 0
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.warning("paris_weather fetch failed: %s", e)
        if _CACHE["data"]:
            stale = dict(_CACHE["data"])
            stale["from_cache"] = True
            stale["cache_age_s"] = int(now - _CACHE["ts"])
            stale["stale"] = True
            return jsonify(stale), 200
        return jsonify({
            "city": "Paris",
            "error": str(e)[:120],
            "observed_utc": datetime.now(timezone.utc).isoformat(),
        }), 503
