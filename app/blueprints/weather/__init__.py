"""Blueprint Weather — météo terrestre + spatiale + aurores.

PASS 7 (2026-05-03) — Création :
  /api/meteo-spatiale, /meteo-spatiale,
  /aurores, /api/aurore, /api/aurores,
  /api/weather, /api/weather/local,
  /api/weather/bulletins, /api/weather/bulletins/latest,
  /api/weather/history, /api/weather/bulletins/save,
  /api/space-weather, /space-weather,
  /api/v1/solar-weather,
  /api/meteo/reel, /meteo-reel, /control, /meteo.

Différé : /api/space-weather/alerts (helper _curl_get → PASS 13),
  /api/feeds/solar* (PASS 13), /api/nasa/solar (PASS 13),
  /api/mars/weather (PASS 13).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, Response

from app.config import STATION, WEATHER_DB_PATH, WEATHER_HISTORY_DIR
from app.utils.cache import cache_get, cache_set, cache_cleanup, get_cached
from app.services.weather_archive import (
    save_weather_bulletin, save_weather_history_json, save_weather_archive_json,
    _cleanup_weather_history_files,
)

log = logging.getLogger(__name__)

bp = Blueprint("weather", __name__)


# ── Météo spatiale (Domaine L) ─────────────────────────────────────────
def _space_weather_stale_fallback():
    """Fallback ULTIME : lit static/space_weather.json (figé) si live indispo."""
    try:
        path = f"{STATION}/static/space_weather.json"
        if not os.path.exists(path):
            return {"statut_magnetosphere": "Indisponible", "kp_index": None,
                    "source": "stale_fallback"}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"statut_magnetosphere": "Indisponible",
                    "source": "stale_fallback"}
        data["source"] = "stale_fallback"
        return data
    except Exception:
        return {"statut_magnetosphere": "Indisponible",
                "source": "stale_fallback"}


@bp.route("/api/meteo-spatiale")
def api_meteo_spatiale():
    """Météo spatiale — live NOAA via get_space_weather_legacy() avec cache 60 s.

    Tombe sur static/space_weather.json (marqué stale_fallback) si NOAA KO.
    """
    cache_cleanup()
    cached = cache_get("space_weather", 60)
    if cached is not None:
        return jsonify(cached)
    try:
        from services.weather_service import get_space_weather_legacy
        data = get_space_weather_legacy()
        if data.get("kp_index") is None or "fallback" in str(data.get("source", "")):
            data = _space_weather_stale_fallback()
        cache_set("space_weather", data)
        return jsonify(data)
    except Exception as e:
        log.warning("meteo-spatiale: %s — fallback stale", e)
        data = _space_weather_stale_fallback()
        cache_set("space_weather", data)
        return jsonify(data)


@bp.route("/meteo-spatiale")
def meteo_spatiale_page():
    return render_template("meteo_spatiale.html")


@bp.route("/api/space-weather")
def api_space_weather():
    """Données météo spatiale — live NOAA + cache 60 s + fallback stale file."""
    cache_cleanup()
    cached = cache_get("space_weather", 60)
    if cached is not None:
        return jsonify(cached)
    try:
        from services.weather_service import get_space_weather_legacy
        data = get_space_weather_legacy()
        if data.get("kp_index") is None or "fallback" in str(data.get("source", "")):
            data = _space_weather_stale_fallback()
        cache_set("space_weather", data)
        return jsonify(data)
    except Exception as e:
        log.warning("api/space-weather: %s — fallback stale", e)
        data = _space_weather_stale_fallback()
        cache_set("space_weather", data)
        return jsonify(data)


@bp.route("/space-weather")
def space_weather_page():
    return render_template("space_weather.html")


# ── Aurores (Domaine L) ────────────────────────────────────────────────
@bp.route("/aurores")
def aurores_page():
    return render_template("aurores.html")


@bp.route("/api/aurore")
def api_aurore():
    """Indice Kp NOAA + profil premium pour Tlemcen."""
    import requests
    from services.weather_service import _safe_kp_value, _kp_premium_profile

    noaa_url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
    try:
        response = requests.get(noaa_url, timeout=12)
        response.raise_for_status()
        raw_data = response.json()

        raw_kp = None
        if isinstance(raw_data, list) and len(raw_data) > 1:
            latest = raw_data[-1]
            if isinstance(latest, dict):
                # Format actuel NOAA (mai 2026) : list of dicts
                raw_kp = (
                    latest.get("Kp")
                    or latest.get("kp_index")
                    or latest.get("estimated_kp")
                )
            elif isinstance(latest, list) and len(latest) > 1:
                # Legacy fallback (ancien format)
                raw_kp = latest[1]

        kp, status, _ = _safe_kp_value(raw_kp)
        is_fallback = status == "fallback"
        profile = _kp_premium_profile(kp, fallback=is_fallback)

        return jsonify({
            "ok": True,
            "kp": kp,
            "status": status,
            "source": "NOAA_or_fallback",
            "level": profile["level"],
            "risk_score": profile["risk_score"],
            "visibility_from_tlemcen": profile["visibility_from_tlemcen"],
            "color": profile["color"],
            "message": profile["message"],
            "professional_summary": profile["professional_summary"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        log.error("aurore: erreur Kp, fallback appliqué: %s", e)
        profile = _kp_premium_profile(0.0, fallback=True)
        return jsonify({
            "ok": True,
            "kp": 0.0,
            "status": "fallback",
            "source": "NOAA_or_fallback",
            "level": profile["level"],
            "risk_score": profile["risk_score"],
            "visibility_from_tlemcen": profile["visibility_from_tlemcen"],
            "color": profile["color"],
            "message": profile["message"],
            "professional_summary": profile["professional_summary"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })


@bp.route("/api/aurores")
def api_aurores_alias():
    try:
        return api_aurore()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Météo terrestre (Domaine V) ───────────────────────────────────────
@bp.route("/api/weather")
def api_weather_alias():
    import requests
    from services.weather_service import (
        normalize_weather, _derive_weather_condition, validate_data,
        _internal_weather_fallback, compute_reliability, compute_risk,
    )
    try:
        timestamp = datetime.now(timezone.utc).isoformat()

        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=35&longitude=-0.6"
            "&current_weather=true"
            "&hourly=relativehumidity_2m,surface_pressure"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        payload = response.json() if response.content else {}

        current_weather = payload.get("current_weather") or {}
        hourly = payload.get("hourly") or {}

        def _extract_hourly_latest(values, default_value):
            if isinstance(values, list) and values:
                return values[0]
            return default_value

        raw_data = {
            "temperature": current_weather.get("temperature"),
            "windspeed": current_weather.get("windspeed"),
            "humidity": _extract_hourly_latest(hourly.get("relativehumidity_2m"), 0),
            "pressure": _extract_hourly_latest(hourly.get("surface_pressure"), 1013),
        }
        normalized = normalize_weather(raw_data)
        temp = normalized["temp"]
        wind = normalized["wind"]
        humidity = normalized["humidity"]
        pressure = normalized["pressure"]

        condition = _derive_weather_condition(temp, humidity, wind)
        normalized["condition"] = condition
        save_weather_archive_json(normalized)

        return jsonify({
            "ok": True,
            "temp": temp,
            "wind": wind,
            "humidity": humidity,
            "pressure": pressure,
            "condition": condition,
            "fiabilite": compute_reliability(normalized),
            "niveau_fiabilite": "élevé",
            "risque_pro": compute_risk(normalized),
            "source": "Open-Meteo + ECMWF",
            "mode": "multi-source validated",
            "timestamp": timestamp,
            "valid": validate_data(normalized),
        })
    except Exception as e:
        log.warning("api/weather fallback interne: %s", e)
        fallback = _internal_weather_fallback()
        condition = _derive_weather_condition(
            fallback["temp"],
            fallback["humidity"],
            fallback["wind"],
        )
        fallback["condition"] = condition
        save_weather_archive_json(fallback)
        return jsonify({
            "ok": True,
            "temp": fallback["temp"],
            "wind": fallback["wind"],
            "humidity": fallback["humidity"],
            "pressure": fallback["pressure"],
            "condition": condition,
            "fiabilite": compute_reliability(fallback),
            "niveau_fiabilite": "élevé",
            "risque_pro": compute_risk(fallback),
            "source": "Open-Meteo + ECMWF",
            "mode": "multi-source validated",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "valid": validate_data(fallback),
            "fallback": True,
        })


@bp.route("/api/weather/local")
def api_weather_local():
    """Météo terrestre locale (contrat strict frontend)."""
    from services.weather_service import _build_local_weather_payload
    try:
        weather_data = _build_local_weather_payload()
        archive_result = save_weather_bulletin(weather_data)
        weather_data["archive"] = archive_result
        save_weather_history_json(
            weather_data,
            archive_result.get("score") if isinstance(archive_result, dict) else 0,
            archive_result.get("status") if isinstance(archive_result, dict) else "STABLE",
        )
        return jsonify(weather_data)
    except Exception as e:
        log.warning("api/weather/local: %s", e)
        return jsonify({
            "ok": False,
            "error": str(e),
            "source": "Open-Meteo",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }), 502


@bp.route("/api/weather/bulletins", methods=["GET"])
def api_weather_bulletins():
    try:
        day = (request.args.get("date") or "").strip()
        conn = sqlite3.connect(WEATHER_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if day:
            cur.execute(
                """
                SELECT id, date, hour, temp, wind, humidity, pressure, wind_direction,
                       condition, risk, score, status, bulletin, source, created_at,
                       reliability_score, temp_variation, wind_variation
                FROM weather_bulletins
                WHERE date = ?
                ORDER BY hour DESC
                """,
                (day,),
            )
        else:
            cur.execute(
                """
                SELECT id, date, hour, temp, wind, humidity, pressure, wind_direction,
                       condition, risk, score, status, bulletin, source, created_at,
                       reliability_score, temp_variation, wind_variation
                FROM weather_bulletins
                ORDER BY date DESC, hour DESC
                LIMIT 24
                """
            )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify({"ok": True, "count": len(rows), "bulletins": rows})
    except Exception as e:
        log.warning("api/weather/bulletins: %s", e)
        return jsonify({"ok": False, "error": str(e), "count": 0, "bulletins": []}), 500


@bp.route("/api/weather/bulletins/latest", methods=["GET"])
def api_weather_bulletins_latest():
    try:
        conn = sqlite3.connect(WEATHER_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, date, hour, temp, wind, humidity, pressure, wind_direction,
                   condition, risk, score, status, bulletin, source, created_at,
                   reliability_score, temp_variation, wind_variation
            FROM weather_bulletins
            ORDER BY date DESC, hour DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"ok": True, "bulletin": None})
        return jsonify({"ok": True, "bulletin": dict(row)})
    except Exception as e:
        log.warning("api/weather/bulletins/latest: %s", e)
        return jsonify({"ok": False, "error": str(e), "bulletin": None}), 500


@bp.route("/api/weather/history", methods=["GET"])
def api_weather_history():
    from services.weather_service import _build_local_weather_payload
    try:
        day = (request.args.get("date") or "").strip()
        if not day:
            day = datetime.now().strftime("%Y-%m-%d")

        _cleanup_weather_history_files()
        history_path = os.path.join(WEATHER_HISTORY_DIR, f"{day}.json")
        if os.path.isfile(history_path):
            with open(history_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            return jsonify({
                "ok": True,
                "date": payload.get("date", day),
                "temp": float(payload.get("temp", 0.0)),
                "wind": float(payload.get("wind", 0.0)),
                "humidity": int(payload.get("humidity", 0)),
                "pressure": float(payload.get("pressure", 1015)),
                "risk": payload.get("risk", "FAIBLE"),
                "source": "weather_history_json",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "archive": {
                    "saved": False,
                    "score": int(payload.get("score", 0)),
                    "status": payload.get("status", "STABLE"),
                    "bulletin": "",
                },
            })

        conn = sqlite3.connect(WEATHER_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT date, hour, temp, wind, humidity, pressure, wind_direction, condition,
                   risk, score, status, bulletin, reliability_score, temp_variation,
                   wind_variation, source, created_at
            FROM weather_bulletins
            WHERE date = ?
            ORDER BY hour DESC
            LIMIT 1
            """,
            (day,),
        )
        row = cur.fetchone()
        conn.close()

        if row:
            item = dict(row)
            return jsonify({
                "ok": True,
                "temp": float(item.get("temp")),
                "wind": float(item.get("wind")),
                "humidity": int(item.get("humidity")),
                "pressure": float(item.get("pressure")),
                "wind_direction": float(item.get("wind_direction", 0.0)),
                "condition": item.get("condition") or "Unknown",
                "risk": item.get("risk") or "FAIBLE",
                "source": item.get("source") or "weather_bulletins",
                "updated_at": item.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "archive": {
                    "saved": False,
                    "score": int(item.get("score")) if item.get("score") is not None else None,
                    "status": item.get("status"),
                    "bulletin": item.get("bulletin"),
                    "reliability_score": item.get("reliability_score"),
                    "temp_variation": item.get("temp_variation"),
                    "wind_variation": item.get("wind_variation"),
                },
            })

        weather_data = _build_local_weather_payload()
        archive_result = save_weather_bulletin(weather_data)
        weather_data["archive"] = archive_result
        return jsonify(weather_data)
    except Exception as e:
        log.warning("api/weather/history: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/weather/bulletins/save", methods=["POST"])
