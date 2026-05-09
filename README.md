<div align="center">

# 🛰️ ASTRO-SCAN

### Real-time Space Observatory · Open Scientific Data
*Observatoire spatial en temps réel · Données scientifiques ouvertes*

[![Live](https://img.shields.io/badge/🌐_Live-astroscan.space-00ff88?style=for-the-badge)](https://astroscan.space)
[![Security Policy](https://img.shields.io/badge/🛡️_Security-Policy-blue?style=for-the-badge)](./SECURITY.md)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-CC_BY--NC--SA_4.0-EF9421?style=for-the-badge)](./LICENSE)

**[🌐 Live Demo](https://astroscan.space)** · **[📊 Dashboard](https://astroscan.space/portail)** · **[📡 Orbital Live](https://astroscan.space/orbital)** · **[🔭 Observatory](https://astroscan.space/observatoire)**

**🇫🇷 [Version française](https://astroscan.space)** · **🇬🇧 [English version](https://astroscan.space/?lang=en)** · **📰 [Press Kit](./press-kit/)**

</div>

---

## 🌍 What is ASTRO-SCAN?

**ASTRO-SCAN** is a real-time astronomical observatory platform that aggregates live data from NASA, NOAA, ESA, JPL, CelesTrak, Harvard MicroObservatory, and N2YO into a unified open-access scientific dashboard. Built solo by **Zakaria Chohra** in Tlemcen, Algeria (34.87°N · 1.32°W).

**EN** · A free, ad-free, open-data observatory that brings space science to anyone with a browser. Live ISS tracking, NOAA space weather, NASA Astronomy Picture of the Day, electromagnetic spectrum monitoring, and AI-powered anomaly detection — all served from a hardened production stack with zero third-party API keys exposed to the frontend.

**FR** · Un observatoire gratuit, sans publicité, en données ouvertes, qui met la science spatiale à portée de tout navigateur. Suivi ISS en direct, météo spatiale NOAA, image astronomique du jour de la NASA, monitoring du spectre électromagnétique, et détection d'anomalies par IA — le tout servi depuis une infrastructure de production durcie, sans aucune clé d'API exposée côté client.

---

## 📊 Live Stats

| Metric | Value |
|---|---|
| **Total visitors** (humans, deduplicated) | **2,195+** |
| **Countries reached** | **49+** |
| **Top regions** | 🇺🇸 USA · 🇩🇿 Algeria · 🇨🇳 China · 🇳🇱 Netherlands · 🇸🇬 Singapore · 🇩🇪 Germany · 🇬🇧 UK |
| **External data sources** | 8 (NASA JPL Horizons · NOAA SWPC · NASA APOD · N2YO · CelesTrak · Open-Notify · Harvard MicroObservatory · Skyfield) |
| **Languages** | 🇫🇷 French · 🇬🇧 English (cookie-persistent + hreflang sitemap) |
| **Architecture** | 291 routes · 29 blueprints · 26 services · Phase 2C complete |

*Live counter updates daily on [astroscan.space](https://astroscan.space).*

---

## ⚡ Features

### 🛰️ Real-time Orbital Tracking
- **ISS live position** with SGP4/TLE-based pass predictions
- **N2YO API** integration for satellite passes (radio + visual)
- **CelesTrak GP** active satellites database
- Live globe visualization (Cesium 3D + custom Canvas rendering)

### 🌌 Astronomical Data
- **NASA APOD** (Astronomy Picture of the Day) with AI translation FR/EN
- **JWST** observation panel
- **Hubble** + **Harvard MicroObservatory** FITS feed
- Sky map and ephemerides (Skyfield · Astropy)
- Anomaly detection archive (1,500+ observations indexed)

### ⛈️ Space Weather
- **NOAA SWPC** integration: Kp index, solar wind, geomagnetic storms
- **Aurora forecast** by region (real-time SWPC alerts)
- Telegram alert pipeline for storm-class events

### 📡 Radio Observatory (ORBITAL-RADIO)
- 8 NASA audio channels
- SDR satellite pass countdown
- Frequency monitoring with capture indicator

### 🤖 AI Integration
- **AEGIS AI chatbot** (French/English astronomical Q&A, SSE streaming)
- **Multi-LLM analysis pipeline**: Anthropic Claude · Google Gemini · Groq · xAI Grok
- Provider failover via per-API circuit breakers
- Anomaly detection from raw observation feeds

### 🌙 Hilal & Hijri Computation
- Multi-criteria moon visibility: ODEH · UIOF · Oum Al Qura
- Hijri calendar synchronization

### 🌐 Production-Grade Infrastructure
- **29 Flask blueprints**, **291 routes**, **26 service modules**
- **Server-side proxy** for all external API keys (zero frontend exposure)
- **Bilingual FR/EN** with cookie persistence + hreflang sitemap
- **Schema.org Observatory** structured data for SEO
- **Sentry** error monitoring + structured logging
- **Build info endpoint** (`/api/build`) for due-diligence and uptime monitoring

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│              astroscan.space (HTTPS)                 │
│         Let's Encrypt SSL via certbot                │
└─────────────────────┬────────────────────────────────┘
                      │ nginx reverse proxy
         ┌────────────▼────────────┐
         │  Gunicorn (4 workers)   │
         │  preloaded · port 5003  │
         └────────────┬────────────┘
                      │
     ┌────────────────▼─────────────────┐
     │  Flask Factory  create_app()     │
     │  29 blueprints · 291 routes      │
     │  app/hooks.py · 8 hooks          │
     │  app/bootstrap.py · 5 threads    │
     └─┬───────────────┬────────────────┬┘
       │               │                │
   ┌───▼───┐    ┌──────▼──────┐  ┌──────▼──────┐
   │ APIs  │    │  Templates  │  │  Background │
   │       │    │   Jinja2    │  │   threads   │
   │ NASA  │    │  bilingual  │  │             │
   │ NOAA  │    │   FR/EN     │  │ TLE refresh │
   │ ESA   │    └─────────────┘  │ APOD cache  │
   │ JPL   │                     │ Translate   │
   │ N2YO  │                     │ Skyview     │
   │ JWST  │                     │ Watchdog    │
   └───────┘                     └─────────────┘
       │
   ┌───▼─────────────────────────────────────────┐
   │  SQLite (WAL)  ·  archive_stellaire.db      │
   │  visitor_log · anomalies · observations     │
   └─────────────────────────────────────────────┘
```

Engineering deep-dive: **[ARCHITECTURE.md](./ARCHITECTURE.md)**

---

## 🛠️ Tech Stack

**Backend** · Flask 3.1 · Werkzeug 3.1 · Gunicorn (preloaded, 4 workers) · SQLite + WAL · Redis (optional cache)

**Astronomy & orbital mechanics** · `sgp4` ≥ 2.21 (TLE propagation) · `skyfield` ≥ 1.46 (ephemerides) · `astropy` · `numpy`

**AI orchestration** · Anthropic Claude · Google Gemini · Groq · xAI Grok · SSE streaming · per-provider circuit breakers

**External integrations** · NASA APOD/NEO/DONKI/SkyView/Mars rovers · NOAA SWPC · JPL Horizons (Voyager, Parker, BepiColombo) · CelesTrak · Harvard MicroObservatory FITS · Cesium Ion

**Frontend** · Cesium.js (3D globe) · Vanilla JS · Service Worker (PWA, Android-installable) · Schema.org structured data

**Infrastructure** · Nginx + Let's Encrypt · systemd (`astroscan.service`) · Sentry SDK 2.58 · structured logging · Hetzner Cloud

---

## 🔌 API Highlights

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Liveness probe (no external dependencies) |
| `GET /api/build` | Build info (commit SHA, deploy time) |
| `GET /api/system-status` | Full system health (DB, cache, circuit breakers) |
| `GET /api/iss` | ISS live position + crew |
| `GET /api/iss/passes` | Next 5 ISS passes over Tlemcen |
| `GET /api/satellites` | TLE catalog (paginated) |
| `GET /api/weather` | NOAA Kp + aurora forecast |
| `GET /api/apod` | NASA APOD (FR auto-translated) |
| `GET /api/feeds/<source>` | Aggregated external feed (NASA/NOAA/ESA) |
| `GET /sitemap.xml` | SEO sitemap (hreflang FR/EN) |

Full route map at runtime: `python3 -c "from wsgi import app; [print(r) for r in app.url_map.iter_rules()]"` — see also [docs/API_ENDPOINTS.md](./docs/API_ENDPOINTS.md).

---

## 🧪 Testing

The codebase ships with a three-tier pytest suite (`tests/smoke/`, `tests/unit/`, `tests/integration/`) and a GitHub Actions workflow that runs smoke + unit on every push.

```bash
make install-dev    # pytest + pytest-cov + pytest-mock
make test           # full suite
make test-smoke     # smoke tier (factory, critical endpoints, WSGI loader)
make test-unit      # pure-logic services + blueprint registration
make test-coverage  # HTML + terminal coverage report (app/ + services/)
```

Baseline on a non-root host: **51 passed · 85 skipped · 0 failed**. Skips are deliberate and environment-bound (root-only `.env`, Redis-backed circuit breakers) — not regressions. See [tests/README.md](./tests/README.md) for layout, markers, fixtures, and skip rationale.

---

## 📜 Migration History

This codebase underwent a **19-pass migration** from a 12,159-line monolith to a blueprint+factory architecture, executed without service interruption:

| Pass | Scope | Outcome |
|---|---|---|
| 1–4 | Factory bootstrapping + first blueprints | 4 BPs registered |
| 5–10 | Pages, cameras, weather, feeds, telescope, AI | 108 routes migrated |
| 11–17 | Audit, analytics, lab, ISS, helpers, full registration | 99% coverage |
| 18 | **Production switch** — `wsgi.py → create_app()` | bascule complete |
| 19 | Monolith dead-code cleanup | −1,781 lines |
| 20–30 | Hardening, SEO, i18n, security, observability | production-grade |

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full engineering record.

---

## 👨 About Zakaria

**Zakaria Chohra** — *Built ASTRO-SCAN solo · Tlemcen, Algeria*
34.87°N · 1.32°W

Independent solo developer. Built ASTRO-SCAN to make real-time orbital intelligence and space science accessible to the Francophone, Arabic-speaking, and global research communities.

📧 **zakaria.chohra@gmail.com** · 🌍 **[astroscan.space](https://astroscan.space)** · 📰 **[Press Kit](./press-kit/)**

---

## 📰 Press & Outreach

For journalists, institutional partners (NASA, ESA, CNES, IAU, universities), or research collaborations:

- **Press Kit (bilingual FR/EN)**: [`./press-kit/`](./press-kit/)
- **Media contact**: zakaria.chohra@gmail.com
- **High-resolution screenshots**: [`./press-kit/screenshots/`](./press-kit/screenshots/)

---

## 📄 License

ASTRO-SCAN is licensed under **[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](./LICENSE)**.

- ✅ Free for **education, research, citizen science, and public outreach**
- 📌 Attribution required (Zakaria Chohra · ASTRO-SCAN)
- 🚫 Commercial use requires written authorization — contact `zakaria.chohra@gmail.com`

---

## 🙏 Acknowledgments

Built on open data and APIs provided by:
**NASA** · **NOAA SWPC** · **ESA** · **JAXA** · **JPL Horizons** · **CelesTrak** · **Harvard MicroObservatory** · **N2YO** · **Open-Notify** · **AMSAT** · **IAU** · **UNAWE**

Open-source foundations: Flask · Gunicorn · Skyfield · SGP4-Python · Astropy · NumPy · Cesium.js · Sentry.

---

<div align="center">

### 🛰️ ASTRO-SCAN Observatory
**Tlemcen, Algeria** · *Operated independently · Open to scientific collaboration*

*"The universe belongs to everyone. Knowledge should too."*

</div>
