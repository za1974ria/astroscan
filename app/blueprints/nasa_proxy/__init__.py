"""Blueprint nasa_proxy — server-side proxy for NASA API.

Created in PASS 26.B (2026-05-04) to fix CRITICAL security finding:
NASA_API_KEY was previously exposed via Jinja in templates/observatoire.html.

All NASA API calls now happen server-side. Frontend calls /api/nasa/*
which adds the API key from environment and relays to api.nasa.gov.

Cache: in-memory dict with TTL per endpoint to reduce NASA rate-limit pressure
(NASA free tier = 1000 req/h per key).
"""
import logging
import os
import time
from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)
bp = Blueprint("nasa_proxy", __name__, url_prefix="/api/nasa")

_CACHE: dict = {}


def _cache_get(key):
    entry = _CACHE.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if time.time() > expires_at:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key, payload, ttl_seconds):
    _CACHE[key] = (time.time() + ttl_seconds, payload)


def _nasa_key():
    return os.environ.get("NASA_API_KEY", "DEMO_KEY") or "DEMO_KEY"


def _proxy_get(url_path, params, ttl, cache_key):
    """Generic NASA proxy: cache → if miss, fetch with server-side key → cache."""
    import requests
    cached = _cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)
    try:
        params = dict(params or {})
        params["api_key"] = _nasa_key()
        r = requests.get(f"https://api.nasa.gov{url_path}", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        _cache_set(cache_key, data, ttl)
        return jsonify(data)
    except requests.RequestException as e:
        log.warning("[nasa_proxy] %s failed: %s", cache_key, e)
        return jsonify({"error": "nasa_upstream_error", "detail": str(e)[:200]}), 502
    except ValueError as e:
        log.warning("[nasa_proxy] %s json decode failed: %s", cache_key, e)
        return jsonify({"error": "nasa_invalid_json"}), 502


@bp.route("/insight-weather")
def insight_weather():
    """Mars InSight weather data — TTL 30 min (data updates ~daily)."""
    return _proxy_get(
        "/insight_weather/",
        {"feedtype": "json", "ver": "1.0"},
        ttl=1800,
        cache_key="insight_weather",
    )


@bp.route("/neo/<asteroid_id>")
def neo_asteroid(asteroid_id):
    """Near-Earth Object lookup — TTL 1h (orbital params stable)."""
    if not asteroid_id.isdigit():
        return jsonify({"error": "invalid_asteroid_id"}), 400
    return _proxy_get(
        f"/neo/rest/v1/neo/{asteroid_id}",
        {},
        ttl=3600,
        cache_key=f"neo_{asteroid_id}",
    )


@bp.route("/apod")
def apod():
    """Astronomy Picture of the Day — TTL 1h (changes once per day)."""
    date = request.args.get("date", "")
    params = {"date": date} if date else {}
    cache_key = f"apod_{date or 'today'}"
    return _proxy_get("/planetary/apod", params, ttl=3600, cache_key=cache_key)
