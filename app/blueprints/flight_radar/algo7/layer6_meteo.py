"""Layer 6 — Jet stream tailwind score.

Lightweight empirical model: at cruise altitude (FL250+) over mid-latitudes
of the northern hemisphere, the jet stream blows roughly W→E with mean
~70 kts core, weaker poleward and equatorward. Southern hemisphere jets
behave similarly.

We don't fetch live GFS here (the existing aurores module handles that
asynchronously). The score is purely directional: aircraft heading aligned
with the jet → high tailwind score; cross-stream → neutral; against jet
→ low score. Plug in a real GFS reading later by overriding
`get_jet_stream_vector()`.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any

log = logging.getLogger(__name__)


def get_jet_stream_vector(lat: float, lon: float, altitude_m: float | None) -> dict[str, Any]:
    """Return {u_wind_kts, v_wind_kts, vector_deg, magnitude_kts, source}.

    Empirical model (no HTTP). Negative latitude flips the meridional sign.
    Above FL250 the wind grows; below it we return a much weaker estimate.
    """
    if altitude_m is None or altitude_m < 7000:
        return {
            "u_wind_kts": 10.0,
            "v_wind_kts": 0.0,
            "vector_deg": 90.0,
            "magnitude_kts": 10.0,
            "source": "empirical_lowlevel",
        }
    fl = (altitude_m * 3.28084) / 100.0
    # Magnitude peaks near 30-50° latitude, FL340-FL400.
    abs_lat = abs(lat)
    lat_factor = max(0.0, math.cos(math.radians((abs_lat - 40) * 3))) if abs_lat < 60 else 0.4
    alt_factor = min(1.0, (fl - 250) / 100.0)
    magnitude = 70.0 * lat_factor * alt_factor + 15.0  # 15-85 kts
    # Direction: westerly (90°) in NH mid-latitudes, with seasonal-agnostic
    # shift toward the equator over oceans (we approximate with longitude).
    u = magnitude
    v = 0.0
    if lat < 0:
        # Southern hemisphere: still westerly but slight northerly component.
        v = -3.0
    return {
        "u_wind_kts": round(u, 1),
        "v_wind_kts": round(v, 1),
        "vector_deg": 90.0,  # blowing toward the east
        "magnitude_kts": round(magnitude, 1),
        "source": "empirical_jetmodel",
    }


def tailwind_for_heading(jet: dict[str, Any], heading_deg: float | None) -> float:
    """Returns tailwind component in knots (positive = with the jet)."""
    if heading_deg is None:
        return 0.0
    # Aircraft motion vector
    h_rad = math.radians(float(heading_deg))
    ax, ay = math.sin(h_rad), math.cos(h_rad)
    # Jet vector — vector_deg is the direction the wind blows toward.
    j_rad = math.radians(float(jet.get("vector_deg") or 90))
    jx, jy = math.sin(j_rad), math.cos(j_rad)
    mag = float(jet.get("magnitude_kts") or 0)
    return mag * (ax * jx + ay * jy)


def score_jet_alignment(
    lat: float,
    lon: float,
    altitude_m: float | None,
    heading_deg: float | None,
) -> dict[str, Any]:
    """Return {score, tailwind_kts, jet}.

    Score 0..1: 1 = strong tailwind (>60 kts), 0.5 = no jet effect,
    0 = strong headwind. Aircraft heading determines sign.
    """
    jet = get_jet_stream_vector(lat, lon, altitude_m)
    tw = tailwind_for_heading(jet, heading_deg)
    # Map -80..+80 kts → 0..1
    score = max(0.0, min(1.0, 0.5 + tw / 160.0))
    return {
        "score": round(score, 3),
        "tailwind_kts": round(tw, 1),
        "jet": jet,
    }
