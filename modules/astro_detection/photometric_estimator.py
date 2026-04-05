# -*- coding: utf-8 -*-
"""
AstroScan — Photometric Estimator.

Estimates approximate astronomical magnitudes for detected sources
using simple aperture photometry. Enriches MPC reports and other
downstream modules with magnitude_estimate.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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


def _load_image_as_float(image_path: Path) -> Optional[np.ndarray]:
    """Load image from path as 2D float64 array (normalized). Returns None on failure."""
    if not image_path or not Path(image_path).exists():
        return None
    path = Path(image_path)
    suffix = path.suffix.lower()
    if suffix in (".fits", ".fit") and _HAS_ASTROPY:
        try:
            with fits.open(path) as hdul:
                data = hdul[0].data
            if data is None:
                return None
            if data.ndim > 2:
                data = data[0] if data.shape[0] in (1, 3) else data.mean(axis=0)
            data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
            dmin, dmax = float(data.min()), float(data.max())
            if dmax > dmin:
                data = (data - dmin) / (dmax - dmin)
            return data.astype(np.float64)
        except Exception as e:
            log.debug("photometric_estimator: FITS load failed: %s", e)
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return (img.astype(np.float64) / 255.0)


def estimate_flux(
    image: np.ndarray,
    x: float,
    y: float,
    radius: int = 5,
) -> Optional[float]:
    """
    Estimate flux at (x, y) using a circular aperture and local background subtraction.

    1. Extract circular aperture (pixels within radius of center).
    2. Sum pixel values in aperture.
    3. Subtract local background (median in annulus or outer region).

    Returns flux value, or None if invalid.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        return None
    h, w = image.shape
    ix, iy = int(round(x)), int(round(y))
    r = max(1, min(int(radius), min(h, w) // 2 - 1))
    r_out = min(r + 6, min(h, w) // 2)
    # Bounds for aperture + annulus (need extra margin for background)
    y0 = max(0, iy - r_out)
    y1 = min(h, iy + r_out + 1)
    x0 = max(0, ix - r_out)
    x1 = min(w, ix + r_out + 1)
    if y1 <= y0 or x1 <= x0:
        return None
    yy, xx = np.ogrid[y0:y1, x0:x1]
    cy, cx = iy - y0, ix - x0
    dist_sq = (yy - cy) ** 2 + (xx - cx) ** 2
    aperture = dist_sq <= (r * r)
    if not np.any(aperture):
        return None
    aperture_sum = np.sum(image[y0:y1, x0:x1][aperture])
    n_aperture = np.sum(aperture)
    r_in = r + 1
    annulus = (dist_sq >= r_in * r_in) & (dist_sq <= r_out * r_out)
    if np.any(annulus):
        bg_median = float(np.median(image[y0:y1, x0:x1][annulus]))
        background = bg_median * n_aperture
    else:
        background = 0.0
    flux = float(aperture_sum - background)
    return flux if flux > 0 else None


def flux_to_magnitude(flux: Optional[float]) -> Optional[float]:
    """
    Convert flux to approximate magnitude: mag = -2.5 * log10(flux).

    Returns None if flux is None or <= 0.
    """
    if flux is None or flux <= 0:
        return None
    try:
        return -2.5 * math.log10(flux)
    except (ValueError, ZeroDivisionError):
        return None


def estimate_magnitude(
    image_path: Any,
    x: float,
    y: float,
    radius: int = 5,
) -> Dict[str, Any]:
    """
    Estimate approximate magnitude for a source at (x, y) in the image.

    Loads image, runs aperture flux estimation, converts to magnitude.
    Safe structure on missing image, invalid coordinates, or flux <= 0.

    Returns:
        {
            "flux": float | None,
            "magnitude_estimate": float | None,
            "method": "simple_aperture",
            "confidence": "low" | "medium"
        }
    """
    empty: Dict[str, Any] = {
        "flux": None,
        "magnitude_estimate": None,
        "method": "simple_aperture",
        "confidence": "low",
    }
    path = Path(image_path) if image_path is not None else None
    if path is None or not path.exists():
        log.debug("photometric_estimator: missing or invalid image path")
        return empty
    try:
        img = _load_image_as_float(path)
    except Exception as e:
        log.debug("photometric_estimator: load failed: %s", e)
        return empty
    if img is None or img.size == 0:
        return empty
    h, w = img.shape
    try:
        x_f = float(x)
        y_f = float(y)
    except (TypeError, ValueError):
        return empty
    if x_f < 0 or x_f >= w or y_f < 0 or y_f >= h:
        log.debug("photometric_estimator: coordinates out of bounds")
        return empty
    flux = estimate_flux(img, x_f, y_f, radius=radius)
    if flux is None or flux <= 0:
        return empty
    mag = flux_to_magnitude(flux)
    confidence = "medium" if (flux > 0 and mag is not None) else "low"
    return {
        "flux": flux,
        "magnitude_estimate": mag,
        "method": "simple_aperture",
        "confidence": confidence,
    }
