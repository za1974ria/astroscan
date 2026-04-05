# -*- coding: utf-8 -*-
"""
AstroScan — Real Telescope Connector layer.

Normalized interface to telescope/archive providers. Honesty-safe: only
verified capabilities are exposed; unsupported flows return supported=false.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from modules.observatory.provider_registry import (
    get_registry,
    get_provider,
    CONNECTION_ARCHIVE,
    CONNECTION_PENDING_AUTH,
    CONNECTION_MANUAL,
)

log = logging.getLogger(__name__)

_USER_AGENT = "AstroScan-VO/1.0"

# Normalized observation keys (aligned with robotic_telescopes.OBS_KEYS)
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


# ---------------------------------------------------------------------------
# LCO — archive_connected (public archive API verified)
# ---------------------------------------------------------------------------

def _fetch_lco_recent(limit: int) -> List[Dict[str, Any]]:
    """Fetch recent observations from LCO archive. Returns normalized list."""
    out: List[Dict[str, Any]] = []
    try:
        import urllib.request
        url = "https://archive-api.lco.global/frames/?limit=%d&format=json" % limit
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("results") or []
        for frame in results:
            try:
                url_val = frame.get("url") or ""
                version_set = frame.get("version_set") or []
                if not url_val and version_set:
                    url_val = (version_set[0].get("url") or "") if version_set else ""
                if not url_val:
                    continue
                obs_date = frame.get("observation_date") or frame.get("DATE_OBS") or ""
                if isinstance(obs_date, str) and "T" in obs_date:
                    obs_date = obs_date.split("T")[0]
                target = (frame.get("target_name") or frame.get("OBJECT") or "").strip()
                instrument_id = (frame.get("instrument_id") or frame.get("INSTRUME") or "").strip()
                telescope_id = (frame.get("telescope_id") or frame.get("TELID") or "").strip()
                site_id = (frame.get("site_id") or frame.get("SITEID") or "").strip()
                exp = frame.get("exposure_time") or frame.get("EXPTIME")
                exp_str = str(exp) if exp is not None else ""
                filt = (frame.get("primary_optical_element") or frame.get("FILTER") or "").strip()
                ra_str = ""
                dec_str = ""
                area = frame.get("area")
                if isinstance(area, dict) and area.get("type") == "Polygon":
                    coords = area.get("coordinates", [[]])[0]
                    if coords:
                        ra_str = str(coords[0][0])
                        dec_str = str(coords[0][1])
                out.append(_obs(
                    source_provider="LCO",
                    telescope="LCO %s %s" % (site_id, telescope_id),
                    instrument=instrument_id or "LCO imager",
                    object_name=target or "LCO observation",
                    title=target or "LCO observation",
                    observation_date=obs_date,
                    ra=ra_str,
                    dec=dec_str,
                    exposure_time=exp_str,
                    filter_name=filt,
                    image_url=url_val,
                ))
            except Exception:
                continue
    except Exception as e:
        log.debug("LCO archive fetch failed: %s", e)
    return out


# ---------------------------------------------------------------------------
# NOIRLab — archive_connected (public Astro Data Archive; dataset/archive only)
# ---------------------------------------------------------------------------

def _fetch_noirlab_recent(limit: int) -> List[Dict[str, Any]]:
    """Fetch recent/recently available observations from NOIRLab Astro Data Archive when public API allows."""
    out: List[Dict[str, Any]] = []
    try:
        import urllib.request
        # Public archive search; exact endpoint may vary by NOIRLab API version
        url = "https://astroarchive.noirlab.edu/api/search?limit=%d" % limit
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("results") or data.get("data") or data.get("records") or []
        if not isinstance(results, list):
            results = []
        for item in results[:limit]:
            try:
                img_url = item.get("url") or item.get("access_url") or item.get("image_url") or ""
                if not img_url:
                    continue
                out.append(_obs(
                    source_provider="NOIRLab",
                    telescope=item.get("telescope") or "NOIRLab",
                    instrument=item.get("instrument") or item.get("instrument_name") or "NOIRLab",
                    object_name=item.get("object_name") or item.get("target") or "NOIRLab observation",
                    title=item.get("title") or item.get("name") or "NOIRLab",
                    observation_date=item.get("observation_date") or item.get("date") or "",
                    ra=str(item.get("ra", "")),
                    dec=str(item.get("dec", "")),
                    exposure_time=str(item.get("exposure_time", "")),
                    filter_name=str(item.get("filter", "")),
                    image_url=img_url,
                ))
            except Exception:
                continue
    except Exception as e:
        log.debug("NOIRLab archive fetch failed: %s", e)
    return out


# ---------------------------------------------------------------------------
# Skynet (pending_auth) and MicroObservatory (manual_only): no archive/request
# implemented; _unsupported_reason() returns clear message for request/status/download.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_provider_status() -> List[Dict[str, Any]]:
    """Return list of provider status dicts (from registry)."""
    return list(get_registry())


def fetch_recent_observations(provider_name: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch recent observations from the given provider. Returns normalized list.
    For pending_auth / manual_only / unavailable providers, returns [] (no fake data).
    """
    name = (provider_name or "").strip().upper()
    if not name:
        return []
    provider = get_provider(name)
    if not provider:
        return []
    if provider.get("connection_type") != CONNECTION_ARCHIVE:
        log.debug("Provider %s not archive_connected; skipping fetch.", name)
        return []
    if name == "LCO":
        return _fetch_lco_recent(limit)
    if name == "NOIRLAB":
        return _fetch_noirlab_recent(limit)
    return []


