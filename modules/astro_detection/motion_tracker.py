# -*- coding: utf-8 -*-
"""
AstroScan — Motion Tracker.

Tracks moving celestial object candidates across multiple consecutive images,
estimates trajectory, motion vector, apparent angular speed, and provides
classification hints. Designed for future extension (Kalman, orbit fitting, MPC).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Default max pixel distance for associating detections across consecutive frames
DEFAULT_MAX_ASSOCIATION_PX = 50.0

# Minimum number of points to consider a track valid; fewer → marked as likely_artifact
TRACK_MIN_POINTS = 2


def _distance(det_a: Dict[str, Any], det_b: Dict[str, Any]) -> float:
    """Euclidean pixel distance between two detections."""
    xa = float(det_a.get("x", 0))
    ya = float(det_a.get("y", 0))
    xb = float(det_b.get("x", 0))
    yb = float(det_b.get("y", 0))
    return math.sqrt((xa - xb) ** 2 + (ya - yb) ** 2)


def _brightness_similarity(det_a: Dict[str, Any], det_b: Dict[str, Any]) -> float:
    """
    Similarity in brightness and size; returns value in [0, 1], 1 = very similar.
    """
    ba = float(det_a.get("brightness", 0) or 0)
    bb = float(det_b.get("brightness", 0) or 0)
    sa = max(1e-6, float(det_a.get("size", 1) or 1))
    sb = max(1e-6, float(det_b.get("size", 1) or 1))
    b_ratio = min(ba, bb) / max(ba, bb) if max(ba, bb) > 0 else 1.0
    s_ratio = min(sa, sb) / max(sa, sb)
    return 0.5 * b_ratio + 0.5 * s_ratio


def _observation_timestamp_from_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[datetime]:
    """Parse observation time from metadata; returns None if missing or invalid."""
    if not metadata:
        return None
    obs = (
        metadata.get("observation_date")
        or metadata.get("date")
        or metadata.get("timestamp")
        or metadata.get("observation_date_utc")
    )
    if not obs:
        return None
    if isinstance(obs, (int, float)):
        try:
            return datetime.fromtimestamp(float(obs), tz=timezone.utc)
        except (OSError, ValueError):
            return None
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
    return None


def _associate_detections_between_frames(
    dets_a: List[Dict[str, Any]],
    dets_b: List[Dict[str, Any]],
    max_px: float = DEFAULT_MAX_ASSOCIATION_PX,
) -> List[Tuple[int, int]]:
    """
    Nearest-neighbor association between two consecutive frames.
    Returns list of (index_in_a, index_in_b) for paired detections.
    Prefers closer pairs and similar brightness/size.
    """
    if not dets_a or not dets_b:
        return []
    pairs: List[Tuple[int, int, float]] = []
    for ia, da in enumerate(dets_a):
        for ib, db in enumerate(dets_b):
            d = _distance(da, db)
            if d > max_px:
                continue
            sim = _brightness_similarity(da, db)
            cost = d * (1.2 - 0.2 * sim)
            pairs.append((ia, ib, cost))
    pairs.sort(key=lambda x: x[2])
    used_a: set = set()
    used_b: set = set()
    result: List[Tuple[int, int]] = []
    for ia, ib, _ in pairs:
        if ia in used_a or ib in used_b:
            continue
        result.append((ia, ib))
        used_a.add(ia)
        used_b.add(ib)
    return result


def _build_tracks(
    detections_per_image: List[List[Dict[str, Any]]],
    metadata_list: Optional[List[Optional[Dict[str, Any]]]] = None,
    max_association_px: float = DEFAULT_MAX_ASSOCIATION_PX,
) -> List[List[Tuple[int, Dict[str, Any]]]]:
    """
    Build tracks from detections per frame. Each track is a list of (frame_index, detection).
    Uses nearest-neighbor association between consecutive frames.
    """
    n_frames = len(detections_per_image)
    if n_frames == 0:
        return []
    metadata_list = metadata_list or [None] * n_frames
    while len(metadata_list) < n_frames:
        metadata_list.append(None)

    # Tracks as list of (frame_index, detection)
    tracks: List[List[Tuple[int, Dict[str, Any]]]] = []

    if n_frames == 1:
        for det in detections_per_image[0]:
            tracks.append([(0, det)])
        return tracks

    # Associate frame 0 and 1, then 1 and 2, etc.
    # Map: (frame_idx, det_idx) -> track_id
    assignment: Dict[Tuple[int, int], int] = {}
    next_track_id = 0

    for f in range(n_frames - 1):
        dets_a = detections_per_image[f]
        dets_b = detections_per_image[f + 1]
        pairs = _associate_detections_between_frames(dets_a, dets_b, max_association_px)
        for ia, ib in pairs:
            key_a = (f, ia)
            key_b = (f + 1, ib)
            if key_a in assignment:
                tid = assignment[key_a]
                assignment[key_b] = tid
            else:
                tid = next_track_id
                next_track_id += 1
                assignment[key_a] = tid
                assignment[key_b] = tid

    # Build track_id -> list of (frame_index, detection)
    track_lists: Dict[int, List[Tuple[int, Dict[str, Any]]]] = {}
    for (fi, di), tid in assignment.items():
        det = detections_per_image[fi][di]
        track_lists.setdefault(tid, []).append((fi, det))
    for tid, points in track_lists.items():
        points.sort(key=lambda x: x[0])
        tracks.append(points)

    # Add unassociated detections as single-point tracks
    for f in range(n_frames):
        for di, det in enumerate(detections_per_image[f]):
            if (f, di) in assignment:
                continue
            tracks.append([(f, det)])

    return tracks


def _track_to_output(
    track_id: str,
    points: List[Tuple[int, Dict[str, Any]]],
    metadata_list: List[Optional[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    Convert one track (list of (frame_index, det)) to output format with
    velocity, direction, angular velocity, classification_hint, confidence.
    """
    n = len(points)
    out_points: List[Dict[str, Any]] = []
    for fi, det in points:
        meta = metadata_list[fi] if fi < len(metadata_list) else None
        ts = _observation_timestamp_from_metadata(meta) if meta else None
        ts_str: Optional[str] = None
        if ts is not None:
            try:
                ts_str = ts.isoformat()
            except Exception:
                ts_str = None
        out_points.append({
            "frame_index": fi,
            "x": float(det.get("x", 0) or 0),
            "y": float(det.get("y", 0) or 0),
            "brightness": float(det.get("brightness", 0) or 0),
            "size": float(det.get("size", 0) or 0),
            "timestamp": ts_str,
        })

    velocity_px_per_frame: Optional[float] = None
    velocity_px_per_sec: Optional[float] = None
    direction_deg: float = 0.0
    angular_velocity_arcsec_per_hr: Optional[float] = None
    rejection_reason: Optional[str] = None

    if n >= 2:
        first = points[0][1]
        last = points[-1][1]
        dx = float(last.get("x", 0)) - float(first.get("x", 0))
        dy = float(last.get("y", 0)) - float(first.get("y", 0))
        num_frames = points[-1][0] - points[0][0]
        if num_frames > 0:
            velocity_px_per_frame = math.sqrt(dx * dx + dy * dy) / num_frames
        else:
            velocity_px_per_frame = math.sqrt(dx * dx + dy * dy)
        direction_deg = math.degrees(math.atan2(dy, dx))

        # velocity_px_per_sec from timestamps
        if n >= 2 and metadata_list:
            t0 = _observation_timestamp_from_metadata(metadata_list[points[0][0]])
            t1 = _observation_timestamp_from_metadata(metadata_list[points[-1][0]])
            if t0 is not None and t1 is not None and t1 > t0:
                dt_sec = (t1 - t0).total_seconds()
                if dt_sec > 0:
                    total_px = math.sqrt(dx * dx + dy * dy)
                    velocity_px_per_sec = total_px / dt_sec
                    # angular velocity: need scale and time in hours
                    scale_arcsec_per_px: Optional[float] = None
                    meta = metadata_list[points[0][0]] if points[0][0] < len(metadata_list) else None
                    if meta:
                        scale_arcsec = meta.get("scale_arcsec")
                        scale_deg = meta.get("scale_deg")
                        if scale_arcsec is not None:
                            try:
                                scale_arcsec_per_px = float(scale_arcsec)
                            except (TypeError, ValueError):
                                pass
                        if scale_arcsec_per_px is None and scale_deg is not None:
                            try:
                                scale_arcsec_per_px = float(scale_deg) * 3600.0
                            except (TypeError, ValueError):
                                pass
                    if scale_arcsec_per_px is not None and scale_arcsec_per_px > 0 and dt_sec > 0:
                        dt_hr = dt_sec / 3600.0
                        pixel_speed_per_hour = (total_px / dt_sec) * 3600.0
                        angular_velocity_arcsec_per_hr = pixel_speed_per_hour * scale_arcsec_per_px

    # Image width for aberrant-speed check (metadata or estimate from points)
    image_width: Optional[float] = None
    if points:
        first_meta = metadata_list[points[0][0]] if points[0][0] < len(metadata_list) else None
        if first_meta is not None:
            w = first_meta.get("image_width") or first_meta.get("width")
            if w is not None:
                try:
                    image_width = float(w)
                except (TypeError, ValueError):
                    pass
        if image_width is None or image_width <= 0:
            try:
                image_width = max(float(p[1].get("x", 0) or 0 for p in points) + 1.0
            except (ValueError, TypeError):
                image_width = 1.0
    else:
        image_width = 1.0

    # Classification hint and confidence (respect TRACK_MIN_POINTS and aberrant speed)
    classification_hint, confidence = _classify_track(
        points, velocity_px_per_frame, velocity_px_per_sec, angular_velocity_arcsec_per_hr,
    )

    if n < TRACK_MIN_POINTS:
        classification_hint = "likely_artifact"
        confidence = "low"
        rejection_reason = "insufficient_points"
    elif (
        velocity_px_per_frame is not None
        and image_width is not None
        and image_width > 0
        and velocity_px_per_frame > image_width * 0.5
    ):
        classification_hint = "likely_artifact"
        confidence = "low"
        rejection_reason = "aberrant_speed"
        log.debug(
            "motion_tracker: rejecting track %s due to aberrant speed (%.2f px/frame)",
            track_id,
            velocity_px_per_frame,
        )

    return {
        "track_id": track_id,
        "points": out_points,
        "velocity_px_per_frame": velocity_px_per_frame,
        "velocity_px_per_sec": velocity_px_per_sec,
        "direction_deg": round(direction_deg, 2),
        "angular_velocity_arcsec_per_hr": round(angular_velocity_arcsec_per_hr, 4) if angular_velocity_arcsec_per_hr is not None else None,
        "classification_hint": classification_hint,
        "confidence": confidence,
        "rejection_reason": rejection_reason,
    }


def _classify_track(
    points: List[Tuple[int, Dict[str, Any]]],
    velocity_px_per_frame: Optional[float],
    velocity_px_per_sec: Optional[float],
    angular_velocity_arcsec_per_hr: Optional[float],
) -> Tuple[str, str]:
    """
    Heuristic classification hint and confidence.
    Returns (classification_hint, confidence).
    Tracks with fewer than TRACK_MIN_POINTS are overridden to likely_artifact in _track_to_output.
    """
    n = len(points)
    if n == 0:
        return "likely_artifact", "low"
    if n < TRACK_MIN_POINTS:
        return "likely_artifact", "low"

    # Brightness stability (safe defaults for missing brightness/size)
    brights = [float(p[1].get("brightness", 0) or 0) for p in points]
    bright_std = (max(brights) - min(brights)) / (max(brights) or 1.0)
    stable_brightness = bright_std < 0.4

    # Path consistency: rough straight-line check (safe get for x,y)
    if n >= 3:
        first, mid, last = points[0][1], points[n // 2][1], points[-1][1]
        x1, y1 = float(first.get("x", 0) or 0), float(first.get("y", 0) or 0)
        x2, y2 = float(last.get("x", 0) or 0), float(last.get("y", 0) or 0)
        xm, ym = float(mid.get("x", 0) or 0), float(mid.get("y", 0) or 0)
        # expected mid if linear
        t = 0.5
        xe = x1 + t * (x2 - x1)
        ye = y1 + t * (y2 - y1)
        dev = math.sqrt((xm - xe) ** 2 + (ym - ye) ** 2)
        linear_path = dev < 30
    else:
        linear_path = True

    # Very fast angular speed + long straight → likely_satellite
    if angular_velocity_arcsec_per_hr is not None and angular_velocity_arcsec_per_hr > 60 and linear_path:
        return "likely_satellite", "medium" if n >= 3 else "low"
    if velocity_px_per_sec is not None and velocity_px_per_sec > 100 and linear_path and n >= 2:
        return "likely_satellite", "low"

    # Moderate displacement, stable brightness → likely_asteroid
    if n >= 2 and stable_brightness and linear_path:
        v = velocity_px_per_frame or 0
        if 1 < v < 80:
            return "likely_asteroid", "high" if n >= 3 else "medium"
        if v >= 80 and angular_velocity_arcsec_per_hr is not None and angular_velocity_arcsec_per_hr < 30:
            return "likely_asteroid", "medium"

    # Inconsistent path or single weak
    if not linear_path and n >= 3:
        return "likely_artifact", "medium"
    if n == 1:
        return "likely_artifact", "low"

    return "uncertain_motion", "medium" if n >= 3 else "low"


def _make_summary(tracks: List[Dict[str, Any]], n_frames: int) -> str:
    """Human-readable observatory-style summary; includes rejection counts when applicable."""
    if not tracks:
        return "No motion tracks identified."
    parts = [f"{len(tracks)} motion track(s) identified across {n_frames} frame(s)."]
    n_insufficient = sum(1 for t in tracks if t.get("rejection_reason") == "insufficient_points")
    n_aberrant = sum(1 for t in tracks if t.get("rejection_reason") == "aberrant_speed")
    if n_insufficient > 0:
        parts.append(f"{n_insufficient} track(s) rejected due to insufficient points.")
    if n_aberrant > 0:
        parts.append(f"{n_aberrant} track(s) rejected due to aberrant speed.")
    for t in tracks:
        tid = t.get("track_id", "?")
        hint = t.get("classification_hint", "uncertain_motion")
        n_pts = len(t.get("points", []))
        if hint == "likely_satellite":
            parts.append(f"Track {tid} shows rapid linear motion ({n_pts} points), consistent with a likely satellite.")
        elif hint == "likely_asteroid":
            parts.append(f"Track {tid} shows moderate stable motion ({n_pts} points), consistent with a possible asteroid.")
        elif hint == "likely_artifact":
            parts.append(f"Track {tid} shows inconsistent or weak signal ({n_pts} points), consistent with a likely artifact.")
        else:
            parts.append(f"Track {tid} shows uncertain motion ({n_pts} points).")
    return " ".join(parts)


def track_moving_objects(
    image_paths: List[Any],
    metadata_list: Optional[List[Optional[Dict[str, Any]]]] = None,
    detections_per_image: Optional[List[List[Dict[str, Any]]]] = None,
    max_association_px: float = DEFAULT_MAX_ASSOCIATION_PX,
) -> Dict[str, Any]:
    """
    Track moving object candidates across consecutive images.

    Input:
        image_paths: ordered list of consecutive image paths (at least 2, ideally 3+).
        metadata_list: optional list of metadata dicts, one per image.
        detections_per_image: optional list of detection lists (from asteroid_detector).
            If not provided, detections are computed between consecutive pairs.

    Output:
        {
            "track_count": int,
            "tracks": [ { track_id, points, velocity_px_per_frame, velocity_px_per_sec,
                         direction_deg, angular_velocity_arcsec_per_hr,
                         classification_hint, confidence } ],
            "summary": str
        }
    """
    empty = {
        "track_count": 0,
        "tracks": [],
        "summary": "No motion tracking performed (insufficient images or tracking failed).",
    }
    paths = [Path(p) for p in image_paths if p is not None]
    if len(paths) < 2:
        log.debug("motion_tracker: fewer than 2 images, skipping")
        return empty

    n = len(paths)
    metadata_list = metadata_list or [None] * n
    while len(metadata_list) < n:
        metadata_list.append(None)

    if detections_per_image is not None:
        if len(detections_per_image) != n:
            detections_per_image = None
    if detections_per_image is None:
        try:
            from modules.astro_detection.asteroid_detector import detect_moving_objects
        except ImportError:
            log.warning("motion_tracker: asteroid_detector not available")
            return empty
        detections_per_image = []
        for i in range(n):
            if i == 0:
                detections_per_image.append([])
                continue
            try:
                dets = detect_moving_objects(str(paths[i - 1]), str(paths[i]))
                detections_per_image.append(dets)
            except Exception as e:
                log.debug("motion_tracker: detection failed for pair %s,%s: %s", paths[i - 1], paths[i], e)
                detections_per_image.append([])
        # Frame 0 has no detections from a previous pair; we have detections in frames 1..n-1
        # So we have n-1 frames with detection data. Align: detections_per_image[0] = [] always
        # and detections_per_image[i] for i>=1 are detections in image i from (image i-1, image i).
        # So number of "frames with detections" is n. Frame 0 is empty. For _build_tracks we pass
        # detections_per_image as-is; tracks can have points in frames 1..n-1 only for multi-frame.
    else:
        detections_per_image = [list(d) for d in detections_per_image]

    try:
        raw_tracks = _build_tracks(detections_per_image, metadata_list, max_association_px)
    except Exception as e:
        log.warning("motion_tracker: build_tracks failed: %s", e)
        return empty

    raw_tracks = [t for t in raw_tracks if len(t) >= 1]

    tracks_out: List[Dict[str, Any]] = []
    for i, raw in enumerate(raw_tracks):
        tid = f"T{i + 1}"
        try:
            tr = _track_to_output(tid, raw, metadata_list)
            tracks_out.append(tr)
        except Exception as e:
            log.debug("motion_tracker: track %s output failed: %s", tid, e)
            continue

    summary = _make_summary(tracks_out, n)
    return {
        "track_count": len(tracks_out),
        "tracks": tracks_out,
        "summary": summary,
    }
