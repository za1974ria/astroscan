"""
Digital Lab — Image loader.
Loads FITS or standard images into a NumPy array (grayscale for pipeline).
"""
import numpy as np
from pathlib import Path


def load_image(source):
    """
    Load image from file path or bytes.
    source: path (str/Path) or bytes
    Returns: numpy array (2D grayscale, float64 [0,1] or uint8).
    """
    if isinstance(source, bytes):
        return _load_from_bytes(source)
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    suffix = path.suffix.lower()
    if suffix == '.fits' or suffix == '.fit':
        return _load_fits(path)
    return _load_raster(path)


def _load_from_bytes(data):
    import cv2
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("Could not decode image from bytes")
    return img.astype(np.float64) / 255.0


def _load_raster(path):
    import cv2
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not load image: {path}")
    return img.astype(np.float64) / 255.0


def _load_fits(path):
    try:
        from astropy.io import fits
    except ImportError:
        import cv2
        return _load_raster(path)
    with fits.open(path) as hdu:
        data = hdu[0].data
    if data is None:
        raise ValueError("FITS has no data")
    if data.ndim > 2:
        data = data[0] if data.shape[0] in (1, 3) else data.mean(axis=0)
    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    if data.max() > data.min():
        data = (data - data.min()) / (data.max() - data.min())
    return data.astype(np.float64)
