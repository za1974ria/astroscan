"""Blueprint Satellites — TLE catalog + per-satellite SGP4 propagation + passes.

PASS 14 (2026-05-03) — Création :
  /api/satellite/<name> (SGP4 sur SATELLITES dict),
  /api/satellites/tle (Celestrak TLE catalog),
  /api/satellites/tle/debug (TLE file diagnostics),
  /api/satellite/passes (predictions par observateur lat/lon).

Pattern : lazy-import des helpers/globals monolithe via `from station_web import`.
Constantes TLE_ACTIVE_PATH, TLE_MAX_SATELLITES, SATELLITES restent en monolithe.
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify

log = logging.getLogger(__name__)

bp = Blueprint("satellites", __name__)


# ── /api/satellite/<name> — propagation SGP4 d'un satellite connu ─────
@bp.route("/api/satellite/<name>")
def api_satellite(name):
    from app.services.satellites import SATELLITES, list_satellites
    from station_web import (
        _get_satellite_tle_by_name,
        propagate_tle_debug,
    )
    satellite_name = str(name or "").upper()
    if satellite_name not in SATELLITES:
        return jsonify({
            "ok": False,
            "error": "unknown_satellite",
            "available": list_satellites(),
        }), 404

    tle1, tle2, resolved_name = _get_satellite_tle_by_name(satellite_name)
    if not (tle1 and tle2):
        return jsonify({
            "ok": False,
            "name": satellite_name,
            "norad_id": SATELLITES[satellite_name],
            "meta": {"status": "no_tle", "source": "tle"},
        })

    sgp4_data, reason = propagate_tle_debug(tle1, tle2)
    if sgp4_data:
        return jsonify({
            "ok": True,
            "name": resolved_name,
            "norad_id": SATELLITES[satellite_name],
            "sgp4": sgp4_data,
            "meta": {"status": "live", "source": "SGP4"},
        })

    return jsonify({
        "ok": False,
        "name": resolved_name,
        "norad_id": SATELLITES[satellite_name],
        "meta": {"status": "fallback", "source": "SGP4", "reason": reason},
    })


# ── /api/satellites/tle — Celestrak active TLE ─────────────────────────
@bp.route("/api/satellites/tle")
def api_satellites_tle():
    """Serves real Celestrak active TLE from data/tle/active.tle."""
    from app.services.tle import TLE_ACTIVE_PATH, _parse_tle_file, _TLE_FOR_PASSES
    from station_web import TLE_MAX_SATELLITES
    try:
        satellites = _parse_tle_file(TLE_ACTIVE_PATH, limit=TLE_MAX_SATELLITES)
        if not satellites:
            log.info("api/satellites/tle: cache empty or missing, using fallback TLE")
            satellites = [
                {"name": s["name"], "line1": s["tle1"], "line2": s["tle2"]}
                for s in _TLE_FOR_PASSES
            ]
        out = [
            {
                "name": s.get("name", "Unknown"),
                "tle1": s.get("line1", ""),
                "tle2": s.get("line2", ""),
            }
            for s in satellites[:TLE_MAX_SATELLITES]
        ]
        log.info("TLE satellites served: %s", len(out))
        if os.path.isfile(TLE_ACTIVE_PATH):
            log.info("TLE FILE SIZE: %s", os.path.getsize(TLE_ACTIVE_PATH))
        return jsonify({
            "source": "celestrak",
            "group": "active",
            "format": "tle",
            "satellites": out,
        })
    except Exception as e:
        log.warning("api/satellites/tle: %s", e)
        return jsonify({
            "source": "celestrak",
            "group": "active",
            "format": "tle",
            "satellites": [],
        })


@bp.route("/api/satellites/tle/debug")
def debug_tle():
    from app.services.tle import TLE_ACTIVE_PATH, _parse_tle_file
    exists = os.path.exists(TLE_ACTIVE_PATH)
    size = os.path.getsize(TLE_ACTIVE_PATH) if exists else 0
    sats = _parse_tle_file(TLE_ACTIVE_PATH, limit=10) if exists else []
    return jsonify({
        "file_exists": exists,
        "file_size": size,
        "satellite_count": len(sats),
        "sample": sats[:2],
    })


# ── /api/satellite/passes — prédictions multi-satellites ─────────────
def _elevation_above_observer(lat, lon, jd, fr, obs_teme, obs_norm, sat_teme):
    """Élévation (degrés) du satellite vu depuis l'observateur (TEME, km)."""
    dx = sat_teme[0] - obs_teme[0]
    dy = sat_teme[1] - obs_teme[1]
    dz = sat_teme[2] - obs_teme[2]
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist < 1e-6:
        return -90.0
    ux, uy, uz = dx / dist, dy / dist, dz / dist
    dot = (
        ux * (obs_teme[0] / obs_norm)
        + uy * (obs_teme[1] / obs_norm)
        + uz * (obs_teme[2] / obs_norm)
    )
    return math.degrees(math.asin(max(-1, min(1, dot))))


