"""
Digital Lab — Full analysis pipeline.
Orchestrates: load → reduce noise → detect stars → detect objects → photometry → anomalies → asteroid detection.
"""
from pathlib import Path
import os
import json

from .image_loader import load_image
from .astro_preprocessing import reduce_noise, normalize
from .object_detection import detect_stars, detect_objects
from .photometry import compute_brightness
from .anomaly_detection import detect_anomalies
from .report_generator import generate_report


def _find_previous_image(current_path: Path) -> Path | None:
    """
    Find the immediately previous image file in the same directory by mtime.
    Only considers basic AstroScan lab extensions.
    """
    if not current_path.exists():
        return None
    exts = (".png", ".jpg", ".jpeg", ".fits", ".fit")
    folder = current_path.parent
    files = []
    for name in os.listdir(folder):
        p = folder / name
        if not p.is_file():
            continue
        if not p.suffix.lower() in exts:
            continue
        files.append((p.stat().st_mtime, p))
    if not files:
        return None
    files.sort(key=lambda x: x[0])
    ordered = [p for _, p in files]
    try:
        idx = ordered.index(current_path)
    except ValueError:
        return None
    if idx <= 0:
        return None
    return ordered[idx - 1]


def _find_recent_images(current_path: Path, n: int = 3) -> list:
    """
    Find up to n most recent images including current, ordered oldest first (by mtime).
    Returns list of Path; length at least 1 (current) if current exists.
    """
    if not current_path.exists():
        return []
    exts = (".png", ".jpg", ".jpeg", ".fits", ".fit")
    folder = current_path.parent
    files = []
    for name in os.listdir(folder):
        p = folder / name
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        files.append((p.stat().st_mtime, p))
    if not files:
        return []
    files.sort(key=lambda x: x[0])
    ordered = [p for _, p in files]
    try:
        idx = ordered.index(current_path)
    except ValueError:
        return [current_path]
    start = max(0, idx - (n - 1))
    return ordered[start : idx + 1]


def _metadata_path_for_image(image_path: Path) -> Path | None:
    """Resolve metadata JSON path for a raw image path. Returns None if path pattern not matched."""
    parts = list(image_path.parts)
    if "images_espace" not in parts:
        return None
    idx = parts.index("images_espace")
    if idx + 1 >= len(parts) or parts[idx + 1] != "raw":
        return None
    root = Path(*parts[:idx])
    return root / "metadata" / (image_path.name + ".json")


def _update_metadata_for_asteroids(
    image_path: Path,
    moving_info: dict,
    validation_result: dict | None = None,
    motion_tracking: dict | None = None,
    mpc_report: dict | None = None,
    astrometry_solution: dict | None = None,
) -> None:
    """
    Persist asteroid detection, optional validation, motion tracking, and optional MPC report in lab metadata JSON.
    data/images_espace/raw/<file>  →  data/metadata/<file>.json
    """
    try:
        meta_path = _metadata_path_for_image(image_path)
        if meta_path is None:
            return
        meta_dir = meta_path.parent
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta = {}
        if meta_path.exists():
            with meta_path.open("r", encoding="utf-8") as f:
                try:
                    meta = json.load(f) or {}
                except Exception:
                    meta = {}
        meta["asteroid_detection"] = moving_info
        if validation_result is not None:
            meta["moving_object_validation"] = validation_result
        if motion_tracking is not None:
            meta["motion_tracking"] = motion_tracking
        if mpc_report is not None:
            meta["mpc_report"] = mpc_report
        if astrometry_solution is not None:
            meta["astrometry_solution"] = astrometry_solution
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception:
        # Never break pipeline on metadata write
        return


def _update_metadata_astrometry(image_path: Path, astrometry_solution: dict) -> None:
    """
    Persist only astrometry_solution in lab metadata JSON (merge, do not overwrite other keys).
    Used when pipeline runs astrometry but does not run the full asteroid/motion block.
    """
    try:
        meta_path = _metadata_path_for_image(image_path)
        if meta_path is None:
            return
        meta_dir = meta_path.parent
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta = {}
        if meta_path.exists():
            with meta_path.open("r", encoding="utf-8") as f:
                try:
                    meta = json.load(f) or {}
                except Exception:
                    meta = {}
        meta["astrometry_solution"] = astrometry_solution
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception:
        return


