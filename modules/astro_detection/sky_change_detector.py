# -*- coding: utf-8 -*-
"""
AstroScan — Sky Change Detector.

Detects astronomical changes between two images of the same sky field
(supernovae, novae, variable stars, new objects) via alignment, subtraction,
and source detection. Designed to integrate with the Digital Lab pipeline.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import cv2

log = logging.getLogger(__name__)

# Optional: astropy, photutils (used only if available)
try:
    from astropy.io import fits  # type: ignore
    _HAS_ASTROPY = True
except ImportError:
    _HAS_ASTROPY = False
try:
    import photutils  # type: ignore
    _HAS_PHOTUTILS = True
except ImportError:
    _HAS_PHOTUTILS = False


def _load_image(path: Path) -> np.ndarray:
    """
    Load image from path as 2D float64 in [0, 1].
    Supports FITS (if astropy available) and raster via OpenCV.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    suffix = path.suffix.lower()
    if suffix in (".fits", ".fit") and _HAS_ASTROPY:
        try:
            with fits.open(path) as hdul:
                data = hdul[0].data
            if data is None:
                raise ValueError(f"FITS has no data: {path}")
            if data.ndim > 2:
                data = data[0] if data.shape[0] in (1, 3) else data.mean(axis=0)
            data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
            dmin, dmax = float(data.min()), float(data.max())
            if dmax > dmin:
                data = (data - dmin) / (dmax - dmin)
            return data.astype(np.float64)
        except Exception as e:
            log.debug("sky_change_detector: FITS load failed, fallback to raster: %s", e)
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not load image: {path}")
    return (img.astype(np.float64) / 255.0)


