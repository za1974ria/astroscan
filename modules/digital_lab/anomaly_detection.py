"""
Digital Lab — Anomaly detection (outliers, artifacts).
"""
import numpy as np


def detect_anomalies(image, stars, objects, brightness):
    """
    Flag potential anomalies: saturated pixels, too many/few sources, outliers.
    Returns dict: anomalies list + summary.
    """
    anomalies = []
    img = np.asarray(image, dtype=np.float64)
    # Saturation
    saturated = np.sum(img >= 0.99)
    if saturated > 10:
        anomalies.append({"type": "saturation", "message": f"{int(saturated)} saturated pixels", "severity": "high" if saturated > 100 else "medium"})
    # Very bright single pixels (cosmic?)
    if img.size > 0 and np.max(img) > 0.95:
        anomalies.append({"type": "hot_pixel", "message": "Very bright pixel(s) detected", "severity": "low"})
    # Source count
    n_stars = brightness.get("star_count", 0)
    if n_stars == 0 and img.size > 1000:
        anomalies.append({"type": "no_sources", "message": "No point sources detected", "severity": "medium"})
    if n_stars > 400:
        anomalies.append({"type": "crowded", "message": f"Very crowded field ({n_stars} sources)", "severity": "low"})
    return {
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
    }
