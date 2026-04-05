# Rapport détaillé — ASTRO-SCAN (ORBITAL-CHOHRA)

**Projet :** Station web observatoire astronomique  
**Directeur :** Zakaria Chohra · Tlemcen, Algérie  
**Environnement :** Hillsboro · Linux · 5.78.153.17  
**Date :** Mars 2026

---

## 1. Vue d’ensemble

ASTRO-SCAN est une application web Flask (Python 3) qui agrège des flux astronomiques en temps réel : télescope live (APOD, Hubble, archive), ISS avec carte et géolocalisation (BigDataCloud), sondes (Voyager, Mars, JWST, Hubble, BepiColombo), alertes NEO et météo solaire, passages ISS (Tlemcen), Deep Space Network, catalogue Messier/DSO, système solaire interactif, quiz, tuteur IA (Gemini/Groq), radio SDR, NASA SkyView. Inclut un **Mode Scientifique** (/scientific) et un **Portail** (/portail) comme hub avec sidebar et grille de cartes. Compteur de visites, traduction EN→FR (Gemini), API publique v1.

---

## 2. Architecture des connexions

### 2.1 Schéma des pages et liens HTML

```
/ (racine)
  └── redirect → /observatoire

/portail (portail.html)
  ├── Sidebar : Accueil, Dashboard, Overlord, Galerie, Observatoire, Vision 2026
  ├── Lien direct : <a href="/scientific"> MODE SCIENTIFIQUE (PRO)
  ├── Splash (grille) : cartes → navigate('home'|'dashboard'|'overlord'|'galerie'|'observatoire'|'vision')
  ├── Splash : window.open('/scientific') (x2), window.open('http://5.78.153.17:5000')
  ├── Iframes (lazy) : data-src="/dashboard", "/overlord_live", "/galerie", "/observatoire?v=1002", "/vision"
  └── Scripts : /api/visits, /api/iss, /api/sdr/status, /api/sdr/passes, /api/hubble/images, /api/latest, /api/voyager-live
  └── Static : /static/sondes_aegis.js?v=999

/observatoire (observatoire.html)
  ├── Nav : tabs telescope, accueil, archive, iss, sondes, catalogue, systeme, quiz, ia, radio, deep, skyview
  ├── Bouton : window.open('/scientific') → MODE SCIENTIFIQUE
  ├── Tab : switchTab('lab') → panel-lab (LABORATOIRE)
  ├── Déconnexion : location.href='/portail' ou '/'
  ├── Iframe : /galerie?embed=1 (dans panel-archive)
  └── Lien externe : https://www.n2yo.com/space-station/

/scientific (scientific.html)
  ├── Header : <a href="/portail"> ← PORTAIL
  ├── Section Laboratoire : <a href="/portail"> Retour au portail, <a href="/observatoire"> Observatoire
  └── Fetch : /api/v1/iss, /api/moon, /api/v1/solar-weather, /api/v1/tonight, /api/v1/catalog, /api/v1/asteroids, /api/live/spacex

/dashboard, /overlord_live, /galerie, /vision, /vision-2026, /sondes, /ce_soir, /mission-control, /telescopes, /globe
  └── Templates respectifs ou rendu dynamique
```

### 2.2 Connexions API (côté frontend)

