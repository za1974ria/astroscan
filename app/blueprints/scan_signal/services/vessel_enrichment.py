"""SCAN A SIGNAL — vessel enrichment helpers.

Self-contained helpers used by VesselService to enrich a raw AIS
PositionReport / ShipStaticData payload with:

  • Flag (pavillon) decoded from the MMSI MID prefix (ITU table)
  • Sea/ocean zone via static bbox lookup
  • Destination port / country via static port table
  • Human-readable tracking duration

All data sources are local JSON dictionaries — no network calls,
no third-party dependencies, no recurring cost.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")


def _load_json(name: str, fallback):
    path = os.path.join(_DATA_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("[vessel_enrichment] failed to load %s: %s", name, exc)
        return fallback


MID_COUNTRY: dict[str, dict[str, str]] = _load_json("mid_country.json", {})
SEA_ZONES: list[dict[str, Any]] = _load_json("sea_zones.json", [])
MAJOR_PORTS: dict[str, dict[str, str]] = _load_json("major_ports.json", {})
INLAND_WATERWAYS: list[dict[str, Any]] = _load_json("inland_waterways.json", [])


# Reverse index: ISO country code -> first MID entry that uses it (so we can
# look up flag/name from a destination country code).
_ISO_TO_COUNTRY: dict[str, dict[str, str]] = {}
for _mid, _info in MID_COUNTRY.items():
    iso = (_info or {}).get("iso")
    if iso and iso not in _ISO_TO_COUNTRY:
        _ISO_TO_COUNTRY[iso] = _info


# ------------------------------------------------------------------
# Pavillon / flag state
# ------------------------------------------------------------------

def mid_to_country(mmsi) -> dict[str, str] | None:
    """Return {iso, name_fr, name_en, flag} for the given MMSI, or None.

    The first three digits of an MMSI are the Maritime Identification
    Digit (MID), assigned by ITU per country.
    """
    if mmsi is None:
        return None
    s = str(mmsi).strip()
    if len(s) < 3 or not s[:3].isdigit():
        return None
    info = MID_COUNTRY.get(s[:3])
    if not info:
        return None
    return {
        "iso": info.get("iso"),
        "name_fr": info.get("fr"),
        "name_en": info.get("en"),
        "flag": info.get("flag"),
    }


def country_by_iso(iso_code: str) -> dict[str, str] | None:
    """Reverse lookup: ISO-2 country code → {iso, name_fr, name_en, flag}."""
    if not iso_code:
        return None
    info = _ISO_TO_COUNTRY.get(iso_code.upper())
    if not info:
        return None
    return {
        "iso": info.get("iso"),
        "name_fr": info.get("fr"),
        "name_en": info.get("en"),
        "flag": info.get("flag"),
    }


# ------------------------------------------------------------------
# Sea / ocean reverse geocoding
# ------------------------------------------------------------------

def geocode_sea_zone(lat, lon, lang: str = "fr") -> str | None:
    """Return the human-readable name of the sea/ocean for (lat, lon).

    Walks the ordered SEA_ZONES list (specific seas first, broad oceans
    last) and returns the first bbox match. None if no zone matches.
    """
    try:
        flat = float(lat)
        flon = float(lon)
    except (TypeError, ValueError):
        return None

    key = "name_fr" if lang == "fr" else "name_en"
    for zone in SEA_ZONES:
        bbox = zone.get("bbox")
        if not bbox or len(bbox) != 2:
            continue
        try:
            (lat_min, lon_min), (lat_max, lon_max) = bbox
        except (ValueError, TypeError):
            continue
        if lat_min <= flat <= lat_max and lon_min <= flon <= lon_max:
            return zone.get(key) or zone.get("name_en") or zone.get("name_fr")
    return None


# ------------------------------------------------------------------
# Inland waterway detection
# ------------------------------------------------------------------

def detect_inland_waterway(lat, lon, lang: str = "fr") -> dict[str, Any] | None:
    """Return inland-waterway info if (lat, lon) falls in a known bbox.

    Many AIS-tracked vessels appear "on land" at zoom levels where rivers
    aren't rendered (Antwerp 65 km up the Scheldt, Hamburg 110 km up the
    Elbe, Rouen 80 km up the Seine, etc.). This helper provides an honest
    geographic disclosure: when the position falls into one of the known
    inland-port bboxes, we return a label like:

        "Port intérieur d'Anvers (Escaut, 65 km en amont)"

    The list is small (~12 entries), so a linear scan is appropriate.
    """
    if lat is None or lon is None:
        return None
    try:
        flat = float(lat)
        flon = float(lon)
    except (TypeError, ValueError):
        return None

    for zone in INLAND_WATERWAYS:
        bbox = zone.get("bbox")
        if not bbox or len(bbox) != 2:
            continue
        try:
            (lat_min, lon_min), (lat_max, lon_max) = bbox
        except (TypeError, ValueError):
            continue
        if not (lat_min <= flat <= lat_max and lon_min <= flon <= lon_max):
            continue

        river = zone.get("river_fr") if lang == "fr" else zone.get("river_en")
        port = zone.get("port_name") if lang == "fr" else zone.get("port_name_en")
        distance_km = zone.get("distance_inland_km")

        if distance_km is not None:
            if lang == "fr":
                # French elision: "de" + vowel → "d'". Aspirated H ("Hambourg",
                # "Houston") is treated like a consonant — no elision.
                first = (port or "").lstrip()[:1].lower()
                connector = "d'" if first in {"a", "e", "i", "o", "u", "y", "à", "é", "è", "ê", "â", "î", "ô", "û"} else "de "
                label = f"Port intérieur {connector}{port} ({river}, {distance_km} km en amont)"
            else:
                label = f"Inland port of {port} ({river}, {distance_km} km upstream)"
        else:
            if lang == "fr":
                label = f"Corridor {river}"
            else:
                label = f"{river} corridor"

        return {
            "id": zone.get("id"),
            "river": river,
            "port": port,
            "country_iso": zone.get("country_iso"),
            "distance_km": distance_km,
            "label": label,
        }
    return None


# ------------------------------------------------------------------
# Destination parsing
# ------------------------------------------------------------------

_INVALID_DESTINATIONS = {
    "", "TBN", "UNKNOWN", "FOR ORDERS", "SEA", "NIL", "NONE", "*",
    "N/A", "NA", "ANCHORAGE", "AT SEA", "OFFSHORE", "ORDER", "ORDERS",
    "TBA", "HIGH SEA", "HIGH SEAS", "OPEN SEA", "FISHING", "FISHING GROUND",
}


def _normalise_dest(text: str) -> str:
    s = text.strip().upper().replace("@", " ").replace("_", " ")
    # Many AIS Type 5 destinations come in the form "LOCODE >LOCODE" (e.g.
    # "NLRTM>FRMRS"). Split on common separators and keep the last token,
    # which is by convention the next port of call.
    for sep in (">", "->", " TO ", " VIA ", "/", "|", "  "):
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if parts:
                s = parts[-1]
    return " ".join(s.split())


def parse_destination(raw_dest: str | None) -> dict[str, Any] | None:
    """Parse the AIS Type 5 destination string and try to map to a port.

    Returns a dict {raw, port, country_iso} when a usable destination is
    found, or None for AIS placeholders ("TBN", "FOR ORDERS", etc.).
    """
    if not raw_dest:
        return None
    raw = raw_dest.strip()
    if not raw:
        return None

    cleaned = _normalise_dest(raw)
    if cleaned in _INVALID_DESTINATIONS:
        return None
    # Strip leading/trailing punctuation
    cleaned = cleaned.strip(".,;:!?-")
    if not cleaned or cleaned in _INVALID_DESTINATIONS:
        return None

    for port_name, info in MAJOR_PORTS.items():
        if port_name == cleaned or (
            len(port_name) >= 4 and (port_name in cleaned or cleaned in port_name)
        ):
            return {
                "raw": raw,
                "port": info.get("name_fr") or port_name.title(),
                "port_key": port_name,
                "country_iso": info.get("country_iso"),
            }

    return {"raw": raw, "port": None, "port_key": None, "country_iso": None}


# ------------------------------------------------------------------
# Duration formatting
# ------------------------------------------------------------------

def format_duration(seconds, lang: str = "fr") -> str | None:
    """Format a duration (seconds) into a compact human string."""
    if seconds is None:
        return None
    try:
        s = int(float(seconds))
    except (TypeError, ValueError):
        return None
    if s < 0:
        return None

    minutes = s // 60
    if minutes < 1:
        return "moins d'1 min" if lang == "fr" else "<1 min"
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    mins = minutes % 60
    if hours < 24:
        if lang == "fr":
            return f"{hours}h {mins:02d}min"
        return f"{hours}h {mins:02d}m"
    days = hours // 24
    h = hours % 24
    if lang == "fr":
        return f"{days}j {h}h"
    return f"{days}d {h}h"


# ------------------------------------------------------------------
# AIS sentinel value cleanup
# ------------------------------------------------------------------

def is_invalid_ais_value(value, kind: str) -> bool:
    """Return True if the AIS field carries the "not available" sentinel.

    Reference: ITU-R M.1371-5
      • TrueHeading 511     → not available
      • COG 360.0           → not available; also negative or >= 360 → invalid
      • SOG 102.3           → not available; >102.2 → invalid range
    """
    if value is None:
        return True
    try:
        v = float(value)
    except (TypeError, ValueError):
        return True

    if kind == "heading":
        # 511 is the "not available" sentinel; anything >360 is bogus
        return v == 511 or v < 0 or v > 360
    if kind == "cog":
        return v < 0 or v >= 360
    if kind == "sog":
        # 102.3 = not available; also clip negatives
        return v < 0 or v >= 102.3
    return False
