# ASTRO-SCAN

> *A work in progress. Open to feedback, critique, and improvement.*

**Astronomical observations from Tlemcen, Algeria — in real time, open to all.**
*Observations astronomiques depuis Tlemcen, Algérie — en temps réel, ouvertes à tous.*

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-yellow.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-live-brightgreen.svg)](https://astroscan.space)
[![Version](https://img.shields.io/badge/version-v2.7.4-blue.svg)](https://github.com/za1974ria/astroscan/releases/tag/v2.7.4-analytics-cockpit)
[![Lighthouse](https://img.shields.io/badge/Lighthouse-21%2F50%20PERFECT-success.svg)](https://github.com/za1974ria/astroscan/releases/tag/v2.8.0-lighthouse-58pct-ui-clean)
[![A11y](https://img.shields.io/badge/Accessibility-100%2F100%20on%2046%20modules-brightgreen.svg)](https://github.com/za1974ria/astroscan/releases/tag/v2.8.0-lighthouse-58pct-ui-clean)
[![CI](https://github.com/za1974ria/astroscan/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/za1974ria/astroscan/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/badge/coverage-25%25%20%E2%86%92%20%E2%89%A560%25%20target-yellow.svg)](#development)

🌐 **Live site:** https://astroscan.space
📐 **Methodology:** https://astroscan.space/methodology
🛰️ **Mission Control:** https://astroscan.space/mission-control

![ASTRO-SCAN Portal — ORBITAL-CHOHRA](docs/images/orbital-chohra-portail.png)

---

## About this project

ASTRO-SCAN is a small contribution to open astronomy, built and maintained from Tlemcen, Algeria.

The platform aggregates real-time astronomical data from public scientific sources and presents it through a unified web interface. It is offered as is — to be tested, challenged, and improved by anyone who finds it useful.

This is not an institutional observatory. It is an independent effort to make astronomical observation accessible from North Africa, using established open-source tools and public data feeds.

---

## What you can observe

| Module | Description | Data source |
|--------|-------------|-------------|
| **ISS & satellites** | Live positions of the International Space Station and tracked satellites | NORAD / CelesTrak TLE + Skyfield SGP4 |
| **Space weather** | Solar wind, Kp index, geomagnetic activity | NOAA SWPC |
| **Tonight's sky** | Planet visibility and ISS passes for Tlemcen | Astropy ephemerides |
| **Daily astronomy** | NASA Astronomy Picture of the Day | NASA APOD API |
| **Open data portal** | Raw scientific datasets for research and education | All sources above |

---

## Technical stack

- **Backend:** Python 3.10+, Flask (Blueprint architecture)
- **Orbital computation:** [Skyfield](https://rhodesmill.org/skyfield/) (SGP4 propagator)
- **Ephemerides:** [Astropy](https://www.astropy.org/)
- **TLE source:** [CelesTrak](https://celestrak.org/) (NORAD)
- **Space weather:** [NOAA SWPC](https://www.swpc.noaa.gov/)
- **Daily images:** [NASA APOD](https://api.nasa.gov/)
- **Frontend:** Vanilla HTML/CSS/JS (no framework dependency)
- **Database:** SQLite (lightweight DBs for archives, sessions, alerts)
- **Deployment:** Gunicorn + Nginx on Ubuntu VPS
- **Domain:** astroscan.space

---

## Performance & Quality

Continuous Lighthouse audits across all 50 modules (May 2026, v2.8.0):

| Metric | Score | Note |
|--------|-------|------|
| **Modules PERFECT 100/100/100/100** (stable, 5/5 audits) | **21 / 50** (42%) | Always at 100 in every audit |
| **Modules ≥3/5 audits PERFECT** (reliable) | **26 / 50** (52%) | Pass 100 in majority of audits |
| **Best-of-3 peak measurement** | **29 / 50** (58%) | Maximum observed in best run |
| **Accessibility ≥ 100/100** | **46 / 50** (92%) | WCAG 2.1 AA compliance |
| **SEO ≥ 100/100** | **50 / 50** (100%) | All modules indexed correctly |

Transformation: from **1 module PERFECT (1.9%)** baseline (May 16, 2026) to **21 stable + 29 peak (58%)** in 20 chirurgical sprints over 55 hours.

Methodology: [Lighthouse CLI](https://github.com/GoogleChrome/lighthouse) (headless Chrome), single-run + best-of-N consolidation against variance, scripts in [`audit/`](audit/).

Known structural limits (documented, not reducible without backend rewrite):
- `mission_control`, `orbital_map` — Cesium WebGL errors in headless Chrome (`BP=96`)
- `lab` — SQLite 503 race conditions on `/lab/raw/<image>` (`BP=96`)
- `europe_live` — YouTube embed same-site cookies (`BP=96`)

Full tag with detailed bilan: [v2.8.0-lighthouse-58pct-ui-clean](https://github.com/za1974ria/astroscan/releases/tag/v2.8.0-lighthouse-58pct-ui-clean)

---

## Project status

Active development. Current state can be summarized as:

- ✅ **Live in production** since April 2026
- ✅ **Real-time data feeds** from public scientific sources (NORAD, NOAA, NASA)
- ✅ **Bilingual interface** (English / French)
- ✅ **Open data portal** at [/data](https://astroscan.space/data)
- ✅ **Methodology page** live at [/methodology](https://astroscan.space/methodology)
- ✅ **Mission Control** orbital surveillance module at [/mission-control](https://astroscan.space/mission-control)
- ✅ **Lighthouse audit v2.8.0** — 21 modules at 100/100/100/100 stable (May 2026)
- ⏳ **Architecture migration** in progress (monolith → Flask Blueprints, Phase 2C)
- ⏳ **International scientific outreach** (ESA, NASA, IAU, UNAWE) — in preparation

---

## Quick start (local development)

```bash
# Clone the repo
git clone https://github.com/za1974ria/astroscan.git
cd astroscan

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables (see .env.example)
cp .env.example .env

# Run the development server
python station_web.py
```

The application will be available at `http://127.0.0.1:5003`.

---

## Roadmap

Current priorities (open to suggestions):

- Methodology page documenting computational methods and data sources
- Improved English-language documentation
- Performance optimization for low-bandwidth users
- Expanded coverage of North African observation conditions
- Better mobile experience

---

## Development

Setup once:

```bash
make install-dev    # installs dev deps + pre-commit hooks
```

Day-to-day:

```bash
make test           # all tests
make test-smoke     # smoke tests (no external deps)
make test-unit      # unit tests (pure logic)
make test-cov       # full suite with coverage report (term + HTML)
make lint           # ruff lint on tests/
make format         # ruff format + autofix on tests/
make precommit      # run all pre-commit hooks on all files
```

CI runs Python 3.11 + 3.12 matrix, ruff lint/format check, pytest, and a coverage gate (`--cov-fail-under=20`). The threshold is conservative — it tracks the worst-case attainable level without app-code changes — and is raised as new tests land. See `.github/workflows/test.yml`.

`pytest.ini` defines markers (`smoke`, `unit`, `integration`, `slow`) for filtering. `tests/conftest.py` provides Flask app fixtures and gracefully skips runs without read access to `.env` or writable `data/` (production runs as root and is unaffected).

---

## How to contribute

Feedback, bug reports, and suggestions are genuinely welcome.

- **Issues:** Open a GitHub issue for bugs or feature requests
- **Pull requests:** Always welcome, especially for documentation improvements
- **Scientific feedback:** If you spot a methodological error, please flag it — the project depends on rigor

There is no contributor's guide yet. For now, common sense and clear communication are enough.

---

## License

This project is released under the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)](LICENSE).

You are free to **share** and **adapt** the work for non-commercial purposes, as long as you:
- 📌 Give appropriate **attribution** to the author
- 🚫 Do not use it for **commercial purposes** without explicit permission
- 🔄 Distribute derivative works under the **same license**

For commercial use, hosted SaaS partnerships, or enterprise integration, please contact the maintainer via GitHub issues.

Full license text: [https://creativecommons.org/licenses/by-nc-sa/4.0/](https://creativecommons.org/licenses/by-nc-sa/4.0/)

---

## Acknowledgments

ASTRO-SCAN relies entirely on public scientific infrastructure made available by:

- **NASA** (APOD, ephemerides data)
- **NOAA** Space Weather Prediction Center
- **NORAD / CelesTrak** (TLE catalog)
- **The Skyfield project** (Brandon Rhodes)
- **The Astropy collaboration**

Without these open scientific resources, this project would not exist.

---

## Maintainer

Maintained by Zakaria Chohra, Tlemcen, Algeria.
For contact, please use GitHub issues or discussions.

---

*Last updated: May 18, 2026 — v2.8.0-lighthouse-58pct-ui-clean*
