# Digital Lab — AstroScan image analysis pipeline

Optional dependencies for full functionality:

- **opencv-python** (cv2): image load, bilateral filter, blob detection fallback
- **numpy**: required
- **astropy**: FITS loading
- **scikit-image**: blob_log, denoise_wavelet, label, regionprops

Install: `pip install numpy opencv-python astropy scikit-image`

Pipeline: load image → reduce noise → detect stars → detect objects → compute brightness → anomaly detection → report.
