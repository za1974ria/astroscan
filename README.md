# 🔭 ORBITAL-CHOHRA — Real-Time Web Observatory

<div align="center">

![Status](https://img.shields.io/badge/Status-OPERATIONAL-00ff88?style=for-the-badge)
![Platform](https://img.shields.io/badge/Platform-Web-00d4ff?style=for-the-badge)
![Language](https://img.shields.io/badge/Language-French%20%7C%20English-ffffff?style=for-the-badge)
![License](https://img.shields.io/badge/License-Open%20Science-brightgreen?style=for-the-badge)

**The first free, real-time, French-language web space observatory — built from Tlemcen, Algeria.**

🌐 **Live Platform**: [astroscan.space](https://astroscan.space) | [orbital-chohra-dz.duckdns.org](https://orbital-chohra-dz.duckdns.org)

</div>

---

## 🌌 What is ORBITAL-CHOHRA?

ORBITAL-CHOHRA (also known as **ASTRO-SCAN**) is a free, open-access web platform that brings real-time space data to the French-speaking world. Built by a solo developer from **Tlemcen, Algeria**, it aggregates live data from NASA, ESA, NOAA, and other space agencies into a single, unified French-language interface.

**No registration. No subscription. No cost. Just space.**

> *"One person. One AI. Zero budget. A window to the universe — from Tlemcen."*

---

## ✨ Key Features

### 🛸 Live Space Tracking
- **ISS Real-Time Tracking** — Live position, altitude, velocity, crew names
- **ISS Pass Predictions** — Next 5 passes over Tlemcen (34.87°N, 1.32°E) via SGP4/TLE
- **3D Orbital Globe** — Cesium.js powered globe with 1,000+ real satellites

### 🌞 Space Weather
- **NOAA SWPC Alerts** — Geomagnetic storms, solar flares, radiation events (last 24h)
- **Real-time Kp Index** — Aurora forecast and geomagnetic activity
- **Notification System** — Live bell alert 🔔 when Kp > 4 or active NOAA alerts

### 🔭 Astronomy Data
- **NASA APOD** — Astronomy Picture of the Day with French AI translation (Gemini)
- **JWST Images** — 6 live James Webb Space Telescope images
- **Hubble Archive** — Latest HST observations
- **Harvard MicroObservatory** — Real FITS astronomical images
- **NASA SkyView** — Multi-wavelength sky survey viewer

### 🚀 Deep Space Missions
- **Voyager 1 & 2** — Real-time distance from Sun (JPL Horizons API)
- **Parker Solar Probe** — Live telemetry
- **BepiColombo** — ESA/JAXA mission to Mercury
- **Mars Rovers** — Perseverance & Curiosity latest photos (NASA API)
- **DSN Live** — Deep Space Network communication status (Goldstone, Madrid, Canberra)

### ☄️ Near-Earth Objects
- **NASA NEO API** — Asteroids approaching Earth (today & this week)
- **Hazard classification** — Size, velocity, miss distance

### 🧠 AI Integration
- **AEGIS AI Chatbot** — Powered by Gemini, answers astronomical questions in French
- **Auto-translation Daemon** — Translates NASA/ESA observations to French in real time
- **Space Intelligence** — AI-powered alerts: events, risk index, Kp forecasting

---

## 🏗️ Technical Architecture

```
ORBITAL-CHOHRA
├── Backend          Flask + Gunicorn (Python)
├── Database         SQLite (archive_stellaire.db)
├── Reverse Proxy    Nginx + Let's Encrypt (HTTPS)
├── Hosting          Hetzner Cloud (Helsinki, Finland)
├── Domain           astroscan.space (OVH) + DuckDNS
├── Analytics        Google Analytics GA4
└── PWA              Android-installable (Service Worker v140)

External APIs
├── NASA             APOD, NEO, DONKI, SkyView, Mars Rovers
├── JPL Horizons     Voyager 1 & 2, Parker Solar Probe
├── CelesTrak        TLE data (15,000+ satellites)
├── NOAA SWPC        Space weather alerts
├── Harvard MO       MicroObservatory FITS images
├── Google Gemini    AI translation + AEGIS chatbot
└── Cesium Ion       3D globe rendering
```

---

## 🌍 Mission & Vision

ORBITAL-CHOHRA was born from a simple observation: **500 million French and Arabic speakers have no unified, free, real-time portal for space science**.

### Goals
- 🎓 **Education** — Make space science accessible to students across North Africa and the Francophone world
- 🔬 **Citizen Science** — Provide real astronomical data to amateur astronomers
- 🤝 **International Collaboration** — Bridge the gap between global space agencies and the Global South
- 🌙 **Inspiration** — Show that world-class science platforms can be built from anywhere

### Target Audience
- Students and teachers in Francophone Africa
- Amateur astronomers across the Maghreb region
- Space enthusiasts in France, Belgium, Canada, and the broader French-speaking world
- Research institutions seeking public outreach tools

---

## 📊 Observatory Dashboard

The platform includes a **Research Dashboard** (`/dashboard`) with:
- Live visitor counter & geographic distribution (GEO-IP tracker)
- System status monitoring (LIVE/SIMULATION/OFFLINE modes)
- AEGIS AI test interface
- Solar Shield adaptive display system

---

## 🏆 Uniqueness

A global search confirms: **no equivalent platform exists** combining all of the following:
- ✅ Entirely in French
- ✅ Free with no registration
- ✅ Real-time ISS + Deep Space + Solar Weather + NEO in one interface
- ✅ AI-powered French translation of NASA/ESA data
- ✅ Live 3D orbital map with 1,000+ satellites
- ✅ Built in and for the Global South

---

## 👨‍🔬 Director & Developer

**Zakaria Chohra**
Independent Developer & Observatory Director
📍 Tlemcen, Algeria (34.87°N, 1.32°E)
🌐 Station IP: 5.78.153.17 (Hetzner Helsinki)

*Built solo with Python, Flask, JavaScript, and AI assistance.*
*Dedicated to the scientific community of the Arab and Francophone world.*

---

## 🤝 Collaboration & Outreach

ORBITAL-CHOHRA has reached out to:
- **UNAWE** (Universe Awareness) — info@unawe.org
- **IAU** (International Astronomical Union) — public@iau.org
- **ESA Education** — ESA Education Division
- **Astronomers Without Borders**

We welcome collaboration with:
- Space agencies for data partnerships
- Educational institutions for curriculum integration
- Citizen science networks for observation programs
- Researchers interested in public astronomy outreach

**Contact**: Available via GitHub Issues or platform contact form.

---

## 🚀 Running Locally

```bash
git clone https://github.com/[your-username]/orbital-chohra
cd orbital-chohra
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
python station_web.py
```

**Required API Keys** (free tiers available):
- `NASA_API_KEY` — api.nasa.gov
- `GEMINI_API_KEY` — Google AI Studio
- `N2YO_API_KEY` — n2yo.com (satellite tracking)
- `CESIUM_ION_TOKEN` — cesium.com

---

## 📈 Roadmap

- [ ] Public API documentation (REST endpoints)
- [ ] Multi-language support (Arabic, English)
- [ ] Mobile app (React Native)
- [ ] Citizen science contribution system
- [ ] Partnership with CRAAG (Centre de Recherche en Astronomie, Astrophysique et Géophysique, Algeria)

---

## 📄 License

This project is open for educational and scientific use.
Commercial use requires explicit permission from the author.

---

<div align="center">

**Built with ❤️ from Tlemcen, Algeria 🇩🇿**

*"The universe belongs to everyone. Knowledge should too."*

⭐ Star this repo if ORBITAL-CHOHRA inspires you!

</div>
