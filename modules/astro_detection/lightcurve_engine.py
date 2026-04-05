# -*- coding: utf-8 -*-
"""
AstroScan — Light Curve Engine.

Tracks brightness changes of detected objects across multiple images
to identify variable candidates and brightness events. Uses photometric
quality weighting and simple temporal trend detection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Magnitude variation threshold above which object is classified as variable candidate
VARIATION_THRESHOLD_MAG = 0.3

# Flux thresholds for quality (normalized image units): above high -> high, above medium -> medium
FLUX_QUALITY_HIGH = 0.05
FLUX_QUALITY_MEDIUM = 0.01

# Trend slope threshold (mag per hour): |slope| > this => brightening or fading
TREND_SLOPE_THRESHOLD = 0.01


def _time_to_hours(ts: Any) -> Optional[float]:
    """Parse timestamp to hours since epoch; return None if unparseable."""
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return float(ts) / 3600.0
        s = str(ts).strip()
        if not s:
            return None
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp() / 3600.0
    except Exception:
        return None


def _flux_to_quality(flux: Optional[float], mag: Optional[float]) -> str:
    """Assign quality from flux and magnitude. If magnitude missing -> low."""
    if mag is None:
        return "low"
    if flux is None or flux <= 0:
        return "low"
    if flux >= FLUX_QUALITY_HIGH:
        return "high"
    if flux >= FLUX_QUALITY_MEDIUM:
        return "medium"
    return "low"


def build_light_curve(
    object_id: str,
    detections: List[Dict[str, Any]],
    image_paths: List[Any],
    variation_threshold: float = VARIATION_THRESHOLD_MAG,
) -> Dict[str, Any]:
    """
    Build a light curve for an object from detections across multiple images.

    For each detection, extracts magnitude via photometric_estimator and stores
    (timestamp, magnitude). Computes mag_min, mag_max, variation and optional
    classification (variable_candidate when variation > threshold).

    detections: list of { "x", "y", "timestamp" } (one per frame).
    image_paths: list of image paths, same order as detections (detection i uses image_paths[i]).

    Returns:
        {
            "object_id": str,
            "points": [ { "time": str, "mag": float | None, "quality": "low"|"medium"|"high" }, ... ],
            "mag_min": float | None,
            "mag_max": float | None,
            "variation": float | None,
            "trend": "brightening" | "fading" | "flat" | "unknown",
            "classification": "variable_candidate" | "stable" | "unknown",
            "point_count": int
        }
    """
    empty: Dict[str, Any] = {
        "object_id": object_id or "",
        "points": [],
        "mag_min": None,
        "mag_max": None,
        "variation": None,
        "trend": "unknown",
        "classification": "unknown",
        "point_count": 0,
    }
    object_id = object_id or ""
    if not detections or not isinstance(detections, list):
        return empty
    try:
        from modules.astro_detection.photometric_estimator import estimate_magnitude
    except ImportError:
        log.debug("lightcurve_engine: photometric_estimator not available")
        return empty

    paths = list(image_paths) if image_paths else []
    points: List[Dict[str, Any]] = []
    mags_valid: List[float] = []

    for i, det in enumerate(detections):
        if not isinstance(det, dict):
            continue
        ts = det.get("timestamp")
        x = det.get("x")
        y = det.get("y")
        if x is None or y is None:
            continue
        path = paths[i] if i < len(paths) else (paths[-1] if paths else None)
        if path is None:
            points.append({"time": str(ts) if ts is not None else "", "mag": None, "quality": "low"})
            continue
        try:
            result = estimate_magnitude(path, float(x), float(y))
        except Exception:
            points.append({"time": str(ts) if ts is not None else "", "mag": None, "quality": "low"})
            continue
        if not isinstance(result, dict):
            points.append({"time": str(ts) if ts is not None else "", "mag": None, "quality": "low"})
            continue
        mag = result.get("magnitude_estimate")
        flux = result.get("flux")
        quality = _flux_to_quality(flux, mag)
        time_str = str(ts) if ts is not None else ""
        points.append({"time": time_str, "mag": mag, "quality": quality})
        if mag is not None:
            try:
                mags_valid.append(float(mag))
            except (TypeError, ValueError):
                pass

    # Weighted variation: use only points with quality != "low"; fallback to all valid
    mags_for_variation = [p["mag"] for p in points if p.get("mag") is not None and p.get("quality") != "low"]
    if not mags_for_variation:
        mags_for_variation = mags_valid
    mag_min = min(mags_for_variation) if mags_for_variation else None
    mag_max = max(mags_for_variation) if mags_for_variation else None
    variation = None
    if mag_min is not None and mag_max is not None:
        variation = float(mag_max - mag_min)

    if variation is not None and variation > variation_threshold:
        classification = "variable_candidate"
    elif mags_valid:
        classification = "stable"
    else:
        classification = "unknown"

    # Trend: first_mag, last_mag, duration; slope = (last_mag - first_mag) / duration_hours
    trend = "unknown"
    if len(mags_valid) >= 2:
        valid_points_with_time = [(p.get("time"), p.get("mag")) for p in points if p.get("mag") is not None]
        if len(valid_points_with_time) >= 2:
            first_time_str = valid_points_with_time[0][0]
            last_time_str = valid_points_with_time[-1][0]
            first_mag = valid_points_with_time[0][1]
            last_mag = valid_points_with_time[-1][1]
            t_first = _time_to_hours(first_time_str)
            t_last = _time_to_hours(last_time_str)
            if t_first is not None and t_last is not None and first_mag is not None and last_mag is not None:
                duration_hours = float(t_last - t_first)
                if duration_hours > 0:
                    slope = (float(last_mag) - float(first_mag)) / duration_hours
                    if slope < -TREND_SLOPE_THRESHOLD:
                        trend = "brightening"
                    elif slope > TREND_SLOPE_THRESHOLD:
                        trend = "fading"
                    else:
                        trend = "flat"

    return {
        "object_id": object_id,
        "points": points,
        "mag_min": mag_min,
        "mag_max": mag_max,
        "variation": variation,
        "trend": trend,
        "classification": classification,
        "point_count": len(points),
    }
