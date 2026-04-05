"""
Encapsulation défensive des imports orbitaux (sgp4, skyfield).
Évite les imports globaux lourds ; retourne None si indisponible.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Tuple, TypeVar

T = TypeVar("T")


def try_sgp4_api() -> Tuple[Optional[Any], Optional[Any]]:
    try:
        from sgp4.api import Satrec, jday

        return Satrec, jday
    except Exception:
        return None, None


def try_skyfield_earth_satellite():
    try:
        from skyfield.api import EarthSatellite, load, wgs84

        return EarthSatellite, load, wgs84
    except Exception:
        return None, None, None


def with_fallback(
    primary: Callable[[], T],
    fallback: Callable[[], T],
) -> T:
    try:
        return primary()
    except Exception:
        return fallback()
