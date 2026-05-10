"""Logique météo AstroScan — terrestre + spatiale (Kp / aurores).

Source unique extraite de station_web.py.
Aucune dépendance Flask. Testable isolément.
"""

import requests
from datetime import datetime, timezone

from services.circuit_breaker import CB_NOAA, CB_METEO


# ── Codes météo WMO ──────────────────────────────────────────────────────────

def interpretWeatherCode(code):
    try:
        c = int(code)
    except Exception:
        c = -1
    if c == 0:
        return {"condition": "Ciel clair", "phenomenon": "Aucun phénomène significatif", "severity": "faible"}
    if c in (1, 2, 3):
        return {"condition": "Partiellement nuageux", "phenomenon": "Nébulosité", "severity": "faible"}
    if c in (45, 48):
        return {"condition": "Brouillard", "phenomenon": "Brouillard", "severity": "modérée"}
    if c in (51, 53, 55):
        return {"condition": "Bruine", "phenomenon": "Bruine", "severity": "modérée"}
    if c in (61, 63, 65):
        return {"condition": "Pluie", "phenomenon": "Pluie", "severity": "modérée"}
    if c in (66, 67):
        return {"condition": "Pluie verglaçante", "phenomenon": "Pluie verglaçante", "severity": "élevée"}
    if c in (71, 73, 75):
        return {"condition": "Neige", "phenomenon": "Neige", "severity": "élevée"}
    if c == 77:
        return {"condition": "Grains de neige", "phenomenon": "Grains de neige", "severity": "modérée"}
    if c in (80, 81, 82):
        return {"condition": "Averses", "phenomenon": "Averses", "severity": "modérée"}
    if c in (85, 86):
        return {"condition": "Averses de neige", "phenomenon": "Averses de neige", "severity": "élevée"}
    if c == 95:
        return {"condition": "Orage", "phenomenon": "Orage", "severity": "élevée"}
    if c in (96, 99):
        return {"condition": "Orage avec grêle", "phenomenon": "Orage avec grêle", "severity": "critique"}
    return {"condition": "Inconnue", "phenomenon": "Non déterminé", "severity": "faible"}


# ── Scoring météo terrestre ──────────────────────────────────────────────────

def compute_weather_score(data):
    score = 100
    temp = float(data.get("temp", 0))
    wind = float(data.get("wind", 0))
    humidity = float(data.get("humidity", 0))
    risk = str(data.get("risk") or "FAIBLE")
    weather_code = int(data.get("weather_code", -1))
    snowfall = float(data.get("snowfall", 0))
    wind_gust = float(data.get("wind_gust", 0))
    precipitation = float(data.get("precipitation", 0))
    visibility = float(data.get("visibility", 10000))

    if humidity > 85:
        score -= 15
    elif humidity > 70:
        score -= 10
    if wind > 40:
        score -= 25
    elif wind > 20:
        score -= 10
    if temp < 5 or temp > 38:
        score -= 20
    elif temp < 12 or temp > 30:
        score -= 10
    if risk == "ÉLEVÉ":
        score -= 25
    elif risk == "MOYEN":
        score -= 10
    if weather_code in (95, 96, 99):
        score -= 25
    if snowfall > 0:
        score -= 15
    if wind_gust > 60:
        score -= 20
    if precipitation > 10:
        score -= 15
    if visibility < 1000:
        score -= 15
    if temp < 0 or temp > 38:
        score -= 20

    score = max(0, min(100, int(round(score))))
    if score >= 85:
        status = "OPTIMAL"
    elif score >= 70:
        status = "STABLE"
    elif score >= 50:
        status = "INSTABLE"
    else:
        status = "CRITIQUE"
    return score, status


