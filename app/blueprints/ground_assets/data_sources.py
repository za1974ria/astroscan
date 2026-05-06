"""Ground Assets — data providers.

Three providers, all deterministic from time:
  - load_observatories()   -> static JSON (12 sites with real GPS)
  - simulate_missions(now) -> 3 field expeditions following great-circle routes
  - simulate_balloons(now) -> 2 stratospheric probes (ascent / plateau / descent)

Determinism is intentional: the same UTC second always yields the same state,
so multi-worker deployments stay coherent and the live page doesn't flicker.

Solar altitude is computed in solar_altitude_deg() using the NOAA solar
position formula (~0.05° accuracy). No JPL ephemeris needed.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Iterable

_HERE = os.path.dirname(os.path.abspath(__file__))
_OBS_PATH = os.path.join(_HERE, "observatories.json")

EARTH_RADIUS_KM = 6371.0088
RANGE_KM_VISIBLE = 3000.0


# ──────────────────────────────────────────────────────────────────────
# Observatories — static catalogue
# ──────────────────────────────────────────────────────────────────────

_OBS_CACHE: list[dict] | None = None


def load_observatories() -> list[dict]:
    """Returns the 12 observatories from the seed JSON (cached in-process)."""
    global _OBS_CACHE
    if _OBS_CACHE is None:
        with open(_OBS_PATH, "r", encoding="utf-8") as f:
            _OBS_CACHE = json.load(f)
    return [dict(o) for o in _OBS_CACHE]


# ──────────────────────────────────────────────────────────────────────
# Solar altitude — NOAA formula, accurate to <0.1°
# ──────────────────────────────────────────────────────────────────────

def solar_altitude_deg(lat: float, lon: float, when: datetime) -> float:
    """Returns the sun's altitude in degrees at (lat, lon) for `when` (UTC).

    Negative = below horizon. Civil twilight ends at -6°, astronomical at -18°.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    # Julian day
    y, m, d = when.year, when.month, when.day
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    jd = (math.floor(365.25 * (y + 4716))
          + math.floor(30.6001 * (m + 1))
          + d + b - 1524.5)
    frac = (when.hour + when.minute / 60 + when.second / 3600) / 24
    jd += frac
    n = jd - 2451545.0  # days since J2000
    # Mean longitude and anomaly of the sun (degrees)
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    # Ecliptic longitude
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    # Obliquity
    eps = math.radians(23.439 - 0.0000004 * n)
    # Right ascension and declination
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    # Greenwich mean sidereal time (hours), local sidereal time (hours)
    gmst = (18.697374558 + 24.06570982441908 * n) % 24
    lst_hours = (gmst + lon / 15.0) % 24
    ha = math.radians(lst_hours * 15.0) - ra
    # Altitude
    lat_r = math.radians(lat)
    sin_alt = (math.sin(lat_r) * math.sin(dec)
               + math.cos(lat_r) * math.cos(dec) * math.cos(ha))
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


# ──────────────────────────────────────────────────────────────────────
# Geo helpers
# ──────────────────────────────────────────────────────────────────────

