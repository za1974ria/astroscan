"""Données NASA AstroScan — APOD, NEO, DONKI, DSN.

Source unique extraite de station_web.py.
Rewrite des fetchers : requests au lieu de _curl_get.
Aucune dépendance Flask. Testable isolément.
"""

import json
import os
import requests
from datetime import datetime, timedelta, timezone

from services.circuit_breaker import CB_NASA


# ── Clé API ──────────────────────────────────────────────────────────────────

def get_api_key():
    """Clé NASA depuis l'environnement (fallback DEMO_KEY)."""
    try:
        return (os.environ.get("NASA_API_KEY") or "DEMO_KEY").strip()
    except Exception:
        return "DEMO_KEY"


# ── Helper HTTP générique ─────────────────────────────────────────────────────

def fetch_nasa_json(url, timeout=12):
    """GET JSON depuis une URL NASA. Lève une exception en cas d'erreur.
    Retry automatique une fois sur erreur réseau transitoire."""
    _timeout = timeout if isinstance(timeout, tuple) else (5, timeout)
    _headers = {
        'User-Agent': 'AstroScan/2.0 Mozilla/5.0',
        'Accept': 'application/json',
    }
    last_exc = None
    for attempt in range(2):
        try:
            r = requests.get(url, timeout=_timeout, headers=_headers)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                raise ValueError(f'NASA API: réponse inattendue (type={type(data).__name__})')
            return data
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                import time as _t; _t.sleep(1)
    raise last_exc


# ── Fetchers privés ───────────────────────────────────────────────────────────

def _fetch_nasa_apod():
    """NASA APOD (image du jour) — protégé par CB_NASA."""
    def _raw():
        key = get_api_key()
        data = fetch_nasa_json(f"https://api.nasa.gov/planetary/apod?api_key={key}", timeout=12)
        return {
            "ok": True,
            "source": "NASA APOD",
            "title": data.get("title"),
            "date": data.get("date"),
            "media_type": data.get("media_type"),
            "url": data.get("url"),
            "hdurl": data.get("hdurl"),
            "explanation": data.get("explanation"),
            "copyright": data.get("copyright"),
        }
    return CB_NASA.call(_raw, fallback={"ok": False, "error": "NASA APOD indisponible (circuit ouvert)"})


def _fetch_nasa_neo():
    """NASA NEO feed (7 jours) normalisé — protégé par CB_NASA."""
    def _raw():
        key = get_api_key()
        start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        end_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
        url = (
            f"https://api.nasa.gov/neo/rest/v1/feed?"
            f"start_date={start_date}&end_date={end_date}&api_key={key}"
        )
        data = fetch_nasa_json(url, timeout=12)
        items = []
        for day, asteroids in (data.get("near_earth_objects") or {}).items():
            for a in asteroids or []:
                cad = (a.get("close_approach_data") or [{}])[0]
                relv = (cad.get("relative_velocity") or {}).get("kilometers_per_second")
                dist = (cad.get("miss_distance") or {}).get("kilometers")
                try:
                    relv = round(float(relv), 2) if relv is not None else None
                except Exception:
                    relv = None
                try:
                    dist = round(float(dist)) if dist is not None else None
                except Exception:
                    dist = None
                items.append({
                    "name": a.get("name"),
                    "date": day,
                    "hazardous": bool(a.get("is_potentially_hazardous_asteroid")),
                    "velocity_kms": relv,
                    "miss_distance_km": dist,
                    "nasa_jpl_url": a.get("nasa_jpl_url"),
                })
        items.sort(key=lambda x: (x.get("miss_distance_km") is None, x.get("miss_distance_km") or 10 ** 18))
        return {
            "ok": True,
            "source": "NASA NEO",
            "count": len(items),
            "window": {"start": start_date, "end": end_date},
            "asteroids": items[:20],
        }
    return CB_NASA.call(_raw, fallback={"ok": False, "error": "NASA NEO indisponible (circuit ouvert)", "asteroids": []})


def _fetch_nasa_solar():
    """NASA DONKI (space weather events) — protégé par CB_NASA."""
    def _raw():
        key = get_api_key()
        start_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = (
            f"https://api.nasa.gov/DONKI/notifications?"
            f"startDate={start_date}&endDate={end_date}&type=all&api_key={key}"
        )
        data = fetch_nasa_json(url, timeout=12)
        events = []
        for ev in (data or [])[:25]:
            events.append({
                "type": ev.get("messageType") or ev.get("type"),
                "message_id": ev.get("messageID"),
                "message_url": ev.get("messageURL"),
                "issue_time": ev.get("messageIssueTime"),
            })
        return {
            "ok": True,
            "source": "NASA DONKI",
            "window": {"start": start_date, "end": end_date},
            "count": len(events),
            "events": events,
        }
    return CB_NASA.call(_raw, fallback={"ok": False, "error": "NASA DONKI indisponible (circuit ouvert)", "events": []})


# ── API publique ─────────────────────────────────────────────────────────────

def get_apod_data():
    """Image du jour NASA."""
    return _fetch_nasa_apod()


def get_neo_feed():
    """Astéroïdes en approche proche (7 jours)."""
    return _fetch_nasa_neo()


def get_space_events():
    """Événements météo spatiale NASA DONKI."""
    return _fetch_nasa_solar()


def get_dsn_status(station=None):
    """Statut DSN depuis core.dsn_engine_safe."""
    try:
        from core import dsn_engine_safe as _dsn
        return _dsn.get_dsn_safe(station)
    except Exception:
        try:
            from core import dsn_engine_safe as _dsn
            return _dsn.build_dsn_fallback_payload()
        except Exception:
            return {
                "stations": [
                    {"friendlyName": "Goldstone (USA)", "name": "GDS", "dishes": []},
                    {"friendlyName": "Madrid (Spain)", "name": "MDS", "dishes": []},
                    {"friendlyName": "Canberra (Australia)", "name": "CDS", "dishes": []},
                ],
                "status": "fallback",
            }
