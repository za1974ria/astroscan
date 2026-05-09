"""Aircraft enrichment helpers.

- icao24_to_country(): decode the ICAO 24-bit address country block via
  data/icao24_country_blocks.json (ranges loaded once at import).
- format_altitude / format_velocity: human strings for HUD display.
- is_invalid_aircraft_value(): defensive check on ADS-B sentinel values.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BLOCKS_PATH = os.path.join(_BASE_DIR, "data", "icao24_country_blocks.json")


@lru_cache(maxsize=1)
def _load_blocks() -> list[tuple[int, int, dict[str, str]]]:
    """Load the ICAO blocks list once. Each item: (start, end, info_dict)."""
    out: list[tuple[int, int, dict[str, str]]] = []
    try:
        with open(_BLOCKS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        log.warning("[flight_radar] icao24_country_blocks.json missing")
        return []
    for entry in raw:
        try:
            start = int(entry["start"], 16)
            end = int(entry["end"], 16)
            out.append((start, end, entry))
        except Exception:
            continue
    out.sort(key=lambda t: t[0])
    return out


def icao24_to_country(hex_addr: str | None) -> dict[str, str] | None:
    """Return {iso, name_fr, name_en, flag} or None if unknown."""
    if not hex_addr or not isinstance(hex_addr, str):
        return None
    try:
        n = int(hex_addr, 16)
    except ValueError:
        return None
    blocks = _load_blocks()
    # Linear scan is fine: ~150 entries, called per request only on the
    # selected aircraft + its rendered list.
    for start, end, entry in blocks:
        if start <= n <= end:
            return {
                "iso": entry.get("iso", ""),
                "name_fr": entry.get("name_fr", ""),
                "name_en": entry.get("name_en", entry.get("name_fr", "")),
                "flag": entry.get("flag", ""),
            }
    return None


# ----------------------------------------------------------------------
# Formatting helpers
# ----------------------------------------------------------------------

def is_invalid_aircraft_value(val: Any, kind: str = "num") -> bool:
    """OpenSky uses None for missing fields; some feeds also use 0 sentinels."""
    if val is None:
        return True
    if kind == "num":
        try:
            n = float(val)
        except (TypeError, ValueError):
            return True
        if n != n:  # NaN
            return True
    return False


def format_altitude(meters: float | None, lang: str = "fr") -> str:
    if is_invalid_aircraft_value(meters):
        return "—"
    m = float(meters)  # type: ignore[arg-type]
    fl = int(round((m * 3.28084) / 100))  # flight level (hundreds of ft)
    return f"{int(round(m)):,} m / FL{fl:03d}".replace(",", " ")


def format_velocity(m_per_s: float | None, lang: str = "fr") -> str:
    if is_invalid_aircraft_value(m_per_s):
        return "—"
    v = float(m_per_s)  # type: ignore[arg-type]
    kmh = v * 3.6
    return f"{v:.0f} m/s · {kmh:.0f} km/h"


def format_vertical_rate(m_per_s: float | None) -> str:
    if is_invalid_aircraft_value(m_per_s):
        return "—"
    ft_per_min = float(m_per_s) * 196.85  # type: ignore[arg-type]
    sign = "▲" if ft_per_min >= 0 else "▼"
    return f"{sign} {abs(ft_per_min):,.0f} ft/min".replace(",", " ")


def format_callsign(raw: str | None) -> str:
    if not raw:
        return ""
    return str(raw).strip().upper()
