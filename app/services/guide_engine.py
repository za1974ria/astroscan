"""Guide Stellaire engine — orchestration weather + sunrise + planets + Claude Opus.

Extrait de station_web.py (PASS 17) pour permettre l'utilisation
par ai_bp sans dépendance circulaire.

Délègue la majorité des appels à modules.guide_stellaire (existant) :
    fetch_sunrise_sunset, generate_orbital_guide_opus,
    planets_v1_payload, summarize_weather
+ modules.observation_planner.get_moon_phase
+ core.weather_engine_safe.get_weather_safe

Fonction exposée :
    build_orbital_guide(ville, lat, lon, date_iso) -> dict
        retourne {ok, ville, date, guide, context}  (ou {ok: False, error, ...})
"""
from __future__ import annotations

import json
import logging

from app.config import STATION

log = logging.getLogger(__name__)


def build_orbital_guide(ville: str, lat: float, lon: float, date_iso: str) -> dict:
    """Construit le guide stellaire pour ville/lat/lon/date_iso (YYYY-MM-DD).

    Returns:
        Dict avec clés:
        - ok (bool)
        - ville, date
        - guide: {text, format} si ok
        - context: snapshot données utilisées
        - error (optional, si ok=False)
    """
    from modules.guide_stellaire import (
        fetch_sunrise_sunset,
        generate_orbital_guide_opus,
        planets_v1_payload,
        summarize_weather,
    )
    from modules.observation_planner import get_moon_phase

    try:
        moon_obj = get_moon_phase()
        moon_data = json.dumps(moon_obj, ensure_ascii=False)

        planets_obj = planets_v1_payload()
        planets_data = json.dumps(planets_obj, ensure_ascii=False)

        # Météo wttr.in : couche résiliente data_core/weather (fetch + snapshot + fallback)
        from core import weather_engine_safe as _weather_safe

        wx = _weather_safe.get_weather_safe(STATION, ville, lat, lon)
        meteo_raw = wx.get("meteo_raw") or {}
        meteo_data = wx.get("meteo_resume") or summarize_weather(meteo_raw)

        sun = fetch_sunrise_sunset(lat, lon, date_iso)
        sun_ephemeris = json.dumps(
            {
                "date": date_iso,
                "sunrise": sun.get("sunrise"),
                "sunset": sun.get("sunset"),
                "civil_twilight_begin": sun.get("civil_twilight_begin"),
                "civil_twilight_end": sun.get("civil_twilight_end"),
                "nautical_twilight_end": sun.get("nautical_twilight_end"),
                "astronomical_twilight_begin": sun.get("astronomical_twilight_begin"),
                "astronomical_twilight_end": sun.get("astronomical_twilight_end"),
                "error": sun.get("error"),
            },
            ensure_ascii=False,
        )

        context = {
            "ville": ville,
            "latitude": lat,
            "longitude": lon,
            "date": date_iso,
            "lune": moon_obj,
            "meteo_resume": meteo_data,
            "meteo_source": wx.get("meteo_source_label") or "wttr.in (ville puis coords)",
            "planetes_catalogue_v1": planets_obj,
            "soleil": sun,
            "weather_status": wx.get("status"),
            "weather_stale": wx.get("stale"),
            "weather_fetched_at_iso": wx.get("fetched_at_iso"),
            "weather_error": wx.get("error"),
        }

        guide_text, err = generate_orbital_guide_opus(
            ville, lat, lon, moon_data, meteo_data, planets_data, sun_ephemeris,
        )
    except Exception as e:
        log.exception("guide-stellaire agrégation")
        return {"ok": False, "error": f"agrégation données: {e}"}

    if err:
        return {"ok": False, "error": err, "context": context}

    return {
        "ok": True,
        "ville": ville,
        "date": date_iso,
        "guide": {"text": guide_text, "format": "markdown"},
        "context": context,
    }
