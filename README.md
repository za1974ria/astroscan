# ASTRO-SCAN

> *A work in progress. Open to feedback, critique, and improvement.*

**Astronomical observations from Tlemcen, Algeria — in real time, open to all.**
*Observations astronomiques depuis Tlemcen, Algérie — en temps réel, ouvertes à tous.*

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-yellow.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-live-brightgreen.svg)](https://astroscan.space)

🌐 **Live site:** https://astroscan.space

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

## Project status

Active development. Current state can be summarized as:

- ✅ **Live in production** since April 2026
- ✅ **Real-time data feeds** from public scientific sources (NORAD, NOAA, NASA)
- ✅ **Bilingual interface** (English / French)
- ✅ **Open data portal** at [/data](https://astroscan.space/data)
- ⏳ **Architecture migration** in progress (monolith → Flask Blueprints)
- ⏳ **Methodology page** in preparation

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

## How to contribute

Feedback, bug reports, and suggestions are genuinely welcome.

- **Issues:** Open a GitHub issue for bugs or feature requests
- **Pull requests:** Always welcome, especially for documentation improvements
- **Scientific feedback:** If you spot a methodological error, please flag it — the project depends on rigor

There is no contributor's guide yet. For now, common sense and clear communication are enough.

---

## License

This project is released under the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)](LICENSE).

In short: free for educational, scientific and personal use, with attribution and share-alike. Commercial use requires a separate license — see [LICENSE](LICENSE) for details.

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

*Last updated: May 2026*
