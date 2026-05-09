"""ALGO-7 destination engine — combines the 7 layers."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from typing import Any

from app.blueprints.flight_radar.algo7.layer1_flight_plan import fetch_flight_plan
from app.blueprints.flight_radar.algo7.layer2_callsign_decoder import decode_callsign
from app.blueprints.flight_radar.algo7.layer3_geographic import (
    score_carrier_network_global,
    score_geographic_coherence,
)
from app.blueprints.flight_radar.algo7.layer4_aircraft_type import (
    decode_aircraft_type,
    is_destination_compatible,
    score_destination_for_type,
)
from app.blueprints.flight_radar.algo7.layer5_corridors import (
    detect_corridor,
    score_destination_in_corridor,
)
from app.blueprints.flight_radar.algo7.layer6_meteo import score_jet_alignment
from app.blueprints.flight_radar.algo7.layer7_projection import (
    find_candidate_airports,
    haversine_km,
)

log = logging.getLogger(__name__)


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AIRPORTS_PATH = os.path.join(_BASE_DIR, "data", "airports_geo.json")


@lru_cache(maxsize=1)
def _airports_index() -> dict[str, dict[str, Any]]:
    try:
        with open(_AIRPORTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    out = {}
    for ap in data:
        if "icao" in ap:
            out[ap["icao"].upper()] = ap
    return out


@dataclass
class Algo7Result:
    confidence_global: float
    level_used: int
    primary_destination: dict[str, Any] | None
    alternatives: list[dict[str, Any]]
    layer_results: dict[str, Any]
    sources: list[str]
    progress_pct: float | None
    aircraft_origin: dict[str, Any] | None = None
    departure_airport: dict[str, Any] | None = None
    arrival_airport: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Layer weights — sum = 0.75; remaining 0.25 reserved for agreement bonus.
WEIGHTS = {
    "l2": 0.20,
    "l3": 0.15,
    "l4": 0.12,
    "l5": 0.12,
    "l6": 0.08,
    "l7": 0.08,
}


class Algo7DestinationEngine:
    def __init__(self, redis_client: Any | None = None) -> None:
        self.redis = redis_client

    def predict(self, aircraft_state: dict[str, Any]) -> Algo7Result:
        lat = float(aircraft_state.get("lat") or 0)
        lon = float(aircraft_state.get("lon") or 0)
        heading = aircraft_state.get("true_track")
        speed_ms = float(aircraft_state.get("velocity") or 0)
        baro = aircraft_state.get("baro_altitude")
        velocity = aircraft_state.get("velocity")
        on_ground = bool(aircraft_state.get("on_ground"))
        icao24 = aircraft_state.get("icao24") or ""
        callsign = aircraft_state.get("callsign") or ""

        airports_idx = _airports_index()

        layer_results: dict[str, Any] = {}
        sources: list[str] = []

        # ----- LAYER 1: filed flight plan -----
        l1 = fetch_flight_plan(icao24, redis_client=self.redis)
        if l1:
            layer_results["layer1"] = {"available": True, **l1}
        else:
            layer_results["layer1"] = {"available": False}

        # If layer 1 has both departure and arrival → high confidence shortcut.
        if l1 and l1.get("arrival_icao"):
            arr_icao = l1["arrival_icao"].upper()
            arr = airports_idx.get(arr_icao, {"icao": arr_icao})
            dep_icao = (l1.get("departure_icao") or "").upper() or None
            dep = airports_idx.get(dep_icao, {"icao": dep_icao}) if dep_icao else None

            # Progress (great-circle).
            progress = None
            if dep and "lat" in dep and "lat" in arr:
                total = haversine_km(dep["lat"], dep["lon"], arr["lat"], arr["lon"])
                done = haversine_km(dep["lat"], dep["lon"], lat, lon)
                if total > 1:
                    progress = max(0.0, min(100.0, (done / total) * 100.0))

            eta_min = None
            if "lat" in arr and speed_ms > 5:
                d = haversine_km(lat, lon, arr["lat"], arr["lon"])
                eta_min = round(d / (speed_ms * 3.6) * 60.0)

            primary = {
                **arr,
                "prob": 1.0,
                "eta_minutes": eta_min,
            }
            sources.append("OpenSky flight plan")
            return Algo7Result(
                confidence_global=0.95,
                level_used=1,
                primary_destination=primary,
                alternatives=[],
                layer_results=layer_results,
                sources=sources,
                progress_pct=round(progress, 1) if progress is not None else None,
                departure_airport=dep,
                arrival_airport=primary,
            )

        # ----- LAYER 2: callsign → carrier -----
        carrier = decode_callsign(callsign)
        if carrier:
            layer_results["layer2"] = {
                "available": True,
                "carrier_iata": carrier.get("iata"),
                "carrier_icao": carrier.get("icao"),
                "carrier_name": carrier.get("name_fr") or carrier.get("name_en"),
                "carrier_country": carrier.get("country_iso"),
                "hubs": carrier.get("hubs"),
                "score": score_carrier_network_global(carrier, lat, lon),
            }
            if carrier.get("name_fr"):
                sources.append(f"callsign {carrier.get('icao')}")
        else:
            layer_results["layer2"] = {"available": False, "score": 0.0}

        # ----- LAYER 4: aircraft type -----
        aircraft_type = decode_aircraft_type(
            icao24, baro, velocity, on_ground, redis_client=self.redis,
        )
        layer_results["layer4"] = {
            "available": True,
            "category": aircraft_type["category"],
            "range_km": aircraft_type["range_km"],
            "source": aircraft_type["source"],
            "score": 0.5,  # depends on candidate; updated below
        }
        sources.append(f"type {aircraft_type['category']} ({aircraft_type['range_km']} km)")

        # ----- LAYER 5: corridor detection -----
        corridor = detect_corridor(lat, lon, baro, heading)
        if corridor:
            layer_results["layer5"] = {
                "available": True,
                "corridor": corridor["name"],
                "type": corridor["type"],
                "typical_origins": corridor["typical_origins"],
                "typical_destinations": corridor["typical_destinations"],
                "score": 0.7,
            }
            sources.append(f"corridor {corridor['name']}")
        else:
            layer_results["layer5"] = {"available": False, "score": 0.0}

        # ----- LAYER 6: jet stream / meteo -----
        l6 = score_jet_alignment(lat, lon, baro, heading)
        layer_results["layer6"] = {
            "available": True,
            "tailwind_kts": l6["tailwind_kts"],
            "jet_magnitude_kts": l6["jet"]["magnitude_kts"],
            "score": l6["score"],
        }
        if l6["tailwind_kts"] > 30:
            sources.append(f"jet stream +{int(l6['tailwind_kts'])}kt")
        elif l6["tailwind_kts"] < -30:
            sources.append(f"jet stream {int(l6['tailwind_kts'])}kt headwind")

        # ----- LAYER 7: candidate airports via projection -----
        if heading is None or speed_ms < 30:
            layer_results["layer7"] = {"available": False, "score": 0.0}
            return Algo7Result(
                confidence_global=0.05,
                level_used=2 if carrier else 0,
                primary_destination=None,
                alternatives=[],
                layer_results=layer_results,
                sources=sources,
                progress_pct=None,
            )

        candidates = find_candidate_airports(
            lat, lon, float(heading), speed_ms,
            aircraft_range_km=aircraft_type["range_km"],
        )
        layer_results["layer7"] = {
            "available": bool(candidates),
            "candidates_count": len(candidates),
            "score": (max(c["score"] for c in candidates) if candidates else 0.0),
        }

        # Pool candidates: L7 + carrier hubs + corridor destinations.
        pool: dict[str, dict[str, Any]] = {}
        for c in candidates:
            if c.get("icao"):
                pool[c["icao"]] = dict(c)

        if carrier:
            for hub_icao in carrier.get("hubs") or []:
                hub = airports_idx.get(hub_icao.upper())
                if not hub:
                    continue
                if hub_icao.upper() in pool:
                    continue
                d = haversine_km(lat, lon, hub["lat"], hub["lon"])
                if d < 30:
                    continue
                pool[hub_icao.upper()] = {
                    "icao": hub.get("icao"),
                    "iata": hub.get("iata"),
                    "name_fr": hub.get("name_fr"),
                    "name_en": hub.get("name_en"),
                    "country_iso": hub.get("country_iso"),
                    "lat": hub["lat"],
                    "lon": hub["lon"],
                    "distance_km": round(d, 1),
                    "score": 0.0,
                    "eta_minutes": (round(d / (speed_ms * 3.6) * 60.0) if speed_ms > 5 else None),
                }

        if corridor:
            for icao_t in corridor.get("typical_destinations") or []:
                ap = airports_idx.get(icao_t.upper())
                if not ap or icao_t.upper() in pool:
                    continue
                d = haversine_km(lat, lon, ap["lat"], ap["lon"])
                if d < 30:
                    continue
                pool[icao_t.upper()] = {
                    "icao": ap.get("icao"),
                    "iata": ap.get("iata"),
                    "name_fr": ap.get("name_fr"),
                    "name_en": ap.get("name_en"),
                    "country_iso": ap.get("country_iso"),
                    "lat": ap["lat"],
                    "lon": ap["lon"],
                    "distance_km": round(d, 1),
                    "score": 0.0,
                    "eta_minutes": (round(d / (speed_ms * 3.6) * 60.0) if speed_ms > 5 else None),
                }

        # ----- Layer-3 evaluation per candidate -----
        scored: list[dict[str, Any]] = []
        for cand in pool.values():
            l2_score = layer_results["layer2"].get("score") or 0.0
            l3_score = score_geographic_coherence(carrier, cand, lat, lon, heading)
            l4_score = score_destination_for_type(aircraft_type, cand.get("distance_km") or 0)
            l5_score = (
                score_destination_in_corridor(corridor, cand.get("icao") or "")
                if corridor else 0.0
            )
            l6_score = layer_results["layer6"]["score"]
            l7_score = cand.get("score") or 0.0

            base = (
                WEIGHTS["l2"] * l2_score +
                WEIGHTS["l3"] * l3_score +
                WEIGHTS["l4"] * l4_score +
                WEIGHTS["l5"] * l5_score +
                WEIGHTS["l6"] * l6_score +
                WEIGHTS["l7"] * l7_score
            )

            # Multi-layer agreement bonus: how many layers gave >= 0.5 for this dest?
            agree_count = sum(
                1 for s in (l2_score, l3_score, l4_score, l5_score, l7_score)
                if s >= 0.5
            )
            if agree_count >= 4:
                base += 0.10
            elif agree_count >= 3:
                base += 0.05

            # Hard penalty if range incompatible.
            if not is_destination_compatible(aircraft_type, cand.get("distance_km") or 0):
                base *= 0.40

            cand["combined_score"] = round(base, 4)
            cand["layer_scores"] = {
                "l3": round(l3_score, 3),
                "l4": round(l4_score, 3),
                "l5": round(l5_score, 3),
            }
            scored.append(cand)

        if not scored:
            level_used = 2 if carrier else 0
            return Algo7Result(
                confidence_global=0.10 if carrier else 0.0,
                level_used=level_used,
                primary_destination=None,
                alternatives=[],
                layer_results=layer_results,
                sources=sources,
                progress_pct=None,
            )

        scored.sort(key=lambda c: c["combined_score"], reverse=True)
        top = scored[0]
        # Normalize confidence by total of scores (gives probabilities).
        total = sum(c["combined_score"] for c in scored) or 1.0
        for c in scored:
            c["prob"] = round(c["combined_score"] / total, 3)
        top_prob = top["prob"]
        confidence = round(min(0.92, max(0.10, top_prob * 1.5)), 3)

        primary = {k: v for k, v in top.items() if k not in ("layer_scores",)}
        primary["prob"] = top_prob

        alternatives = []
        for alt in scored[1:4]:
            alternatives.append({
                "icao": alt.get("icao"),
                "iata": alt.get("iata"),
                "name_fr": alt.get("name_fr"),
                "name_en": alt.get("name_en"),
                "country_iso": alt.get("country_iso"),
                "prob": alt["prob"],
                "distance_km": alt.get("distance_km"),
                "eta_minutes": alt.get("eta_minutes"),
            })

        # Choose level_used:
        #   2 if only callsign known
        #   higher if multiple layers agreed
        agreement = sum(
            1 for k in ("layer2", "layer4", "layer5", "layer6", "layer7")
            if layer_results.get(k, {}).get("available")
        )
        if confidence >= 0.65 and agreement >= 4:
            level_used = 4
        elif confidence >= 0.45:
            level_used = 3
        else:
            level_used = 2

        return Algo7Result(
            confidence_global=confidence,
            level_used=level_used,
            primary_destination=primary,
            alternatives=alternatives,
            layer_results=layer_results,
            sources=sources,
            progress_pct=None,  # no flight plan → can't compute
            arrival_airport=primary,
        )
