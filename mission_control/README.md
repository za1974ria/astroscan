# ASTROSCAN COMMAND - Mission Control

Real-time situational awareness dashboard for low-Earth orbit operations.

**Live deployment:** https://astroscan.space/command/

---

## What it does

Mission Control aggregates five independent public data sources into a
single command-center interface, producing a derived global threat index
and a live event log. Every value displayed is sourced from a public,
auditable upstream. No synthetic metrics are presented as real.

### Live data sources

| Metric | Upstream | Refresh | License |
|---|---|---|---|
| ISS TLE | AMSAT nasabare.txt | 1h | Public |
| Kp index | NOAA SWPC | 5min | US Gov public domain |
| F10.7 flux | NOAA SWPC | 5min | US Gov public domain |
| X-Ray flux | NOAA SWPC | 5min | US Gov public domain |
| Space alerts | NOAA SWPC | 5min | US Gov public domain |
| Earthquakes | USGS Earthquake Hazards | 2min | US Gov public domain |
| Aircraft | OpenSky Network | 60s | CC-BY 4.0 |

### Derived signals

**Global Threat Index** - weighted blend of five normalized signals,
each clipped to [0, 100]:

    threat_index =
        0.35 * normalize(kp, 0, 9)
      + 0.20 * normalize(log10(xray_wm2), -8, -3)
      + 0.25 * seismic_score
      + 0.10 * air_traffic_density
      + 0.10 * min(48, tle_age_hours) / 48 * 100

**Seismic score** - magnitude-weighted aggregate over 24h:

    weights: M4+ -> 1, M5+ -> 5, M6+ -> 20, M7+ -> 100
    tsunami_multiplier: 2.0 if NOAA tsunami flag, else 1.0

**Mission Advisor** - most recent significant NOAA alert (24h window),
classified into geomagnetic_storm, solar_flare, radiation_storm, or
radio_blackout. Empty pool falls back to nominal.

---

## Architecture

    nginx (port 443, /command/)
      -> reverse_proxy 127.0.0.1:8000
         -> astroscan-command.service (systemd hardened)
            -> uvicorn -> FastAPI
               - HTTP endpoints (5 cached)
               - WebSocket /ws (telemetry frames)
               - Static templates (Jinja2)

### Backend (backend/app/main.py)

FastAPI app with five HTTP endpoints, all cached server-side:

- GET /api/tle/iss          AMSAT TLE, CelesTrak fallback
- GET /api/space-weather    NOAA Kp + F10.7 + X-Ray
- GET /api/air-traffic      OpenSky aircraft
- GET /api/seismic          USGS earthquakes 24h
- GET /api/space-alerts     NOAA alerts classified

Plus WS /ws and GET /healthz.

### Frontend (frontend/)

Vanilla JavaScript SPA:

- Cesium for ISS globe (NASA Blue/Black Marble)
- Live overrides: background fetchers populate LIVE_OVERRIDES
  from real sources; frame interceptor replaces synthetic
  metrics before render
- Modules: AirTrafficLive, SeismicLive, AdvisorLive,
  TleAgeMonitor, RealEventStream

---

## Honesty principles

Every metric shown is either real or marked as derived:

- Live (NASA): streamed directly from a public API
- Live derived: computed transparently from live inputs
- Removed: synthetic decorative elements that could not be
  wired to a real source (RF SIGNAL, DEEP SIGINT, MARITIME,
  ENVIRONMENTAL, SUBSYSTEM STATUS) were deleted in v2.6
  rather than masked with a SIM badge.

---

## Operations

### Service

    systemctl status astroscan-command.service
    systemctl restart astroscan-command.service
    journalctl -u astroscan-command.service -f

### Health check

    curl -sI https://astroscan.space/command/healthz

### Live audit

    for ep in tle/iss space-weather air-traffic seismic space-alerts; do
      curl -s "https://astroscan.space/command/api/$ep" \
        | python3 -c "import sys,json; d=json.load(sys.stdin); \
                       print(f'$ep live={d.get(chr(34)+chr(108)+chr(105)+chr(118)+chr(101)+chr(34))}')"
    done

---

## Dependencies

- Python 3.12+
- FastAPI 0.136 + Uvicorn (uvloop disabled)
- httpx for upstream calls

---

## License

Inherits ASTRO-SCAN project license. Upstream licenses per table above.
