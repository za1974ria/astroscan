# -*- coding: utf-8 -*-
"""
AstroScan — Object Identity Engine.

Combines motion tracking, catalog cross-checks, light curves and sky change
detection to determine the most probable identity of detected objects.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_FALLBACK_TOLERANCE_PX = 10.0


def _tolerance_px(image_width: Optional[float]) -> float:
    """Resolution-aware matching tolerance: max(5, image_width * 0.01), fallback 10 px."""
    if image_width is not None and image_width > 0:
        return max(5.0, image_width * 0.01)
    return _FALLBACK_TOLERANCE_PX


def _track_matches_matches(
    track: Optional[Dict[str, Any]],
    matches: List[Dict[str, Any]],
    tolerance_px: float,
) -> bool:
    """True if track has any point near any match (x, y) within tolerance_px."""
    if not track or not matches:
        return False
    points = track.get("points") or []
    for pt in points:
        try:
            tx = float(pt.get("x", 0) or 0)
            ty = float(pt.get("y", 0) or 0)
        except (TypeError, ValueError):
            continue
        for m in matches:
            try:
                mx = float(m.get("x", 0) or 0)
                my = float(m.get("y", 0) or 0)
                if abs(tx - mx) <= tolerance_px and abs(ty - my) <= tolerance_px:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _confidence_label(score: float) -> str:
    """Map confidence_score in [0, 1] to low / medium / high."""
    if score > 0.8:
        return "high"
    if score > 0.5:
        return "medium"
    return "low"


def determine_identity(
    track: Optional[Dict[str, Any]],
    validation: Optional[Dict[str, Any]],
    lightcurve: Optional[Dict[str, Any]] = None,
    sky_change: Optional[Dict[str, Any]] = None,
    image_width: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Determine the most probable identity of a detected object from track,
    validation, optional light curve and sky change.

    Returns:
        { "identity", "confidence", "confidence_score": 0..1, "reason" }
    """
    tolerance_px = _tolerance_px(image_width)
    out: Dict[str, Any] = {
        "identity": "unknown_object",
        "confidence": "low",
        "confidence_score": 0.2,
        "reason": "Insufficient data.",
    }
    validation = validation or {}

    sat_check = validation.get("satellite_crosscheck") or {}
    ast_check = validation.get("asteroid_crosscheck") or {}
    sat_matches = sat_check.get("matches") if isinstance(sat_check, dict) else []
    ast_matches = ast_check.get("matches") if isinstance(ast_check, dict) else []
    if not isinstance(sat_matches, list):
        sat_matches = []
    if not isinstance(ast_matches, list):
        ast_matches = []

    if _track_matches_matches(track, sat_matches, tolerance_px):
        out["identity"] = "known_satellite"
        out["confidence_score"] = 0.95
        out["confidence"] = _confidence_label(out["confidence_score"])
        out["reason"] = "Matched by satellite catalog cross-check."
        return out

    if _track_matches_matches(track, ast_matches, tolerance_px):
        out["identity"] = "known_asteroid"
        out["confidence_score"] = 0.95
        out["confidence"] = _confidence_label(out["confidence_score"])
        out["reason"] = "Matched by asteroid catalog cross-check."
        return out

    if track and isinstance(track, dict):
        points = track.get("points") or []
        if len(points) >= 3:
            # Motion sanity check: unrealistically high velocity → artifact
            try:
                v = track.get("velocity_px_per_frame")
                w = image_width if image_width and image_width > 0 else None
                if v is not None and w is not None:
                    vf = float(v)
                    if vf > w * 0.2:
                        out["identity"] = "artifact"
                        out["confidence_score"] = 0.9
                        out["confidence"] = _confidence_label(out["confidence_score"])
                        out["reason"] = "Velocity exceeds sanity threshold (motion artifact)."
                        return out
            except (TypeError, ValueError):
                pass
            out["identity"] = "candidate_asteroid"
            out["confidence_score"] = 0.65
            out["confidence"] = _confidence_label(out["confidence_score"])
            out["reason"] = "Multi-point motion track; not matched to catalog."

    if sky_change and isinstance(sky_change, dict):
        cl = (sky_change.get("classification") or "").strip().lower()
        if "supernova" in cl:
            out["identity"] = "transient_candidate"
            out["confidence_score"] = 0.6
            out["confidence"] = _confidence_label(out["confidence_score"])
            out["reason"] = "Sky change classification indicates possible supernova."
            return out

    if lightcurve and isinstance(lightcurve, dict):
        lc_class = (lightcurve.get("classification") or "").strip()
        if lc_class == "variable_candidate":
            out["identity"] = "variable_star"
            out["confidence_score"] = 0.6
            out["confidence"] = _confidence_label(out["confidence_score"])
            out["reason"] = "Light curve shows significant variation."
            return out

    if track and isinstance(track, dict) and track.get("classification_hint") == "likely_artifact":
        out["identity"] = "artifact"
        out["confidence_score"] = 0.9
        out["confidence"] = _confidence_label(out["confidence_score"])
        out["reason"] = "Track classified as likely artifact."
        return out

    if track and isinstance(track, dict) and (track.get("points") or []):
        n = len(track.get("points") or [])
        if n >= 3:
            return out  # already set to candidate_asteroid
    out["identity"] = "unknown_object"
    out["confidence_score"] = 0.2
    out["confidence"] = _confidence_label(out["confidence_score"])
    out["reason"] = "Insufficient or ambiguous data."
    return out


