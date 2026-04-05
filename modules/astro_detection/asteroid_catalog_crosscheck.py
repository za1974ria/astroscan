# -*- coding: utf-8 -*-
"""
AstroScan — Cross-check moving object detections with known asteroid catalogs.

Loads asteroid orbital elements from a local MPC-style catalog, propagates to
observation time, converts predicted RA/Dec to image pixels (same method as
catalog_crosscheck), and matches detections to classify known_asteroid.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# GM_sun in AU^3/day^2 (approximate)
_GM_SUN_AU3_DAY2 = 2.959122082855909e-04

# Limit catalog size to avoid slowdown with full MPC (hundreds of thousands of objects)
MAX_ASTEROIDS = 2000

# Module-level cache: (path, list) to avoid re-reading MPC file on every pipeline run
_ASTEROID_CACHE: Optional[Tuple[Path, List[Dict[str, Any]]]] = None


def _default_mpc_path() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return root / "data" / "mpc" / "asteroids.dat"


def _parse_mpc_file(path: Path, max_entries: int = MAX_ASTEROIDS) -> List[Dict[str, Any]]:
    """
    Parse a simple MPC-style catalog: one record per line.
    Format: name epoch_jd a_au e i_deg Omega_deg omega_deg M_deg
    (space-separated). Lines starting with # are skipped.
    Stops after max_entries valid records to scale with large catalogs.
    """
    out: List[Dict[str, Any]] = []
    if not path or not path.is_file():
        return out
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if len(out) >= max_entries:
                break
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                out.append({
                    "name": parts[0],
                    "mpc_id": parts[0],
                    "epoch_jd": float(parts[1]),
                    "a_au": float(parts[2]),
                    "e": float(parts[3]),
                    "i_deg": float(parts[4]),
                    "Omega_deg": float(parts[5]),
                    "omega_deg": float(parts[6]),
                    "M_deg": float(parts[7]),
                })
            except (ValueError, IndexError):
                continue
    except Exception:
        pass
    return out


def _kepler_solve(M_rad: float, e: float, max_iter: int = 20) -> float:
    """Solve E - e*sin(E) = M for E (eccentric anomaly) in radians."""
    E = M_rad if abs(e) < 0.8 else math.pi
    for _ in range(max_iter):
        d = E - e * math.sin(E) - M_rad
        if abs(d) < 1e-10:
            return E
        E = E - d / (1.0 - e * math.cos(E))
    return E


def _heliocentric_ecliptic_to_ra_dec(
    x_ecl_au: float,
    y_ecl_au: float,
    z_ecl_au: float,
    jd: float,
) -> Tuple[float, float]:
    """Convert heliocentric ecliptic (AU) to geocentric RA/Dec (deg) at JD."""
    try:
        from astropy.time import Time
        from astropy.coordinates import get_body_barycentric, solar_system_ephemeris
    except ImportError:
        return 0.0, 0.0

    obliquity_rad = math.radians(23.43928)
    co, so = math.cos(obliquity_rad), math.sin(obliquity_rad)
    x_eq = x_ecl_au
    y_eq = y_ecl_au * co - z_ecl_au * so
    z_eq = y_ecl_au * so + z_ecl_au * co

    try:
        with solar_system_ephemeris.set("builtin"):
            earth = get_body_barycentric("earth", Time(jd, format="jd"))
    except Exception:
        return 0.0, 0.0

    x_geo = x_eq - earth.x.to_value("AU")
    y_geo = y_eq - earth.y.to_value("AU")
    z_geo = z_eq - earth.z.to_value("AU")

    r = math.sqrt(x_geo * x_geo + y_geo * y_geo + z_geo * z_geo)
    if r < 1e-12:
        return 0.0, 0.0
    ra_rad = math.atan2(y_geo, x_geo)
    dec_rad = math.asin(z_geo / r)
    ra_deg = math.degrees(ra_rad) % 360.0
    dec_deg = math.degrees(dec_rad)
    return ra_deg, dec_deg


def _orbit_position_at_jd(elt: Dict[str, Any], target_jd: float) -> Optional[Tuple[float, float]]:
    """Compute RA/Dec (deg) of asteroid at target_jd from orbital elements."""
    a = elt["a_au"]
    e = elt["e"]
    if a <= 0 or e < 0 or e >= 1:
        return None
    n_rad_per_day = math.sqrt(_GM_SUN_AU3_DAY2 / (a * a * a))
    epoch_jd = elt["epoch_jd"]
    M_epoch_rad = math.radians(elt["M_deg"])
    M_rad = M_epoch_rad + n_rad_per_day * (target_jd - epoch_jd)
    M_rad = M_rad % (2.0 * math.pi)

    E = _kepler_solve(M_rad, e)
    nu = 2.0 * math.atan2(
        math.sqrt(1.0 + e) * math.sin(E / 2.0),
        math.sqrt(1.0 - e) * math.cos(E / 2.0),
    )
    r_au = a * (1.0 - e * e) / (1.0 + e * math.cos(nu))
    x_orb = r_au * math.cos(nu)
    y_orb = r_au * math.sin(nu)

    i_rad = math.radians(elt["i_deg"])
    O_rad = math.radians(elt["Omega_deg"])
    o_rad = math.radians(elt["omega_deg"])
    ci, si = math.cos(i_rad), math.sin(i_rad)
    cO, sO = math.cos(O_rad), math.sin(O_rad)
    co, so = math.cos(o_rad), math.sin(o_rad)

    x_ecl = (cO * co - sO * so * ci) * x_orb + (-cO * so - sO * co * ci) * y_orb
    y_ecl = (sO * co + cO * so * ci) * x_orb + (-sO * so + cO * co * ci) * y_orb
    z_ecl = (so * si) * x_orb + (co * si) * y_orb

    return _heliocentric_ecliptic_to_ra_dec(x_ecl, y_ecl, z_ecl, target_jd)


def crosscheck_detections_with_mpc(
    detections: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    mpc_path: Optional[Path] = None,
    threshold_px: float = 25.0,
    max_asteroids: int = 300,
) -> Dict[str, Any]:
    """
    Cross-check moving object detections with asteroid catalog.

    - Loads orbital elements from mpc_path (default: data/mpc/asteroids.dat).
    - Propagates each asteroid to observation time from metadata.
    - Converts predicted RA/Dec to pixels using same projection as catalog_crosscheck.
    - If a detection is within threshold_px of a predicted position, record as known_asteroid.

    Returns:
        { "checked": bool, "matches": [ {"object_name": "...", "mpc_id": "...", "distance_px": ...}, ... ] }
    """
    metadata = metadata or {}
    out: Dict[str, Any] = {"checked": False, "matches": [], "reason": "asteroid catalog cross-check not configured"}

    path = mpc_path or _default_mpc_path()
    global _ASTEROID_CACHE
    if _ASTEROID_CACHE is not None and _ASTEROID_CACHE[0] == path:
        asteroids = _ASTEROID_CACHE[1]
    else:
        asteroids = _parse_mpc_file(path, max_entries=MAX_ASTEROIDS)
        _ASTEROID_CACHE = (path, asteroids)
    if not asteroids:
        out["checked"] = True
        out["reason"] = "no MPC catalog available"
        return out

    if not detections:
        out["checked"] = True
        out["reason"] = "no detections to cross-check"
        return out

    # Prefer astrometry_solution when solved; fallback to legacy pointing
    from modules.astro_detection.catalog_crosscheck import (
        _get_pointing_from_metadata,
        _ra_dec_to_pixel,
        _observation_time_from_metadata,
    )
    pointing = _get_pointing_from_metadata(metadata)
    if pointing is not None:
        ra_center, dec_center = pointing[0], pointing[1]
        image_width_from_pointing = pointing[3]
    else:
        ra_center = metadata.get("ra_center") or metadata.get("ra")
        dec_center = metadata.get("dec_center") or metadata.get("dec")
        image_width_from_pointing = None
    if ra_center is None or dec_center is None:
        out["reason"] = "metadata missing pointing (ra_center, dec_center)"
        return out

    obs_dt = _observation_time_from_metadata(metadata)
    try:
        from astropy.time import Time
        target_jd = Time(obs_dt).jd
    except Exception:
        y, m, d = obs_dt.year, obs_dt.month, obs_dt.day
        target_jd = 367 * y - 7 * (y + (m + 9) // 12) // 4 + 275 * m // 9 + d + 1721013.5

    # Resolution-independent threshold (use pointing width if from astrometry)
    image_width = image_width_from_pointing if image_width_from_pointing is not None else (metadata.get("image_width") or metadata.get("width"))
    if image_width is not None:
        try:
            image_width = int(image_width)
        except (TypeError, ValueError):
            image_width = None
    if not image_width and detections:
        image_width = max((d.get("x", 0) for d in detections), default=0) + 1
    if image_width and image_width > 0:
        threshold_px = max(10.0, image_width * 0.02)
    else:
        threshold_px = 25.0
        log.warning("asteroid_catalog_crosscheck: image_width unknown; using fixed threshold 25 px")

    # Coarse sky filter: only propagate asteroids whose approximate (epoch) position is in field
    field_radius_deg = 5.0
    try:
        ra_c = float(ra_center)
        dec_c = float(dec_center)
    except (TypeError, ValueError):
        ra_c, dec_c = 0.0, 0.0

    def _in_field(ra_deg: float, dec_deg: float) -> bool:
        diff_ra = abs((ra_deg - ra_c + 180.0) % 360.0 - 180.0)
        return diff_ra <= field_radius_deg and abs(dec_deg - dec_c) <= field_radius_deg

    predicted_pixels: List[Tuple[float, float, str, str]] = []
    tested_count = 0
    for elt in asteroids[:max_asteroids]:
        # Pre-filter by approximate position at epoch
        try:
            approx = _orbit_position_at_jd(elt, elt["epoch_jd"])
            if approx is None:
                continue
            ra_a, dec_a = approx
            if not _in_field(ra_a, dec_a):
                continue
        except Exception:
            continue
        # Full propagation at observation time and pixel conversion
        try:
            ra_dec = _orbit_position_at_jd(elt, target_jd)
            if ra_dec is None:
                continue
            ra_deg, dec_deg = ra_dec
            xy = _ra_dec_to_pixel(ra_deg, dec_deg, metadata)
            if xy is None:
                continue
            name = elt.get("name", "Unknown")
            mpc_id = elt.get("mpc_id", name)
            predicted_pixels.append((xy[0], xy[1], name, mpc_id))
            tested_count += 1
        except Exception:
            continue

    if not predicted_pixels:
        log.debug(
            "asteroid_crosscheck: tested %d asteroids, found 0 matches (none in field)",
            tested_count,
        )
        out["checked"] = True
        out["reason"] = "no asteroids in field (pointing or catalog)"
        return out

    matches: List[Dict[str, Any]] = []
    used_det: set = set()
    for (px, py, obj_name, mpc_id) in predicted_pixels:
        best_dist = threshold_px + 1.0
        best_idx = -1
        for idx, det in enumerate(detections):
            if idx in used_det:
                continue
            dx = det.get("x", 0) - px
            dy = det.get("y", 0) - py
            d = math.sqrt(dx * dx + dy * dy)
            if d < best_dist:
                best_dist = d
                best_idx = idx
        if best_idx >= 0 and best_dist <= threshold_px:
            used_det.add(best_idx)
            det = detections[best_idx]
            matches.append({
                "object_name": obj_name,
                "mpc_id": mpc_id,
                "distance_px": round(best_dist, 2),
                "x": det.get("x"),
                "y": det.get("y"),
            })

    log.debug(
        "asteroid_crosscheck: tested %d asteroids, found %d matches",
        tested_count,
        len(matches),
    )
    out["checked"] = True
    out["matches"] = matches
    out["reason"] = "asteroid cross-check complete"
    return out
