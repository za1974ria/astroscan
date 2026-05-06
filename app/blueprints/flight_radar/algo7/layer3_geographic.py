"""Layer 3 — Geographic coherence.

Scores how well a destination candidate fits the carrier's known network
(country + hubs) and the aircraft's current heading.
"""
from __future__ import annotations

from typing import Any

from app.blueprints.flight_radar.algo7.layer7_projection import (
    haversine_km,
    initial_bearing_deg,
)


def score_geographic_coherence(
    carrier: dict[str, Any] | None,
    candidate_airport: dict[str, Any],
    current_lat: float,
    current_lon: float,
    heading_deg: float | None,
) -> float:
    """Return 0..1 coherence score for (carrier, candidate)."""
    score = 0.4  # neutral baseline

    if carrier:
        cc = (carrier.get("country_iso") or "").upper()
        if cc and candidate_airport.get("country_iso") == cc:
            score += 0.20  # destination is in carrier home country
        hubs = [h.upper() for h in (carrier.get("hubs") or [])]
        if hubs and candidate_airport.get("icao") in hubs:
            score += 0.30  # destination is a known hub

    # Heading alignment with the candidate bearing.
    if heading_deg is not None:
        bearing = initial_bearing_deg(
            current_lat, current_lon,
            candidate_airport["lat"], candidate_airport["lon"],
        )
        diff = abs(((bearing - heading_deg + 540.0) % 360.0) - 180.0)
        # 0° → +0.20 ; 90° → 0.0
        score += max(0.0, 0.20 * (1 - diff / 90.0))

    return max(0.0, min(1.0, score))


def score_carrier_network_global(
    carrier: dict[str, Any] | None,
    current_lat: float,
    current_lon: float,
) -> float:
    """Score the carrier's likelihood of operating *here*, regardless of dest.

    Used as the layer's overall confidence input even when no candidate
    is being evaluated yet. 0..1.
    """
    if not carrier:
        return 0.0
    cc = (carrier.get("country_iso") or "").upper()
    hubs = list(carrier.get("hubs") or [])
    # Without an airports DB lookup here we use a coarse heuristic: long-haul
    # carriers operate worldwide, regional carriers stay close to home. We
    # don't know coordinates of hubs in this layer, so we just say "carrier
    # known" → 0.7.
    return 0.7 if (cc or hubs) else 0.0
