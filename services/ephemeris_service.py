"""Éphémérides AstroScan — soleil, lune, crépuscules, planètes depuis Tlemcen.

Logique extraite de station_web.py / api_ephemerides_tlemcen().
Aucune dépendance Flask. Testable isolément.
Localisation : Tlemcen, Algérie — 34.8753°N / -1.3167°W / 816 m
Fuseau horaire affiché : UTC+1 (Algérie)
"""

import datetime as _dt
from astropy.coordinates import EarthLocation, AltAz, get_sun, get_body
from astropy.time import Time
import astropy.units as u

from app.constants.observatory import TLEMCEN_LAT, TLEMCEN_LON, TLEMCEN_ALT


# ── Constantes lieu ───────────────────────────────────────────────────────────

TLEMCEN = EarthLocation(lat=TLEMCEN_LAT * u.deg, lon=TLEMCEN_LON * u.deg, height=TLEMCEN_ALT * u.m)

_PLANET_FR = {
    "mercury": "Mercure", "venus": "Vénus", "mars": "Mars",
    "jupiter": "Jupiter", "saturn": "Saturne",
    "uranus": "Uranus", "neptune": "Neptune",
}


# ── Utilitaires internes ──────────────────────────────────────────────────────

def _utc_plus1(dt):
    """Convertit un datetime UTC en heure locale UTC+1 (HH:MM)."""
    return (dt + _dt.timedelta(hours=1)).strftime("%H:%M")


def _midnight_steps():
    """Renvoie (dt_steps, times, frame) pour le jour courant (5 min, minuit → minuit)."""
    now_utc = _dt.datetime.now(_dt.timezone.utc)
    today = now_utc.date()
    midnight = _dt.datetime(today.year, today.month, today.day, 0, 0, 0)
    dt_steps = [midnight + _dt.timedelta(minutes=5 * i) for i in range(289)]
    times = Time(dt_steps)
    frame = AltAz(obstime=times, location=TLEMCEN)
    return dt_steps, times, frame


def _find_crossing(alts, dt_steps, threshold, rising=True):
    """Retourne l'heure UTC+1 (str) du premier passage d'altitude au seuil threshold."""
    for i in range(len(alts) - 1):
        if rising and alts[i] < threshold <= alts[i + 1]:
            return _utc_plus1(dt_steps[i])
        if not rising and alts[i] >= threshold > alts[i + 1]:
            return _utc_plus1(dt_steps[i])
    return None


# ── Fonctions publiques ───────────────────────────────────────────────────────

def get_sun_ephemeris():
    """Lever, coucher et position actuelle du soleil depuis Tlemcen."""
    dt_steps, times, frame = _midnight_steps()
    sun_alts = get_sun(times).transform_to(frame).alt.deg

    now_utc = _dt.datetime.now(_dt.timezone.utc)
    now_time = Time(now_utc)
    now_frame = AltAz(obstime=now_time, location=TLEMCEN)
    sun_now = get_sun(now_time).transform_to(now_frame)

    return {
        "alt_now": round(float(sun_now.alt.deg), 1),
        "az_now": round(float(sun_now.az.deg), 1),
        "lever": _find_crossing(sun_alts, dt_steps, 0, rising=True),
        "coucher": _find_crossing(sun_alts, dt_steps, 0, rising=False),
    }


def get_moon_ephemeris():
    """Lever, coucher et position actuelle de la lune depuis Tlemcen."""
    dt_steps, times, frame = _midnight_steps()
    moon_alts = get_body("moon", times, TLEMCEN).transform_to(frame).alt.deg

    now_utc = _dt.datetime.now(_dt.timezone.utc)
    now_time = Time(now_utc)
    now_frame = AltAz(obstime=now_time, location=TLEMCEN)
    moon_now = get_body("moon", now_time).transform_to(now_frame)

    phase = get_moon_phase()
    return {
        "alt_now": round(float(moon_now.alt.deg), 1),
        "az_now": round(float(moon_now.az.deg), 1),
        "lever": _find_crossing(moon_alts, dt_steps, 0, rising=True),
        "coucher": _find_crossing(moon_alts, dt_steps, 0, rising=False),
        "phase": phase.get("phase", "—"),
        "illumination_pct": phase.get("illumination_pct", 0),
    }


