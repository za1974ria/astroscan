"""External feeds — NASA, NOAA SWPC, JPL Horizons fetchers.

Extrait de station_web.py (PASS 8) pour permettre l'utilisation
par feeds_bp sans dépendance circulaire.

Toutes les fonctions ici utilisent app.services.http_client._curl_get
(curl wrapper) pour contourner les restrictions urllib serveur.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from app.config import STATION
from app.services.http_client import _curl_get, _safe_json_loads

log = logging.getLogger(__name__)


# ── JPL Horizons : Voyager 1 & 2 ──────────────────────────────────────
def fetch_voyager():
    """Position Voyager 1 & 2 via NASA JPL Horizons."""
    try:
        now = _dt.datetime.utcnow()
        y, mo, d = now.year, now.month, now.day
        results = {}
        for name, target in [("VOYAGER_1", "-31"), ("VOYAGER_2", "-32")]:
            url = (
                f"https://ssd.jpl.nasa.gov/api/horizons.api?"
                f"format=text&COMMAND='{target}'&OBJ_DATA=YES&MAKE_EPHEM=YES"
                f"&EPHEM_TYPE=VECTORS&CENTER='500@10'"
                f"&START_TIME='{y}-{mo:02d}-{d:02d}'&STOP_TIME='{y}-{mo:02d}-{d:02d}T23:59'"
                f"&STEP_SIZE='1d'&QUANTITIES='20'"
            )
            raw = _curl_get(url, timeout=20)
            if not raw:
                continue
            dist_au = None
            speed_km_s = None
            rg_match = re.search(r"RG=\s*([\d.]+)", raw)
            if rg_match:
                dist_au = float(rg_match.group(1))
            rr_match = re.search(r"RR=\s*([-\d.]+)", raw)
            if rr_match:
                speed_au_d = float(rr_match.group(1))
                speed_km_s = abs(speed_au_d * 1731.46)
            if dist_au is not None:
                results[name] = {
                    "dist_au": round(dist_au, 4),
                    "dist_km": round(dist_au * 149597870.7),
                    "speed_km_s": round(speed_km_s, 2) if speed_km_s else None,
                    "source": "NASA JPL Horizons",
                }
        return results if results else None
    except Exception as e:
        log.warning("voyager: %s", e)
        return None


# ── NASA NeoWs ─────────────────────────────────────────────────────────
def fetch_neo():
    """Astéroïdes NEO du jour via NASA NeoWs API."""
    try:
        nasa_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        today = _dt.datetime.utcnow().date().isoformat()
        url = (
            f"https://api.nasa.gov/neo/rest/v1/feed?"
            f"start_date={today}&end_date={today}&api_key={nasa_key}"
        )
        raw = _curl_get(url, timeout=20)
        if not raw:
            return None
        data = _safe_json_loads(raw, "neo")
        if not isinstance(data, dict):
            return None
        neos = []
        for date_key, objects in data.get("near_earth_objects", {}).items():
            for obj in (objects or [])[:8]:
                ca = (obj.get("close_approach_data") or [{}])[0]
                dist_au = ca.get("miss_distance", {}).get("astronomical", "?")
                dist_km = ca.get("miss_distance", {}).get("kilometers", "?")
                vel = ca.get("relative_velocity", {}).get("kilometers_per_second", 0)
                try:
                    vel = round(float(vel), 2)
                except (TypeError, ValueError):
                    vel = 0
                diam = obj.get("estimated_diameter", {}).get("meters", {}) or {}
                diam_min = round(float(diam.get("estimated_diameter_min", 0)))
                diam_max = round(float(diam.get("estimated_diameter_max", 0)))
                neos.append({
                    "name": obj.get("name", ""),
                    "dist_au": dist_au,
                    "dist_km": dist_km,
                    "vel_km_s": vel,
                    "diam_min": diam_min,
                    "diam_max": diam_max,
                    "hazardous": obj.get("is_potentially_hazardous_asteroid", False),
                    "date": ca.get("close_approach_date", today),
                })
        neos.sort(key=lambda x: (float(x["dist_au"]) if x["dist_au"] != "?" else 999))
        return neos
    except Exception as e:
        log.warning("neo: %s", e)
        return None


# ── NOAA SWPC : vent solaire DSCOVR ──────────────────────────────────
def fetch_solar_wind():
    """Vent solaire NOAA DSCOVR temps réel."""
    try:
        url = "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json"
        raw = _curl_get(url, timeout=15)
        if not raw:
            return None
        data = _safe_json_loads(raw, "solar_wind")
        if not isinstance(data, list) or len(data) < 2:
            return None
        latest = data[-1]
        return {
            "timestamp": latest[0],
            "density": latest[1],
            "speed": latest[2],
            "temperature": latest[3],
            "source": "NOAA DSCOVR",
        }
    except Exception as e:
        log.warning("solar_wind: %s", e)
        return None


# ── NOAA SWPC : alertes éruptions solaires ───────────────────────────
def fetch_solar_alerts():
    """Alertes éruptions solaires et événements — NOAA SWPC."""
    try:
        out = {"alerts": [], "flares": [], "source": "NOAA SWPC"}
        raw = _curl_get("https://services.swpc.noaa.gov/json/alerts.json", timeout=12)
        if raw:
            data = _safe_json_loads(raw, "solar_alerts")
            if isinstance(data, list):
                out["alerts"] = [a for a in data[-10:] if isinstance(a, dict)]
            elif isinstance(data, dict) and "alerts" in data:
                out["alerts"] = data["alerts"][-10:]
        raw2 = _curl_get(
            "https://services.swpc.noaa.gov/json/xray-flares-latest.json",
            timeout=10,
        )
        if raw2:
            data2 = _safe_json_loads(raw2, "solar_alerts_xray")
            if isinstance(data2, list):
                out["flares"] = data2[-5:]
            elif isinstance(data2, dict):
                fl = data2.get("flares", data2.get("xray_flares", [])) or []
                if isinstance(fl, list):
                    out["flares"] = fl[-5:]
        return out if (out["alerts"] or out["flares"]) else None
    except Exception as e:
        log.warning("solar_alerts: %s", e)
        return None


# ── NASA Mars Rovers ─────────────────────────────────────────────────
def fetch_mars_rover():
    """Photos Mars Rovers (Curiosity / Perseverance) du jour."""
    try:
        nasa_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        photos = []
        for rover in ["curiosity", "perseverance"]:
            try:
                url = (
                    f"https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/"
                    f"latest_photos?api_key={nasa_key}&page=1"
                )
                raw = _curl_get(url, timeout=20)
                if not raw:
                    continue
                data = _safe_json_loads(raw, "mars_rover")
                if not isinstance(data, dict):
                    continue
                for p in (data.get("latest_photos") or [])[:3]:
                    photos.append({
                        "rover": rover.capitalize(),
                        "sol": p.get("sol"),
                        "date": p.get("earth_date"),
                        "camera": (p.get("camera") or {}).get("full_name", ""),
                        "img_url": p.get("img_src", ""),
                    })
            except Exception:
                continue
        return photos if photos else None
    except Exception as e:
        log.warning("mars_rover: %s", e)
        return None


# ── NASA APOD HD ─────────────────────────────────────────────────────
def fetch_apod_hd():
    """APOD HD — image du jour NASA."""
    try:
        nasa_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        url = f"https://api.nasa.gov/planetary/apod?api_key={nasa_key}&hd=True"
        raw = _curl_get(url, timeout=15)
        if not raw:
            return None
        data = _safe_json_loads(raw, "apod_hd")
        if not isinstance(data, dict):
            return None
        img_url = data.get("hdurl") or data.get("url", "")
        if not img_url or not str(img_url).startswith("http"):
            return None
        hd_path = f"{STATION}/telescope_live/apod_hd.jpg"
        subprocess.run(
            ["curl", "-s", "-L", "--max-time", "30", "-o", hd_path, img_url],
            timeout=35, capture_output=True,
        )
        if Path(hd_path).exists():
            return {
                "title": data.get("title", ""),
                "date": data.get("date", ""),
                "explanation": (data.get("explanation") or "")[:300],
                "url": img_url,
                "hd_path": hd_path,
            }
        return {"title": data.get("title", ""), "date": data.get("date", ""), "url": img_url}
    except Exception as e:
        log.warning("apod_hd: %s", e)
        return None


# ── NOAA SWPC : alertes 24h normalisées ───────────────────────────────
def fetch_swpc_alerts():
    """Alertes NOAA SWPC dernières 24h — format normalisé."""
    try:
        raw = _curl_get("https://services.swpc.noaa.gov/products/alerts.json", timeout=12)
        if not raw:
            return []
        data = _safe_json_loads(raw, "swpc_alerts")
        if not isinstance(data, list):
            return []
        cutoff = _dt.datetime.utcnow() - _dt.timedelta(hours=24)
        alerts = []
        for item in data:
            if not isinstance(item, dict):
                continue
            issued_str = (item.get("issue_datetime") or item.get("issued") or "").strip()
            try:
                issued_dt = _dt.datetime.strptime(issued_str[:16], "%Y-%m-%d %H:%M")
            except Exception:
                try:
                    issued_dt = _dt.datetime.strptime(issued_str[:16], "%Y-%m-%dT%H:%M")
                except Exception:
                    issued_dt = _dt.datetime.utcnow()
            if issued_dt < cutoff:
                continue
            msg = (item.get("message") or item.get("msg") or "").strip()
            alert_type = "Alerte Spatiale"
            level = ""
            msg_up = msg.upper()
            if "GEOMAGNETIC" in msg_up or "K-INDEX" in msg_up or "G-SCALE" in msg_up:
                alert_type = "Tempête Géomagnétique"
                for g in ["G5", "G4", "G3", "G2", "G1"]:
                    if g in msg_up:
                        level = g
                        break
                if not level:
                    m_k = re.search(r"K-?index\s+of\s+(\d)", msg, re.IGNORECASE)
                    if m_k:
                        k = int(m_k.group(1))
                        level = "G" + str(max(1, min(5, k - 4))) if k >= 5 else "Kp=" + str(k)
            elif "SOLAR FLARE" in msg_up or "X-RAY" in msg_up or "FLARE" in msg_up:
                alert_type = "Éruption Solaire"
                m_f = re.search(r"\b([XMC]\d[\.\d]*)\b", msg, re.IGNORECASE)
                if m_f:
                    level = m_f.group(1).upper()
                else:
                    for cls in ["X", "M", "C"]:
                        if cls + "-CLASS" in msg_up or " " + cls + " CLASS" in msg_up:
                            level = cls
                            break
            elif "RADIATION STORM" in msg_up or "S-SCALE" in msg_up or "PROTON" in msg_up:
                alert_type = "Tempête Radiative"
                for s in ["S5", "S4", "S3", "S2", "S1"]:
                    if s in msg_up:
                        level = s
                        break
            elif "RADIO BLACKOUT" in msg_up or "R-SCALE" in msg_up:
                alert_type = "Éclipse Radio"
                for r in ["R5", "R4", "R3", "R2", "R1"]:
                    if r in msg_up:
                        level = r
                        break
            alerts.append({
                "type": alert_type,
                "level": level,
                "message": msg[:300],
                "issued": issued_str,
                "issued_dt": issued_dt.strftime("%Y-%m-%dT%H:%M"),
            })
        return sorted(alerts, key=lambda x: x["issued_dt"], reverse=True)[:10]
    except Exception as e:
        log.warning("swpc_alerts: %s", e)
        return []