def run_object_identity_engine(pipeline_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run identity classification on all detected objects from pipeline result.

    Inputs (all optional): motion_tracking, moving_object_validation,
    sky_changes, light_curves (dict keyed by object/track id).

    Returns:
        {
            "object_count": int,
            "objects": [ { "object_id", "identity", "confidence", "reason" }, ... ],
            "summary": str
        }
    """
    empty: Dict[str, Any] = {
        "object_count": 0,
        "objects": [],
        "summary": "Object identity classification completed.",
    }
    try:
        pipeline_result = pipeline_result or {}
    except Exception:
        return empty

    motion = pipeline_result.get("motion_tracking") or {}
    validation = pipeline_result.get("moving_object_validation") or {}
    tracks = motion.get("tracks") if isinstance(motion, dict) else []
    if not isinstance(tracks, list):
        tracks = []
    light_curves = pipeline_result.get("light_curves") or {}
    if not isinstance(light_curves, dict):
        light_curves = {}
    sky_changes_data = pipeline_result.get("sky_changes") or {}
    sky_changes_list = sky_changes_data.get("changes") if isinstance(sky_changes_data, dict) else []
    if not isinstance(sky_changes_list, list):
        sky_changes_list = []

    image_width: Optional[float] = None
    try:
        image_width = pipeline_result.get("image_width")
        if image_width is not None:
            image_width = float(image_width)
        if image_width is None or image_width <= 0:
            meta = pipeline_result.get("metadata") or {}
            if isinstance(meta, dict):
                image_width = meta.get("width") or meta.get("image_width")
                if image_width is not None:
                    image_width = float(image_width)
    except (TypeError, ValueError):
        image_width = None
    tolerance_px = _tolerance_px(image_width)

    objects_out: List[Dict[str, Any]] = []

    for track in tracks:
        if not isinstance(track, dict):
            continue
        object_id = track.get("track_id") or "unknown"
        lightcurve = light_curves.get(object_id) if isinstance(light_curves, dict) else None
        sky_change = None
        points = track.get("points") or []
        if points:
            last_pt = points[-1]
            try:
                lx = float(last_pt.get("x", 0) or 0)
                ly = float(last_pt.get("y", 0) or 0)
            except (TypeError, ValueError):
                lx = ly = 0.0
            for sc in sky_changes_list:
                if not isinstance(sc, dict):
                    continue
                try:
                    sx = float(sc.get("x", 0) or 0)
                    sy = float(sc.get("y", 0) or 0)
                    if abs(lx - sx) <= tolerance_px and abs(ly - sy) <= tolerance_px:
                        sky_change = sc
                        break
                except (TypeError, ValueError):
                    continue
        try:
            ident = determine_identity(
                track, validation,
                lightcurve=lightcurve,
                sky_change=sky_change,
                image_width=image_width,
            )
        except Exception as e:
            log.debug("object_identity_engine: determine_identity failed: %s", e)
            ident = {
                "identity": "unknown_object",
                "confidence": "low",
                "confidence_score": 0.2,
                "reason": "Classification failed.",
            }
        objects_out.append({
            "object_id": object_id,
            "identity": ident.get("identity", "unknown_object"),
            "confidence": ident.get("confidence", "low"),
            "confidence_score": ident.get("confidence_score", 0.2),
            "reason": ident.get("reason", ""),
        })

    objects_out.sort(key=lambda o: o.get("confidence_score", 0.0), reverse=True)

    return {
        "object_count": len(objects_out),
        "objects": objects_out,
        "summary": "Object identity classification completed.",
    }