def generate_weather_bulletin(data, score, status):
    now = datetime.now()
    dt_txt = now.strftime("%d/%m/%Y")
    hr_txt = now.strftime("%H")
    temp = float(data.get("temp", 0))
    wind = float(data.get("wind", 0))
    humidity = int(round(float(data.get("humidity", 0))))
    pressure = int(round(float(data.get("pressure", 1015))))
    wind_direction = float(data.get("wind_direction", 0.0))
    condition = str(data.get("condition") or "Inconnue")
    risk = str(data.get("risk") or "FAIBLE")
    cloud_cover = float(data.get("cloud_cover", 0))
    visibility = float(data.get("visibility", 0))
    rain = float(data.get("rain", 0))
    snowfall = float(data.get("snowfall", 0))
    wind_gust = float(data.get("wind_gust", 0))
    phenomenon = str(data.get("phenomenon") or condition)
    hail_possible = bool(data.get("hail_possible", False))
    reliability = data.get("reliability_score")
    reliability_txt = f"{int(reliability)}%" if isinstance(reliability, (int, float)) else "--%"

    zone = "Tlemcen, Algérie"
    vis_km = round(visibility / 1000.0, 1) if visibility > 0 else 0.0
    cloud_txt = f"{cloud_cover:.0f}%"
    hail_txt = "possible" if hail_possible else "aucun signal détecté"

    return (
        f"Bulletin météorologique AstroScan — {dt_txt} à {hr_txt}h00. "
        f"Zone analysée : {zone}. Température {temp:.1f}°C, vent moyen {wind:.1f} km/h "
        f"orienté à {wind_direction:.1f}°, rafales {wind_gust:.1f} km/h, humidité {humidity}%, "
        f"pression {pressure} hPa. "
        f"Phénomène dominant : {phenomenon}. Condition : {condition}. "
        f"Précipitations : pluie {rain:.1f} mm, neige {snowfall:.1f} cm. "
        f"Risque de grêle : {hail_txt}. "
        f"Visibilité : {vis_km:.1f} km. Couverture nuageuse : {cloud_txt}. "
        f"Risque météo : {risk}. "
        f"Score météo : {score}/100. Statut système : {status}. "
        f"Indice de fiabilité des données : {reliability_txt}. "
        f"Conclusion opérationnelle : conditions "
        f"{'globalement stables' if score >= 70 else 'sous vigilance renforcée'}, "
        f"surveillance recommandée en cas d'évolution rapide."
    )


# ── Normalisation / validation / calculs dérivés ─────────────────────────────

def normalize_weather(data):
    temperature = float(data.get("temperature", 0.0) or 0.0)
    windspeed = float(data.get("windspeed", 0.0) or 0.0)
    humidity = int(round(float(data.get("humidity", 0) or 0)))
    pressure = int(round(float(data.get("pressure", 1013) or 1013)))
    temperature = max(-50.0, min(60.0, temperature))
    windspeed = max(0.0, min(200.0, windspeed))
    humidity = max(0, min(100, humidity))
    pressure = max(850, min(1100, pressure))
    return {
        "temp": round(temperature, 1),
        "wind": round(windspeed, 1),
        "humidity": humidity,
        "pressure": pressure,
        "source": "open-meteo",
    }


def compute_reliability(data, source=None):
    score = 100
    temp_val = data.get("temperature", data.get("temp"))
    wind_val = data.get("wind", data.get("windspeed"))
    humidity_val = data.get("humidity")
    if temp_val is None:
        score -= 20
    if wind_val is None:
        score -= 15
    if humidity_val is None:
        score -= 10
    trusted_sources = {"Open-Meteo", "NOAA", "ECMWF"}
    effective_source = source if isinstance(source, str) else data.get("source")
    if effective_source in trusted_sources:
        score += 5
    return max(0, min(100, int(round(score))))


def compute_weather_reliability(data):
    return compute_reliability(data)


def validate_data(data):
    temp = float(data.get("temp", 0.0) or 0.0)
    return -80 <= temp <= 60


def compute_risk(data):
    if float(data.get("wind", 0.0) or 0.0) > 70:
        return "élevé"
    if float(data.get("humidity", 0.0) or 0.0) > 90:
        return "modéré"
    return "faible"


def _internal_weather_fallback():
    return {
        "temp": 22.0,
        "wind": 12.0,
        "humidity": 55,
        "pressure": 1013,
        "source": "internal-fallback",
    }


def _derive_weather_condition(temp, humidity, wind):
    if wind >= 45:
        return "Venteux"
    if humidity >= 85:
        return "Humide"
    if temp >= 30:
        return "Chaud"
    if temp <= 5:
        return "Froid"
    return "Stable"


# ── Kp / aurores / météo spatiale ────────────────────────────────────────────

def _safe_kp_value(raw_value):
    try:
        kp = float(raw_value)
    except (TypeError, ValueError):
        kp = None
    if kp is None or not (kp == kp) or kp in (float("inf"), float("-inf")):
        return 0.0, "fallback", "Données Kp indisponibles, fallback utilisé"
    return round(kp, 2), "live", "Données Kp en direct"