def run_pipeline(image_source):
    """
    Run full pipeline on image (path or bytes).
    image_source: str path, Path, or bytes
    Returns: dict with keys: image_loaded, preprocessed, stars, objects, brightness, anomalies, report.
    """
    result = {
        "image_loaded": False,
        "preprocessed": False,
        "stars": [],
        "objects": [],
        "brightness": {},
        "anomalies": {},
        "report": {},
        "error": None,
        "moving_objects": {},
        "motion_tracking": {
            "track_count": 0,
            "tracks": [],
            "summary": "No motion tracking performed.",
        },
        "mpc_report": None,
        "mpc_report_validation": None,
        "astrometry_solution": None,
    }
    try:
        image = load_image(image_source)
        result["image_loaded"] = True
        result["shape"] = list(image.shape)
    except Exception as e:
        result["error"] = str(e)
        return result

    try:
        image = reduce_noise(image)
        image = normalize(image)
        result["preprocessed"] = True
    except Exception as e:
        result["error"] = f"Preprocessing: {e}"
        return result

    try:
        stars = detect_stars(image)
        objects = detect_objects(image)
        result["stars"] = stars
        result["objects"] = objects
    except Exception as e:
        result["error"] = f"Detection: {e}"
        return result

    try:
        brightness = compute_brightness(image, stars, objects)
        result["brightness"] = brightness
    except Exception as e:
        result["brightness"] = {}
        result["error"] = (result.get("error") or "") + f" Photometry: {e}"

    try:
        result["anomalies"] = detect_anomalies(image, stars, objects, result["brightness"])
    except Exception:
        result["anomalies"] = {"anomalies": [], "anomaly_count": 0}

    # Asteroid / moving-object detection using consecutive lab images
    validation_result = {
        "summary": "No validation performed.",
        "classified_candidates": [],
        "count_by_class": {},
    }
    try:
        prev_path = None
        current_path = None
        if isinstance(image_source, (str, bytes, Path)) and not isinstance(image_source, bytes):
            current_path = Path(image_source)
        if current_path is not None and current_path.exists():
            prev_path = _find_previous_image(current_path)

        # Astrometry: solve when we have a current image path (before sky-dependent modules)
        if current_path is not None and current_path.exists():
            try:
                from modules.astro_detection.astrometric_solver import (
                    solve_astrometry,
                    astrometry_solution_for_metadata,
                )
                lab_meta_ast = {}
                mp = _metadata_path_for_image(current_path)
                if mp and mp.exists():
                    try:
                        with mp.open("r", encoding="utf-8") as f:
                            lab_meta_ast = json.load(f) or {}
                    except Exception:
                        pass
                astro_result = solve_astrometry(current_path, metadata=lab_meta_ast, config=None)
                result["astrometry_solution"] = astro_result
                meta_block = astrometry_solution_for_metadata(astro_result)
                _update_metadata_astrometry(current_path, meta_block)
            except Exception:
                result["astrometry_solution"] = {
                    "solved": False,
                    "solver_mode": "disabled",
                    "warnings": [],
                    "error": "Astrometry failed or skipped",
                    "summary": "Astrometric solving failed or skipped.",
                }

        moving_info = {
            "moving_objects_detected": False,
            "candidate_count": 0,
            "detections": [],
            "annotated_path": None,
        }
        if prev_path is not None and current_path is not None:
            try:
                from modules.astro_detection.asteroid_detector import (
                    detect_moving_objects,
                    draw_detections,
                )

                detections = detect_moving_objects(str(prev_path), str(current_path))
                moving_info["detections"] = detections
                moving_info["candidate_count"] = len(detections)
                moving_info["moving_objects_detected"] = len(detections) > 0

                if detections:
                    # Save annotated image into analysed directory mirroring RAW layout
                    parts = list(current_path.parts)
                    if "images_espace" in parts:
                        idx = parts.index("images_espace")
                        if idx + 1 < len(parts) and parts[idx + 1] == "raw":
                            root = Path(*parts[:idx])  # .../data
                            analysed_dir = root.parent / "images_espace" / "analysed"
                            analysed_dir.mkdir(parents=True, exist_ok=True)
                            annotated_name = current_path.name.rsplit(".", 1)[0] + "_asteroids.png"
                            annotated_path = analysed_dir / annotated_name
                            annotated_img = draw_detections(str(current_path), detections)
                            try:
                                import cv2

                                cv2.imwrite(str(annotated_path), annotated_img)
                                moving_info["annotated_path"] = str(annotated_path)
                            except Exception:
                                moving_info["annotated_path"] = None

                # Validation layer: classify candidates and optional satellite cross-check
                validation_result = None
                try:
                    from modules.astro_detection.object_validation import (
                        validate_moving_candidates,
                        crosscheck_with_known_satellites,
                    )
                    meta_path = _metadata_path_for_image(current_path)
                    lab_meta = {}
                    if meta_path is not None and meta_path.exists():
                        try:
                            with meta_path.open("r", encoding="utf-8") as f:
                                lab_meta = json.load(f) or {}
                        except Exception:
                            pass
                    validation_result = validate_moving_candidates(
                        moving_info.get("detections", []),
                        metadata=lab_meta,
                    )
                    satellite_check = crosscheck_with_known_satellites(
                        lab_meta,
                        moving_info.get("detections", []),
                    )
                    validation_result["satellite_crosscheck"] = satellite_check
                    # Mark matched detections as confirmed_satellite in classified_candidates
                    if satellite_check.get("checked") and satellite_check.get("matches"):
                        for m in satellite_check["matches"]:
                            mx, my = m.get("x"), m.get("y")
                            for c in validation_result.get("classified_candidates", []):
                                if c.get("x") == mx and c.get("y") == my:
                                    c["classification"] = "confirmed_satellite"
                                    break
                        count_by_class = validation_result.get("count_by_class") or {}
                        n_confirmed = len(satellite_check["matches"])
                        count_by_class["confirmed_satellite"] = count_by_class.get("confirmed_satellite", 0) + n_confirmed
                        validation_result["count_by_class"] = count_by_class
                        if n_confirmed:
                            validation_result["summary"] = (validation_result.get("summary") or "") + "; %d confirmed satellite(s) from TLE." % n_confirmed

                    # Asteroid catalog cross-check
                    try:
                        from modules.astro_detection.asteroid_catalog_crosscheck import crosscheck_detections_with_mpc
                        asteroid_check = crosscheck_detections_with_mpc(
                            moving_info.get("detections", []),
                            metadata=lab_meta,
                            mpc_path=None,
                            max_asteroids=300,
                        )
                        validation_result["asteroid_crosscheck"] = asteroid_check
                        if asteroid_check.get("checked") and asteroid_check.get("matches"):
                            for m in asteroid_check["matches"]:
                                mx, my = m.get("x"), m.get("y")
                                for c in validation_result.get("classified_candidates", []):
                                    if c.get("x") == mx and c.get("y") == my:
                                        c["classification"] = "known_asteroid"
                                        break
                            count_by_class = validation_result.get("count_by_class") or {}
                            n_asteroids = len(asteroid_check["matches"])
                            count_by_class["known_asteroid"] = count_by_class.get("known_asteroid", 0) + n_asteroids
                            validation_result["count_by_class"] = count_by_class
                            if n_asteroids:
                                validation_result["summary"] = (validation_result.get("summary") or "") + "; %d known asteroid(s) from MPC." % n_asteroids
                    except Exception:
                        validation_result["asteroid_crosscheck"] = {
                            "checked": False,
                            "matches": [],
                            "reason": "asteroid cross-check failed",
                        }
                except Exception:
                    validation_result = {
                        "summary": "Validation failed.",
                        "classified_candidates": [],
                        "count_by_class": {},
                        "satellite_crosscheck": {
                            "checked": False,
                            "matches": [],
                            "reason": "validation error",
                        },
                        "asteroid_crosscheck": {"checked": False, "matches": [], "reason": "not run"},
                    }

                motion_tracking_result = result["motion_tracking"]
                if current_path is not None and len(recent_paths := _find_recent_images(current_path, 3)) >= 2:
                    try:
                        from modules.astro_detection.motion_tracker import track_moving_objects
                        metadata_list_mt = []
                        for p in recent_paths:
                            mp = _metadata_path_for_image(p)
                            m = {}
                            if mp and mp.exists():
                                try:
                                    with mp.open("r", encoding="utf-8") as f:
                                        m = json.load(f) or {}
                                except Exception:
                                    pass
                            metadata_list_mt.append(m)
                        detections_per_image_mt = []
                        for i in range(len(recent_paths)):
                            if i == 0:
                                detections_per_image_mt.append([])
                            else:
                                if (
                                    recent_paths[i] == current_path
                                    and prev_path is not None
                                    and recent_paths[i - 1] == prev_path
                                ):
                                    detections_per_image_mt.append(moving_info.get("detections", []))
                                else:
                                    try:
                                        from modules.astro_detection.asteroid_detector import detect_moving_objects
                                        dets = detect_moving_objects(str(recent_paths[i - 1]), str(recent_paths[i]))
                                        detections_per_image_mt.append(dets)
                                    except Exception:
                                        detections_per_image_mt.append([])
                        motion_tracking_result = track_moving_objects(
                            [str(p) for p in recent_paths],
                            metadata_list=metadata_list_mt,
                            detections_per_image=detections_per_image_mt,
                        )
                    except Exception:
                        motion_tracking_result = {
                            "track_count": 0,
                            "tracks": [],
                            "summary": "Motion tracking failed or skipped.",
                        }
                result["motion_tracking"] = motion_tracking_result

                mpc_report_result = None
                mpc_validation_result = None
                try:
                    from modules.astro_detection.discovery_engine import run_discovery_engine
                    from modules.astro_detection.mpc_reporter import (
                        build_mpc_candidate_report,
                        validate_report_readiness,
                    )
                    discovery_result = run_discovery_engine(result)
                    lab_meta = {}
                    if current_path is not None:
                        mp = _metadata_path_for_image(current_path)
                        if mp and mp.exists():
                            try:
                                with mp.open("r", encoding="utf-8") as f:
                                    lab_meta = json.load(f) or {}
                            except Exception:
                                pass
                    if discovery_result.get("candidate_count", 0) > 0:
                        mpc_report_result = build_mpc_candidate_report(
                            image_metadata=lab_meta,
                            motion_tracking=motion_tracking_result,
                            moving_object_validation=validation_result,
                            discovery_engine_result=discovery_result,
                            observatory_config=None,
                            source_image=current_path.name if current_path else None,
                        )
                        mpc_validation_result = validate_report_readiness(mpc_report_result)
                    else:
                        mpc_report_result = {
                            "status": "draft",
                            "observatory_code": None,
                            "candidate_count": 0,
                            "candidates": [],
                            "submission_format": "ADES_PSV",
                            "ack_requested": False,
                            "summary": "No MPC-ready candidates.",
                        }
                        mpc_validation_result = {"ready": False, "missing_fields": [], "warnings": []}
                except Exception:
                    mpc_report_result = {
                        "status": "draft",
                        "observatory_code": None,
                        "candidate_count": 0,
                        "candidates": [],
                        "submission_format": "ADES_PSV",
                        "ack_requested": False,
                        "summary": "MPC report generation failed or skipped.",
                    }
                    mpc_validation_result = {"ready": False, "missing_fields": [], "warnings": ["Report generation failed."]}
                result["mpc_report"] = mpc_report_result
                result["mpc_report_validation"] = mpc_validation_result

                if current_path is not None:
                    from modules.astro_detection.astrometric_solver import astrometry_solution_for_metadata
                    astro_meta_block = astrometry_solution_for_metadata(result.get("astrometry_solution")) if result.get("astrometry_solution") else None
                    _update_metadata_for_asteroids(
                        current_path,
                        moving_info,
                        validation_result=validation_result,
                        motion_tracking=motion_tracking_result,
                        mpc_report=mpc_report_result,
                        astrometry_solution=astro_meta_block,
                    )
            except Exception:
                # Swallow all errors from asteroid detection
                pass
        result["moving_objects"] = moving_info
        result["moving_object_validation"] = validation_result
    except Exception:
        result["moving_objects"] = {}
        result["moving_object_validation"] = {
            "summary": "Validation skipped (pipeline error).",
            "classified_candidates": [],
            "count_by_class": {},
        }

    try:
        from modules.astro_detection.object_identity_engine import run_object_identity_engine
        result["object_identity"] = run_object_identity_engine(result)
    except Exception:
        result["object_identity"] = {
            "object_count": 0,
            "objects": [],
            "summary": "Object identity classification skipped.",
        }

    try:
        result["report"] = generate_report(result)
    except Exception as e:
        result["report"] = {"summary": f"Report generation failed: {e}", "sections": []}

    return result
