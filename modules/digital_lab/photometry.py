"""
Digital Lab — Simple photometry (brightness metrics).
"""
import numpy as np


def compute_brightness(image, stars, objects):
    """
    Compute brightness metrics for image and detected sources.
    stars, objects: lists from object_detection
    Returns dict: global stats + per-source metrics.
    """
    img = np.asarray(image, dtype=np.float64)
    global_mean = float(np.mean(img))
    global_std = float(np.std(img)) if img.size > 0 else 0.0
    global_max = float(np.max(img))
    # Star fluxes (sum in small aperture)
    aperture_r = 3
    star_fluxes = []
    h, w = img.shape
    for s in stars:
        x, y = int(s["x"]), int(s["y"])
        y0, y1 = max(0, y - aperture_r), min(h, y + aperture_r + 1)
        x0, x1 = max(0, x - aperture_r), min(w, x + aperture_r + 1)
        patch = img[y0:y1, x0:x1]
        star_fluxes.append(float(np.sum(patch)))
    object_fluxes = [float(o["mean_brightness"] * o["area"]) for o in objects]
    return {
        "global_mean": global_mean,
        "global_std": global_std,
        "global_max": global_max,
        "star_count": len(stars),
        "object_count": len(objects),
        "star_fluxes": star_fluxes[:50],
        "object_fluxes": object_fluxes[:30],
        "mean_star_flux": float(np.mean(star_fluxes)) if star_fluxes else 0.0,
        "mean_object_flux": float(np.mean(object_fluxes)) if object_fluxes else 0.0,
    }
