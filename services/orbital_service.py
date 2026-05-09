"""Logique orbitale AstroScan — TLE, ISS, satellites.

Fonctions pures extraites de station_web.py + nouveaux wrappers autonomes.
Aucune dépendance Flask ni globals station_web.
"""

import requests

from services.circuit_breaker import CB_ISS


# ── Fonctions pures TLE / fusion ─────────────────────────────────────────────

def compute_tle_risk_signal(tle_data_freshness):
    """Signal orbital simple dérivé de data_freshness (TLE)."""
    df = str(tle_data_freshness or "").strip().lower()
    if df == "fresh":
        return "MEDIUM"
    if df == "stale":
        return "HIGH"
    return "LOW"


def build_final_core(priority_object, tle_risk, nasa_data):
    """Fusion finale NASA + TLE (risque) + Stellarium (priority_object)."""
    try:
        nd = nasa_data if isinstance(nasa_data, dict) else {}
        score = 0.0
        signals = []

        if priority_object and isinstance(priority_object, dict):
            try:
                sc = int(priority_object.get("score") or 0)
                score += sc * 0.5
            except (TypeError, ValueError):
                pass
            signals.append("object_priority")

        if tle_risk == "HIGH":
            score += 30
            signals.append("tle_high_risk")
        elif tle_risk == "MEDIUM":
            score += 15
            signals.append("tle_medium_risk")

        if nd.get("url"):
            score += 10
            signals.append("nasa_visual")

        score_i = int(min(score, 100))
        return {
            "fusion_score": score_i,
            "signals": signals,
            "active": bool(signals),
        }
    except Exception:
        return {"fusion_score": 0, "signals": [], "active": False}


def normalize_celestrak_record(rec):
    """Normalise un enregistrement JSON CelesTrak GP ou SatNOGS en structure TLE homogène."""
    try:
        tle0_raw = rec.get("tle0") or ""
        tle0_name = tle0_raw[2:] if tle0_raw.startswith("0 ") else tle0_raw
        name = (rec.get("OBJECT_NAME") or rec.get("object_name") or tle0_name or "").strip()
        line1 = (rec.get("TLE_LINE1") or rec.get("tle_line1") or rec.get("tle1") or "").strip()
        line2 = (rec.get("TLE_LINE2") or rec.get("tle_line2") or rec.get("tle2") or "").strip()
        if not name or not line1 or not line2:
            return None
        return {
            "name": name,
            "norad_cat_id": rec.get("NORAD_CAT_ID") or rec.get("norad_cat_id"),
            "tle_line1": line1,
            "tle_line2": line2,
            "object_type": rec.get("OBJECT_TYPE") or rec.get("object_type"),
            "epoch": rec.get("EPOCH") or rec.get("epoch") or rec.get("updated"),
        }
    except Exception:
        return None


# ── Lecture fichier TLE ───────────────────────────────────────────────────────

def load_tle_data(path):
    """Parse un fichier TLE 3-lignes. Retourne liste de dicts {name, line1, line2}."""
    entries = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip() for l in f if l.strip()]
        i = 0
        while i + 2 < len(lines):
            name = lines[i].lstrip("0 ").strip()
            l1 = lines[i + 1].strip()
            l2 = lines[i + 2].strip()
            if l1.startswith("1 ") and l2.startswith("2 "):
                entries.append({"name": name, "line1": l1, "line2": l2})
                i += 3
            else:
                i += 1
    except Exception:
        pass
    return entries


# ── Position ISS (Where The ISS At) ──────────────────────────────────────────

def get_iss_position():
    """Position ISS courante via wheretheiss.at — protégée par CB_ISS."""
    def _raw():
        r = requests.get(
            "https://api.wheretheiss.at/v1/satellites/25544",
            timeout=8,
        )
        r.raise_for_status()
        d = r.json()
        return {
            "ok": True,
            "latitude": d.get("latitude"),
            "longitude": d.get("longitude"),
            "altitude_km": d.get("altitude"),
            "velocity_kms": d.get("velocity"),
            "timestamp": d.get("timestamp"),
            "visibility": d.get("visibility"),
            "source": "wheretheiss.at",
        }
    return CB_ISS.call(_raw, fallback={"ok": False, "error": "ISS indisponible (circuit ouvert)"})


def get_iss_orbit():
    """Wrapper public autour de get_iss_position."""
    return get_iss_position()


# ── Track satellite via SGP4 ──────────────────────────────────────────────────

def compute_satellite_track(tle_line1, tle_line2, steps=90, step_seconds=60):
    """Propagation SGP4 déléguée à app/services/orbit_sgp4. Retourne liste de points."""
    try:
        from app.services.orbit_sgp4 import propagate_tle
        return propagate_tle(tle_line1, tle_line2, steps=steps, step_seconds=step_seconds)
    except Exception as e:
        return {"ok": False, "error": str(e)}