def _kp_premium_profile(kp, fallback=False):
    if kp <= 2:
        base = {
            "level": "calme",
            "risk_score": 10,
            "visibility_from_tlemcen": "très faible",
            "color": "green",
            "message": "Activité géomagnétique calme",
            "professional_summary": (
                "Conditions spatiales stables. Aucune probabilité significative "
                "d'aurore visible depuis Tlemcen."
            ),
        }
    elif kp <= 4:
        base = {
            "level": "modéré",
            "risk_score": 35,
            "visibility_from_tlemcen": "faible",
            "color": "yellow",
            "message": "Activité géomagnétique modérée",
            "professional_summary": (
                "L'activité solaire reste modérée. Une visibilité aurorale depuis "
                "Tlemcen demeure très improbable."
            ),
        }
    elif kp < 6:
        base = {
            "level": "actif",
            "risk_score": 65,
            "visibility_from_tlemcen": "possible",
            "color": "orange",
            "message": "Activité géomagnétique active",
            "professional_summary": (
                "Perturbation géomagnétique détectée. Une observation exceptionnelle "
                "reste possible dans des conditions rares."
            ),
        }
    else:
        base = {
            "level": "tempête",
            "risk_score": 90,
            "visibility_from_tlemcen": "élevée",
            "color": "red",
            "message": "Tempête géomagnétique",
            "professional_summary": (
                "Tempête géomagnétique notable. Surveillance recommandée des "
                "conditions spatiales et de la visibilité nocturne."
            ),
        }
    if fallback:
        base.update({
            "level": "calme",
            "risk_score": 10,
            "visibility_from_tlemcen": "très faible",
            "color": "green",
            "message": "Activité géomagnétique calme",
            "professional_summary": (
                "Conditions spatiales stables. Données temps réel temporairement "
                "indisponibles, estimation de sécurité appliquée."
            ),
        })
    return base


# ── Fetch Open-Meteo (météo terrestre) ───────────────────────────────────────