def _unsupported_reason(provider_name: str, default: str = "pending auth or no verified public submission API") -> str:
    """Return a clear reason when an operation is not supported for this provider."""
    name = (provider_name or "").strip().upper()
    if name == "SKYNET":
        return "Skynet integration requires authenticated or undocumented workflow confirmation"
    if name == "MICROOBSERVATORY":
        return "No verified stable public API found; manual workflow required"
    return default


def request_observation(
    provider_name: str,
    target: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Request an observation from the provider. Only active when provider has
    verified observation request support; otherwise returns supported=false.
    """
    name = (provider_name or "").strip().upper()
    provider = get_provider(name) if name else None
    if not provider or not provider.get("supports_observation_request"):
        return {"supported": False, "reason": _unsupported_reason(name)}
    # Future: real implementation for real_connected providers
    return {"supported": False, "reason": "Observation request not implemented for this provider."}


def fetch_observation_status(provider_name: str, job_id: str) -> Dict[str, Any]:
    """Poll observation status. Only supported when provider has verified status polling."""
    name = (provider_name or "").strip().upper()
    provider = get_provider(name) if name else None
    if not provider or not provider.get("supports_status_polling"):
        return {"supported": False, "reason": _unsupported_reason(name)}
    return {"supported": False, "reason": "Status polling not implemented for this provider."}


def fetch_result_images(provider_name: str, job_id: str) -> Dict[str, Any]:
    """Fetch result images for a job. Only supported when provider supports result_download for jobs."""
    name = (provider_name or "").strip().upper()
    provider = get_provider(name) if name else None
    if not provider or not provider.get("supports_result_download"):
        return {"supported": False, "reason": _unsupported_reason(name)}
    # Archive download is separate (fetch_recent_observations returns image_url); job-based download not implemented
    return {"supported": False, "reason": "Job-based result download not implemented for this provider."}


def get_observatory_status() -> Dict[str, Any]:
    """
    Return status structure for display: providers list (name, connection_type,
    supports_archive_fetch, supports_observation_request, notes) and summary.
    """
    providers = []
    for p in get_registry():
        providers.append({
            "provider_name": p.get("provider_name", ""),
            "connection_type": p.get("connection_type", "unavailable"),
            "supports_archive_fetch": bool(p.get("supports_archive_fetch")),
            "supports_observation_request": bool(p.get("supports_observation_request")),
            "notes": p.get("notes", ""),
        })
    summary = "Real telescope connector: LCO and NOIRLab archive-connected; Skynet pending auth; MicroObservatory manual-only."
    return {"providers": providers, "summary": summary}