def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    dp = p2 - p1
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing (degrees, 0=N, clockwise) from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def interpolate_great_circle(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float,
) -> tuple[float, float]:
    """Returns (lat, lon) at `fraction` of the great-circle from 1 -> 2."""
    fraction = max(0.0, min(1.0, fraction))
    p1, p2 = math.radians(lat1), math.radians(lat2)
    l1, l2 = math.radians(lon1), math.radians(lon2)
    d = great_circle_km(lat1, lon1, lat2, lon2) / EARTH_RADIUS_KM
    if d < 1e-9:
        return lat1, lon1
    a = math.sin((1 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
    lon = math.degrees(math.atan2(y, x))
    return lat, lon


# ──────────────────────────────────────────────────────────────────────
# Mobile field missions — three deterministic narratives
# ──────────────────────────────────────────────────────────────────────
#
# Each mission has:
#   - a route (waypoints with timestamps fraction in [0,1] over the day-loop)
#   - equipment + target description
#   - a frequency for radio-link RSSI computation
#
# We loop the timeline over a 6-hour cycle so the page is always alive for
# visitors, regardless of when they load it. The phase is derived from
# (epoch_seconds % CYCLE_SECONDS) so all workers agree.

_CYCLE_S = 6 * 3600  # 6h cycle

_MISSIONS = [
    {
        "id": "eclipse-egypt",
        "name": "Eclipse Expedition — Western Desert",
        "callsign": "ECL-CAIRO",
        "type": "mission",
        "operator": "ASTRO-SCAN Field Team",
        "target": "Total solar eclipse path — observation campaign",
        "frequency_mhz": 145.825,
        "vehicle": "Toyota Land Cruiser 4x4",
        "equipment": [
            "Coronado SolarMax II 90mm",
            "ZWO ASI2600MM Pro",
            "GPS RTK + INS",
            "Iridium beacon",
        ],
        "waypoints": [
            {"lat": 30.0444, "lon": 31.2357, "label": "Cairo HQ"},
            {"lat": 29.3084, "lon": 30.8418, "label": "Faiyum"},
            {"lat": 28.4519, "lon": 30.0728, "label": "Bahariya"},
            {"lat": 27.5640, "lon": 28.7180, "label": "Farafra"},
            {"lat": 27.0820, "lon": 28.0050, "label": "Western Desert site"},
        ],
    },
    {
        "id": "atacama-radio",
        "name": "Atacama Radio Survey",
        "callsign": "ATC-RAD",
        "type": "mission",
        "operator": "ASTRO-SCAN / ALMA partnership",
        "target": "21 cm hydrogen line — galactic plane scan",
        "frequency_mhz": 1420.405,
        "vehicle": "Mobile parabolic 3m on truck",
        "equipment": [
            "3m parabolic antenna",
            "LNA + RTL-SDR mosaic",
            "GNSS time reference",
            "Starlink uplink",
        ],
        "waypoints": [
            {"lat": -22.9560, "lon": -68.1980, "label": "San Pedro de Atacama"},
            {"lat": -23.0290, "lon": -67.7549, "label": "ALMA site"},
            {"lat": -23.4500, "lon": -67.9300, "label": "Llano de Chajnantor"},
            {"lat": -23.8920, "lon": -68.2890, "label": "Salar relay"},
            {"lat": -24.6275, "lon": -70.4044, "label": "Paranal"},
        ],
    },
    {
        "id": "icefield-aurora",
        "name": "Icefield Aurora Mission",
        "callsign": "ICE-AUR",
        "type": "mission",
        "operator": "ASTRO-SCAN / Sodankylä",
        "target": "All-sky imager — Kp>5 substorm capture",
        "frequency_mhz": 437.800,
        "vehicle": "Tracked snowcat",
        "equipment": [
            "All-sky CCD imager",
            "Magnetometer fluxgate",
            "VLF receiver 0.5–10 kHz",
            "Iridium burst beacon",
        ],
        "waypoints": [
            {"lat": 67.3666, "lon": 26.6290, "label": "Sodankylä Geophysical"},
            {"lat": 68.0710, "lon": 23.0240, "label": "Kilpisjärvi"},
            {"lat": 69.0660, "lon": 20.5450, "label": "Norwegian border"},
            {"lat": 69.6492, "lon": 18.9553, "label": "Tromsø"},
            {"lat": 70.6630, "lon": 23.6820, "label": "Nordkapp"},
        ],
    },
]


def simulate_missions(now: datetime) -> list[dict]:
    """Returns the live state of the 3 field missions."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    out: list[dict] = []
    epoch = int(now.timestamp())
    phase = (epoch % _CYCLE_S) / _CYCLE_S  # 0..1
    for idx, m in enumerate(_MISSIONS):
        offset = (idx * 0.18) % 1.0
        f = (phase + offset) % 1.0
        wp = m["waypoints"]
        seg_count = len(wp) - 1
        seg_f = f * seg_count
        seg_idx = min(int(seg_f), seg_count - 1)
        local_f = seg_f - seg_idx
        a = wp[seg_idx]
        b = wp[seg_idx + 1]
        lat, lon = interpolate_great_circle(
            a["lat"], a["lon"], b["lat"], b["lon"], local_f,
        )
        bearing = initial_bearing_deg(a["lat"], a["lon"], b["lat"], b["lon"])
        seg_km = great_circle_km(a["lat"], a["lon"], b["lat"], b["lon"])
        # Cycle = 6h, so total trip ~ 6h across all segments. Avg speed ~ 50–80 km/h.
        speed = max(20.0, (seg_km / (_CYCLE_S / 3600 / seg_count)) * (0.85 + 0.3 * local_f))
        out.append({
            "id": m["id"],
            "name": m["name"],
            "callsign": m["callsign"],
            "type": "mission",
            "operator": m["operator"],
            "target": m["target"],
            "vehicle": m["vehicle"],
            "equipment": list(m["equipment"]),
            "frequency_mhz": m["frequency_mhz"],
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "heading_deg": round(bearing, 1),
            "speed_kmh": round(speed, 1),
            "altitude_m": 0,
            "current_leg": {
                "from": a["label"],
                "to": b["label"],
                "progress": round(local_f, 3),
            },
            "status": "active",
        })
    return out


# ──────────────────────────────────────────────────────────────────────
# Stratospheric balloons — simple physics
# ──────────────────────────────────────────────────────────────────────
#
# Profile:
#   t in [0.00, 0.40] ascent  (5 m/s) → up to ~33 km
#   t in [0.40, 0.55] plateau drift
#   t in [0.55, 0.65] burst + free fall
#   t in [0.65, 1.00] parachute descent + rest

_BALLOONS = [
    {
        "id": "saharien-1",
        "name": "Saharien-1",
        "callsign": "AS-BAL-01",
        "operator": "ASTRO-SCAN Stratos",
        "payload": [
            "Cosmic ray scintillator",
            "UV/IR sky camera",
            "Sondage radiosonde Vaisala",
            "APRS 144.800 MHz",
        ],
        "frequency_mhz": 144.800,
        "launch_lat": 34.87,
        "launch_lon": -1.32,
        "drift_lat": 0.6,
        "drift_lon": 1.8,
        "max_altitude_m": 33800,
    },
    {
        "id": "andes-prime",
        "name": "Andes-Prime",
        "callsign": "AS-BAL-02",
        "operator": "ASTRO-SCAN / LCO",
        "payload": [
            "Hard X-ray detector",
            "Ozone sonde",
            "GPS RTK",
            "LoRa + Iridium SBD",
        ],
        "frequency_mhz": 869.525,
        "launch_lat": -30.1675,
        "launch_lon": -70.8047,
        "drift_lat": 0.4,
        "drift_lon": 2.1,
        "max_altitude_m": 32400,
    },
]


def simulate_balloons(now: datetime) -> list[dict]:
    """Returns the live state of stratospheric balloons."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    out: list[dict] = []
    epoch = int(now.timestamp())
    phase = (epoch % _CYCLE_S) / _CYCLE_S
    for idx, b in enumerate(_BALLOONS):
        f = (phase + idx * 0.42) % 1.0
        if f < 0.40:
            stage = "ascent"
            alt_frac = f / 0.40
            alt = b["max_altitude_m"] * (alt_frac ** 0.85)
            vspeed = 5.0
        elif f < 0.55:
            stage = "float"
            alt = b["max_altitude_m"] * (1.0 - 0.04 * (f - 0.40) / 0.15)
            vspeed = 0.3
        elif f < 0.65:
            stage = "burst"
            burst_f = (f - 0.55) / 0.10
            alt = b["max_altitude_m"] * (1.0 - burst_f * 0.55)
            vspeed = -45.0 * (0.4 + burst_f)
        else:
            stage = "descent"
            d_f = (f - 0.65) / 0.35
            alt = max(0.0, b["max_altitude_m"] * (0.45 - 0.45 * d_f))
            vspeed = -7.0 * (1 - d_f)
        # Horizontal drift driven by trajectory fraction (not just altitude)
        lat = b["launch_lat"] + b["drift_lat"] * f
        lon = b["launch_lon"] + b["drift_lon"] * f
        out.append({
            "id": b["id"],
            "name": b["name"],
            "callsign": b["callsign"],
            "type": "balloon",
            "operator": b["operator"],
            "payload": list(b["payload"]),
            "frequency_mhz": b["frequency_mhz"],
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "altitude_m": round(alt, 0),
            "vertical_speed_ms": round(vspeed, 2),
            "stage": stage,
            "status": "flying" if stage in ("ascent", "float", "burst") else "descending",
        })
    return out


# ──────────────────────────────────────────────────────────────────────
# Antenna links — observatories tracking missions/balloons
# ──────────────────────────────────────────────────────────────────────

def compute_antenna_links(
    observatories: Iterable[dict],
    targets: Iterable[dict],
) -> list[dict]:
    """For each (obs, target) within RANGE_KM_VISIBLE, returns a link with RSSI."""
    obs_list = list(observatories)
    targets_list = list(targets)
    links: list[dict] = []
    for t in targets_list:
        # Closest observatory becomes primary (gold)
        candidates = []
        for o in obs_list:
            d = great_circle_km(o["lat"], o["lon"], t["lat"], t["lon"])
            if d <= RANGE_KM_VISIBLE:
                # Spec RSSI model
                rssi = -67.0 - (d / 50.0)
                rssi = max(-110.0, min(-40.0, rssi))
                candidates.append({"obs_id": o["id"], "distance_km": d, "rssi": rssi})
        if not candidates:
            continue
        candidates.sort(key=lambda x: x["distance_km"])
        primary = candidates[0]
        primary["primary"] = True
        links.append({
            "target_id": t["id"],
            "target_lat": t["lat"],
            "target_lon": t["lon"],
            "obs_id": primary["obs_id"],
            "distance_km": round(primary["distance_km"], 1),
            "rssi_dbm": round(primary["rssi"], 1),
            "primary": True,
        })
        for c in candidates[1:3]:  # up to 2 secondary links
            links.append({
                "target_id": t["id"],
                "target_lat": t["lat"],
                "target_lon": t["lon"],
                "obs_id": c["obs_id"],
                "distance_km": round(c["distance_km"], 1),
                "rssi_dbm": round(c["rssi"], 1),
                "primary": False,
            })
    return links
