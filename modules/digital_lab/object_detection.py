"""
Digital Lab — Star and extended object detection.
Uses blob detection for stars and thresholding for extended objects.
"""
import numpy as np


def detect_stars(image, min_sigma=1, max_sigma=8, threshold=0.05):
    """
    Detect point-like sources (stars).
    Returns list of dicts: {x, y, sigma, peak}.
    """
    try:
        from skimage.feature import blob_log
    except ImportError:
        return _detect_stars_cv2(image, threshold)
    img = np.clip(image, 0, 1)
    blobs = blob_log(img, min_sigma=min_sigma, max_sigma=max_sigma, num_sigma=4, threshold=threshold)
    stars = []
    for r, c, s in blobs:
        y, x = int(r), int(c)
        if 0 <= y < image.shape[0] and 0 <= x < image.shape[1]:
            peak = float(image[y, x])
            stars.append({"x": x, "y": y, "sigma": float(s), "peak": peak})
    return stars[:500]


def _detect_stars_cv2(image, threshold):
    import cv2
    img_u8 = (np.clip(image, 0, 1) * 255).astype(np.uint8)
    params = cv2.SimpleBlobDetector_Params()
    params.minThreshold = int(threshold * 255)
    params.filterByArea = True
    params.minArea = 3
    det = cv2.SimpleBlobDetector_create(params)
    kps = det.detect(img_u8)
    stars = [{"x": int(kp.pt[0]), "y": int(kp.pt[1]), "sigma": kp.size / 2.0, "peak": float(image[int(kp.pt[1]), int(kp.pt[0])])} for kp in kps[:500]]
    return stars


def detect_objects(image, threshold=0.15, min_area=25):
    """
    Detect extended objects (regions above threshold).
    Returns list of dicts: {x, y, area, mean_brightness}.
    """
    try:
        from skimage.measure import label, regionprops
    except ImportError:
        return []
    binary = (image >= threshold).astype(np.uint8)
    labeled = label(binary)
    objects = []
    for r in regionprops(labeled):
        if r.area >= min_area and r.area < image.size // 4:
            y, x = r.centroid[0], r.centroid[1]
            mean_b = float(np.mean(image[r.slice]))
            objects.append({"x": float(x), "y": float(y), "area": int(r.area), "mean_brightness": mean_b})
    return objects[:200]
