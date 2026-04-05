# -*- coding: utf-8 -*-
"""
AstroScan — Cross-check moving object detections against TLE satellite catalog.

Uses the same TLE catalog as orbital_map (data/tle/active.tle), propagates with SGP4,
converts predicted RA/Dec to image coordinates when metadata has pointing data,
and matches detections to classify confirmed satellites.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

log = logging.getLogger(__name__)
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Default path to TLE catalog (same as orbital_map / station_web)
def _default_tle_path() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return root / "data" / "tle" / "active.tle"


def _parse_tle_file(path: Path) -> List[Dict[str, str]]:
    """Parse TLE file (3-line blocks: name, line1, line2). Returns list of {name, line1, line2}."""
    out: List[Dict[str, str]] = []
    if not path or not path.is_file():
        return out
    try:
        lines = [line.rstrip("\r\n") for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
        i = 0
        while i + 2 < len(lines):
            name = (lines[i] or "").strip()
            line1 = (lines[i + 1] or "").strip()
            line2 = (lines[i + 2] or "").strip()
            if line1.startswith("1 ") and line2.startswith("2 "):
                out.append({"name": name or "Unknown", "line1": line1, "line2": line2})
            i += 3
    except Exception:
        pass
    return out


def _eci_to_ra_dec(r_km: Tuple[float, float, float]) -> Tuple[float, float]:
    """Convert ECI position (TEME, km) to (ra_deg, dec_deg)."""
    x, y, z = r_km[0], r_km[1], r_km[2]
    dist = math.sqrt(x * x + y * y + z * z)
    if dist < 1e-6:
        return 0.0, 0.0
    ra_rad = math.atan2(y, x)
    dec_rad = math.asin(z / dist)
    ra_deg = math.degrees(ra_rad) % 360.0
    dec_deg = math.degrees(dec_rad)
    return ra_deg, dec_deg


def _get_pointing_from_metadata(metadata: Dict[str, Any]) -> Optional[Tuple[float, float, float, int, int]]:
    """
    Get (ra_center, dec_center, scale_deg, width, height) with preference for astrometry_solution.
    Returns None if insufficient data. Does not crash on incomplete astrometry_solution.
    """
    if not metadata:
        return None
    astro = metadata.get("astrometry_solution")
    if isinstance(astro, dict) and astro.get("solved"):
        ra_c = astro.get("ra_center")
        dec_c = astro.get("dec_center")
        scale_arcsec = astro.get("pixel_scale_arcsec_per_px")
        scale_deg = float(scale_arcsec) / 3600.0 if scale_arcsec is not None else None
        if scale_deg is None or scale_deg <= 0:
            scale_deg = metadata.get("scale_deg")
            if scale_deg is None and metadata.get("scale_arcsec") is not None:
                try:
                    scale_deg = float(metadata["scale_arcsec"]) / 3600.0
                except (TypeError, ValueError):
                    scale_deg = None
        w = metadata.get("image_width") or metadata.get("width")
        h = metadata.get("image_height") or metadata.get("height")
        if ra_c is None:
            ra_c = metadata.get("ra_center") or metadata.get("ra")
        if dec_c is None:
            dec_c = metadata.get("dec_center") or metadata.get("dec")
    else:
        ra_c = metadata.get("ra_center") or metadata.get("ra")
        dec_c = metadata.get("dec_center") or metadata.get("dec")
        scale_deg = metadata.get("scale_deg")
        if scale_deg is None and metadata.get("scale_arcsec") is not None:
            try:
                scale_deg = float(metadata["scale_arcsec"]) / 3600.0
            except (TypeError, ValueError):
                scale_deg = None
        w = metadata.get("image_width") or metadata.get("width")
        h = metadata.get("image_height") or metadata.get("height")
    if ra_c is None or dec_c is None:
        return None
    if scale_deg is None or scale_deg <= 0:
        return None
    if w is None or h is None:
        return None
    try:
        return (float(ra_c), float(dec_c), float(scale_deg), int(w), int(h))
    except (TypeError, ValueError):
        return None


def _ra_dec_to_pixel(
    ra_deg: float,
    dec_deg: float,
    metadata: Dict[str, Any],
) -> Optional[Tuple[float, float]]:
    """
    Convert (ra_deg, dec_deg) to image (x, y) pixels using metadata pointing.
    Prefers metadata["astrometry_solution"] when solved; falls back to ra_center, dec_center, scale_deg, image_width/height.
    """
    pointing = _get_pointing_from_metadata(metadata)
    if pointing is None:
        return None
    ra_c, dec_c, scale, width, height = pointing
    cos_dec = math.cos(math.radians(dec_c))
    dx_deg = (ra_deg - ra_c) * cos_dec
    dy_deg = dec_deg - dec_c
    x_px = width / 2.0 + dx_deg / scale
    y_px = height / 2.0 - dy_deg / scale  # y down
    return (x_px, y_px)


def _observation_time_from_metadata(metadata: Dict[str, Any]) -> datetime:
    """Parse observation date from metadata; default to now UTC."""
    obs = metadata.get("observation_date") or metadata.get("date") or metadata.get("observation_date_utc")
    if not obs:
        return datetime.now(tz=timezone.utc)
    if isinstance(obs, str):
        try:
            from dateutil import parser as date_parser
            dt = date_parser.parse(obs)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(obs[:19], fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                continue
    return datetime.now(tz=timezone.utc)


def crosscheck_detections_with_tle(
    detections: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    tle_path: Optional[Path] = None,
    threshold_px: float = 25.0,
    max_satellites: int = 500,
) -> Dict[str, Any]:
    """
    Cross-check moving object detections against TLE catalog.

    - Loads TLE from tle_path (default: data/tle/active.tle).
    - Propagates each satellite with SGP4 at observation time from metadata.
    - Converts predicted RA/Dec to image pixels if metadata has pointing (ra_center, dec_center, scale, image size).
    - If a detection is within threshold_px of a predicted position, record as confirmed satellite.

    Match threshold is resolution-independent: threshold_px = max(10.0, image_width * 0.02).
    The threshold is proportional to the image width (2% of width),
    with a minimum of 10 pixels to avoid overly strict matching on small images.
    Example thresholds:
      512 px  → 10.24 px
      1024 px → 20.48 px
      4096 px → 81.92 px

    Returns:
        {
            "checked": True/False,
            "matches": [ {"object_name": "...", "catalog_id": "...", "distance_px": ...}, ... ],
            "reason": "..." (if not checked)
        }
    """
    metadata = metadata or {}
    out: Dict[str, Any] = {"checked": False, "matches": [], "reason": "satellite catalog cross-check not yet configured"}

    path = tle_path or _default_tle_path()
    satellites = _parse_tle_file(path)
    if not satellites:
        out["reason"] = "no TLE catalog available"
        return out

    if not detections:
        out["checked"] = True
        out["reason"] = "no detections to cross-check"
        return out

    # Need pointing to convert RA/Dec to pixels
    ra_center = metadata.get("ra_center") or metadata.get("ra")
    dec_center = metadata.get("dec_center") or metadata.get("dec")
    if ra_center is None or dec_center is None:
        out["reason"] = "metadata missing pointing (ra_center, dec_center)"
        return out

    # Resolution-independent match threshold: 2% of image width, min 10 px.
    # Example: 512 px → 10.24 px; 1024 px → 20.48 px; 4096 px → 81.92 px.
    image_width = metadata.get("image_width") or metadata.get("width")
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
        log.warning("catalog_crosscheck: image_width unknown; using fixed threshold 25 px")

    try:
        from sgp4.api import Satrec, jday
    except ImportError:
        out["reason"] = "sgp4 not installed"
        return out

    obs_dt = _observation_time_from_metadata(metadata)
    jd, fr = jday(
        obs_dt.year,
        obs_dt.month,
        obs_dt.day,
        obs_dt.hour,
        obs_dt.minute,
        obs_dt.second + obs_dt.microsecond / 1e6,
    )

    predicted_pixels: List[Tuple[float, float, str, str]] = []  # (x, y, name, line1_id)
    for sat in satellites[:max_satellites]:
        try:
            rec = Satrec.twoline2rv(sat["line1"], sat["line2"])
            e, r, v = rec.sgp4(jd, fr)
            if e != 0:
                continue
            ra_deg, dec_deg = _eci_to_ra_dec((r[0], r[1], r[2]))
            xy = _ra_dec_to_pixel(ra_deg, dec_deg, metadata)
            if xy is None:
                continue
            name = sat.get("name", "Unknown")
            catalog_id = sat.get("line1", "")[:12].strip() or name
            predicted_pixels.append((xy[0], xy[1], name, catalog_id))
        except Exception:
            continue

    if not predicted_pixels:
        out["checked"] = True
        out["reason"] = "no satellites in field (pointing or TLE)"
        return out

    matches: List[Dict[str, Any]] = []
    used_det: set = set()
    for (px, py, obj_name, cat_id) in predicted_pixels:
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
                "catalog_id": cat_id,
                "distance_px": round(best_dist, 2),
                "x": det.get("x"),
                "y": det.get("y"),
            })

    out["checked"] = True
    out["matches"] = matches
    out["reason"] = "cross-check complete"
    return out
