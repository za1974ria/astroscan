"""
Météo wttr.in résiliente : snapshot data_core/weather/, sans dépendance Flask.
Réutilise modules.guide_stellaire pour fetch / résumé (comportement inchangé).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_log = logging.getLogger("astroscan.weather")

SNAPSHOT_NAME = "last_weather.json"
DEFAULT_MAX_AGE_SECONDS = 900.0


def _weather_dir(station_root: str) -> Path:
    return Path(station_root) / "data_core" / "weather"


def _cache_key(ville: str, lat: float, lon: float) -> str:
    return f"{(ville or '').strip()}|{lat:.4f}|{lon:.4f}"


def is_weather_fresh(fetched_at_iso: Optional[str], max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> bool:
    if not fetched_at_iso or not isinstance(fetched_at_iso, str):
        return False
    s = fetched_at_iso.strip()
    if not s:
        return False
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return 0 <= age <= float(max_age_seconds)
    except Exception:
        return False


def parse_weather_payload(raw: Dict[str, Any]) -> bool:
    """True si le JSON wttr j1 est exploitable (pas d’erreur + condition courante)."""
    try:
        if not isinstance(raw, dict) or raw.get("error"):
            return False
        cc = raw.get("current_condition")
        return isinstance(cc, list) and len(cc) > 0
    except Exception:
        return False


def fetch_remote_weather(ville: str, lat: float, lon: float) -> Dict[str, Any]:
    """Délègue à guide_stellaire (ville puis coords) — même stratégie qu’historique."""
    from modules.guide_stellaire import fetch_weather_wttr_coords, fetch_weather_wttr_ville

    raw = fetch_weather_wttr_ville(ville)
    if raw.get("error"):
        raw = fetch_weather_wttr_coords(lat, lon)
    return raw


def build_weather_fallback_payload() -> Dict[str, Any]:
    from modules.guide_stellaire import summarize_weather

    err_raw: Dict[str, Any] = {"error": "weather_unavailable"}
    resume = summarize_weather(err_raw)
    return {
        "meteo_raw": err_raw,
        "meteo_resume": resume,
        "status": "fallback",
        "source": "fallback_static",
        "meteo_source_label": "indisponible (fallback)",
        "stale": True,
        "fetched_at_iso": None,
        "error": "weather_unavailable",
    }


def load_local_weather_snapshot(station_root: str, cache_key: str) -> Optional[Dict[str, Any]]:
    try:
        p = _weather_dir(station_root) / SNAPSHOT_NAME
        if not p.is_file():
            return None
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            return None
        if data.get("cache_key") != cache_key:
            return None
        raw = data.get("meteo_raw")
        if not isinstance(raw, dict) or not parse_weather_payload(raw):
            return None
        return {
            "meteo_raw": raw,
            "fetched_at_iso": data.get("fetched_at_iso"),
            "ville": data.get("ville"),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
        }
    except Exception:
        return None


def save_local_weather_snapshot(
    station_root: str,
    ville: str,
    lat: float,
    lon: float,
    meteo_raw: Dict[str, Any],
    fetched_at_iso: str,
) -> bool:
    """Écriture atomique ; refuse d’écraser par un payload invalide ou vide."""
    try:
        if not parse_weather_payload(meteo_raw):
            _log.warning("WEATHER snapshot save skipped: invalid payload")
            return False
        d = _weather_dir(station_root)
        d.mkdir(parents=True, exist_ok=True)
        dest = d / SNAPSHOT_NAME
        to_write = {
            "cache_key": _cache_key(ville, lat, lon),
            "ville": ville,
            "lat": lat,
            "lon": lon,
            "meteo_raw": meteo_raw,
            "fetched_at_iso": fetched_at_iso,
        }
        fd, tmp = tempfile.mkstemp(prefix="wx_", suffix=".json", dir=str(d))
        try:
            os.close(fd)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(to_write, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(dest))
            return True
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as e:
        _log.warning("WEATHER snapshot save failed: %s", e)
        return False


def get_weather_safe(
    station_root: str,
    ville: str,
    lat: float,
    lon: float,
    *,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
) -> Dict[str, Any]:
    """
    Retourne meteo_raw, meteo_resume, métadonnées. Snapshot si clé identique et wttr OK.
    """
    from modules.guide_stellaire import summarize_weather

    ck = _cache_key(ville, lat, lon)
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    last_err: Optional[str] = None

    raw = fetch_remote_weather(ville, lat, lon)
    if parse_weather_payload(raw):
        save_local_weather_snapshot(station_root, ville, lat, lon, raw, now_iso)
        _log.info("WEATHER refreshed from remote")
        return {
            "meteo_raw": raw,
            "meteo_resume": summarize_weather(raw),
            "status": "ok",
            "source": "remote",
            "meteo_source_label": "wttr.in (ville puis coords)",
            "stale": False,
            "fetched_at_iso": now_iso,
            "error": None,
        }

    if raw.get("error"):
        last_err = str(raw.get("error"))[:300]

    snap = load_local_weather_snapshot(station_root, ck)
    if snap and isinstance(snap.get("meteo_raw"), dict):
        mr = snap["meteo_raw"]
        fa = snap.get("fetched_at_iso")
        stale = not is_weather_fresh(fa, max_age_seconds=max_age_seconds)
        _log.info("WEATHER loaded from cache")
        return {
            "meteo_raw": mr,
            "meteo_resume": summarize_weather(mr),
            "status": "cache",
            "source": "cache_local",
            "meteo_source_label": "wttr.in (cache local)",
            "stale": stale,
            "fetched_at_iso": fa,
            "error": last_err,
        }

    _log.info("WEATHER fallback used")
    fb = build_weather_fallback_payload()
    if last_err:
        fb["error"] = last_err
    return fb
