"""Hilal Observatory blueprint — endpoints scientifiques pour
calcul du croissant lunaire, calendrier hégirien, prières & Ramadan.

Ne tranche pas. Calcule. Affiche les méthodes en parallèle.
"""

import logging
from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request

from . import calculations as calc

log = logging.getLogger(__name__)

bp = Blueprint("hilal_bp", __name__, url_prefix="/api/hilal")


@bp.route("/today")
def today():
    """Snapshot du jour : phase lunaire, hijri, prochain croissant visible."""
    try:
        now = datetime.now(timezone.utc)
        moon = calc.get_moon_today()
        nm = calc.find_next_newmoon(now)
        crescent = (
            calc.crescent_visibility(nm, lat=34.87, lng=-1.32)
            if nm else {"yallop_1997": {}, "odeh_2006": {}}
        )
        h = calc.hijri_today()
        return jsonify({
            "gregorian": now.date().isoformat(),
            "hijri": h,
            "moon": moon,
            "next_newmoon_utc": nm.isoformat().replace("+00:00", "Z") if nm else None,
            "next_crescent_visible": crescent,
            "library": "Skyfield + hijridate + adhan",
            "ephemeris": "NASA JPL DE421",
            "note": "Calculs astronomiques purs. Observation locale peut différer ±1 jour.",
        })
    except Exception as e:
        log.exception("hilal/today failed")
        return jsonify({"error": str(e)[:300]}), 500


@bp.route("/events")
def events():
    """Fêtes du calendrier hégirien — 10 dates par année × N années (1..5).

    Endpoint distinct de /api/hilal/calendar (astro_bp, prédictions
    de croissant 24 mois) — ici on donne les fêtes religieuses majeures.
    """
    try:
        years = max(1, min(5, int(request.args.get("years", 3))))
        events = calc.islamic_calendar(years)
        return jsonify({
            "events": events,
            "count": len(events),
            "years": years,
            "scientific_note": (
                "Calculs astronomiques purs (algorithme tabulaire Umm-al-Qura). "
                "Variation possible ±1 jour selon observation locale du croissant."
            ),
            "method": "hijridate (Umm-al-Qura tabular)",
        })
    except Exception as e:
        log.exception("hilal/calendar failed")
        return jsonify({"error": str(e)[:300]}), 500


@bp.route("/prayers")
def prayers():
    """Horaires de prière — 5 méthodes en parallèle + 3 décalages Imsak."""
    try:
        lat = float(request.args.get("lat", 34.87))
        lng = float(request.args.get("lng", -1.32))
        city = request.args.get("city", "Tlemcen")
        country = request.args.get("country", "DZ")
        out = calc.prayer_times_5_methods(lat, lng)
        return jsonify({
            "location": {
                "lat": lat, "lng": lng,
                "name": city, "country": country,
                "timezone": out["timezone"],
                "tz_offset_hours": out["tz_offset_hours"],
            },
            "date_local": date.today().isoformat(),
            "methods": out["methods"],
            "fasting_duration_minutes": out["fasting_duration_minutes"],
            "library": "adhan-python 0.1.1",
        })
    except Exception as e:
        log.exception("hilal/prayers failed")
        return jsonify({"error": str(e)[:300]}), 500


@bp.route("/cities/search")
def cities_search():
    """Recherche libre de villes via OpenStreetMap Nominatim (cache 24h)."""
    try:
        q = request.args.get("q", "")
        limit = max(1, min(20, int(request.args.get("limit", 10))))
        results = calc.cities_search(q, limit)
        return jsonify({"query": q, "count": len(results), "results": results})
    except Exception as e:
        log.exception("hilal/cities/search failed")
        return jsonify({"error": str(e)[:300]}), 500


@bp.route("/ramadan")
def ramadan():
    """Status Ramadan : en cours / approche / prochain."""
    try:
        return jsonify(calc.ramadan_status())
    except Exception as e:
        log.exception("hilal/ramadan failed")
        return jsonify({"error": str(e)[:300]}), 500