@bp.route("/api/satellite/passes")
def api_satellite_passes():
    """Prédiction des prochains passages (élévation > 10°) pour un observateur lat/lon."""
    from app.services.tle import _TLE_FOR_PASSES

    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon required", "passes": []}), 400
    passes_out = []
    try:
        from sgp4.api import Satrec, jday
        rad = math.radians
        a, b = 6378.137, 6356.752
        coslat = math.cos(rad(lat))
        sinlat = math.sin(rad(lat))
        n = a * a / math.sqrt(a * a * coslat * coslat + b * b * sinlat * sinlat)
        x_ecef = (n + 0) * coslat * math.cos(rad(lon))
        y_ecef = (n + 0) * coslat * math.sin(rad(lon))
        z_ecef = (n * (b * b) / (a * a) + 0) * sinlat
        obs_ecef = (x_ecef, y_ecef, z_ecef)
        obs_norm = math.sqrt(x_ecef * x_ecef + y_ecef * y_ecef + z_ecef * z_ecef)

        def obs_teme_at(jd, fr):
            t = (jd - 2451545.0) + fr
            gmst_deg = (280.46061837 + 360.98564736629 * t) % 360
            gmst = math.radians(gmst_deg)
            c, s = math.cos(gmst), math.sin(gmst)
            return (
                c * obs_ecef[0] - s * obs_ecef[1],
                s * obs_ecef[0] + c * obs_ecef[1],
                obs_ecef[2],
            )

        now = datetime.utcnow()
        for sat in _TLE_FOR_PASSES:
            rec = Satrec.twoline2rv(sat["tle1"], sat["tle2"])
            next_pass_dt = None
            max_elev = 0.0
            for minute in range(0, 24 * 60, 2):
                t = now + timedelta(minutes=minute)
                jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
                obs_teme = obs_teme_at(jd, fr)
                e, r, v = rec.sgp4(jd, fr)
                if e != 0:
                    continue
                elev = _elevation_above_observer(
                    lat, lon, jd, fr, obs_teme, obs_norm, (r[0], r[1], r[2]),
                )
                if elev > 10:
                    if next_pass_dt is None:
                        next_pass_dt = t
                    max_elev = max(max_elev, elev)
                elif next_pass_dt is not None:
                    break
            if next_pass_dt is not None:
                passes_out.append({
                    "name": sat["name"],
                    "elevation": round(max_elev, 1),
                    "next_pass": next_pass_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
    except ImportError:
        log.warning("api/satellite/passes: sgp4 not installed, returning empty passes")
        return jsonify({
            "passes": [],
            "message": "Install sgp4 for pass prediction",
        })
    except Exception as e:
        log.warning("api/satellite/passes: %s", e)
        return jsonify({"passes": [], "error": str(e)})
    return jsonify({"passes": passes_out})
