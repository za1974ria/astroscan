"""
ASTROSCAN COMMAND V2
Mission Control Situational Awareness Platform

FastAPI application entrypoint:
  - Serves the Jinja2 mission control template
  - Mounts static assets (CSS, JS, audio, imagery)
  - Streams synthetic live telemetry over a WebSocket channel
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
TEMPLATES_DIR = FRONTEND_DIR / "templates"


# ---------------------------------------------------------------------------
# Telemetry synthesis
# ---------------------------------------------------------------------------

class TelemetryEmitter:
    """
    Generates plausible, smoothly varying mission-control telemetry frames.
    Uses sinusoidal drift plus light gaussian jitter so values feel organic.
    """

    SYSTEM_TAG = "ASTROSCAN-COMMAND-V2"

    def __init__(self) -> None:
        self._t0 = time.monotonic()
        self._seed = random.random() * 1000.0

    def _drift(self, period: float, phase: float, scale: float, base: float) -> float:
        t = time.monotonic() - self._t0 + self._seed
        return base + math.sin((t / period) + phase) * scale

    def next_frame(self) -> Dict[str, Any]:
        threat_index = _clamp(
            self._drift(period=18.0, phase=0.0, scale=14.0, base=32.0)
            + random.gauss(0, 1.6),
            0.0,
            100.0,
        )

        orbital_integrity = _clamp(
            self._drift(period=22.0, phase=1.4, scale=3.5, base=97.0)
            + random.gauss(0, 0.4),
            85.0,
            100.0,
        )

        iss_velocity = 7.66 + math.sin(time.monotonic() / 25.0) * 0.015
        iss_altitude = 408.0 + math.sin(time.monotonic() / 31.0) * 1.2

        return {
            "system": self.SYSTEM_TAG,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "threat_index": round(threat_index, 2),
            "orbital_status": {
                "integrity": round(orbital_integrity, 2),
                "iss_velocity_km_s": round(iss_velocity, 4),
                "iss_altitude_km": round(iss_altitude, 2),
                "tracked_objects": 28412 + random.randint(-12, 12),
            },
            "metrics": {
                "air_traffic_density": round(
                    _clamp(self._drift(11.0, 0.3, 18.0, 58.0) + random.gauss(0, 1.2), 0, 100), 2
                ),
                "maritime_density": round(
                    _clamp(self._drift(14.0, 1.1, 16.0, 52.0) + random.gauss(0, 1.4), 0, 100), 2
                ),
                "solar_activity": round(
                    _clamp(self._drift(20.0, 2.2, 22.0, 44.0) + random.gauss(0, 1.8), 0, 100), 2
                ),
                "seismic_activity": round(
                    _clamp(self._drift(17.0, 0.9, 12.0, 28.0) + random.gauss(0, 1.0), 0, 100), 2
                ),
                "weather_score": round(
                    _clamp(self._drift(24.0, 1.7, 8.0, 82.0) + random.gauss(0, 0.6), 0, 100), 2
                ),
                "visibility_score": round(
                    _clamp(self._drift(19.0, 0.5, 7.0, 88.0) + random.gauss(0, 0.5), 0, 100), 2
                ),
                "system_health": round(
                    _clamp(self._drift(30.0, 2.0, 2.5, 96.5) + random.gauss(0, 0.3), 0, 100), 2
                ),
            },
        }


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# External feed proxies (TLE + Space Weather) — stdlib HTTP in a thread pool,
# small in-memory cache, graceful fallback. No new Python dependencies.
# ---------------------------------------------------------------------------

_HTTP_EXEC = ThreadPoolExecutor(max_workers=4, thread_name_prefix="astroscan-http")

# Background refresh cadences
_TLE_REFRESH_OK_S   = 3_600.0   # refresh hourly on success
_TLE_REFRESH_FAIL_S = 300.0     # retry in 5 min on total failure
_SWX_TTL_S          = 300.0     # 5 minutes

_TLE_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_SWX_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_AIR_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_AIR_TTL_S = 60.0  # Refresh air traffic every 60s (upstream caches 30s)
_AIR_TRAFFIC_UPSTREAM = "https://astroscan.space/api/flight-radar/aircraft"
# World aviation reference: ~12000 aircraft typically in flight at a given moment.
# We map total_in_cache → density [0..100] with sigmoid-like scaling.
_AIR_WORLD_BASELINE = 12000

# === Seismic activity (USGS Earthquake Hazards Program — US Gov public domain) ===
_SEISMIC_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_SEISMIC_TTL_S = 120.0  # Refresh every 2 minutes (USGS updates ~1min cadence)
_SEISMIC_UPSTREAM = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"

# === Space Weather alerts (NOAA SWPC — US Gov public domain) ===
_ALERTS_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_ALERTS_TTL_S = 300.0  # Refresh every 5 minutes
_ALERTS_UPSTREAM = "https://services.swpc.noaa.gov/products/alerts.json"

_FALLBACK_TLE = {
    "name": "ISS (ZARYA)",
    "line1": "1 25544U 98067A   24130.50000000  .00010000  00000-0  18000-3 0  9990",
    "line2": "2 25544  51.6400 100.0000 0006000  90.0000 270.0000 15.50000000  9990",
    "source": "fallback",
    "live": False,
}

# Multi-source TLE strategy. AMSAT primary (Hetzner IPs blocked by CelesTrak
# rate-limiter since 2024). AMSAT publishes the NASA bare format daily — same
# data CelesTrak gets from NORAD. CelesTrak kept as last-resort in case AMSAT
# CDN ever fails. N2YO requires API auth and is not usable as a public backup.
_TLE_SOURCES = [
    ("amsat.org/nasabare.txt",     "https://www.amsat.org/tle/current/nasabare.txt"),
    ("celestrak.org/gp/CATNR",     "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"),
    ("celestrak.org/gp/NAME",      "https://celestrak.org/NORAD/elements/gp.php?NAME=ISS+(ZARYA)&FORMAT=TLE"),
    ("celestrak.org/stations.txt", "https://celestrak.org/NORAD/elements/stations.txt"),
]

# Pre-initialize cache with synthetic so the first request never blocks
# and the background refresh writes a real TLE on top when internet is up.
_TLE_CACHE["data"] = dict(_FALLBACK_TLE)
_TLE_CACHE["data"]["fetched"] = datetime.now(timezone.utc).isoformat()

_TLE_REFRESH_TASK: Optional["asyncio.Task[None]"] = None
_TLE_REFRESH_LOCK = asyncio.Lock()


def _http_text(url: str, timeout: float = 8.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AstroScan-Command/2.0 (educational simulation)",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


async def _http_get(url: str, timeout: float = 8.0) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _HTTP_EXEC, lambda: _http_text(url, timeout)
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iss_tle(text: str) -> Optional[Dict[str, Any]]:
    """Extract ISS (NORAD 25544) TLE from any CelesTrak response format.

    Handles single-satellite responses (3 lines: name + line1 + line2)
    AND multi-satellite files like stations.txt — by locating the lines
    that start with the actual catalog number '1 25544' / '2 25544'.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if line.startswith("1 25544"):
            if i + 1 < len(lines) and lines[i + 1].startswith("2 25544"):
                name = lines[i - 1].strip() if i > 0 else "ISS (ZARYA)"
                # Guard against name being one of the data lines (single-line TLEs)
                if name.startswith("1 ") or name.startswith("2 "):
                    name = "ISS (ZARYA)"
                return {
                    "name": name,
                    "line1": line,
                    "line2": lines[i + 1],
                    "fetched": _now_iso(),
                }
    return None


