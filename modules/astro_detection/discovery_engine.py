# -*- coding: utf-8 -*-
"""
AstroScan — Discovery Engine.

Identifies potential new astronomical discoveries by combining
motion tracking, catalog cross-checks, and sky change detection.
Does not modify asteroid_detector, motion_tracker, sky_change_detector,
or satellite/MPC cross-check modules.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Pixel tolerance to consider a track point "matched" to a validation match
_MATCH_PX_TOL = 10.0


def _track_matches_validation_list(track: Dict[str, Any], matches: List[Dict[str, Any]]) -> bool:
    """Return True if any point of the track is near any validation match (x, y)."""
    if not matches:
        return False
    points = track.get("points") or []
    for pt in points:
        tx = float(pt.get("x", 0) or 0)
        ty = float(pt.get("y", 0) or 0)
        for m in matches:
            try:
                mx = float(m.get("x", 0) or 0)
                my = float(m.get("y", 0) or 0)
                if abs(tx - mx) <= _MATCH_PX_TOL and abs(ty - my) <= _MATCH_PX_TOL:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def evaluate_motion_candidate(
    track: Dict[str, Any],
    validation: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Evaluate a motion track as a potential new discovery (unmatched asteroid candidate).

    Rules:
    - If track is likely_artifact → return None.
    - If track is matched by satellite_crosscheck or asteroid_crosscheck → return None.
    - If track has at least 3 points and motion is coherent → return candidate_asteroid.
    - Else return None.
    """
    if not track:
        return None
    try:
        if track.get("classification_hint") == "likely_artifact":
            return None

        validation = validation or {}
        sat_check = validation.get("satellite_crosscheck") or {}
        ast_check = validation.get("asteroid_crosscheck") or {}
        sat_matches = sat_check.get("matches") if isinstance(sat_check, dict) else []
        ast_matches = ast_check.get("matches") if isinstance(ast_check, dict) else []

        if not isinstance(sat_matches, list):
            sat_matches = []
        if not isinstance(ast_matches, list):
            ast_matches = []

        if _track_matches_validation_list(track, sat_matches):
            return None
        if _track_matches_validation_list(track, ast_matches):
            return None

        points = track.get("points") or []
        if len(points) < 3:
            return None

        # "Motion coherent" ≈ not flagged as artifact (already excluded) and has velocity
        rejection = track.get("rejection_reason")
        if rejection in ("insufficient_points", "aberrant_speed"):
            return None

        # Use last point position for candidate location
        last = points[-1] if points else {}
        x = float(last.get("x", 0) or 0)
        y = float(last.get("y", 0) or 0)

        return {
            "type": "candidate_asteroid",
            "confidence": "medium",
            "x": x,
            "y": y,
        }
    except Exception as e:
        log.debug("discovery_engine: evaluate_motion_candidate failed: %s", e)
        return None


def evaluate_transient(change: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Evaluate a sky change as a potential transient (supernova, new object).

    Rules:
    - If classification == "possible_supernova" → candidate_supernova, confidence medium.
    - If classification == "new_object" → unknown_transient, confidence low.
    - Else return None.
    """
    if not change:
        return None
    try:
        classification = change.get("classification") or ""
        if classification == "possible_supernova":
            x = float(change.get("x", 0) or 0)
            y = float(change.get("y", 0) or 0)
            return {
                "type": "candidate_supernova",
                "confidence": "medium",
                "x": x,
                "y": y,
            }
        if classification == "new_object":
            x = float(change.get("x", 0) or 0)
            y = float(change.get("y", 0) or 0)
            return {
                "type": "unknown_transient",
                "confidence": "low",
                "x": x,
                "y": y,
            }
        return None
    except Exception as e:
        log.debug("discovery_engine: evaluate_transient failed: %s", e)
        return None


def run_discovery_engine(pipeline_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the discovery engine on a pipeline result.

    Inputs (all optional) may include:
    - motion_tracking (tracks list)
    - moving_object_validation (satellite/asteroid cross-check results)
    - sky_changes (changes list)

    Process:
    1. Analyze motion tracks → candidate_asteroid when unmatched and coherent.
    2. Analyze sky changes → candidate_supernova / unknown_transient.
    3. Collect all discovery candidates.

    Returns:
        {
            "candidate_count": int,
            "candidates": [ { "type", "x", "y", "confidence" }, ... ],
            "summary": str
        }
    """
    empty: Dict[str, Any] = {
        "candidate_count": 0,
        "candidates": [],
        "summary": "No discovery candidates detected.",
    }
    try:
        pipeline_result = pipeline_result or {}
    except Exception:
        return empty

    candidates: List[Dict[str, Any]] = []

    # 1. Motion tracks
    try:
        motion = pipeline_result.get("motion_tracking") or {}
        tracks = motion.get("tracks")
        if isinstance(tracks, list):
            validation = pipeline_result.get("moving_object_validation") or {}
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                c = evaluate_motion_candidate(track, validation)
                if c is not None:
                    candidates.append(c)
    except Exception as e:
        log.debug("discovery_engine: motion analysis failed: %s", e)

    # 2. Sky changes
    try:
        sky = pipeline_result.get("sky_changes") or {}
        changes = sky.get("changes")
        if isinstance(changes, list):
            for ch in changes:
                if not isinstance(ch, dict):
                    continue
                c = evaluate_transient(ch)
                if c is not None:
                    candidates.append(c)
    except Exception as e:
        log.debug("discovery_engine: sky change analysis failed: %s", e)

    if not candidates:
        return empty

    return {
        "candidate_count": len(candidates),
        "candidates": candidates,
        "summary": "Discovery engine completed.",
    }