def align_images(img_a: np.ndarray, img_b: np.ndarray) -> np.ndarray:
    """
    Align img_b onto img_a using feature matching (ORB) or ECC.
    Returns aligned img_b. On failure, returns img_b unchanged.
    """
    if img_a is None or img_b is None:
        return img_b if img_b is not None else img_a
    if img_a.size == 0 or img_b.size == 0:
        return img_b
    if img_a.shape != img_b.shape:
        try:
            img_b = cv2.resize(
                img_b.astype(np.float32),
                (img_a.shape[1], img_a.shape[0]),
                interpolation=cv2.INTER_LINEAR,
            ).astype(np.float64)
        except Exception:
            return img_b

    h, w = img_a.shape
    if h < 32 or w < 32:
        return img_b

    # Prefer ORB feature matching for robustness
    try:
        orb = cv2.ORB_create(nfeatures=2000, edgeThreshold=10)
        kp_a, desc_a = orb.detectAndCompute(
            (img_a * 255).astype(np.uint8), None
        )
        kp_b, desc_b = orb.detectAndCompute(
            (img_b * 255).astype(np.uint8), None
        )
        if desc_a is None or desc_b is None or len(kp_a) < 4 or len(kp_b) < 4:
            raise ValueError("Insufficient keypoints")
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(desc_a, desc_b)
        if len(matches) < 4:
            raise ValueError("Insufficient matches")
        matches = sorted(matches, key=lambda m: m.distance)[: min(100, len(matches))]
        pts_a = np.float32([kp_a[m.queryIdx].pt for m in matches])
        pts_b = np.float32([kp_b[m.trainIdx].pt for m in matches])
        H, mask = cv2.findHomography(pts_b, pts_a, cv2.RANSAC, 5.0)
        if H is None:
            raise ValueError("Homography failed")
        aligned = cv2.warpPerspective(
            img_b.astype(np.float32),
            H,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        return aligned.astype(np.float64)
    except Exception as e:
        log.debug("sky_change_detector: ORB alignment failed, trying ECC: %s", e)

    # Fallback: ECC (intensity-based)
    try:
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6)
        warp = np.eye(2, 3, dtype=np.float32)
        _, warp = cv2.findTransformECC(
            img_a.astype(np.float32),
            img_b.astype(np.float32),
            warp,
            cv2.MOTION_EUCLIDEAN,
            criteria,
        )
        aligned = cv2.warpAffine(
            img_b.astype(np.float32),
            warp,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        return aligned.astype(np.float64)
    except Exception as e:
        log.debug("sky_change_detector: ECC alignment failed: %s", e)
    return img_b.copy()


def normalize_background(img: np.ndarray) -> np.ndarray:
    """
    Apply Gaussian blur, background subtraction, and contrast normalization.
    Returns normalized image (float64, roughly [0, 1] range).
    """
    if img is None or img.size == 0:
        return img.copy() if img is not None else np.array([])
    img = np.asarray(img, dtype=np.float64)
    # Gaussian blur to estimate background (large kernel)
    k = max(3, min(img.shape[0], img.shape[1]) // 20)
    if k % 2 == 0:
        k += 1
    try:
        background = cv2.GaussianBlur(img, (k, k), 0)
        img_sub = img - background
    except Exception:
        img_sub = img
    vmin, vmax = float(np.nanmin(img_sub)), float(np.nanmax(img_sub))
    if vmax > vmin:
        out = (img_sub - vmin) / (vmax - vmin)
    else:
        out = np.zeros_like(img_sub)
    return np.clip(out, 0.0, 1.0).astype(np.float64)


def subtract_images(img_a: np.ndarray, img_b: np.ndarray) -> np.ndarray:
    """
    Compute absolute difference and threshold to isolate strong changes.
    Returns difference image (float64).
    """
    if img_a is None or img_b is None:
        return np.zeros((1, 1), dtype=np.float64)
    if img_a.shape != img_b.shape:
        try:
            img_b = cv2.resize(
                img_b.astype(np.float32),
                (img_a.shape[1], img_a.shape[0]),
                interpolation=cv2.INTER_LINEAR,
            ).astype(np.float64)
        except Exception:
            return np.zeros_like(img_a)
    diff = np.abs(img_a.astype(np.float64) - img_b.astype(np.float64))
    # Threshold: keep pixels above mean + factor * std
    dmean, dstd = float(np.mean(diff)), float(np.std(diff)) or 1e-10
    thresh_val = dmean + 2.0 * dstd
    _, diff_bin = cv2.threshold(
        (diff * 255).astype(np.uint8),
        min(255, max(1, int(thresh_val * 255))),
        255,
        cv2.THRESH_BINARY,
    )
    return (diff_bin.astype(np.float64) / 255.0)


def detect_sources(diff_image: np.ndarray) -> List[Dict[str, Any]]:
    """
    Use connected components / contours on diff_image to find change sources.
    Returns list of {x, y, brightness, area}.
    """
    sources: List[Dict[str, Any]] = []
    if diff_image is None or diff_image.size == 0:
        return sources
    diff_u8 = (np.clip(diff_image, 0, 1) * 255).astype(np.uint8)
    contours, _ = cv2.findContours(
        diff_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    min_area = 4
    max_area = 10000
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        M = cv2.moments(cnt)
        if M["m00"] and M["m00"] > 0:
            cx = float(M["m10"] / M["m00"])
            cy = float(M["m01"] / M["m00"])
        else:
            x, y, w, h = cv2.boundingRect(cnt)
            cx = x + w / 2.0
            cy = y + h / 2.0
        # Brightness: mean value in a small patch around centroid
        ix, iy = int(cx), int(cy)
        patch = diff_image[
            max(0, iy - 2) : min(diff_image.shape[0], iy + 3),
            max(0, ix - 2) : min(diff_image.shape[1], ix + 3),
        ]
        brightness = float(np.mean(patch)) if patch.size else 0.0
        sources.append({
            "x": cx,
            "y": cy,
            "brightness": brightness,
            "area": float(area),
        })
    return sources


def classify_change(source: Dict[str, Any]) -> Tuple[str, str]:
    """
    Classify a change source into astrophysical hint and confidence.
    Returns (classification, confidence).
    """
    brightness = float(source.get("brightness", 0) or 0)
    area = float(source.get("area", 0) or 0)
    # Very high brightness, small area → possible_supernova
    if brightness > 0.7 and area < 50:
        return "possible_supernova", "medium"
    if brightness > 0.5 and area < 30:
        return "possible_supernova", "low"
    # Moderate brightness, moderate area → possible variable
    if 0.2 < brightness < 0.7 and 20 < area < 200:
        return "possible_variable_star", "medium"
    if 0.15 < brightness < 0.6 and area < 300:
        return "possible_variable_star", "low"
    # Small, faint → often new object (appeared in new image)
    if area < 25 and brightness > 0.1:
        return "new_object", "medium"
    if area < 50:
        return "new_object", "low"
    return "unknown_change", "low"


def detect_sky_changes(
    image_a_path: Any,
    image_b_path: Any,
    metadata_a: Optional[Dict[str, Any]] = None,
    metadata_b: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Detect astronomical changes between two images of the same sky field.

    Pipeline: load → align → normalize_background → subtract → detect_sources
    → classify_change.

    Returns:
        {
            "change_count": int,
            "changes": [ { "x", "y", "brightness", "classification", "confidence" }, ... ],
            "summary": str
        }
    """
    empty: Dict[str, Any] = {
        "change_count": 0,
        "changes": [],
        "summary": "Sky change detection completed.",
    }
    try:
        path_a = Path(image_a_path) if image_a_path is not None else None
        path_b = Path(image_b_path) if image_b_path is not None else None
        if path_a is None or path_b is None or not path_a.exists() or not path_b.exists():
            log.debug("sky_change_detector: missing or invalid image paths")
            return empty
    except Exception:
        return empty

    try:
        img_a = _load_image(path_a)
        img_b = _load_image(path_b)
    except Exception as e:
        log.warning("sky_change_detector: failed to load images: %s", e)
        return empty

    if img_a is None or img_b is None or img_a.size == 0 or img_b.size == 0:
        return empty

    try:
        aligned_b = align_images(img_a, img_b)
    except Exception as e:
        log.debug("sky_change_detector: alignment failed, using unaligned: %s", e)
        aligned_b = img_b

    try:
        norm_a = normalize_background(img_a)
        norm_b = normalize_background(aligned_b)
    except Exception as e:
        log.debug("sky_change_detector: normalize_background failed: %s", e)
        norm_a = img_a
        norm_b = aligned_b

    try:
        diff = subtract_images(norm_a, norm_b)
    except Exception as e:
        log.warning("sky_change_detector: subtract_images failed: %s", e)
        return empty

    try:
        sources = detect_sources(diff)
    except Exception as e:
        log.warning("sky_change_detector: detect_sources failed: %s", e)
        return empty

    changes: List[Dict[str, Any]] = []
    for src in sources:
        try:
            classification, confidence = classify_change(src)
            changes.append({
                "x": src.get("x", 0),
                "y": src.get("y", 0),
                "brightness": src.get("brightness", 0),
                "classification": classification,
                "confidence": confidence,
            })
        except Exception:
            changes.append({
                "x": src.get("x", 0),
                "y": src.get("y", 0),
                "brightness": src.get("brightness", 0),
                "classification": "unknown_change",
                "confidence": "low",
            })

    return {
        "change_count": len(changes),
        "changes": changes,
        "summary": "Sky change detection completed.",
    }