def get_moon_phase():
    """Phase lunaire (pourcentage + nom). Délègue à modules.observation_planner."""
    from modules.observation_planner import get_moon_phase as _gmp
    return _gmp()


def get_twilight_times():
    """Crépuscule civil (-6°), nautique (-12°) et astronomique (-18°) depuis Tlemcen."""
    dt_steps, times, frame = _midnight_steps()
    sun_alts = get_sun(times).transform_to(frame).alt.deg

    return {
        "civil_begin": _find_crossing(sun_alts, dt_steps, -6, rising=True),
        "civil_end": _find_crossing(sun_alts, dt_steps, -6, rising=False),
        "nautical_begin": _find_crossing(sun_alts, dt_steps, -12, rising=True),
        "nautical_end": _find_crossing(sun_alts, dt_steps, -12, rising=False),
        "astro_begin": _find_crossing(sun_alts, dt_steps, -18, rising=True),
        "astro_end": _find_crossing(sun_alts, dt_steps, -18, rising=False),
    }


def get_full_ephemeris():
    """Payload complet éphémérides pour Tlemcen (soleil + lune + crépuscules + planètes).

    Retourne le même dict que l'ancienne logique inline de api_ephemerides_tlemcen().
    """
    now_utc = _dt.datetime.now(_dt.timezone.utc)
    today = now_utc.date()

    # Étapes temporelles : minuit → minuit, pas 5 min
    midnight = _dt.datetime(today.year, today.month, today.day, 0, 0, 0)
    dt_steps = [midnight + _dt.timedelta(minutes=5 * i) for i in range(289)]
    times = Time(dt_steps)
    frame = AltAz(obstime=times, location=TLEMCEN)

    # Altitudes soleil sur la journée
    sun_alts = get_sun(times).transform_to(frame).alt.deg

    lever_soleil = _find_crossing(sun_alts, dt_steps, 0, rising=True)
    coucher_soleil = _find_crossing(sun_alts, dt_steps, 0, rising=False)
    debut_nuit_astro = _find_crossing(sun_alts, dt_steps, -18, rising=False)
    fin_nuit_astro = _find_crossing(sun_alts, dt_steps, -18, rising=True)

    # Positions temps réel
    now_time = Time(now_utc)
    now_frame = AltAz(obstime=now_time, location=TLEMCEN)
    sun_now = get_sun(now_time).transform_to(now_frame)
    moon_now = get_body("moon", now_time).transform_to(now_frame)

    # Planètes visibles (altitude > 5°)
    planets_visible = []
    for p in ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]:
        try:
            b = get_body(p, now_time).transform_to(now_frame)
            if b.alt.deg > 5:
                planets_visible.append({
                    "name": _PLANET_FR.get(p, p.capitalize()),
                    "name_en": p.capitalize(),
                    "alt": round(float(b.alt.deg), 1),
                    "az": round(float(b.az.deg), 1),
                })
        except Exception:
            pass

    # Altitudes lune sur la journée
    moon_alts = get_body("moon", times, TLEMCEN).transform_to(frame).alt.deg
    lever_lune = _find_crossing(moon_alts, dt_steps, 0, rising=True)
    coucher_lune = _find_crossing(moon_alts, dt_steps, 0, rising=False)

    moon_data = get_moon_phase()

    return {
        "date": today.strftime("%d/%m/%Y"),
        "lieu": "Tlemcen, Algérie",
        "coordonnees": {"lat": TLEMCEN_LAT, "lon": TLEMCEN_LON, "alt_m": TLEMCEN_ALT},
        "soleil": {
            "alt_now": round(float(sun_now.alt.deg), 1),
            "az_now": round(float(sun_now.az.deg), 1),
            "lever": lever_soleil,
            "coucher": coucher_soleil,
        },
        "lune": {
            "alt_now": round(float(moon_now.alt.deg), 1),
            "az_now": round(float(moon_now.az.deg), 1),
            "lever": lever_lune,
            "coucher": coucher_lune,
            "phase": moon_data.get("phase", "—"),
            "illumination_pct": moon_data.get("illumination_pct", 0),
        },
        "nuit_astronomique": {
            "debut": debut_nuit_astro,
            "fin": fin_nuit_astro,
        },
        "planetes_visibles": planets_visible,
        "timezone": "UTC+1 (Algérie)",
    }
