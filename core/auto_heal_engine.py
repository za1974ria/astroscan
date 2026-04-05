"""
Auto-healing contrôlé : refresh cache via les moteurs *safe* uniquement.
Aucune action destructive, pas de systemd, pas de redémarrage de service.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Sonde SkyView alignée sur get_skyview_status_summary (M42 / DSS2 Red)
_SKYVIEW_PREFETCH_TARGET = "M42"
_SKYVIEW_PREFETCH_COORDS = "83.8221,-5.3911"
_SKYVIEW_PREFETCH_SURVEY = "DSS2 Red"
_SKYVIEW_PREFETCH_SIZE_DEG = 0.5
_SKYVIEW_PREFETCH_PIXELS = 128


def run_auto_heal(station_root: str) -> Dict[str, Any]:
    from core.dsn_engine_safe import get_dsn_safe
    from core.skyview_engine_safe import get_skyview_safe
    from core.system_status_engine import (
        DEFAULT_WEATHER_LAT,
        DEFAULT_WEATHER_LON,
        DEFAULT_WEATHER_VILLE,
        build_system_status_cache_payload,
    )
    from core.weather_engine_safe import get_weather_safe

    status = build_system_status_cache_payload(station_root)
    actions: List[str] = []

    w = status.get("weather") or {}
    if w.get("stale"):
        get_weather_safe(
            station_root,
            DEFAULT_WEATHER_VILLE,
            DEFAULT_WEATHER_LAT,
            DEFAULT_WEATHER_LON,
        )
        actions.append("weather_refresh")

    d = status.get("dsn") or {}
    if d.get("stale"):
        get_dsn_safe(station_root)
        actions.append("dsn_refresh")

    s = status.get("skyview") or {}
    if s.get("status") == "fallback":
        get_skyview_safe(
            station_root,
            _SKYVIEW_PREFETCH_TARGET,
            _SKYVIEW_PREFETCH_COORDS,
            _SKYVIEW_PREFETCH_SURVEY,
            _SKYVIEW_PREFETCH_SIZE_DEG,
            _SKYVIEW_PREFETCH_PIXELS,
        )
        actions.append("skyview_prefetch")

    return {
        "actions": actions,
        "count": len(actions),
    }