| Page / panel | Appels fetch / src |
|--------------|--------------------|
| **observatoire** | /api/image, /api/title, /api/latest, /api/telescope/live, /api/astro/explain, /api/visits, /api/live/mars-weather, /api/alerts/all, /api/hubble/images, /api/bepi/telemetry, /api/live/iss-passes, /api/sondes, /api/dsn, /api/sdr/*, /api/chat, /api/skyview/*, wheretheiss.at, bigdatacloud.net, api.nasa.gov (APOD, NEO, InSight), api.le-systeme-solaire.net (Voyager) |
| **portail** | /api/visits, /api/iss, /api/sdr/status, /api/sdr/passes, /api/hubble/images, /api/latest, /api/voyager-live |
| **scientific** | /api/v1/iss, /api/moon, /api/v1/solar-weather, /api/v1/tonight, /api/v1/catalog, /api/v1/asteroids, /api/live/spacex |

---

## 3. Routes complètes (station_web.py)

### 3.1 Pages HTML (render_template)

| Route | Méthode | Template | Description |
|-------|---------|----------|-------------|
| `/` | GET | — | Redirect → /observatoire |
| `/portail` | GET | portail.html | Hub avec sidebar + splash |
| `/observatoire` | GET | observatoire.html | Observatoire multi-onglets |
| `/scientific` | GET | scientific.html | Mode scientifique (ISS, Lune, catalogue, lab) |
| `/dashboard` | GET | index.html | Dashboard QG |
| `/overlord_live` | GET | overlord_live.html | Overlord Live |
| `/galerie` | GET | (données DB) | Archive stellaire |
| `/vision` | GET | vision.html | Vision 2026 |
| `/vision-2026` | GET | vision_2026.html | Vision 2026 alt |
| `/sondes` | GET | sondes.html | Sondes spatiales |
| `/ce_soir` | GET | ce_soir.html | Ciel ce soir |
| `/mission-control` | GET | (template) | Mission control |
| `/telescopes` | GET | (template) | Télescopes |
| `/globe` | GET | (template) | Globe |

### 3.2 API — Visites, Télescope, Image

| Route | Méthode | Description |
|-------|---------|-------------|
| `/api/visits` | GET | Compteur visites |
| `/api/visits/increment` | POST | Incrémente visites |
| `/api/latest` | GET | Dernières observations (DB) |
| `/api/sync/state` | GET, POST | État sync télescope |
| `/api/telescope/sources` | GET | Liste sources image |
| `/api/telescope/live` | GET | APOD du jour (titre + explication FR) |
| `/api/image` | GET | Image (live/apod/hubble/apod_archive) |
| `/api/title` | GET | Titre courant |

### 3.3 API — ISS, Sondes, Mission, DSN

| Route | Méthode | Description |
|-------|---------|-------------|
| `/api/iss` | GET | Position ISS (wheretheiss.at / cache) |
| `/api/sondes` | GET | Agrégat sondes (ISS, Mars, Voyager, Hubble, JWST…) |
| `/api/dsn` | GET | Deep Space Network (eyes.nasa.gov/dsn) |
| `/api/live/iss-passes` | GET | Passages ISS (Tlemcen, open-notify ou N2YO) |
| `/api/passages-iss` | GET | Passages ISS |
| `/api/iss-passes` | GET | Passages ISS (N2YO si clé) |
| `/api/voyager-live` | GET | Voyager (JPL Horizons) |
| `/api/mission-control` | GET | Vue mission control |
| `/api/survol` | GET | Survol (wheretheiss + nominatim) |

### 3.4 API — Publique v1

| Route | Méthode | Description |
|-------|---------|-------------|
| `/api/v1/iss` | GET | ISS (orbit_engine: position + équipage) |
| `/api/v1/planets` | GET | Liste 8 planètes |
| `/api/v1/asteroids` | GET | NEO du jour (NASA NeoWs, cache 1h) |
| `/api/v1/solar-weather` | GET | Météo solaire (NOAA, cache 5min) |
| `/api/v1/catalog` | GET | Catalogue Messier (q=) |
| `/api/v1/tonight` | GET | Ciel ce soir Tlemcen (cache 1h) |

### 3.5 API — Flux, News, Hubble, Mars, SpaceX

| Route | Méthode | Description |
|-------|---------|-------------|
| `/api/live/spacex` | GET | Lancements SpaceX (spacexdata.com) |
| `/api/live/news` | GET | News (spaceflightnewsapi + traduction) |
| `/api/live/mars-weather` | GET | Météo Mars (InSight) |
| `/api/live/all` | GET | Agrégat live |
| `/api/hubble/images` | GET | Images Hubble (NASA APOD count=6 + MAST) |
| `/api/jwst/images` | GET | Images JWST (MAST) |
| `/api/mars/weather` | GET | InSight weather |
| `/api/news` | GET | News |

### 3.6 API — Alertes, NEO, Bepi, MAST

| Route | Méthode | Description |
|-------|---------|-------------|
| `/api/alerts/asteroids` | GET | Alertes NEO (NASA feed) |
| `/api/alerts/solar` | GET | Météo solaire (NOAA SWPC) |
| `/api/alerts/all` | GET | Asteroids + solar |
| `/api/neo` | GET | NEO (NASA feed) |
| `/api/bepi/telemetry` | GET | BepiColombo (JPL Horizons -121) |
| `/api/mast/targets` | GET | Cibles MAST |

### 3.7 API — SDR, SkyView, Chat, Traduction

| Route | Méthode | Description |
|-------|---------|-------------|
| `/api/sdr/status` | GET | Statut SDR |
| `/api/sdr/passes` | GET | Passages NOAA (TLE CelesTrak) |
| `/api/sdr/stations` | GET | Stations réceptrices |
| `/api/sdr/captures` | GET | Liste captures |
| `/api/skyview/targets` | GET | Cibles SkyView |
| `/api/skyview/fetch` | POST | Récupération image SkyView |
| `/api/skyview/multiwave/<id>` | GET | Multi-longueur d’onde |
| `/api/skyview/list` | GET | Liste images |
| `/api/chat` | POST | Tuteur IA (Gemini / Groq) |
| `/api/translate` | POST | Traduction |
| `/api/astro/explain` | POST | Traduction EN→FR (Gemini) |
| `/api/astro/object` | GET, POST | Explication objet céleste |

### 3.8 API — Catalogue, Ciel, Santé, Divers

| Route | Méthode | Description |
|-------|---------|-------------|
| `/api/catalog` | GET | Catalogue DSO |
| `/api/catalog/<obj_id>` | GET | Objet catalogue |
| `/api/tonight` | GET | Ciel ce soir (observation_planner) |
| `/api/moon` | GET | Phase lunaire |
| `/api/microobservatory` | GET | Cibles MicroObservatory NASA |
| `/api/health` | GET | Santé service |
| `/api/aegis/status` | GET | Statut AEGIS |
| `/api/shield` | GET | Shield |
| `/api/telescope-hub` | GET | Telescope hub (sources) |
| `/api/classification/stats` | GET | Stats classification |
| `/api/meteo-spatiale` | GET | Météo spatiale |
| `/api/feeds/voyager` | GET | Feed Voyager |
| `/api/feeds/neo` | GET | Feed NEO |
| `/api/feeds/solar` | GET | Feed solaire |
| `/api/feeds/solar_alerts` | GET | Alertes solaires |
| `/api/feeds/mars` | GET | Feed Mars |
| `/api/feeds/apod_hd` | GET | APOD HD |
| `/api/feeds/all` | GET | Tous feeds |
| `/api/push/subscribe` | POST | PWA push |
| `/sw.js` | GET | Service Worker |
| `/manifest.json` | GET | Manifest PWA |
| `/static/<path>` | GET | Fichiers statiques |

---

## 4. Connexions externes (URLs complètes)

### 4.1 Depuis le backend (station_web.py + modules)

| Service | URL / usage |
|---------|-------------|
| **NASA APOD** | https://api.nasa.gov/planetary/apod?api_key=… |
| **NASA APOD (date)** | https://api.nasa.gov/planetary/apod?api_key=…&date=… |
| **NASA NEO feed** | https://api.nasa.gov/neo/rest/v1/feed?start_date=…&end_date=…&api_key=… |
| **NASA NEO 99942** | https://api.nasa.gov/neo/rest/v1/neo/99942?api_key=… |
| **NASA InSight** | https://api.nasa.gov/insight_weather/?api_key=…&feedtype=json&ver=1.0 |
| **NASA Mars photos** | https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/latest_photos?api_key=… |
| **wheretheiss.at** | https://api.wheretheiss.at/v1/satellites/25544 |
| **open-notify ISS** | http://api.open-notify.org/iss-now.json |
| **open-notify astros** | http://api.open-notify.org/astros.json |
| **open-notify passes** | https://api.open-notify.org/iss-pass.json?lat=34.88&lon=-1.32&n=5 |
| **N2YO passes** | https://api.n2yo.com/rest/v1/satellite/visualpasses/25544/{lat}/{lon}/0/7/300/&apiKey=… |
| **JPL Horizons** | https://ssd.jpl.nasa.gov/api/horizons.api?… (Voyager -31/-32, Bepi -121) |
| **NOAA vent solaire** | https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json |
| **NOAA alertes** | https://services.swpc.noaa.gov/json/alerts.json, xray-flares-latest.json |
| **CelesTrak TLE** | https://celestrak.org/NORAD/elements/stations.txt, gp.php?CATNR=25544, gp.php?GROUP=noaa |
| **CelesTrak SOCRATES** | https://celestrak.org/SOCRATES/query.php?CODE=ALL&ORDER=5&MAX=5&FORMAT=JSON |
| **NASA DSN** | https://eyes.nasa.gov/dsn/data/dsn.xml |
| **SpaceX** | https://api.spacexdata.com/v4/launches/upcoming |
| **Spaceflight News** | https://api.spaceflightnewsapi.net/v4/articles/?limit=8 |
| **MAST STScI** | https://api.mast.stsci.edu/api/v0.1/invoke, Download/file?uri=… |
| **Gemini** | https://generativelanguage.googleapis.com/v1beta/models/…:generateContent?key=… |
| **Groq** | https://api.groq.com/openai/v1/chat/completions |
| **MicroObservatory** | https://mo-www.cfa.harvard.edu/OWN/ |
| **Nominatim (OSM)** | https://nominatim.openstreetmap.org/reverse?format=json&lat=…&lon=… |
| **Wikipedia ISS** | https://en.wikipedia.org/api/rest_v1/page/summary/International_Space_Station |
| **Flickr TLE** | https://live.staticflickr.com/65535/53518876842_raw.txt |
| **ESA Hubble** | https://esahubble.org/media/archives/images/… (fallback images) |

### 4.2 Depuis le frontend (navigateur)

| Service | Où | URL / usage |
|---------|-----|-------------|
| **wheretheiss.at** | observatoire.html (fetchISS) | https://api.wheretheiss.at/v1/satellites/25544 |
| **BigDataCloud** | observatoire.html (fetchISS) | https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=…&longitude=…&localityLanguage=fr |
| **NASA APOD** | observatoire.html (loadAPOD) | https://api.nasa.gov/planetary/apod?api_key=… |
| **NASA NEO** | observatoire.html (loadNEO) | https://api.nasa.gov/neo/rest/v1/neo/99942?api_key=… |
| **NASA InSight** | observatoire.html (loadMarsRovers) | https://api.nasa.gov/insight_weather/?api_key=… |
| **Le Système Solaire** | observatoire.html (loadVoyager) | https://api.le-systeme-solaire.net/rest/bodies/voyager1, voyager2 |
| **Google Fonts** | portail, observatoire, scientific | https://fonts.googleapis.com/css2?family=Orbitron…&Share+Tech+Mono… |
| **NASA (image)** | portail sidebar | https://science.nasa.gov/wp-content/uploads/2023/04/pillars_of_creation.jpg |
| **Anthropic (optionnel)** | observatoire (askAI fallback) | https://api.anthropic.com/v1/messages (claude-sonnet) |
| **N2YO** | observatoire (lien) | https://www.n2yo.com/space-station/ |

---

## 5. Modules Python et connexions

| Module | Rôle | Connexions externes |
|--------|------|---------------------|
| **orbit_engine** | TLE ISS, position précise, équipage | CelesTrak, wheretheiss.at, open-notify, Wikipedia, JPL Horizons (Voyager) |
| **space_alerts** | NEO, météo solaire, débris | NASA NEO feed, NOAA plasma + alertes, CelesTrak SOCRATES |
| **live_feeds** | APOD, JWST, SpaceX, news, passes ISS, Mars weather | NASA APOD, MAST, spacexdata.com, spaceflightnewsapi, open-notify, NASA InSight |
| **sondes_module** | Mars photos, APOD | NASA mars-photos, NASA APOD |
| **catalog** | Catalogue Messier | Aucune (données en dur) |
| **observation_planner** | Phase lune, ce soir Tlemcen | Aucune (calcul local) |
| **station_web** | Routes, _curl_get, _curl_post, Gemini, Groq, Hubble, DSN, N2YO, etc. | Toutes les URLs listées en §4.1 |

---

## 6. Données, caches, base

- **SQLite** : `data/archive_stellaire.db` — tables `observations`, `visits`.
- **Cache mémoire** : `_feeds_cache` (asteroids, solar_weather, tonight, etc.) avec TTL (ex. 300 s, 3600 s).
- **Fichiers JSON** : `data/shield_status.json`, `telescope_hub.json`, `sdr_status.json`, `noaa_tle.json` ; `static/space_weather.json`, `voyager_live.json`, `passages_iss.json` ; `telescope_live/sync_state.json`.
- **Images** : `telescope_live/current_live.jpg`, `source_apod.jpg`, `source_hubble.jpg` ; `static/earth_texture.jpg`.
- **Logs** : `logs/web.log`, `apod.log`, `orbital_shield.log`, etc. ; sortie Flask vers `/tmp/flask.log`.

---

## 7. Service et déploiement

- **Unité** : `astroscan.service`
- **Commande** : `/usr/bin/python3 /root/astro_scan/station_web.py`
- **Répertoire** : `/root/astro_scan`
- **Port** : 5000 (bind 0.0.0.0)
- **Limites** : MemoryMax 512M, CPUQuota 80 %
- **Compteur visites** : incrémenté sur chargement des pages dans `PAGE_PATHS` (/portail, /observatoire, /dashboard, etc.).

---

## 8. Variables d’environnement (.env)

| Variable | Usage |
|----------|--------|
| `NASA_API_KEY` | APOD, NEO, Mars, InSight (DEMO_KEY si absent) |
| `GEMINI_API_KEY` | Traduction, analyse, chat |
| `N2YO_API_KEY` | Passages ISS (optionnel) |
| `GROQ_API_KEY` | Chat IA (fallback) |
| `ANTHROPIC_API_KEY` | Claude (optionnel) |
| `CESIUM_ION_TOKEN` | Optionnel |

---

## 9. Sécurité et bonnes pratiques

- Clés dans `.env`, non versionné.
- NASA_KEY injecté côté template pour appels client (APOD, NEO côté navigateur).
- Timeouts sur tous les `curl` / `_curl_get` / `_curl_post`.
- Fallbacks : traduction (Gemini → texte brut), image (apod → hubble → apod_archive), ISS (TLE → wheretheiss.at), géocodage (BigDataCloud → affichage LAT/LON).

---

*Rapport détaillé ASTRO-SCAN — ORBITAL-CHOHRA. Toutes les connexions et routes listées ci-dessus sont extraites du dépôt /root/astro_scan.*
