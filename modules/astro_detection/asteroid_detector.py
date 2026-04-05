# -*- coding: utf-8 -*-
"""
AstroScan — Asteroid / moving-object detection.

detect_moving_objects(image1_path, image2_path) compares two consecutive
astronomical images and returns candidate moving objects.
draw_detections(image_path, detections) creates an annotated RGB image.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Tuple

import numpy as np


def _load_gray(path: Path) -> np.ndarray:
    """
    Load image from path as 2D float64 in [0,1].
    Supports FITS via astropy.io.fits and raster via OpenCV.
    """
    suffix = path.suffix.lower()
    if suffix in (".fits", ".fit"):
        try:
            from astropy.io import fits  # type: ignore
        except ImportError:
            import cv2
            img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError(f"Could not load FITS image (fallback raster): {path}")
            return (img.astype(np.float64) / 255.0)
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
    else:
        import cv2
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Could not load image: {path}")
        return (img.astype(np.float64) / 255.0)


def _align_translation(img1: np.ndarray, img2: np.ndarray) -> Tuple[np.ndarray, bool]:
    """
    Align img2 onto img1 using simple translation estimated via phase correlation.
    Returns (aligned_img2, success_flag).
    """
    import cv2

    if img1.shape != img2.shape:
        h, w = img1.shape
        img2 = cv2.resize(img2, (w, h), interpolation=cv2.INTER_LINEAR)

    try:
        shift, _ = cv2.phaseCorrelate(
            img1.astype(np.float32),
            img2.astype(np.float32),
        )
        dx, dy = shift  # x, y in float pixels
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        aligned = cv2.warpAffine(
            img2.astype(np.float32),
            M,
            (img1.shape[1], img1.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        return aligned.astype(np.float64), True
    except Exception:
        return img2, False


def detect_moving_objects(image1_path: str, image2_path: str) -> List[Dict[str, Any]]:
    """
    Detect candidate moving objects between two images.

    image1_path: older image
    image2_path: newer image
    Returns: list of {x, y, brightness, size}
    """
    import cv2

    p1 = Path(image1_path)
    p2 = Path(image2_path)
    img1 = _load_gray(p1)
    img2 = _load_gray(p2)

    # Normalize brightness
    def _norm(im: np.ndarray) -> np.ndarray:
        im = np.asarray(im, dtype=np.float64)
        vmin, vmax = float(im.min()), float(im.max())
        if vmax > vmin:
            im = (im - vmin) / (vmax - vmin)
        return np.clip(im, 0.0, 1.0)

    img1 = _norm(img1)
    img2 = _norm(img2)

    # Align images (translation only)
    img2_aligned, ok_alignment = _align_translation(img1, img2)
    if not ok_alignment:
        # If alignment clearly fails (shapes mismatch after resize), bail out
        if img1.shape != img2_aligned.shape:
            return []

    # Difference image
    diff = np.abs(img2_aligned - img1)
    diff_u8 = (np.clip(diff, 0, 1) * 255).astype(np.uint8)

    # Threshold
    thr_val = max(10, int(diff_u8.mean() + 2 * diff_u8.std()))
    _, mask = cv2.threshold(diff_u8, thr_val, 255, cv2.THRESH_BINARY)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    # Contour detection
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections: List[Dict[str, Any]] = []
    if not contours:
        return detections

    # Filter by size and brightness
    min_area = 5
    max_area = 500  # avoid huge artifacts
    img2_float = img2_aligned.astype(np.float64)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        cx = int(x + w / 2)
        cy = int(y + h / 2)

        # Local brightness in newer image
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(img2_float.shape[1], x + w)
        y1 = min(img2_float.shape[0], y + h)
        patch = img2_float[y0:y1, x0:x1]
        if patch.size == 0:
            continue
        brightness = float(patch.mean())
        if brightness < 0.1:  # discard very faint
            continue

        detections.append(
            {
                "x": int(cx),
                "y": int(cy),
                "brightness": brightness,
                "size": int(area),
            }
        )

    return detections


def draw_detections(image_path: str, detections: List[Dict[str, Any]]) -> np.ndarray:
    """
    Draw simple markers on image_path for given detections.
    Returns an RGB image (numpy array uint8).
    """
    import cv2

    p = Path(image_path)
    img = None
    if p.suffix.lower() in (".fits", ".fit"):
        # Render FITS as grayscale then convert to BGR for annotations
        gray = _load_gray(p)
        img_u8 = (np.clip(gray, 0, 1) * 255).astype(np.uint8)
        img = cv2.cvtColor(img_u8, cv2.COLOR_GRAY2BGR)
    else:
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Could not load image for drawing: {image_path}")

    color = (0, 255, 0)  # bright green
    for det in detections:
        cx = int(det.get("x", 0))
        cy = int(det.get("y", 0))
        size = max(3, int(det.get("size", 5) ** 0.5))
        cv2.circle(img, (cx, cy), size, color, 1)
        cv2.circle(img, (cx, cy), 1, color, -1)

    return img

