"""Ground Assets Network — flagship public-facing module.

A live map of ASTRO-SCAN's distributed ground assets:
  - 12 partner observatories (real GPS coordinates, day/night status)
  - 3 mobile field missions (deterministic great-circle simulation)
  - 2 stratospheric balloons (ascent / float / burst / descent)
  - antenna links + RSSI between observatories and tracked assets

Created 2026-05-05 (Phase 2C).
"""
from app.blueprints.ground_assets.routes import ground_assets_bp

__all__ = ["ground_assets_bp"]
