"""ISS compute helpers — SGP4 ground track + passes (Tlemcen + observer).

Extrait de station_web.py (PASS 14) pour permettre l'utilisation
par iss_bp sans dépendance circulaire.

PASS 27.13 (2026-05-09) — Ajout de 4 helpers TLE + passes calculateur :
    _run_calculateur_passages_iss() -> bool   # subprocess calculateur_passages.py
    ensure_passages_iss_json() -> bool        # garantit présence du fichier JSON
    _get_iss_tle_from_cache() -> tuple|None   # cherche ISS dans TLE_CACHE + fallback fichier
    _get_satellite_tle_by_name(name) -> tuple # cherche par nom canonique

Fonctions exposées :
    _az_to_direction(az_deg) -> str
    compute_iss_ground_track() -> dict       # 90 min, pas 90s, format {"track": [[lat, lon], ...]}
    compute_iss_passes_for_observer(lat, lon) -> list  # 5 prochains passages
    compute_iss_passes_tlemcen() -> list     # alias coords Tlemcen
    + les 4 helpers PASS 27.13 ci-dessus
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import os
import subprocess
import sys
from typing import List

from app.services.station_state import STATION

log = logging.getLogger(__name__)

# Constantes de chemins (cohérent avec station_web.py L262-264)
PASSAGES_ISS_JSON = f'{STATION}/static/passages_iss.json'
CALC_PASSAGES_SCRIPT = os.path.join(STATION, 'calculateur_passages.py')


def _run_calculateur_passages_iss():
    """Exécute calculateur_passages.py pour régénérer static/passages_iss.json."""
    try:
        r = subprocess.run(
            [sys.executable, CALC_PASSAGES_SCRIPT],
            cwd=STATION,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            log.error(
                'passages-iss: calculateur échec rc=%s stderr=%s',
                r.returncode,
                (r.stderr or '')[:800],
            )
            return False
        log.info('passages-iss: fichier JSON généré par calculateur_passages.py')
        return os.path.isfile(PASSAGES_ISS_JSON)
    except subprocess.TimeoutExpired:
        log.error('passages-iss: calculateur timeout (>120s)')
        return False
    except Exception as e:
        log.error('passages-iss: calculateur exception %s', e)
        return False


def ensure_passages_iss_json():
    """Si passages_iss.json est absent, lance le calculateur. Retourne True si le fichier existe."""
    if os.path.isfile(PASSAGES_ISS_JSON):
        return True
    log.info('passages-iss: fichier absent, lancement auto du calculateur…')
    return _run_calculateur_passages_iss()


def _get_iss_tle_from_cache():
    # moved to app/services/tle.py (get_iss_tle_from_sources)
    """Retourne (tle1, tle2) ISS depuis TLE_CACHE si disponible."""
    # Lazy imports inside pour éviter le cycle station_web ↔ iss_compute :
    # _emit_diag_json est défini dans station_web.py et accédé post-bootstrap.
    from app.services.tle_cache import TLE_CACHE, TLE_ACTIVE_PATH, _parse_tle_file
    from station_web import _emit_diag_json
    try:
        items = (TLE_CACHE or {}).get("items") or []
        for item in items:
            name = str(item.get("name") or "").upper()
            if "ISS" in name or "ZARYA" in name:
                tle1 = str(
                    item.get("line1")
                    or item.get("tle1")
                    or item.get("tle_line1")
                    or ""
                ).strip()
                tle2 = str(
                    item.get("line2")
                    or item.get("tle2")
                    or item.get("tle_line2")
                    or ""
                ).strip()
                if tle1 and tle2:
                    _emit_diag_json(
                        {
                            "event": "iss_tle_loaded",
                            "name": item.get("name"),
                            "tle1_len": len(tle1),
                            "tle2_len": len(tle2),
                        }
                    )
                    return tle1, tle2
    except Exception as e:
        _emit_diag_json(
            {
                "event": "iss_tle_missing",
                "reason": f"exception:{e}",
            }
        )
    # Fallback TLE: scanner le fichier complet (le cache items peut être tronqué à 1000 entrées).
    try:
        if os.path.isfile(TLE_ACTIVE_PATH):
            all_items = _parse_tle_file(TLE_ACTIVE_PATH)
            for item in all_items:
                name = str(item.get("name") or "").upper()
                if "ISS" in name or "ZARYA" in name:
                    tle1 = str(item.get("line1") or "").strip()
                    tle2 = str(item.get("line2") or "").strip()
                    if tle1 and tle2:
                        _emit_diag_json(
                            {
                                "event": "iss_tle_loaded",
                                "name": item.get("name"),
                                "source": "tle_active_file",
                                "tle1_len": len(tle1),
                                "tle2_len": len(tle2),
                            }
                        )
                        return tle1, tle2
    except Exception as e:
        _emit_diag_json(
            {
                "event": "iss_tle_missing",
                "reason": f"file_scan_exception:{e}",
            }
        )

    _emit_diag_json(
        {
            "event": "iss_tle_missing",
            "tle_items_count": len((TLE_CACHE or {}).get("items") or []),
        }
    )
    return None, None


def _get_satellite_tle_by_name(target_name):
    from app.services.tle_cache import TLE_CACHE, TLE_ACTIVE_PATH, _parse_tle_file
    from app.services.satellites import get_satellite_tle_name_map

    target_upper = str(target_name or "").upper()
    canonical = get_satellite_tle_name_map().get(target_upper, target_upper)

    for item in (TLE_CACHE or {}).get("items") or []:
        name = str(item.get("name") or "").upper()
        if name == canonical.upper():
            tle1 = str(item.get("line1") or item.get("tle1") or "").strip()
            tle2 = str(item.get("line2") or item.get("tle2") or "").strip()
            if tle1 and tle2:
                return tle1, tle2, str(item.get("name") or canonical)

    if os.path.isfile(TLE_ACTIVE_PATH):
        for item in _parse_tle_file(TLE_ACTIVE_PATH):
            name = str(item.get("name") or "").upper()
            if name == canonical.upper():
                tle1 = str(item.get("line1") or "").strip()
                tle2 = str(item.get("line2") or "").strip()
                if tle1 and tle2:
                    return tle1, tle2, str(item.get("name") or canonical)

    return None, None, canonical


def _az_to_direction(az_deg: float) -> str:
    """Convert azimuth degrees to compass direction (8-point)."""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((az_deg + 22.5) / 45) % 8]


def compute_iss_passes_for_observer(lat_deg: float, lon_deg: float) -> List[dict]:
    """
    Calcule les 5 prochains passages ISS pour un observateur (lat/lon °, WGS84)
    via SGP4 + TLE local. Format enrichi (azimut, visibilité).
    """
    LAT_DEG, LON_DEG = float(lat_deg), float(lon_deg)
    Re = 6371.0

    def xyz_observer(lat, lon):
        return (
            Re * math.cos(lat) * math.cos(lon),
            Re * math.cos(lat) * math.sin(lon),
            Re * math.sin(lat),
        )

    def el_az(sat_xyz, obs_lat, obs_lon):
        rx, ry, rz = sat_xyz
        ox, oy, oz = xyz_observer(obs_lat, obs_lon)
        dx, dy, dz = rx - ox, ry - oy, rz - oz
        d = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
        if d == 0:
            return -90, 0
        nx = math.cos(obs_lat) * math.cos(obs_lon)
        ny = math.cos(obs_lat) * math.sin(obs_lon)
        nz = math.sin(obs_lat)
        ex = -math.sin(obs_lon)
        ey = math.cos(obs_lon)
        ez = 0.0
        north_x = -math.sin(obs_lat) * math.cos(obs_lon)
        north_y = -math.sin(obs_lat) * math.sin(obs_lon)
        north_z = math.cos(obs_lat)
        dot_up = (dx * nx + dy * ny + dz * nz) / d
        el = math.degrees(math.asin(max(-1.0, min(1.0, dot_up))))
        e_comp = (dx * ex + dy * ey + dz * ez) / d
        n_comp = (dx * north_x + dy * north_y + dz * north_z) / d
        az = (math.degrees(math.atan2(e_comp, n_comp)) + 360) % 360
        return el, az

    try:
        from modules.iss_passes import fetch_iss_tle
        name, tle1, tle2 = fetch_iss_tle()
    except Exception:
        tle1 = tle2 = None

    if not tle1 or not tle2:
        return []

    try:
        from sgp4.api import Satrec, jday
    except ImportError:
        return []

    sat = Satrec.twoline2rv(tle1, tle2)
    obs_lat = math.radians(LAT_DEG)
    obs_lon = math.radians(LON_DEG)

    now = _dt.datetime.now(_dt.timezone.utc)
    passes: List[dict] = []
    in_pass = False
    pass_data: dict = {}

    for i in range(int(48 * 3600 / 15)):
        t = now + _dt.timedelta(seconds=i * 15)
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
        err, r, v = sat.sgp4(jd, fr)
        if err != 0:
            continue
        el, az = el_az(r, obs_lat, obs_lon)
        if el >= 10.0:
            if not in_pass:
                in_pass = True
                pass_data = {
                    "start": t, "start_az": az,
                    "max_el": el, "max_t": t, "max_az": az,
                    "prev_t": t, "prev_el": el, "prev_az": az,
                }
            else:
                if el > pass_data["max_el"]:
                    pass_data["max_el"] = el
                    pass_data["max_t"] = t
                    pass_data["max_az"] = az
                pass_data["prev_t"] = t
                pass_data["prev_el"] = el
                pass_data["prev_az"] = az
        else:
            if in_pass:
                in_pass = False
                end_t = pass_data["prev_t"]
                dur_s = int((end_t - pass_data["start"]).total_seconds())
                max_el = round(pass_data["max_el"], 1)
                if max_el >= 45:
                    vis = "excellent"
                elif max_el >= 20:
                    vis = "good"
                else:
                    vis = "fair"
                passes.append({
                    "datetime": pass_data["start"].strftime("%Y-%m-%dT%H:%M:%S"),
                    "datetime_end": end_t.strftime("%Y-%m-%dT%H:%M:%S"),
                    "duration_min": round(dur_s / 60, 1),
                    "max_elevation_deg": max_el,
                    "direction_start": _az_to_direction(pass_data["start_az"]),
                    "direction_end": _az_to_direction(pass_data["prev_az"]),
                    "az_start": round(pass_data["start_az"], 0),
                    "az_end": round(pass_data["prev_az"], 0),
                    "visibility": vis,
                    "timestamp_unix": int(
                        pass_data["start"].replace(tzinfo=_dt.timezone.utc).timestamp()
                    ),
                })
                if len(passes) >= 5:
                    break

    return passes


def compute_iss_passes_tlemcen() -> List[dict]:
    """Tlemcen (34.87°N, 1.32°E) — rétrocompat."""
    return compute_iss_passes_for_observer(34.87, 1.32)


def compute_iss_ground_track() -> dict:
    """Trace au sol (lat, lon) sur ~90 min — SGP4 + position TEME (léger, pas de Skyfield)."""

    def _teme_km_to_latlon(rx, ry, rz):
        lon = math.degrees(math.atan2(ry, rx))
        hyp = math.sqrt(rx * rx + ry * ry)
        lat = math.degrees(math.atan2(rz, hyp))
        return lat, lon

    try:
        from modules.iss_passes import fetch_iss_tle
        from sgp4.api import Satrec, jday
    except Exception:
        return {"track": []}
    try:
        _name, l1, l2 = fetch_iss_tle()
        if not l1 or not l2:
            return {"track": []}
        sat = Satrec.twoline2rv(l1, l2)
        track = []
        now = _dt.datetime.now(_dt.timezone.utc)
        for sec in range(0, 5400, 90):
            t = now + _dt.timedelta(seconds=sec)
            jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
            err, r, _v = sat.sgp4(jd, fr)
            if err != 0:
                continue
            lat, lon = _teme_km_to_latlon(r[0], r[1], r[2])
            if math.isnan(lat) or math.isnan(lon):
                continue
            track.append([round(lat, 4), round(lon, 4)])
        return {"track": track}
    except Exception as e:
        log.warning("iss ground-track compute: %s", e)
        return {"track": []}
