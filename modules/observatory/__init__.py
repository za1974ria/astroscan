# -*- coding: utf-8 -*-
"""AstroScan observatory layer: provider registry and real telescope connector."""

from modules.observatory.provider_registry import get_registry, get_provider
from modules.observatory.real_telescope_connector import (
    list_provider_status,
    fetch_recent_observations,
    request_observation,
    fetch_observation_status,
    fetch_result_images,
    get_observatory_status,
)

__all__ = [
    "get_registry",
    "get_provider",
    "list_provider_status",
    "fetch_recent_observations",
    "request_observation",
    "fetch_observation_status",
    "fetch_result_images",
    "get_observatory_status",
]
