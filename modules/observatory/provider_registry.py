# -*- coding: utf-8 -*-
"""
AstroScan — Provider registry for real telescope / archive connectors.

Honesty-safe: each provider declares only verified capabilities.
Connection types: real_connected | archive_connected | pending_auth | manual_only | unavailable.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Connection types (do not pretend stronger support than verified)
CONNECTION_REAL = "real_connected"
CONNECTION_ARCHIVE = "archive_connected"
CONNECTION_PENDING_AUTH = "pending_auth"
CONNECTION_MANUAL = "manual_only"
CONNECTION_UNAVAILABLE = "unavailable"


def _provider(
    provider_name: str,
    connection_type: str,
    supports_archive_fetch: bool,
    supports_observation_request: bool,
    supports_status_polling: bool,
    supports_result_download: bool,
    notes: str = "",
) -> Dict[str, Any]:
    return {
        "provider_name": provider_name,
        "connection_type": connection_type,
        "supports_archive_fetch": supports_archive_fetch,
        "supports_observation_request": supports_observation_request,
        "supports_status_polling": supports_status_polling,
        "supports_result_download": supports_result_download,
        "notes": notes,
    }


def get_registry() -> List[Dict[str, Any]]:
    """
    Return the list of registered telescope/archive providers with honest capability flags.

    - LCO: public archive API verified → archive_connected.
    - NOIRLab: public Astro Data Archive search → archive_connected (dataset/archive only).
    - Skynet: no verified public programmatic flow → pending_auth.
    - MicroObservatory: no verified stable public API → manual_only.
    """
    return [
        _provider(
            provider_name="LCO",
            connection_type=CONNECTION_ARCHIVE,
            supports_archive_fetch=True,
            supports_observation_request=False,
            supports_status_polling=False,
            supports_result_download=True,
            notes="Las Cumbres Observatory; public archive API for frames. Observation request requires authenticated LCO API.",
        ),
        _provider(
            provider_name="NOIRLab",
            connection_type=CONNECTION_ARCHIVE,
            supports_archive_fetch=True,
            supports_observation_request=False,
            supports_status_polling=False,
            supports_result_download=True,
            notes="NOIRLab Astro Data Archive; dataset/archive search only. No direct telescope tasking via this API.",
        ),
        _provider(
            provider_name="Skynet",
            connection_type=CONNECTION_PENDING_AUTH,
            supports_archive_fetch=False,
            supports_observation_request=False,
            supports_status_polling=False,
            supports_result_download=False,
            notes="Skynet integration requires authenticated or undocumented workflow confirmation.",
        ),
        _provider(
            provider_name="MicroObservatory",
            connection_type=CONNECTION_MANUAL,
            supports_archive_fetch=False,
            supports_observation_request=False,
            supports_status_polling=False,
            supports_result_download=False,
            notes="No verified stable public API found; manual workflow required.",
        ),
    ]


def get_provider(provider_name: str) -> Dict[str, Any] | None:
    """Return the registry entry for the given provider name, or None."""
    name = (provider_name or "").strip().upper()
    for p in get_registry():
        if (p.get("provider_name") or "").strip().upper() == name:
            return p
    return None
