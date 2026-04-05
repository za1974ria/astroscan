"""
Agrégation GET /api/system-status : DSN, Weather, SkyView via les moteurs *safe* uniquement.

GET /api/system-status/cache : lecture seule des snapshots data_core/* (sans get_*_safe, sans réseau).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

# Aligné sur le guide-stellaire / observatoire (Tlemcen)
DEFAULT_WEATHER_VILLE = "Tlemcen"
DEFAULT_WEATHER_LAT = 34.87
DEFAULT_WEATHER_LON = 1.32


def compute_global_status(dsn: Dict[str, Any], weather: Dict[str, Any], skyview: Dict[str, Any]) -> str:
    if (
        dsn.get("status") == "fallback"
        or weather.get("status") == "fallback"
        or skyview.get("status") == "fallback"
    ):
        return "critical"
    if (
        dsn.get("status") not in ("ok",)
        or weather.get("status") not in ("ok",)
        or skyview.get("status") not in ("ok",)
    ):
        return "degraded"
    if dsn.get("stale") or weather.get("stale") or skyview.get("stale"):
        return "degraded"
    return "ok"


def _trim_module(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": d.get("status") or "unknown",
        "source": d.get("source") or "unknown",
        "stale": bool(d.get("stale")),
    }


def _weather_cache_key(ville: str, lat: float, lon: float) -> str:
    """Même clé que weather_engine_safe._cache_key (alignement snapshot last_weather.json)."""
    return f"{(ville or '').strip()}|{lat:.4f}|{lon:.4f}"


def _passive_module_status(present: bool, fresh: bool) -> Dict[str, Any]:
    """ok = snapshot présent et dans le TTL ; cache = présent mais périmé ; fallback = absent/invalide."""
    if not present:
        return {"status": "fallback", "source": "fallback_static", "stale": True}
    if fresh:
        return {"status": "ok", "source": "cache_local", "stale": False}
    return {"status": "cache", "source": "cache_local", "stale": True}


def _passive_dsn(station_root: str) -> Dict[str, Any]:
    from core import dsn_engine_safe as _dsn

    snap = _dsn.load_local_dsn_snapshot(station_root)
    if not snap:
        return _passive_module_status(present=False, fresh=False)
    fa = snap.get("fetched_at_iso")
    fresh = _dsn.is_dsn_snapshot_fresh(
        fa if isinstance(fa, str) else None,
        max_age_seconds=_dsn.DEFAULT_MAX_AGE_SECONDS,
    )
    return _passive_module_status(present=True, fresh=fresh)


def _passive_weather(station_root: str, ville: str, lat: float, lon: float) -> Dict[str, Any]:
    from core import weather_engine_safe as _weather

    ck = _weather_cache_key(ville, lat, lon)
    snap = _weather.load_local_weather_snapshot(station_root, ck)
    if not snap:
        return _passive_module_status(present=False, fresh=False)
    fa = snap.get("fetched_at_iso")
    fresh = _weather.is_weather_fresh(
        fa if isinstance(fa, str) else None,
        max_age_seconds=_weather.DEFAULT_MAX_AGE_SECONDS,
    )
    return _passive_module_status(present=True, fresh=fresh)


def _passive_skyview_latest(station_root: str) -> Dict[str, Any]:
    """Dernier snapshot SkyView valide (GIF + meta cohérents), par mtime des .meta.json."""
    from core import skyview_engine_safe as _sv

    d = Path(station_root) / "data_core" / "skyview"
    if not d.is_dir():
        return _passive_module_status(present=False, fresh=False)
    metas = sorted(d.glob("*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for meta in metas:
        if len(meta.name) < 11 or not meta.name.endswith(".meta.json"):
            continue
        key_hash = meta.name[: -len(".meta.json")]
        if not key_hash:
            continue
        loaded = _sv.load_skyview_snapshot_disk(station_root, key_hash)
        if not loaded:
            continue
        m = loaded.get("meta")
        fa = m.get("fetched_at_iso") if isinstance(m, dict) else None
        fresh = _sv.is_skyview_snapshot_fresh(
            fa if isinstance(fa, str) else None,
            max_age_seconds=_sv.DEFAULT_MAX_AGE_SECONDS,
        )
        return _passive_module_status(present=True, fresh=fresh)
    return _passive_module_status(present=False, fresh=False)


def build_system_status_cache_payload(
    station_root: str,
    *,
    ville: str = DEFAULT_WEATHER_VILLE,
    lat: float = DEFAULT_WEATHER_LAT,
    lon: float = DEFAULT_WEATHER_LON,
) -> Dict[str, Any]:
    """
    État dérivé uniquement des fichiers data_core (aucun fetch réseau, aucun get_*_safe).
    Réutilise load_local_* + is_*_fresh des engines existants (non modifiés).
    """
    dsn = _passive_dsn(station_root)
    weather = _passive_weather(station_root, ville, lat, lon)
    skyview = _passive_skyview_latest(station_root)
    return {
        "dsn": dsn,
        "weather": weather,
        "skyview": skyview,
        "global_status": compute_global_status(dsn, weather, skyview),
    }


def build_system_status_payload(
    station_root: str,
    *,
    ville: str = DEFAULT_WEATHER_VILLE,
    lat: float = DEFAULT_WEATHER_LAT,
    lon: float = DEFAULT_WEATHER_LON,
) -> Dict[str, Any]:
    from core import dsn_engine_safe as _dsn
    from core import weather_engine_safe as _weather
    from core import skyview_engine_safe as _skyview

    d_raw = _dsn.get_dsn_safe(station_root)
    w_raw = _weather.get_weather_safe(station_root, ville, lat, lon)
    sv_raw = _skyview.get_skyview_status_summary(station_root)

    dsn = _trim_module(d_raw)
    weather = _trim_module(w_raw)
    skyview = _trim_module(sv_raw)

    return {
        "dsn": dsn,
        "weather": weather,
        "skyview": skyview,
        "global_status": compute_global_status(dsn, weather, skyview),
    }
