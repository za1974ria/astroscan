"""ALGO-7 — 7-layer Bayesian destination inference for live aircraft.

Layers (in priority order):
  1. Flight plan        — OpenSky /flights/aircraft (filed plan, 0.95-1.0 confidence)
  2. Callsign decoder   — IATA prefix → carrier + hubs
  3. Geographic coh.    — current pos vs carrier country + hubs
  4. Aircraft type      — ICAO24 → manufacturer/model/range
  5. Corridors          — NAT/PACOTS/EURO airway intersection
  6. Meteo (jet stream) — tailwind score
  7. Projection         — Haversine forward → candidate airports

Engine combines layers with weighted Bayesian scoring + multi-layer
agreement bonus.
"""
from app.blueprints.flight_radar.algo7.engine import Algo7DestinationEngine, Algo7Result

__all__ = ["Algo7DestinationEngine", "Algo7Result"]
