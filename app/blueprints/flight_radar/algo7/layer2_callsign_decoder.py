"""Layer 2 — Callsign decoder.

Maps the 3-letter ICAO callsign prefix to its carrier (Air France ICAO=AFR,
IATA=AF). Carriers come from data/airline_callsigns.json which holds 150+
major operators with hubs and country.
"""
from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_PATH = os.path.join(_BASE_DIR, "data", "airline_callsigns.json")

_CALLSIGN_RE = re.compile(r"^([A-Z]{3})\d{1,4}[A-Z]?$")


@lru_cache(maxsize=1)
def _load_carriers() -> dict[str, dict[str, Any]]:
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        log.warning("[algo7.layer2] airline_callsigns.json missing")
        return {}
    out: dict[str, dict[str, Any]] = {}
    for entry in raw:
        icao = (entry.get("icao") or "").upper().strip()
        if icao and icao not in out:
            out[icao] = entry
    return out


def decode_callsign(raw_callsign: str | None) -> dict[str, Any] | None:
    """Return carrier info or None if no recognizable carrier prefix.

    Output: {iata, icao, name_fr, name_en, country_iso, hubs:[icao,...], type}
    """
    if not raw_callsign:
        return None
    cs = raw_callsign.strip().upper()
    m = _CALLSIGN_RE.match(cs)
    if not m:
        return None
    prefix = m.group(1)
    carrier = _load_carriers().get(prefix)
    if not carrier:
        return None
    return {
        "iata": carrier.get("iata"),
        "icao": carrier.get("icao"),
        "name_fr": carrier.get("name_fr"),
        "name_en": carrier.get("name_en"),
        "country_iso": carrier.get("country_iso"),
        "hubs": list(carrier.get("hubs") or []),
        "type": carrier.get("type") or "scheduled",
    }