async def _refresh_iss_tle() -> bool:
    """Try every source, 3 retries per source, exponential backoff.
    Writes to _TLE_CACHE on first success. Returns True if any source succeeded.
    Concurrency-safe via _TLE_REFRESH_LOCK so two refreshes don't overlap.
    """
    async with _TLE_REFRESH_LOCK:
        for source_name, url in _TLE_SOURCES:
            for attempt in range(3):
                try:
                    text = await _http_get(url, timeout=10.0)
                    data = _parse_iss_tle(text)
                    if not data:
                        raise ValueError("ISS 25544 not found in response")
                    data["source"] = source_name
                    data["live"] = True
                    _TLE_CACHE["data"] = data
                    _TLE_CACHE["ts"] = time.time()
                    return True
                except Exception:
                    if attempt < 2:
                        # exponential backoff: 1s, 2s
                        await asyncio.sleep(1 << attempt)
        return False


async def _tle_refresh_loop() -> None:
    """Long-running background task. Survives upstream outages: on failure,
    keeps the last-known-good TLE in cache and retries every 5 min."""
    while True:
        try:
            success = await _refresh_iss_tle()
            await asyncio.sleep(_TLE_REFRESH_OK_S if success else _TLE_REFRESH_FAIL_S)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(_TLE_REFRESH_FAIL_S)


