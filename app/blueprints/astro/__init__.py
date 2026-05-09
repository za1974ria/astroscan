"""Blueprint Astro — calculs astronomiques (éphémérides, lune, tonight, objets célestes).

PASS 7 (2026-05-03) — Création :
  /api/tonight, /api/moon, /api/ephemerides/tlemcen, /api/v1/tonight,
  /api/astro/object, /ephemerides (page).

Différé : /api/astro/explain (deps _translate_to_french/_call_claude → PASS 11),
  /api/hilal, /api/hilal/calendar (helpers astropy >400 lignes → PASS 14).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, request, jsonify

from app.utils.cache import cache_get, cache_set, get_cached

log = logging.getLogger(__name__)

bp = Blueprint("astro", __name__)


# ── Tonight + moon (Domaine X) ─────────────────────────────────────────
@bp.route("/api/tonight")
def api_tonight():
    from modules.observation_planner import get_tonight_objects
    return jsonify(get_cached("tonight", 3600, get_tonight_objects))


@bp.route("/api/moon")
def api_moon():
    from modules.observation_planner import get_moon_phase
    return jsonify(get_moon_phase())


@bp.route("/api/v1/tonight")
def api_v1_tonight():
    from modules.observation_planner import get_tonight_objects
    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "location": "Tlemcen, Algérie (~34,9°N, 1,3°E)",
        "data": get_cached("tonight", 3600, get_tonight_objects),
        "credit": "AstroScan-Chohra · ORBITAL-CHOHRA",
    })


# ── Éphémérides Tlemcen (services + page astropy) ─────────────────────
@bp.route("/api/ephemerides/tlemcen")
def api_ephemerides_tlemcen():
    """Éphémérides du jour pour Tlemcen — cache 5 min."""
    from services.ephemeris_service import get_full_ephemeris
    cached = cache_get("eph_tlemcen", 300)
    if cached:
        return jsonify(cached)
    try:
        result = get_full_ephemeris()
        cache_set("eph_tlemcen", result)
        return jsonify(result)
    except Exception as e:
        log.warning("ephemerides/tlemcen error: %s", e)
        return jsonify({"error": str(e)}), 500


def _compute_ephemerides_tlemcen_astropy():
    """
    Éphémérides journalières pour Tlemcen (UTC) via astropy.
    Corps : Soleil, Lune, Jupiter, Mars, Saturne, Vénus.
    """
    from astropy.coordinates import EarthLocation, AltAz, get_body
    from astropy.time import Time
    import astropy.units as u

    location = EarthLocation(lat=34.8731 * u.deg, lon=1.3154 * u.deg, height=800 * u.m)
    start_dt = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    step_min = 5
    timeline = [start_dt + timedelta(minutes=m) for m in range(0, 24 * 60 + step_min, step_min)]
    times = Time(timeline, scale="utc")
    altaz = AltAz(obstime=times, location=location)

    def _iso_or_none(dt_obj):
        return dt_obj.strftime("%Y-%m-%dT%H:%M:%SZ") if dt_obj else None

    def _crossing_time(vals, mode="rise"):
        for i in range(len(vals) - 1):
            a0, a1 = vals[i], vals[i + 1]
            if mode == "rise" and a0 < 0 <= a1:
                frac = 0.0 if a1 == a0 else (0.0 - a0) / (a1 - a0)
                return timeline[i] + timedelta(seconds=frac * step_min * 60)
            if mode == "set" and a0 > 0 >= a1:
                frac = 0.0 if a1 == a0 else (0.0 - a0) / (a1 - a0)
                return timeline[i] + timedelta(seconds=frac * step_min * 60)
        return None

    bodies = [
        ("Soleil", "sun", -26.74),
        ("Lune", "moon", -12.60),
        ("Jupiter", "jupiter", -2.70),
        ("Mars", "mars", 1.00),
        ("Saturne", "saturn", 0.70),
        ("Vénus", "venus", -4.20),
    ]

    results = []
    for label, body_name, mag in bodies:
        body_alt = get_body(body_name, times, location).transform_to(altaz).alt.deg.tolist()
        max_alt = max(body_alt)
        max_idx = body_alt.index(max_alt)
        rise_dt = _crossing_time(body_alt, mode="rise")
        set_dt = _crossing_time(body_alt, mode="set")
        transit_dt = timeline[max_idx]
        results.append({
            "nom": label,
            "rise": _iso_or_none(rise_dt),
            "transit": _iso_or_none(transit_dt),
            "set": _iso_or_none(set_dt),
            "altitude_max": round(float(max_alt), 2),
            "magnitude": mag,
        })

    return {
        "site": {"name": "Tlemcen", "lat": 34.8731, "lon": 1.3154, "altitude_m": 800},
        "date_utc": start_dt.strftime("%Y-%m-%d"),
        "source": "astropy",
        "ephemerides": results,
    }


@bp.route("/ephemerides")
def page_ephemerides():
    try:
        eph_payload = _compute_ephemerides_tlemcen_astropy()
    except Exception as e:
        log.warning("ephemerides astropy error: %s", e)
        eph_payload = {"error": str(e), "site": {"name": "Tlemcen"}}

    wants_json = request.args.get("format") == "json" or "application/json" in (request.headers.get("Accept") or "")
    if wants_json:
        return jsonify(eph_payload)
    return render_template("ephemerides.html", ephemerides_tlemcen=eph_payload)


# ── Astro object (Domaine AP) ──────────────────────────────────────────
@bp.route("/api/astro/object", methods=["GET", "POST"])
def api_astro_object():
    """Explication d'un objet céleste par nom (modules.astro_ai.explain_object)."""
    name = request.args.get("name") or (request.get_json(silent=True) or {}).get("name") or ""
    try:
        from modules.astro_ai import explain_object
        return jsonify(explain_object(name))
    except Exception as e:
        log.warning("api/astro/object: %s", e)
        return jsonify({"ok": False, "error": str(e)})


# ── PASS 15 — Hilal (Croissant Islamique) ──────────────────────────────
@bp.route("/api/hilal/calendar")
def api_hilal_calendar():
    """Calendrier hégire 24 mois — ODEH 2006 + Istanbul 1978. Cache 24h."""
    cached = cache_get("hilal_calendar", 86400)
    if cached is not None:
        return jsonify(cached)
    try:
        from app.services.hilal_compute import hilal_compute_calendar
        data = hilal_compute_calendar()
        cache_set("hilal_calendar", data)
        return jsonify(data)
    except Exception as e:
        log.error("api_hilal_calendar: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/hilal")
def api_hilal():
    """Calcul du croissant islamique (Hilal) pour Tlemcen. Cache 30 min."""
    cached = cache_get("hilal_data", 1800)
    if cached is not None:
        return jsonify(cached)
    try:
        from app.services.hilal_compute import hilal_compute
        data = hilal_compute()
        cache_set("hilal_data", data)
        return jsonify(data)
    except Exception as e:
        log.error("api_hilal: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
