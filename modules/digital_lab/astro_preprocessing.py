"""
Digital Lab — Astronomical image preprocessing.
Noise reduction and normalization for star/object detection.
"""
import numpy as np


def reduce_noise(image):
    """
    Reduce noise while preserving edges (e.g. Gaussian or bilateral).
    image: 2D float array [0,1]
    Returns: 2D float array
    """
    try:
        import cv2
    except ImportError:
        return _denoise_skimage(image)
    img_u8 = (np.clip(image, 0, 1) * 255).astype(np.uint8)
    denoised = cv2.bilateralFilter(img_u8, 5, 50, 50)
    return denoised.astype(np.float64) / 255.0


def _denoise_skimage(image):
    try:
        from skimage.restoration import denoise_wavelet
    except ImportError:
        return image
    out = denoise_wavelet(np.clip(image, 0, 1), channel_axis=None, rescale_sigma=True)
    return np.clip(out, 0, 1).astype(np.float64)


def normalize(image):
    """Normalize to [0, 1]."""
    im = np.asarray(image, dtype=np.float64)
    if im.max() > im.min():
        im = (im - im.min()) / (im.max() - im.min())
    return np.clip(im, 0, 1)
