# ORBITAL-CHOHRA — Real-Time Web Observatory

<div align="center">

![Status](https://img.shields.io/badge/status-operational-2ea44f)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab)
![Flask](https://img.shields.io/badge/flask-3.1-000000)
![Architecture](https://img.shields.io/badge/architecture-blueprints%20%2B%20factory-blue)
![Routes](https://img.shields.io/badge/routes-262-informational)
![Coverage](https://img.shields.io/badge/migration-complete-2ea44f)
![License](https://img.shields.io/badge/license-proprietary-lightgrey)

**Independent observatory in Tlemcen, Algeria — making real-time orbital intelligence accessible worldwide.**

🌐 **Production**: [astroscan.space](https://astroscan.space)

</div>

---

## Overview

ORBITAL-CHOHRA (also known as **ASTRO-SCAN**) is an independent web observatory that aggregates and serves live data from major space agencies (NASA, NOAA, ESA, JAXA, JPL) through a unified, low-latency interface. The platform combines satellite tracking (SGP4 propagation, TLE catalog), space weather monitoring, deep-space telemetry, AI-assisted translation of scientific data, and an AEGIS reasoning engine — delivered over HTTPS from a single-tenant production stack.

The system is built on Flask 3.1 with an application-factory pattern, 21 thematic blueprints, and 13 service modules. It serves 262 routes in production, with circuit breakers on every external dependency and graceful degradation across all critical paths.

---

## Capabilities

| Domain | Highlights |
|---|---|
| **Orbital tracking** | ISS live position & passes, SGP4 propagation, 1000+ satellite catalog, Cesium 3D globe |
| **Space weather** | NOAA SWPC alerts, Kp index, aurora forecasts, geomagnetic storm notifications |
| **Astronomy archives** | NASA APOD (auto-translated FR), JWST imagery, Hubble, Harvard MicroObservatory FITS, NASA SkyView |
| **Deep space missions** | Voyager 1/2 (JPL Horizons), Parker Solar Probe, BepiColombo, Mars rovers, DSN status |
| **Near-Earth objects** | NASA NEO feed, hazard classification (size, velocity, miss-distance) |
| **Hilal computation** | ODEH, UIOF, Oum Al Qura criteria for moon visibility (Hijri calendar) |
| **AI orchestration** | Multi-provider routing (Claude / Gemini / Groq / Grok), SSE streaming responses |
| **Observatory dashboard** | Live visitor analytics, geo-distribution, system health, circuit-breaker status |

---

## Production Snapshot

```
Stack            Flask 3.1 + Gunicorn (4 workers × 4 threads)
Entry point      wsgi:app  →  app.create_app("production")
Routes           262
Blueprints       21 (registered in app/__init__.py)
Services         13 (app/services/)
Database         SQLite + WAL  (archive_stellaire.db)
Reverse proxy    Nginx + Let's Encrypt (TLS)
Hosting          Hetzner Cloud (Hillsboro, Oregon, US-West)
Domain           astroscan.space
Observability    Sentry SDK 2.58 + structured logging
```

---

## Architecture

```
                    ┌──────────────────────────────┐
                    │      gunicorn wsgi:app       │
                    │   (4 workers × 4 threads)    │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │           wsgi.py            │
                    │   3-tier loader strategy:    │
                    │   1. ASTROSCAN_FORCE_MONOLITH│
                    │   2. create_app("production")│
                    │   3. fallback to monolith    │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
   ┌──────────▼─────────┐ ┌────────▼────────┐ ┌─────────▼──────┐
   │    station_web     │ │  app/__init__   │ │ app/services/  │
   │   (init globals,   │ │  create_app()   │ │  13 modules    │
   │   threads, cache)  │ │  21 blueprints  │ │  (pure logic)  │
   └────────────────────┘ └─────────────────┘ └────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
        external APIs        SQLite (WAL)         circuit breakers
   (NASA · NOAA · ESA ·     archive_stellaire    (per-API isolation,
    JPL · CelesTrak ·                            auto-recovery)
    Harvard · Cesium)
```

---

## Project Structure

```
astro_scan/
├── wsgi.py                       # Production entry (Gunicorn)
├── station_web.py                # Legacy monolith — globals + lazy imports
├── app/
│   ├── __init__.py               # create_app() — 21 BPs registered
│   ├── blueprints/               # 21 thematic blueprints
│   │   ├── feeds/                # 31 routes  — external feeds aggregator
│   │   ├── analytics/            # 18 routes  — visitors, geo, dashboard
│   │   ├── ai/                   # 16 routes  — AI orchestration & SSE
│   │   ├── cameras/              # 15 routes  — camera/gallery routes
│   │   ├── system/               # 20 routes  — health, status, debug
│   │   ├── weather/              # 18 routes  — NOAA, Kp, aurora
│   │   ├── api/                  # 19 routes  — public API
│   │   ├── lab/                  # 16 routes  — Hilal lab + experiments
│   │   ├── telescope/            # 16 routes  — telescope sources
│   │   ├── iss/                  # 14 routes  — ISS tracking & passes
│   │   ├── pages/                # 25 routes  — HTML pages
│   │   ├── satellites/           #  4 routes  — SGP4 propagation
│   │   ├── export/               #  5 routes  — data export
│   │   ├── astro/                #  8 routes  — astropy, ephemerides
│   │   ├── archive/              #  7 routes  — observation archive
│   │   ├── main/                 # 11 routes  — root, sitemap
│   │   ├── research/             #  6 routes  — research dashboard
│   │   ├── seo/                  #  3 routes  — sitemap.xml, robots.txt
│   │   ├── sdr/                  #  5 routes  — software-defined radio
│   │   ├── apod/                 #  3 routes  — NASA APOD
│   │   └── i18n/                 #  1 route   — translation endpoint
│   └── services/                 # 13 service modules (pure logic)
│       ├── ai_translate.py       # 480 LOC — multi-provider AI routing
│       ├── hilal_compute.py      # 404 LOC — Hijri visibility criteria
│       ├── analytics_dashboard.py# 319 LOC — visitor analytics
│       ├── external_feeds.py     # 307 LOC — NASA/NOAA/ESA aggregator
│       ├── weather_archive.py    # 238 LOC — historical weather
│       ├── oracle_engine.py      # 207 LOC — AEGIS reasoning core
│       ├── observatory_feeds.py  # 187 LOC — observatory data sources
│       ├── iss_compute.py        # 183 LOC — ISS pass predictions
│       ├── microobservatory.py   # 168 LOC — Harvard FITS interface
│       ├── telescope_sources.py  # 137 LOC — telescope data sources
│       ├── guide_engine.py       # 107 LOC — observation guide
│       └── http_client.py        #  86 LOC — hardened HTTP client
├── services/                     # Shared low-level services
│   ├── circuit_breaker.py        # Per-API circuit breakers
│   ├── cache_service.py          # In-memory cache layer
│   ├── orbital_service.py        # TLE + SGP4 propagation
│   ├── weather_service.py        # NOAA SWPC integration
│   ├── nasa_service.py           # NASA API client
│   ├── stats_service.py          # Visitor statistics
│   ├── ephemeris_service.py      # Sun/Moon ephemerides
│   └── db.py                     # SQLite WAL accessor
├── templates/                    # Jinja2 templates
├── static/                       # Static assets (JS, CSS, images)
├── requirements.txt              # Python dependencies
└── ARCHITECTURE.md               # Engineering deep-dive (FR)
```

---

## Tech Stack

**Backend**
- Flask 3.1.3, Werkzeug 3.1.6
- Gunicorn (sync workers, threaded)
- SQLite + WAL mode

**Astronomy & orbital mechanics**
- `sgp4` ≥ 2.21 — TLE propagation
- `skyfield` ≥ 1.46 — ephemerides, coordinate transforms
- `astropy` — astronomical computations
- `numpy` — vectorized math

**AI orchestration**
- Multi-provider routing: Anthropic Claude, Google Gemini, Groq, xAI Grok
- Server-Sent Events (SSE) streaming for chat responses
- Circuit breakers per provider with automatic failover

**External integrations**
- NASA APIs (APOD, NEO, DONKI, SkyView, Mars rovers)
- NOAA SWPC (space weather, Kp, alerts)
- JPL Horizons (Voyager, Parker, BepiColombo)
- CelesTrak (TLE catalog)
- Harvard MicroObservatory (FITS imagery)
- Cesium Ion (3D globe assets)

**Frontend**
- Cesium.js — 3D orbital globe
- Vanilla JS + Service Worker (PWA, Android-installable)

**Infrastructure**
- Nginx (reverse proxy, TLS termination)
- Let's Encrypt (certbot, auto-renewal)
- systemd unit (`astroscan.service`)
- Sentry SDK 2.58 (error tracking)
- Redis 5.x (optional cache backend)

---

## API Highlights

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Liveness probe (no external dependencies) |
| `GET /api/system-status` | Full system health (DB, cache, circuit breakers) |
| `GET /api/iss` | ISS live position + crew |
| `GET /api/iss/passes` | Next 5 ISS passes over Tlemcen |
| `GET /api/satellites` | TLE catalog (paginated) |
| `GET /api/weather` | NOAA Kp + aurora forecast |
| `GET /api/apod` | NASA APOD (FR auto-translated) |
| `GET /api/feeds/<source>` | Aggregated external feed (NASA/NOAA/ESA) |
| `GET /sitemap.xml` | SEO sitemap |
| `GET /robots.txt` | Crawler directives |

Full route map is generated at runtime: `python3 -c "from wsgi import app; [print(r) for r in app.url_map.iter_rules()]"`.

---

## Testing

The codebase ships with a three-tier pytest suite (`tests/smoke/`, `tests/unit/`,
`tests/integration/`) and a GitHub Actions workflow that runs smoke + unit on
every push.

```bash
make install-dev    # pytest + pytest-cov + pytest-mock
make test           # full suite
make test-smoke     # smoke tier only (factory, critical endpoints, WSGI loader)
make test-unit      # pure-logic services + blueprint registration
make test-coverage  # HTML + terminal coverage report (app/ + services/)
```

Baseline on a non-root host: **51 passed, 85 skipped, 0 failed**. Skips are
deliberate and environment-bound (root-only `.env`, Redis-backed circuit
breakers) — not regressions. See [tests/README.md](./tests/README.md) for
the full layout, markers, fixtures, and skip rationale.

---

## Migration History

This codebase underwent a 19-pass migration from a 12,159-line monolith to a blueprint+factory architecture, executed without service interruption:

| Pass | Scope | Outcome |
|---|---|---|
| 1–4   | Bootstrapping factory & first blueprints | 4 BPs registered |
| 5     | Pages + PWA routes | 25 routes migrated |
| 6     | Cameras + gallery + observations | 20 routes |
| 7     | Astropy + weather + ephemerides | 18 routes |
| 8     | NASA/NOAA external feeds | 14 routes |
| 9     | Telescope domain | 16 routes |
| 10    | AI orchestration + `ai_translate.py` extraction | 15 routes |
| 11    | Targeted audit + cleanup | 78% coverage |
| 12    | Visitors + analytics | 10 routes |
| 13    | Lab + research | 86% coverage |
| 14    | ISS compute + satellites | 92% coverage |
| 15    | Aggressive helper extraction | 96% coverage |
| 16    | Final blueprint registration | 99% coverage |
| 17    | Last 2 heavy AI routes | 99% coverage |
| 18    | **Production switch** — `wsgi.py → create_app()` | bascule complete |
| 19    | Monolith dead-code cleanup | −1,781 lines |

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full engineering record.

---

## Director

**Zakaria Chohra** — *Director, ORBITAL-CHOHRA Observatory*
Tlemcen, Algeria · 34.87°N · 1.32°E

The observatory operates as an independent scientific platform serving the Francophone and Arabic-speaking research community.

---

## License

Proprietary — © Zakaria Chohra / ORBITAL-CHOHRA Observatory.
Educational and scientific use is permitted with attribution. Commercial use, redistribution, or derivative works require explicit written authorization from the director.

---

## Acknowledgments

This platform builds on open data and APIs provided by:
NASA · NOAA SWPC · ESA · JAXA · JPL Horizons · CelesTrak · Harvard MicroObservatory · AMSAT · IAU · UNAWE.

Open-source foundations: Flask · Gunicorn · Skyfield · SGP4-Python · Astropy · NumPy · Cesium.js · Sentry.

---

<div align="center">

**ORBITAL-CHOHRA Observatory** — Tlemcen, Algeria
*Operated independently. Open to collaboration.*

</div>
