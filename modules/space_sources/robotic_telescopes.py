# -*- coding: utf-8 -*-
"""
Virtual Observatory connectors for AstroScan.
Fetches observation metadata from Las Cumbres, MicroObservatory, Skynet, NOIRLab.
Uses the real telescope connector layer; returns [] for pending/manual providers.
All functions return a list of observation dicts with standardized metadata.
"""
from __future__ import absolute_import

import logging
from typing import Any, Dict, List

from modules.observatory.real_telescope_connector import (
    fetch_recent_observations,
    get_provider,
)
from modules.observatory.provider_registry import CONNECTION_ARCHIVE

log = logging.getLogger(__name__)

# Standardized observation keys for Digital Lab (kept for backward compatibility)
OBS_KEYS = (
    "source_provider", "telescope", "instrument", "object_name", "title",
    "observation_date", "ra", "dec", "exposure_time", "filter", "image_url",
)


def _obs(
    source_provider: str,
    telescope: str = "",
    instrument: str = "",
    object_name: str = "",
    title: str = "",
    observation_date: str = "",
    ra: str = "",
    dec: str = "",
    exposure_time: str = "",
    filter_name: str = "",
    image_url: str = "",
) -> Dict[str, Any]:
    return {
        "source_provider": source_provider,
        "telescope": telescope,
        "instrument": instrument,
        "object_name": object_name,
        "title": title,
        "observation_date": observation_date,
        "ra": ra,
        "dec": dec,
        "exposure_time": exposure_time,
        "filter": filter_name,
        "image_url": image_url,
    }


def fetch_lco_observations(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Query Las Cumbres Observatory archive via connector. Returns normalized observations.
    LCO is archive_connected; data from public archive API.
    """
    return fetch_recent_observations("LCO", limit=limit)


def fetch_microobservatory_images(limit: int = 5) -> List[Dict[str, Any]]:
    """
    MicroObservatory is manual_only; no verified stable public API. Returns [] safely.
    """
    provider = get_provider("MicroObservatory")
    if provider:
        log.debug("MicroObservatory: %s — returning no observations.", provider.get("connection_type"))
    return []


def fetch_skynet_images(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Skynet is pending_auth; no verified public programmatic archive. Returns [] safely.
    """
    provider = get_provider("Skynet")
    if provider:
        log.debug("Skynet: %s — returning no observations.", provider.get("connection_type"))
    return []


def fetch_noirlab_images(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Query NOIRLab Astro Data Archive via connector. Returns normalized observations when available.
    NOIRLab is archive_connected (dataset/archive search only).
    """
    return fetch_recent_observations("NOIRLab", limit=limit)
