# -*- coding: utf-8 -*-
"""Géocodage Nominatim, météo wttr.in, génération guide via Claude (ORBITAL-CHOHRA)."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

# Nominatim exige un User-Agent identifiable (contact).
_GEO_HEADERS = {"User-Agent": "ASTRO-SCAN/1.0 orbital-chohra@gmail.com"}
_NOMINATIM_TIMEOUT = 5


def _geocode_photon(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Fallback rapide si Nominatim est lent ou bloqué (Photon / Komoot)."""
    q = (query or "").strip()
    if len(q) < 2:
        return []
    try:
        r = requests.get(
            "https://photon.komoot.io/api/",
            params={"q": q, "limit": limit},
            headers=_GEO_HEADERS,
            timeout=_NOMINATIM_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        out: List[Dict[str, Any]] = []
        for feat in data.get("features") or []:
            try:
                geom = feat.get("geometry") or {}
                coords = geom.get("coordinates") or []
                lon, lat = float(coords[0]), float(coords[1])
            except (IndexError, TypeError, ValueError):
                continue
            props = feat.get("properties") or {}
            name = (
                props.get("name")
                or props.get("city")
                or props.get("county")
                or props.get("state")
                or q
            )
            parts = [
                props.get("street"),
                props.get("city"),
                props.get("state"),
                props.get("country"),
            ]
            label = ", ".join(str(p) for p in parts if p) or name
            if len(label) > 120:
                label = label[:117] + "..."
            out.append({"label": label, "lat": lat, "lon": lon, "name": name})
        return out
    except Exception as e:
        log.warning("geocode_photon: %s", e)
        return []


def geocode_search(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Suggestions : Nominatim (5 s max) puis Photon en secours."""
    q = (query or "").strip()
    if len(q) < 2:
        return []
    out: List[Dict[str, Any]] = []
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": limit, "addressdetails": 1},
            headers=_GEO_HEADERS,
            timeout=_NOMINATIM_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            for row in data:
                try:
                    lat = float(row.get("lat", 0))
                    lon = float(row.get("lon", 0))
                except (TypeError, ValueError):
                    continue
                out.append(
                    {
                        "label": row.get("display_name", "")[:120],
                        "lat": lat,
                        "lon": lon,
                        "name": row.get("name") or row.get("display_name", "").split(",")[0],
                    }
                )
    except Exception as e:
        log.warning("geocode_search nominatim: %s", e)

    if out:
        return out
    return _geocode_photon(q, limit=min(limit, 5))


def fetch_weather_wttr_ville(ville: str) -> Dict[str, Any]:
    """Météo wttr.in par nom de ville : https://wttr.in/{ville}?format=j1"""
    v = (ville or "").strip()
    if not v:
        return {"error": "ville vide"}
    headers = _GEO_HEADERS
    path = quote(v, safe="")
    url = f"https://wttr.in/{path}?format=j1"
    try:
        r = requests.get(url, timeout=18, headers=headers)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        return r.json()
    except Exception as e:
        log.warning("wttr.in ville: %s", e)
        return {"error": str(e)}


def fetch_weather_wttr_coords(lat: float, lon: float) -> Dict[str, Any]:
    """Fallback météo par coordonnées."""
    url = f"https://wttr.in/{lat:.4f},{lon:.4f}?format=j1"
    headers = _GEO_HEADERS
    try:
        r = requests.get(url, timeout=18, headers=headers)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        return r.json()
    except Exception as e:
        log.warning("wttr.in coords: %s", e)
        return {"error": str(e)}


def summarize_weather(j: Dict[str, Any]) -> str:
    if not j or j.get("error"):
        return str(j.get("error", "Météo indisponible"))
    try:
        cur = j["current_condition"][0]
        desc = (cur.get("weatherDesc") or [{}])[0].get("value", "")
        return f"{desc}, {cur.get('temp_C', '?')}°C, humidité {cur.get('humidity', '?')}%"
    except Exception:
        return "Météo (résumé indisponible)"


def fetch_sunrise_sunset(lat: float, lon: float, date_iso: str) -> Dict[str, Any]:
    url = "https://api.sunrise-sunset.org/json"
    params = {"lat": lat, "lng": lon, "date": date_iso, "formatted": "0"}
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "OK":
            return {"error": data.get("status", "unknown")}
        return dict(data.get("results") or {})
    except Exception as e:
        log.warning("sunrise-sunset: %s", e)
        return {"error": str(e)}


def planets_v1_payload() -> Dict[str, Any]:
    """Même contenu logique que GET /api/v1/planets (catalogue planétaire)."""
    from datetime import datetime, timezone

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "planets": [
            {"name": "Mercure", "distance_au": 0.39, "diameter_km": 4879, "moons": 0, "type": "Tellurique"},
            {"name": "Vénus", "distance_au": 0.72, "diameter_km": 12104, "moons": 0, "type": "Tellurique"},
            {"name": "Terre", "distance_au": 1.0, "diameter_km": 12742, "moons": 1, "type": "Tellurique"},
            {"name": "Mars", "distance_au": 1.52, "diameter_km": 6779, "moons": 2, "type": "Tellurique"},
            {"name": "Jupiter", "distance_au": 5.2, "diameter_km": 139820, "moons": 95, "type": "Gazeuse"},
            {"name": "Saturne", "distance_au": 9.58, "diameter_km": 116460, "moons": 146, "type": "Gazeuse"},
            {"name": "Uranus", "distance_au": 19.2, "diameter_km": 50724, "moons": 28, "type": "Gazeuse"},
            {"name": "Neptune", "distance_au": 30.05, "diameter_km": 49244, "moons": 16, "type": "Gazeuse"},
        ],
        "credit": "AstroScan-Chohra · ORBITAL-CHOHRA",
    }


def generate_orbital_guide_opus(
    ville: str,
    lat: float,
    lon: float,
    moon_data: str,
    meteo_data: str,
    planets_data: str,
    sun_ephemeris: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Appel Claude (SDK anthropic), modèle Opus — prompt utilisateur structuré ORBITAL-CHOHRA."""
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return None, "ANTHROPIC_API_KEY non configurée"
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        user_text = f"""Tu es ORBITAL-CHOHRA, guide astronomique expert et poète des étoiles.

Génère un guide d'observation personnalisé pour ce soir depuis {ville}
(latitude: {lat}, longitude: {lon}).

Données actuelles :
- Phase lune : {moon_data}
- Météo : {meteo_data}
- Planètes visibles : {planets_data}
- Soleil & crépuscules (réf. sunrise-sunset.org, UTC) : {sun_ephemeris}

Inclus obligatoirement :
1. 🌟 ACCUEIL COSMIQUE (2 phrases poétiques sur le ciel ce soir)
2. 🕐 HEURES OPTIMALES (coucher soleil, nuit astronomique, aube)
3. 🔭 TOP 5 OBJETS À OBSERVER (avec difficulté et matériel requis)
4. 🌙 LUNE CE SOIR (impact sur l'observation)
5. ⭐ CONSTELLATION DU MOIS (histoire mythologique incluse)
6. 🪐 PLANÈTES VISIBLES (positions et heures)
7. 💡 CONSEIL EXPERT DU SOIR (1 tip exclusif)
8. 🌌 ANECDOTE COSMIQUE (fait surprenant lié à ce soir)

Ton : scientifique, poétique, inspirant. En français."""
        model_id = (os.environ.get("GUIDE_STELLAIRE_MODEL") or "claude-opus-4-5").strip()
        msg = client.messages.create(
            model=model_id,
            max_tokens=1024,
            messages=[{"role": "user", "content": user_text}],
        )
        if not msg.content:
            return None, "Réponse Claude vide"
        text = msg.content[0].text.strip()
        return text, None
    except Exception as e:
        log.exception("Claude guide stellaire (Opus)")
        return None, str(e)