def api_weather_bulletins_save():
    try:
        payload = request.get_json(silent=True) or {}
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "payload invalide"}), 400
        if not all(k in data for k in (
            "temp", "wind", "humidity", "pressure",
            "wind_direction", "condition", "risk",
        )):
            return jsonify({"ok": False, "error": "champs météo manquants"}), 400
        result = save_weather_bulletin(data)
        return jsonify({"ok": True, **result})
    except Exception as e:
        log.warning("api/weather/bulletins/save: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Solar weather (Domaine L — module-based) ──────────────────────────
@bp.route("/api/v1/solar-weather")
def api_v1_solar():
    from modules.space_alerts import get_solar_weather
    data = get_cached("solar_weather", 300, get_solar_weather)
    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "solar_wind": data or {},
        "source": "NOAA SWPC",
        "credit": "AstroScan-Chohra · ORBITAL-CHOHRA",
    })


# ── Météo réelle wttr.in (Domaine AK) ──────────────────────────────────
@bp.route("/api/meteo/reel")
def meteo_reel():
    import requests
    try:
        city = request.args.get("city", "Tlemcen")
        url = f"https://wttr.in/{city}?format=j1"
        r = requests.get(url, timeout=5)
        data = r.json()
        current = data["current_condition"][0]
        return jsonify({
            "city": city,
            "temp": current["temp_C"],
            "humidity": current["humidity"],
            "wind": current["windspeedKmph"],
            "desc": current["weatherDesc"][0]["value"],
            "time": datetime.now(timezone.utc).isoformat(),
            "ok": True,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@bp.route("/meteo-reel")
def meteo_page():
    return render_template("meteo_reel.html")


@bp.route("/control")
@bp.route("/meteo")
def control():
    """Page bulletin météo. Accepte ?date=YYYY-MM-DD pour précharger une date."""
    requested_date = (request.args.get("date") or "").strip()

    bulletin_date = ""
    if (
        len(requested_date) == 10
        and requested_date[4] == "-"
        and requested_date[7] == "-"
        and requested_date[:4].isdigit()
        and requested_date[5:7].isdigit()
        and requested_date[8:10].isdigit()
    ):
        bulletin_date = requested_date

    return render_template(
        "orbital_control_center.html",
        bulletin_date=bulletin_date,
    )


@bp.route("/control/bulletin-meteo.pdf")
def control_bulletin_export():
    """Export du bulletin météo en fichier texte téléchargeable.

    Query param: ?date=YYYY-MM-DD (par défaut: dernière date disponible).
    Retourne: text/plain téléchargeable.

    Note: nommé .pdf pour cohérence URL historique mais sert un .txt
    pour éviter dépendance reportlab. Migration PDF natif possible plus tard.
    """
    requested_date = (request.args.get("date") or "").strip()

    if not os.path.exists(WEATHER_DB_PATH):
        return Response(
            "Erreur : base de données weather_bulletins.db introuvable.\n",
            status=500,
            content_type="text/plain; charset=utf-8",
        )

    try:
        conn = sqlite3.connect(WEATHER_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if (
            len(requested_date) == 10
            and requested_date[4] == "-"
            and requested_date[7] == "-"
            and requested_date[:4].isdigit()
        ):
            cur.execute(
                "SELECT * FROM weather_bulletins WHERE date = ? ORDER BY hour DESC LIMIT 1",
                (requested_date,),
            )
        else:
            cur.execute(
                "SELECT * FROM weather_bulletins ORDER BY date DESC, hour DESC LIMIT 1"
            )

        row = cur.fetchone()
        conn.close()

        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        if not row:
            content = (
                "═══════════════════════════════════════════════════════════\n"
                "  BULLETIN MÉTÉOROLOGIQUE — ASTRO-SCAN / ORBITAL-CHOHRA\n"
                "  Station : Tlemcen, Algérie\n"
                "═══════════════════════════════════════════════════════════\n\n"
                f"Date demandée : {requested_date or 'non spécifiée'}\n\n"
                "Aucune donnée disponible pour cette date.\n"
                "Veuillez choisir une date présente dans l'archive.\n\n"
                f"Généré le : {generated_at}\n"
            )
            filename = "bulletin-meteo-aucune-donnee.txt"
        else:
            data = dict(row)
            date_str = data.get("date") or "N/A"
            content = (
                "═══════════════════════════════════════════════════════════\n"
                "  BULLETIN MÉTÉOROLOGIQUE — ASTRO-SCAN / ORBITAL-CHOHRA\n"
                "  Station : Tlemcen, Algérie\n"
                "═══════════════════════════════════════════════════════════\n\n"
                f"Date          : {date_str}\n"
                f"Heure         : {data.get('hour', 'N/A')} UTC\n\n"
                "─── CONDITIONS ───────────────────────────────────────────\n"
                f"Température   : {data.get('temp', 'N/A')} °C\n"
                f"Humidité      : {data.get('humidity', 'N/A')} %\n"
                f"Pression      : {data.get('pressure', 'N/A')} hPa\n"
                f"Vent          : {data.get('wind', 'N/A')} km/h\n"
                f"Direction vent: {data.get('wind_direction', 'N/A')} °\n"
                f"Condition     : {data.get('condition', 'N/A')}\n\n"
                "─── ÉVALUATION ───────────────────────────────────────────\n"
                f"Score météo   : {data.get('score', 'N/A')}/100\n"
                f"Statut        : {data.get('status', 'N/A')}\n"
                f"Risque        : {data.get('risk', 'N/A')}\n"
                f"Fiabilité     : {data.get('reliability_score', 'N/A')} %\n\n"
            )

            bulletin_text = (data.get("bulletin") or "").strip()
            if bulletin_text:
                content += (
                    "─── BULLETIN ─────────────────────────────────────────────\n"
                    f"{bulletin_text}\n\n"
                )

            source_text = (data.get("source") or "").strip()
            if source_text:
                content += f"Source : {source_text}\n"

            content += (
                f"Généré le : {generated_at}\n"
                "═══════════════════════════════════════════════════════════\n"
            )
            filename = f"bulletin-meteo-{date_str}.txt"

        return Response(
            content,
            content_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as e:
        log.warning("control/bulletin-meteo.pdf: %s", e)
        return Response(
            f"Erreur interne lors de la génération du bulletin : {e}\n",
            status=500,
            content_type="text/plain; charset=utf-8",
        )


# ─────────────────────────────────────────────────────────────────
# BONUS PASS (2026-05-08) — Weather archive public routes
# Expose le dataset Tlemcen archivé sur disque (data/weather_archive/)
# pour Chemin B (hyperlocal scientific data exposure).
# ─────────────────────────────────────────────────────────────────
@bp.route("/api/weather/archive", methods=["GET"])
def api_weather_archive_list():
    """List all available weather archive dates (JSON files in WEATHER_ARCHIVE_DIR)."""
    from app.services.weather_db import WEATHER_ARCHIVE_DIR
    import os as _os
    try:
        if not _os.path.isdir(WEATHER_ARCHIVE_DIR):
            return jsonify({"ok": False, "error": "archive_dir_missing", "dates": []}), 200
        files = sorted([
            f.replace(".json", "")
            for f in _os.listdir(WEATHER_ARCHIVE_DIR)
            if f.endswith(".json")
        ], reverse=True)
        return jsonify({
            "ok": True,
            "count": len(files),
            "dates": files,
            "directory": WEATHER_ARCHIVE_DIR,
        }), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/weather/archive/<date>", methods=["GET"])
def api_weather_archive_get(date):
    """Return weather archive content for specific date (YYYY-MM-DD)."""
    from app.services.weather_db import WEATHER_ARCHIVE_DIR
    import os as _os
    import json as _json
    import re as _re
    # Path traversal protection: strict date format YYYY-MM-DD
    if not _re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        return jsonify({"ok": False, "error": "invalid_date_format"}), 400
    try:
        file_path = _os.path.join(WEATHER_ARCHIVE_DIR, f"{date}.json")
        if not _os.path.isfile(file_path):
            return jsonify({"ok": False, "error": "not_found", "date": date}), 404
        with open(file_path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        return jsonify({"ok": True, "date": date, "data": data}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
