# Space sources — telescope image collectors for AstroScan Digital Lab
from .telescope_downloader import (
    run_telescope_collector,
    download_hubble_images,
    download_jwst_images,
    download_eso_images,
)

__all__ = [
    "run_telescope_collector",
    "download_hubble_images",
    "download_jwst_images",
    "download_eso_images",
]