def _fetch_open_meteo_raw():
    """Fetch Open-Meteo brut — levée d'exception si erreur (pour CB_METEO)."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=34.87&longitude=-1.32"
        "&current=temperature_2m,relative_humidity_2m,precipitation,rain,showers,snowfall,"
        "weather_code,cloud_cover,visibility,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
    )
    response = requests.get(url, timeout=12)
    response.raise_for_status()
    return response.json() if response.content else {}


def _build_local_weather_payload():
    payload = CB_METEO.call(_fetch_open_meteo_raw, fallback=None)
    if payload is None:
        fb = _internal_weather_fallback()
        fb["source"] = "fallback (Open-Meteo indisponible)"
        return fb
    current = payload.get("current") or {}

    temp = float(current.get("temperature_2m"))
    wind = float(current.get("wind_speed_10m"))
    humidity = int(round(float(current.get("relative_humidity_2m"))))
    wind_direction = float(current.get("wind_direction_10m", 0.0))
    pressure = int(round(float(current.get("surface_pressure", 1015))))
    precipitation = float(current.get("precipitation", 0.0))
    rain = float(current.get("rain", 0.0))
    showers = float(current.get("showers", 0.0))
    snowfall = float(current.get("snowfall", 0.0))
    weather_code = int(current.get("weather_code", -1))
    cloud_cover = float(current.get("cloud_cover", 0.0))
    visibility = float(current.get("visibility", 0.0))
    wind_gust = float(current.get("wind_gusts_10m", 0.0))

    interpretation = interpretWeatherCode(weather_code)
    condition = interpretation.get("condition") or "Inconnue"
    phenomenon = interpretation.get("phenomenon") or "Non déterminé"
    severity = interpretation.get("severity") or "faible"

    if wind > 40:
        risk = "ÉLEVÉ"
    elif wind > 20:
        risk = "MOYEN"
    else:
        risk = "FAIBLE"

    hail_possible = weather_code in (96, 99)
    if snowfall > 0:
        phenomenon = "Neige détectée"
        severity = "élevée"
    if hail_possible:
        phenomenon = "Risque de grêle"
        severity = "critique"
    if wind_gust > 60:
        phenomenon = "Rafales fortes"
        severity = "élevée"
    if visibility > 0 and visibility < 1000:
        phenomenon = "Brouillard dense"
        severity = "élevée"
    if precipitation > 10:
        phenomenon = "Fortes précipitations"
        severity = "élevée"
    if temp > 38:
        phenomenon = "Chaleur extrême"
        severity = "critique"
    if temp < 0:
        phenomenon = "Gel possible"
        severity = "élevée"

    return {
        "ok": True,
        "temp": temp,
        "wind": wind,
        "humidity": humidity,
        "risk": risk,
        "pressure": pressure,
        "wind_direction": wind_direction,
        "wind_gust": wind_gust,
        "condition": condition,
        "phenomenon": phenomenon,
        "severity": severity,
        "precipitation": precipitation,
        "rain": rain,
        "showers": showers,
        "snowfall": snowfall,
        "weather_code": weather_code,
        "cloud_cover": cloud_cover,
        "visibility": visibility,
        "hail_possible": hail_possible,
        "source": "Open-Meteo",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── API publique ─────────────────────────────────────────────────────────────

def get_weather_snapshot():
    """Météo terrestre locale (Open-Meteo, Tlemcen)."""
    try:
        return _build_local_weather_payload()
    except Exception as e:
        fb = _internal_weather_fallback()
        fb["ok"] = False
        fb["error"] = str(e)
        return fb


def get_kp_index():
    """Fetch Kp index depuis NOAA — protégé par CB_NOAA. Retourne (kp_float, status_str)."""
    def _raw():
        r = requests.get(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            timeout=12,
        )
        r.raise_for_status()
        raw_data = r.json()
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
        return kp, status
    result = CB_NOAA.call(_raw, fallback=None)
    return result if result is not None else (0.0, "fallback")


def get_aurora_data():
    """Kp + profil de visibilité aurore depuis NOAA."""
    try:
        kp, status = get_kp_index()
        is_fallback = status == "fallback"
        profile = _kp_premium_profile(kp, fallback=is_fallback)
        return {
            "ok": True,
            "kp": kp,
            "status": status,
            "source": "NOAA_or_fallback",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **profile,
        }
    except Exception as e:
        profile = _kp_premium_profile(0.0, fallback=True)
        return {
            "ok": True,
            "kp": 0.0,
            "status": "fallback",
            "source": "fallback",
            "error": str(e),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **profile,
        }


def get_space_weather():
    """Snapshot météo spatiale complet (Kp + profil aurore)."""
    try:
        kp, status = get_kp_index()
        is_fallback = status == "fallback"
        profile = _kp_premium_profile(kp, fallback=is_fallback)
        return {
            "ok": True,
            "kp": kp,
            "status": status,
            "source": "NOAA",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **profile,
        }
    except Exception as e:
        profile = _kp_premium_profile(0.0, fallback=True)
        return {
            "ok": True,
            "kp": 0.0,
            "status": "fallback",
            "error": str(e),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **profile,
        }


def _kp_status_legacy_fr(kp):
    """Mappe Kp → statut magnétosphère (schéma legacy frontend)."""
    if kp is None:
        return "Indisponible"
    if kp <= 3:
        return "CALME (VERT)"
    if kp <= 5:
        return "MODÉRÉ (JAUNE)"
    if kp <= 7:
        return "ACTIF (ORANGE)"
    return "SÉVÈRE (ROUGE)"


def _kp_impact_orbital_fr(kp):
    """Mappe Kp → impact orbital (schéma legacy frontend)."""
    if kp is None:
        return "Indisponible"
    if kp <= 3:
        return "Conditions calmes — orbites basses normales."
    if kp <= 5:
        return "Perturbations mineures possibles sur les orbites basses."
    if kp <= 7:
        return "Drag atmosphérique et erreurs GPS possibles."
    return "Risque élevé pour satellites et infrastructures (courants telluriques)."


def get_space_weather_legacy():
    """Snapshot météo spatiale au schéma legacy (frontend templates).

    Renvoie : {mise_a_jour_utc, kp_index, statut_magnetosphere,
              impact_orbital, source}.
    """
    kp, status = get_kp_index()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if status == "live":
        source = "NOAA Space Weather Prediction Center"
    else:
        source = "NOAA (fallback)"
    return {
        "mise_a_jour_utc": now_utc,
        "kp_index": kp,
        "statut_magnetosphere": _kp_status_legacy_fr(kp),
        "impact_orbital": _kp_impact_orbital_fr(kp),
        "source": source,
    }
