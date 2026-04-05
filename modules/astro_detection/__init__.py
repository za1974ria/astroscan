"""
AstroScan — Asteroid / moving-object detection, validation, and TLE catalog cross-check.

Expose high-level functions for Digital Lab integration.
"""
from .asteroid_detector import detect_moving_objects, draw_detections
from .object_validation import validate_moving_candidates, crosscheck_with_known_satellites
from .catalog_crosscheck import crosscheck_detections_with_tle
from .asteroid_catalog_crosscheck import crosscheck_detections_with_mpc

__all__ = [
    "detect_moving_objects",
    "draw_detections",
    "validate_moving_candidates",
    "crosscheck_with_known_satellites",
    "crosscheck_detections_with_tle",
    "crosscheck_detections_with_mpc",
]