def _ensure_tle_refresh_started() -> None:
    """Lazy startup of the background refresh task on the first /api/tle/iss
    hit. Safe to call repeatedly — only spawns once per event loop."""
    global _TLE_REFRESH_TASK
    try:
        if _TLE_REFRESH_TASK is None or _TLE_REFRESH_TASK.done():
            loop = asyncio.get_running_loop()
            _TLE_REFRESH_TASK = loop.create_task(_tle_refresh_loop())
    except RuntimeError:
        # No running loop in this context — silent no-op.
        pass


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="ASTROSCAN COMMAND V2",
        version="2.0.0",
        description="Premium mission-control situational awareness platform.",
        root_path="/command",  # Acte 1 — Mounted behind nginx at /command
    )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "build_version": "2.0.0",
                "callsign": "ASTROSCAN-COMMAND",
            },
        )

    @app.get("/healthz")
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}

    # Inline SVG favicon — aerospace target reticle, deep navy ground + cyan pip.
    _FAVICON_SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect width="32" height="32" rx="6" fill="#02060b"/>'
        '<circle cx="16" cy="16" r="11" fill="none" stroke="#7fd1e6" stroke-width="1.2" opacity="0.85"/>'
        '<circle cx="16" cy="16" r="6"  fill="none" stroke="#7fd1e6" stroke-width="0.9" opacity="0.55"/>'
        '<line x1="16" y1="3" x2="16" y2="7"  stroke="#7fd1e6" stroke-width="1.1" stroke-linecap="round"/>'
        '<line x1="16" y1="25" x2="16" y2="29" stroke="#7fd1e6" stroke-width="1.1" stroke-linecap="round"/>'
        '<line x1="3"  y1="16" x2="7"  y2="16" stroke="#7fd1e6" stroke-width="1.1" stroke-linecap="round"/>'
        '<line x1="25" y1="16" x2="29" y2="16" stroke="#7fd1e6" stroke-width="1.1" stroke-linecap="round"/>'
        '<circle cx="16" cy="16" r="1.6" fill="#7fd1e6"/>'
        '</svg>'
    )

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(
            content=_FAVICON_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400, immutable"},
        )

    @app.get("/api/tle/iss")
    async def iss_tle() -> JSONResponse:
        """Live TLE for the ISS (NORAD 25544).

        Always responds instantly from cache. The cache is pre-populated with
        a known-good synthetic TLE so the first request never blocks; a
        background task refreshes from CelesTrak (3 sources × 3 retries with
        backoff) on a 1-hour cadence (5-min on total failure). Once a live
        TLE has been obtained, it stays in cache as last-known-good until
        the next successful refresh overwrites it. Synthetic is only ever
        served when *no* upstream fetch has ever succeeded.
        """
        _ensure_tle_refresh_started()
        return JSONResponse(_TLE_CACHE["data"])

    @app.get("/api/space-weather")
    async def space_weather() -> JSONResponse:
        """Latest Kp, F10.7 flux, and GOES X-ray long-band — NOAA SWPC."""
        now = time.time()
        if _SWX_CACHE["data"] and (now - _SWX_CACHE["ts"]) < _SWX_TTL_S:
            return JSONResponse(_SWX_CACHE["data"])
        try:
            kp_text, flux_text, xray_text = await asyncio.gather(
                _http_get(
                    "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
                    timeout=8.0,
                ),
                _http_get(
                    "https://services.swpc.noaa.gov/json/f107_cm_flux.json",
                    timeout=8.0,
                ),
                _http_get(
                    "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
                    timeout=8.0,
                ),
            )
            kp_arr = json.loads(kp_text)
            flux_arr = json.loads(flux_text)
            xray_arr = json.loads(xray_text)

            # Kp: header row then [time_tag, Kp, a_running, station_count] rows.
            kp_rows = [r for r in kp_arr if isinstance(r, list) and len(r) >= 2 and r[1] != "Kp"]
            latest_kp = float(kp_rows[-1][1]) if kp_rows else 2.5

            # F10.7: list of {time_tag, flux}.
            latest_flux = float(flux_arr[-1].get("flux", 140.0)) if flux_arr else 140.0

            # X-ray flux: filter for 0.1-0.8 nm (long-band, the standard class indicator).
            long_band = [r for r in xray_arr if r.get("energy") == "0.1-0.8nm"]
            latest_xray = float(long_band[-1].get("flux", 1e-7)) if long_band else 1e-7

            data = {
                "kp": latest_kp,
                "f107": latest_flux,
                "xray_long_wm2": latest_xray,
                "source": "NOAA SWPC",
                "live": True,
                "fetched": _now_iso(),
            }
            _SWX_CACHE["data"] = data
            _SWX_CACHE["ts"] = now
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({
                "kp": 2.7,
                "f107": 142.0,
                "xray_long_wm2": 1.6e-7,
                "source": "fallback",
                "live": False,
                "error": str(e)[:200],
                "fetched": _now_iso(),
            })

    @app.get("/api/air-traffic")
    async def air_traffic() -> JSONResponse:
        """Live global air traffic density — proxies ASTRO-SCAN /api/flight-radar/aircraft.

        Returns a normalized density [0..100] computed from the worldwide
        aircraft count served by the flight_radar blueprint (OpenSky OAUTH2 +
        ADS-B.lol fallback). Cached 60s; upstream itself caches ~30s.
        On upstream failure, returns last-known-good or a clearly-marked
        fallback. Live data is identified by `live: true` and `source` field.
        """
        now = time.time()
        if _AIR_CACHE["data"] and (now - _AIR_CACHE["ts"]) < _AIR_TTL_S:
            return JSONResponse(_AIR_CACHE["data"])
        try:
            raw = await _http_get(_AIR_TRAFFIC_UPSTREAM, timeout=8.0)
            payload = json.loads(raw)
            aircraft = payload.get("aircraft", [])
            total_cached = int(payload.get("total", len(aircraft)))
            in_flight = sum(1 for a in aircraft if not a.get("on_ground", False))
            on_ground = sum(1 for a in aircraft if a.get("on_ground", False))
            # Density: linear map [0, baseline*2] → [0, 100]
            density = _clamp(
                (total_cached / _AIR_WORLD_BASELINE) * 50.0,
                0.0, 100.0
            )
            data = {
                "total_aircraft": total_cached,
                "in_flight": in_flight,
                "on_ground": on_ground,
                "rendered": int(payload.get("rendered", 0)),
                "density_pct": round(density, 2),
                "world_baseline": _AIR_WORLD_BASELINE,
                "source": "OpenSky Network (via ASTRO-SCAN flight_radar)",
                "upstream_source": payload.get("source", "unknown"),
                "live": True,
                "fetched": _now_iso(),
                "upstream_ts": payload.get("ts"),
            }
            _AIR_CACHE["data"] = data
            _AIR_CACHE["ts"] = now
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({
                "total_aircraft": 0,
                "in_flight": 0,
                "on_ground": 0,
                "rendered": 0,
                "density_pct": 0.0,
                "world_baseline": _AIR_WORLD_BASELINE,
                "source": "fallback",
                "upstream_source": "unreachable",
                "live": False,
                "error": str(e)[:200],
                "fetched": _now_iso(),
            })

    @app.get("/api/seismic")
    async def seismic() -> JSONResponse:
        """Live global seismic activity — USGS Earthquake Hazards Program.

        Aggregates last-24h earthquakes worldwide and computes a weighted
        activity score [0..100] where:
          - M < 4.0  : ignored (background noise, hundreds/day worldwide)
          - M 4.0-5.0: weight 1
          - M 5.0-6.0: weight 5  (significant)
          - M 6.0-7.0: weight 20 (major)
          - M 7.0+   : weight 100 (catastrophic)
          - Tsunami warning: ×2 multiplier on total

        Cached 120s. On upstream failure, returns last-known-good or fallback
        marked live=false. Source: US Geological Survey public domain.
        """
        now = time.time()
        if _SEISMIC_CACHE["data"] and (now - _SEISMIC_CACHE["ts"]) < _SEISMIC_TTL_S:
            return JSONResponse(_SEISMIC_CACHE["data"])
        try:
            raw = await _http_get(_SEISMIC_UPSTREAM, timeout=8.0)
            payload = json.loads(raw)
            features = payload.get("features", [])
            score = 0.0
            counts = {"4-5": 0, "5-6": 0, "6-7": 0, "7+": 0}
            top_events = []
            tsunami_flagged = 0
            for f in features:
                props = f.get("properties", {})
                mag = props.get("mag") or 0
                if mag < 4.0:
                    continue
                if mag < 5.0:
                    score += 1; counts["4-5"] += 1
                elif mag < 6.0:
                    score += 5; counts["5-6"] += 1
                elif mag < 7.0:
                    score += 20; counts["6-7"] += 1
                else:
                    score += 100; counts["7+"] += 1
                if props.get("tsunami") == 1:
                    tsunami_flagged += 1
                geom = f.get("geometry", {}).get("coordinates", [0, 0, 0])
                top_events.append({
                    "mag": round(mag, 1),
                    "place": props.get("place", "Unknown"),
                    "time": props.get("time"),
                    "tsunami": props.get("tsunami") == 1,
                    "alert": props.get("alert"),
                    "lon": geom[0] if len(geom) > 0 else None,
                    "lat": geom[1] if len(geom) > 1 else None,
                    "depth_km": geom[2] if len(geom) > 2 else None,
                })
            if tsunami_flagged > 0:
                score *= 2
            score = _clamp(score, 0.0, 100.0)
            top_events.sort(key=lambda e: e["mag"], reverse=True)
            top_events = top_events[:5]
            data = {
                "score": round(score, 2),
                "total_events_24h": len(features),
                "significant_events_24h": sum(counts.values()),
                "magnitude_distribution": counts,
                "tsunami_warnings": tsunami_flagged,
                "top_events": top_events,
                "source": "USGS Earthquake Hazards Program",
                "live": True,
                "fetched": _now_iso(),
            }
            _SEISMIC_CACHE["data"] = data
            _SEISMIC_CACHE["ts"] = now
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({
                "score": 0.0,
                "total_events_24h": 0,
                "significant_events_24h": 0,
                "magnitude_distribution": {"4-5": 0, "5-6": 0, "6-7": 0, "7+": 0},
                "tsunami_warnings": 0,
                "top_events": [],
                "source": "fallback",
                "live": False,
                "error": str(e)[:200],
                "fetched": _now_iso(),
            })

    @app.get("/api/space-alerts")
    async def space_alerts() -> JSONResponse:
        """Live NOAA SWPC space weather alerts (last 24h).

        Classifies each alert into a structured payload usable as the
        Mission Advisor message and the ALERTS event log. Categories:
          - geomagnetic_storm (K-index based, G1-G5)
          - solar_flare       (X-ray class M/X)
          - radiation_storm   (electron flux >1000pfu, S-scale)
          - radio_blackout    (R-scale, HF radio degradation)
          - other             (everything else, generic)

        Cached 5min. NOAA public domain. Returns the most recent active alert
        plus a 24h log. On upstream failure: marks live=false.
        """
        import re
        from datetime import datetime, timezone, timedelta
        now = time.time()
        if _ALERTS_CACHE["data"] and (now - _ALERTS_CACHE["ts"]) < _ALERTS_TTL_S:
            return JSONResponse(_ALERTS_CACHE["data"])
        try:
            raw = await _http_get(_ALERTS_UPSTREAM, timeout=8.0)
            all_alerts = json.loads(raw)
            now_utc = datetime.now(timezone.utc)
            cutoff = now_utc - timedelta(hours=24)
            recent = []
            for a in all_alerts:
                try:
                    issue_str = a.get("issue_datetime", "").replace(" ", "T") + "+00:00"
                    dt = datetime.fromisoformat(issue_str)
                    if dt >= cutoff:
                        recent.append((dt, a))
                except Exception:
                    continue
            recent.sort(key=lambda x: x[0], reverse=True)

            def classify(alert: Dict[str, Any]) -> Dict[str, Any]:
                pid = alert.get("product_id", "")
                msg = alert.get("message", "") or ""
                # K-index (geomagnetic storm)
                m = re.search(r"K-index of (\d+)", msg)
                if m:
                    kp = int(m.group(1))
                    if kp >= 7:
                        return {"category": "geomagnetic_storm", "severity": "severe",
                                "advisor": f"Severe geomagnetic storm in progress · Kp {kp} · radio blackouts likely",
                                "log_label": "NOAA", "log_msg": f"Geomagnetic storm Kp {kp} (G{kp-4}+) — severe"}
                    if kp >= 6:
                        return {"category": "geomagnetic_storm", "severity": "strong",
                                "advisor": f"Strong geomagnetic storm · Kp {kp} (G2) · auroras mid-latitudes",
                                "log_label": "NOAA", "log_msg": f"Geomagnetic storm Kp {kp} (G2)"}
                    if kp >= 5:
                        return {"category": "geomagnetic_storm", "severity": "moderate",
                                "advisor": f"Geomagnetic storm in progress · Kp {kp} (G1) · monitor",
                                "log_label": "NOAA", "log_msg": f"Geomagnetic storm Kp {kp} (G1)"}
                # X-ray class flare
                m = re.search(r"Class:\s*([XMC])(\d+(?:\.\d+)?)", msg)
                if m:
                    cls, val = m.group(1), m.group(2)
                    if cls == "X":
                        return {"category": "solar_flare", "severity": "severe",
                                "advisor": f"X-class solar flare X{val} · radio blackout zones possible",
                                "log_label": "NOAA", "log_msg": f"Solar flare X{val} detected"}
                    if cls == "M":
                        return {"category": "solar_flare", "severity": "strong",
                                "advisor": f"M-class solar flare M{val} · ISS exposure nominal",
                                "log_label": "NOAA", "log_msg": f"Solar flare M{val} detected"}
                # Electron flux (radiation storm)
                if "Electron 2MeV" in msg and "1000pfu" in msg:
                    return {"category": "radiation_storm", "severity": "moderate",
                            "advisor": "Electron flux elevated · 2MeV >1000pfu · satellite charging risk",
                            "log_label": "NOAA", "log_msg": "Electron flux >1000pfu (S2 watch)"}
                # Generic WATCH
                if "WATCH" in msg.upper() and "G" in msg:
                    return {"category": "geomagnetic_storm", "severity": "watch",
                            "advisor": "Geomagnetic storm WATCH · NOAA prediction active",
                            "log_label": "NOAA", "log_msg": "Geomagnetic storm watch issued"}
                # Generic ALERT
                first_line = next((l.strip() for l in msg.split("\n") if l.strip() and not l.startswith("Space")), "")
                return {"category": "other", "severity": "info",
                        "advisor": first_line[:80] if first_line else f"NOAA alert {pid}",
                        "log_label": "NOAA", "log_msg": first_line[:60] if first_line else pid}

            log_entries = []
            current_advisor = "Space environment nominal · all systems green"
            current_severity = "info"
            current_category = "nominal"
            for dt, a in recent[:20]:
                c = classify(a)
                log_entries.append({
                    "ts": int(dt.timestamp() * 1000),
                    "iso": dt.isoformat(),
                    "label": c["log_label"],
                    "message": c["log_msg"],
                    "category": c["category"],
                    "severity": c["severity"],
                    "product_id": a.get("product_id"),
                })
            # Pick most recent for advisor
            if recent:
                _, top = recent[0]
                c0 = classify(top)
                current_advisor = c0["advisor"]
                current_severity = c0["severity"]
                current_category = c0["category"]

            data = {
                "advisor": current_advisor,
                "severity": current_severity,
                "category": current_category,
                "active_alerts_24h": len(recent),
                "log": log_entries,
                "source": "NOAA SWPC Alerts",
                "live": True,
                "fetched": _now_iso(),
            }
            _ALERTS_CACHE["data"] = data
            _ALERTS_CACHE["ts"] = now
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({
                "advisor": "Space environment monitoring · awaiting NOAA feed",
                "severity": "info",
                "category": "nominal",
                "active_alerts_24h": 0,
                "log": [],
                "source": "fallback",
                "live": False,
                "error": str(e)[:200],
                "fetched": _now_iso(),
            })

    @app.websocket("/ws")
    async def telemetry_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        emitter = TelemetryEmitter()
        try:
            while True:
                frame = emitter.next_frame()
                await websocket.send_text(json.dumps(frame))
                await asyncio.sleep(2.0)
        except WebSocketDisconnect:
            return
        except Exception:
            try:
                await websocket.close()
            except Exception:
                pass

    return app


# ---------------------------------------------------------------------------
# ASGI entrypoint
# ---------------------------------------------------------------------------

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
