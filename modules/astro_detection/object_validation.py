# -*- coding: utf-8 -*-
"""
AstroScan — Validation layer for moving-object (asteroid) detection.

Classifies candidates using heuristics and provides a placeholder
for future satellite/orbital catalog cross-check.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Classification labels
CLASS_UNKNOWN = "unknown"
CLASS_POSSIBLE_SATELLITE = "possible_satellite"
CLASS_POSSIBLE_ASTEROID = "possible_asteroid"
CLASS_LOW_CONFIDENCE_ARTIFACT = "low_confidence_artifact"


def _spatial_spread(detections: List[Dict[str, Any]]) -> float:
    """Compute mean pairwise distance (pixels) between detections. High = spread out."""
    if len(detections) < 2:
        return 0.0
    n = len(detections)
    total = 0.0
    count = 0
    for i in range(n):
        xi = detections[i].get("x", 0)
        yi = detections[i].get("y", 0)
        for j in range(i + 1, n):
            xj = detections[j].get("x", 0)
            yj = detections[j].get("y", 0)
            total += math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2)
            count += 1
    return total / count if count else 0.0


def validate_moving_candidates(
    detections: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Classify each moving-object candidate using size, brightness, count, and spatial heuristics.

    Returns:
        {
            "summary": str,
            "classified_candidates": [ { ...detection, "classification": str, "confidence": str }, ... ],
            "count_by_class": { "possible_asteroid": n, ... }
        }
    """
    metadata = metadata or {}
    classified: List[Dict[str, Any]] = []
    count_by_class: Dict[str, int] = {
        CLASS_POSSIBLE_ASTEROID: 0,
        CLASS_POSSIBLE_SATELLITE: 0,
        CLASS_UNKNOWN: 0,
        CLASS_LOW_CONFIDENCE_ARTIFACT: 0,
    }

    if not detections:
        return {
            "summary": "No moving candidates to validate.",
            "classified_candidates": [],
            "count_by_class": count_by_class,
        }

    n_total = len(detections)
    spread = _spatial_spread(detections)

    # Resolution-independent spread: use spread_ratio = spread / image_width
    image_width = metadata.get("image_width") or metadata.get("width")
    if image_width is not None:
        try:
            image_width = int(image_width)
        except (TypeError, ValueError):
            image_width = None
    if image_width is None or image_width <= 0:
        image_width = max((d.get("x", 0) for d in detections), default=0) + 1
    if image_width <= 0:
        image_width = None

    if image_width and image_width > 0:
        spread_ratio = spread / image_width
        spread_out = spread_ratio > 0.05
    else:
        spread_out = spread > 80.0
        log.warning(
            "object_validation: image_width could not be determined; using fixed-pixel spread threshold (80 px)"
        )

    many_candidates = n_total > 8

    for det in detections:
        x = int(det.get("x", 0))
        y = int(det.get("y", 0))
        brightness = float(det.get("brightness", 0.0))
        size = int(det.get("size", 0))

        out = dict(det)
        classification = CLASS_UNKNOWN
        confidence = "medium"

        # Size heuristics
        if size < 8:
            classification = CLASS_LOW_CONFIDENCE_ARTIFACT
            confidence = "low"
        elif size > 400:
            classification = CLASS_LOW_CONFIDENCE_ARTIFACT
            confidence = "low"
        elif brightness < 0.08:
            classification = CLASS_LOW_CONFIDENCE_ARTIFACT
            confidence = "low"
        elif many_candidates and n_total > 12:
            classification = CLASS_LOW_CONFIDENCE_ARTIFACT
            confidence = "low"
        else:
            # Few detections, reasonable size and brightness (spread_out is resolution-independent)
            if spread_out and n_total <= 5:
                classification = CLASS_POSSIBLE_ASTEROID
                confidence = "high" if n_total <= 2 and 15 <= size <= 150 else "medium"
            elif not spread_out and n_total <= 4 and size <= 80:
                classification = CLASS_POSSIBLE_SATELLITE
                confidence = "medium"
            else:
                classification = CLASS_UNKNOWN
                confidence = "medium"

        out["classification"] = classification
        out["confidence"] = confidence
        classified.append(out)
        count_by_class[classification] = count_by_class.get(classification, 0) + 1

    # Build summary
    parts = []
    if count_by_class.get(CLASS_POSSIBLE_ASTEROID):
        parts.append(f"{count_by_class[CLASS_POSSIBLE_ASTEROID]} possible asteroid(s)")
    if count_by_class.get(CLASS_POSSIBLE_SATELLITE):
        parts.append(f"{count_by_class[CLASS_POSSIBLE_SATELLITE]} possible satellite(s)")
    if count_by_class.get(CLASS_UNKNOWN):
        parts.append(f"{count_by_class[CLASS_UNKNOWN]} unknown")
    if count_by_class.get(CLASS_LOW_CONFIDENCE_ARTIFACT):
        parts.append(f"{count_by_class[CLASS_LOW_CONFIDENCE_ARTIFACT]} low-confidence artifact(s)")
    summary = "; ".join(parts) if parts else "No candidates classified."

    return {
        "summary": summary,
        "classified_candidates": classified,
        "count_by_class": count_by_class,
    }


def crosscheck_with_known_satellites(
    metadata: Optional[Dict[str, Any]],
    detections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Cross-check detections against TLE satellite catalog (SGP4 + pointing).

    Delegates to catalog_crosscheck. Result is integrated into moving_object_validation.
    """
    try:
        from modules.astro_detection.catalog_crosscheck import crosscheck_detections_with_tle
        return crosscheck_detections_with_tle(
            detections,
            metadata=metadata or {},
            tle_path=None,
            threshold_px=25.0,
        )
    except Exception:
        return {
            "checked": False,
            "matches": [],
            "reason": "satellite catalog cross-check failed",
        }
