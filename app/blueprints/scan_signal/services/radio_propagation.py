"""Radio propagation math for SCAN A SIGNAL.

Pure functions, no dependencies beyond stdlib math.

References:
  - Friis transmission equation (free space path loss)
  - Spherical Earth elevation angle from observer to satellite
"""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance using Haversine formula. Returns km."""
    r1 = math.radians(lat1)
    r2 = math.radians(lat2)
    dr = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dr / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dl / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_KM * c


def free_space_path_loss_db(distance_km: float, freq_mhz: float) -> float:
    """Free space path loss (Friis).
    FSPL(dB) = 20·log10(d_km) + 20·log10(f_MHz) + 32.45
    """
    if distance_km <= 0 or freq_mhz <= 0:
        return 0.0
    return 20.0 * math.log10(distance_km) + 20.0 * math.log10(freq_mhz) + 32.45


def rssi_estimate_dbm(distance_km: float, freq_mhz: float, tx_power_dbm: float = 20.0) -> float:
    """Received signal strength estimate (clamped to a realistic range)."""
    fspl = free_space_path_loss_db(distance_km, freq_mhz)
    rssi = tx_power_dbm - fspl
    return max(-130.0, min(-30.0, rssi))


def satellite_elevation_deg(
    obs_lat: float,
    obs_lon: float,
    obs_alt_m: float,
    sat_lat: float,
    sat_lon: float,
    sat_alt_m: float,
) -> float:
    """Elevation angle (deg) of a satellite seen from an observer.

    Spherical-Earth geometry — accounts for the curvature drop
    of the satellite below the local horizon as ground distance grows.
    Negative values mean below the horizon.
    """
    distance_ground_km = haversine_km(obs_lat, obs_lon, sat_lat, sat_lon)
    height_diff_km = (sat_alt_m - obs_alt_m) / 1000.0

    central_angle_rad = distance_ground_km / EARTH_RADIUS_KM
    apparent_height_km = (
        height_diff_km - EARTH_RADIUS_KM * (1.0 - math.cos(central_angle_rad))
    )

    if distance_ground_km <= 1e-6:
        return 90.0

    elevation_rad = math.atan2(apparent_height_km, distance_ground_km)
    return math.degrees(elevation_rad)


def slant_range_km(
    obs_lat: float,
    obs_lon: float,
    obs_alt_m: float,
    sat_lat: float,
    sat_lon: float,
    sat_alt_m: float,
) -> float:
    """3-D line-of-sight distance (km) between observer and satellite,
    using a spherical-Earth law of cosines."""
    r_obs = EARTH_RADIUS_KM + obs_alt_m / 1000.0
    r_sat = EARTH_RADIUS_KM + sat_alt_m / 1000.0
    central_rad = haversine_km(obs_lat, obs_lon, sat_lat, sat_lon) / EARTH_RADIUS_KM
    return math.sqrt(
        r_obs * r_obs + r_sat * r_sat - 2.0 * r_obs * r_sat * math.cos(central_rad)
    )
