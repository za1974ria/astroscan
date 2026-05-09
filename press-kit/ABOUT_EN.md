# About ASTRO-SCAN (English)

## One-line summary

**ASTRO-SCAN is a free, open-data, real-time space observatory built solo from Tlemcen, Algeria — bringing live NASA, NOAA, ESA, and JPL feeds to anyone with a browser.**

## Short description (50 words)

ASTRO-SCAN is a real-time astronomical observatory aggregating live data from NASA, NOAA, ESA, JPL, CelesTrak, and Harvard MicroObservatory into a unified, ad-free, bilingual (FR/EN) dashboard. Built solo by Zakaria Chohra in Tlemcen, Algeria, it serves the global research and education community with no paywall and no tracking.

## Medium description (150 words)

ASTRO-SCAN is an independent web observatory making real-time orbital intelligence and space science accessible to anyone with a browser. The platform aggregates live data from NASA (APOD, NEO, DONKI, SkyView, Mars rovers), NOAA Space Weather Prediction Center, ESA, JPL Horizons (Voyager, Parker Solar Probe, BepiColombo), CelesTrak, Harvard MicroObservatory, and N2YO into a unified, bilingual (French/English) dashboard.

Built solo by Zakaria Chohra in Tlemcen, Algeria, ASTRO-SCAN runs on a hardened Flask 3.1 production stack (25 blueprints, 266 routes, 13 services) with Gunicorn, Nginx, and Let's Encrypt SSL. The platform exposes zero third-party API keys to the frontend, integrates an AEGIS AI chatbot for astronomical Q&A (Claude, Gemini, Groq, Grok), and serves as a full ISS tracker with SGP4 pass predictions.

ASTRO-SCAN is free under CC BY-NC-SA 4.0 for education, research, and public outreach. As of May 2026, it has reached 2,195+ visitors across 49+ countries.

## Long description (300 words)

**ASTRO-SCAN** is an independent, real-time space observatory built and operated solo by **Zakaria Chohra** from Tlemcen, Algeria (34.87°N · 1.32°W). The mission is straightforward: take the firehose of open scientific data published daily by NASA, NOAA, ESA, JPL, and partner agencies, and turn it into a unified, ad-free, bilingual interface that anyone — student, researcher, journalist, citizen scientist — can use without registration, paywall, or tracking.

**What it does.** ASTRO-SCAN tracks the International Space Station live (SGP4/TLE propagation), predicts visible passes for any observer, monitors space weather (NOAA SWPC: Kp index, geomagnetic storms, aurora forecasts), serves NASA's Astronomy Picture of the Day with AI-translated French commentary, integrates JWST and Hubble feeds, computes deep-space mission positions (Voyager 1/2, Parker Solar Probe, BepiColombo) via JPL Horizons, indexes 1,500+ anomaly observations, and operates a software-defined radio (SDR) panel with 8 NASA audio channels. An AEGIS AI chatbot answers astronomical questions in French and English, routing across Anthropic Claude, Google Gemini, Groq, and xAI Grok with automatic failover.

**How it's built.** Production stack: Flask 3.1 (factory pattern, 25 blueprints, 266 routes, 13 service modules), Gunicorn (4 preloaded workers), Nginx reverse proxy, Let's Encrypt SSL, SQLite + WAL, optional Redis cache, Sentry observability, structured logging, per-API circuit breakers. The codebase underwent a 19-pass live migration from a 12,159-line monolith to a blueprint+factory architecture, executed without service interruption.

**Why it matters.** ASTRO-SCAN is one of the few space observatories operating from North Africa, with a bilingual French/English UI (hreflang sitemap, cookie persistence) explicitly serving Francophone and Arabic-speaking communities. It is licensed CC BY-NC-SA 4.0 — free for education, research, and outreach — and welcomes scientific collaboration with universities, agencies, and observatories worldwide.

**As of May 2026: 2,195+ unique visitors · 49+ countries reached · 8 external data sources · 266 routes · zero ads.**
