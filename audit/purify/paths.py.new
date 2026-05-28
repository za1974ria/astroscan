"""Centralized runtime paths — derived from env, zero hardcoded repo root.

PHASE B.5 (2026-05-23) — Path normalization for /opt/astroscan migration.

Resolution order for each path:
    1. Dedicated env var (e.g. ASTROSCAN_DB_PATH)        — highest priority
    2. ASTROSCAN_HOME / STATION env var (legacy compat)  — base directory
    3. Fallback default _DEFAULT_STATION constant        — kept intentionally
       so this module is safe to deploy on the live system BEFORE the
       user/data migration happens.

Public attributes (all str absolute paths):
    STATION       — repo root
    DATA_DIR      — sqlite + caches + JPL ephemerides
    LOG_DIR       — application logs (RotatingFileHandler targets)
    RUNTIME_DIR   — locks, pidfiles, ephemeral state (defaults to /tmp during
                    transition for backwards-compat; can be overridden to
                    /opt/astroscan/runtime once migration is complete)
    DB_PATH       — main SQLite (archive_stellaire.db)
    MMDB_PATH     — GeoLite2 country database
    EPHEMERIS_BSP — JPL DE421 ephemerides (de421.bsp)
    TLE_DIR       — TLE active.tle/celestrak/...

Helper:
    resolve_under_station(*parts) -> str    — os.path.join(STATION, *parts)
"""
from __future__ import annotations

import os

# Default STATION = repo root, derived from this file's location.
# paths.py lives at <STATION>/app/services/paths.py → 3 levels up = STATION.
# This makes the module portable: wherever the repo is rooted, STATION
# defaults to that root (e.g. /opt/astroscan or any other path).
_DEFAULT_STATION: str = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

STATION: str = (
    os.environ.get("ASTROSCAN_HOME")
    or os.environ.get("STATION")
    or _DEFAULT_STATION
)


def resolve_under_station(*parts: str) -> str:
    """Join path components under STATION root."""
    return os.path.join(STATION, *parts)


DATA_DIR: str = (
    os.environ.get("ASTROSCAN_DATA_DIR")
    or resolve_under_station("data")
)
LOG_DIR: str = (
    os.environ.get("ASTROSCAN_LOG_DIR")
    or resolve_under_station("logs")
)
RUNTIME_DIR: str = (
    os.environ.get("ASTROSCAN_RUNTIME_DIR")
    or "/tmp"  # transition default — bridge to /opt/astroscan/runtime later
)

DB_PATH: str = (
    os.environ.get("ASTROSCAN_DB_PATH")
    or os.environ.get("DB_PATH")
    or os.path.join(DATA_DIR, "archive_stellaire.db")
)
MMDB_PATH: str = (
    os.environ.get("ASTROSCAN_MMDB_PATH")
    or os.path.join(DATA_DIR, "geoip", "GeoLite2-Country.mmdb")
)
EPHEMERIS_BSP: str = (
    os.environ.get("ASTROSCAN_EPHEMERIS_BSP")
    or resolve_under_station("de421.bsp")
)
TLE_DIR: str = (
    os.environ.get("ASTROSCAN_TLE_DIR")
    or os.path.join(DATA_DIR, "tle")
)


__all__ = [
    "DATA_DIR",
    "DB_PATH",
    "EPHEMERIS_BSP",
    "LOG_DIR",
    "MMDB_PATH",
    "RUNTIME_DIR",
    "STATION",
    "TLE_DIR",
    "resolve_under_station",
]
