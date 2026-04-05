# Fiche technique détaillée — Astro Scan (ORBITAL-CHOHRA)

**Produit :** Station web observatoire / sondes spatiales  
**Projet :** Astro Scan  
**Directeur :** Zakaria Chohra  
**Environnement :** Hillsboro · Linux · 5.78.153.17

---

## 1. Vue d’ensemble

Application web Flask pour un **observatoire virtuel** : flux télescope live (APOD, Hubble, archive), ISS temps réel avec carte et géolocalisation (BigDataCloud), Hubble/JWST, SpaceX, alertes NEO et météo spatiale, sondes (Voyager, Mars, BepiColombo), passages ISS (Tlemcen), DSN, catalogue DSO, système solaire interactif, quiz formation, tuteur IA (Gemini/Groq), radio SDR, NASA SkyView. Compteur de visites, traduction EN→FR (Gemini/MyMemory), tableau de bord type « mission control ».

---

## 2. Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3, Flask |
| Base de données | SQLite (`data/archive_stellaire.db`) |
| Frontend | HTML5, CSS3, JavaScript vanilla (pas de framework) |
| Réseau | `curl` (GET/POST) pour APIs externes, contournement IPv4 si besoin |
| Polices | Google Fonts : Share Tech Mono, Orbitron |
| Déploiement | systemd (`astroscan.service`), port 5000 |
| Logs | Fichiers dans `logs/` (web.log, orbital_shield.log, apod.log, etc.) |

**Dépendances Python (principales) :** Flask, sqlite3 (stdlib), subprocess, pathlib, json, re, os, logging.

---

## 3. Structure du projet

```
/root/astro_scan/
├── station_web.py          # Application Flask principale (~2000+ lignes)
├── .env                    # Variables d'environnement (clés API)
├── data/
│   ├── archive_stellaire.db   # SQLite (observations, visits)
│   ├── shield_status.json
│   ├── telescope_hub.json
│   ├── sdr_status.json
│   ├── noaa_tle.json
│   └── ...
├── templates/
│   ├── observatoire.html   # Page principale (observatoire, ~1395 lignes)
│   ├── portail.html
│   ├── ce_soir.html
│   └── ...
├── static/
│   ├── earth_texture.jpg   # Texture Terre pour carte ISS (si présent)
│   ├── space_weather.json
│   ├── voyager_live.json
│   ├── passages_iss.json
│   ├── sondes.js, sondes_aegis.js
│   ├── sw.js               # Service Worker PWA
│   └── manifest.json
├── telescope_live/
│   ├── current_live.jpg
│   ├── current_title.txt
│   ├── sync_state.json
│   └── source_*.jpg
├── modules/
│   ├── sondes_module.py    # ISS, Mars, Voyager, Hubble, JWST, APOD
│   ├── orbit_engine.py     # TLE, wheretheiss.at, équipage ISS, Voyager JPL
│   ├── live_feeds.py       # Hubble, JWST, SpaceX, news, ISS passes
│   ├── space_alerts.py     # Alertes astéroïdes, météo solaire
│   ├── catalog.py         # Catalogue DSO
│   └── observation_planner.py
└── logs/                   # web.log, apod.log, orbital_shield.log, etc.
```

---

## 4. Pages (routes HTML)

| Route | Template | Description |
|-------|----------|-------------|
| `/` | — | Redirection vers `/observatoire` |
| `/portail` | portail.html | Portail d'entrée (sidebar Hubble, ISS, navigation) |
| `/observatoire` | observatoire.html | **Vue principale** : tous les onglets (télescope, ISS, sondes, etc.) |
| `/dashboard` | index.html | Dashboard QG |
| `/galerie` | — | Archive stellaire (données DB) |
| `/vision`, `/vision-2026` | vision.html, vision_2026.html | Vision 2026 |
| `/sondes` | sondes.html | Sondes spatiales dédiées |
| `/ce_soir` | ce_soir.html | Ciel ce soir |
| `/mission-control` | — | Mission control (ISS, Mars, NEO, Voyager) |
| `/telescopes` | — | Page télescopes |
| `/overlord_live` | overlord_live.html | Overlord Live |
| `/globe` | — | Globe |

---

## 5. Page Observatoire (`observatoire.html`) — détail

### 5.1 Onglets (tabs) et panels

| data-tab | panel-id | Contenu principal |
|----------|----------|-------------------|
| telescope | panel-telescope | Flux live `/api/image`, titre, stats station, dernière analyse Gemini, APOD du jour, liste observations |
| accueil | panel-accueil | Stats cosmos, APOD NASA, spectre EM, SpaceX, Hubble live, news |
| archive | panel-archive | Archive stellaire (total, anomalies, dernière), iframe galerie |
| iss | panel-iss | Carte ISS (mascotte), canvas trajectoire, LAT/LON/ALT, **iss-region-name** (BigDataCloud), passes Tlemcen, lien N2YO |
| sondes | panel-sondes | Grille sondes `/api/sondes`, DSN `/api/dsn`, canvas DSN |
| catalogue | panel-catalogue | Catalogue DSO (grille dso-grid) |
| systeme | panel-systeme | Système solaire (soleil, planètes, infos au clic) |
| quiz | panel-quiz | Quiz formation (questions/réponses) |
| ia | panel-ia | Tuteur IA (champ + bouton, réponse via /api/chat) |
| radio | panel-radio | SDR : statut, prochain sat, countdown, passes, stations, captures |
| deep | panel-deep | Voyager 1/2, Mars rovers, JWST, NEO, Hubble, BepiColombo, météo Mars, alertes |
| skyview | panel-skyview | NASA SkyView (cible, multi-longueur d’onde) |

### 5.2 En-tête et navigation

- **Header :** Logo ASTRO-SCAN OBSERVATORY, sous-titre (Zakaria Chohra, Tlemcen, Hillsboro), boutons Actualiser / Déconnexion, horloge locale + UTC.
- **Nav :** Compteur visites (`#visits-val`, `/api/visits`) + boutons onglets.
- **Fonctions globales JS :** `disconnectObservatory()`, `updateClock()`, `formatVisits()`, `loadVisits()`, `switchTab(id, btn)`.

### 5.3 Télescope (panel-telescope)

- **Image :** `#tele-img` → `src="/api/image"`.
- **Texte :** `#tele-source`, `#tele-name` (titre), `#tp-total`, `#tp-anomalies`, `#tp-last`, `#tp-analyse` (Gemini), `#tele-desc` (APOD du jour).
- **APIs :** `GET /api/image`, `GET /api/title`, `GET /api/latest`, `GET /api/telescope/live`, `POST /api/astro/explain` (traduction).
- **Fonction :** `refreshTelescope()` (recharge image, title, latest, live, analyse).

### 5.4 ISS (panel-iss)

- **Carte miniature :** `#iss-map`, `#iss-mascotte`, `#iss-mascotte-pulse` (position en %).
- **Stats :** `#iss-lat`, `#iss-lng`, `#iss-alt`, `#iss-vel`.
- **Canvas monde :** `#iss-map-canvas` (texture `earth_texture.jpg` ou fallback polygones), grille, équateur, trajectoire, point ISS.
- **Coords sous canvas :** `#iss-map-lat`, `#iss-map-lon`, `#iss-map-alt`.
- **Région au-dessus :** `#iss-region-name` — texte « 📍 Au-dessus de : [pays/continent] » ou « 📍 LAT: …° | LON: …° » (fallback).
- **APIs externes :**
  - **Position ISS :** `https://api.wheretheiss.at/v1/satellites/25544`
  - **Géocodage inverse :** `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=…&longitude=…&localityLanguage=fr`
- **API interne :** `GET /api/live/iss-passes` → passages Tlemcen dans `#iss-passes-tlemcen`.
- **Fonction :** `fetchISS()` (AbortController, fetch ISS → mise à jour stats + canvas + lat2/lon2 → fetch BigDataCloud → mise à jour `#iss-region-name`). Rafraîchi toutes les 10 s quand l’onglet ISS est actif.

### 5.5 Sondes & DSN (panel-sondes)

- **Grille :** `#sondes-grid` remplie par `loadSondesData()`.
- **DSN :** `#dsn-grid`, `#dsn-canvas`, `#dsn-update`.
- **APIs :** `GET /api/sondes`, `GET /api/dsn`.
- **Modal :** `#sonde-modal`, `#sonde-live-content` (détail sonde via `openSondeModal(k)`).

### 5.6 Cosmos profond (panel-deep)

- **Voyager :** API externe `https://api.le-systeme-solaire.net/rest/bodies/voyager1` et `voyager2` → `#voyager1-au`, `#voyager2-au`, etc.
- **Mars rovers :** NASA InSight Weather → `#curiosity-sol`, `#perseverance-sol`, etc.
- **JWST / NEO / Hubble / Bepi :** `loadJWST()`, `loadNEO()` (NASA NEO 99942), `loadHubble()` → `/api/hubble/images`, `loadBepi()` → `/api/bepi/telemetry`.
- **Météo Mars :** `GET /api/live/mars-weather` → `#mars-weather-live`.
- **Alertes :** `GET /api/alerts/all` → `#space-alerts-box`.

### 5.7 Archive (panel-archive)

- **APIs :** `GET /api/latest` → `#arch-total`, `#arch-anomalies`, `#arch-last`, `#archive-obs`.
- **iframe :** `/galerie?embed=1`.

### 5.8 Accueil / Cosmos (panel-accueil)

- **APOD :** `https://api.nasa.gov/planetary/apod?api_key=…` → `#apod-img-wrap`, `#apod-title`, `#apod-desc`.
- **SpaceX :** `GET /api/live/spacex` → `#spacex-launches`.
- **Hubble :** `GET /api/hubble/images` → `#hubble-live`.
- **News :** `GET /api/live/news` → `#space-news`.

### 5.9 Radio SDR (panel-radio)

- **APIs :** `GET /api/sdr/status`, `GET /api/sdr/passes`, `GET /api/sdr/stations`, `GET /api/sdr/captures`.
- **Éléments :** `#sdr-status-val`, `#sdr-next-sat`, `#sdr-countdown`, `#sdr-freq`, `#sdr-passes-list`, `#sdr-stations-list`, `#sdr-captures-list`.
- **Fonction :** `loadRadio()`.

### 5.10 Cerveau IA (panel-ia)

- **Chat :** `#ai-input`, `#ai-btn`, `#ai-thinking`, `#ai-answer`, `#ai-text`.
- **API :** `POST /api/chat` (corps JSON avec message).
- **Fonction :** `askAI()`.

### 5.11 Catalogue DSO, Système solaire, Quiz, SkyView

- **Catalogue :** `#dso-grid` (données catalogue).
- **Système solaire :** `#solar-planets`, `#planet-info`, `#planet-grid` (clic planète).
- **Quiz :** questions/réponses, score, `#qprog`, `#qscore`, `#quiz-q`, etc.
- **SkyView :** panneau dédié, `svInit()` si présent.

---

## 6. APIs (routes Flask) — liste détaillée

### Visites
| Méthode | Route | Description |
|---------|--------|-------------|
| GET | `/api/visits` | Nombre de visites |
| POST | `/api/visits/increment` | Incrémente et retourne le count |

### Télescope / Image / APOD
| GET | `/api/image` | Image live (apod, hubble, apod_archive selon source) |
| GET | `/api/title` | Titre courant (fichier / cache) |
| GET | `/api/telescope/sources` | Liste des sources |
| GET | `/api/telescope/live` | APOD du jour (titre + explication, FR si dispo) |
| GET | `/api/latest` | Dernières observations (total, anomalies, liste) |
| GET | `/api/sync/state` | État de synchronisation |
| POST | `/api/sync/state` | Mise à jour état sync |

### ISS / Sondes / Mission control
| GET | `/api/iss` | Données ISS (wheretheiss.at ou cache) |
| GET | `/api/sondes` | Agrégat sondes (ISS, Mars, Voyager, Hubble, JWST, etc.) |
| GET | `/api/dsn` | Deep Space Network (antennes, missions) |
| GET | `/api/live/iss-passes` | Passages ISS (ex. Tlemcen) |
| GET | `/api/voyager-live` | Voyager |
| GET | `/api/mission-control` | Vue mission control |
| GET | `/api/passages-iss` | Passages ISS (autre format) |
| GET | `/api/iss-passes` | Passages ISS |
| GET | `/api/survol` | Survol terrestre |

### Flux et news
| GET | `/api/live/news` | News spatiales (traductions) |
| GET | `/api/live/spacex` | Lancements SpaceX |
| GET | `/api/live/mars-weather` | Météo Mars |
| GET | `/api/live/all` | Agrégat live |
| GET | `/api/hubble/images` | Images Hubble |
| GET | `/api/news` | News |

### Alertes
| GET | `/api/alerts/asteroids` | Alertes astéroïdes |
| GET | `/api/alerts/solar` | Météo solaire |
| GET | `/api/alerts/all` | Toutes alertes |

### Traduction / IA / Explications
| POST | `/api/translate` | Traduction (corps JSON) |
| POST | `/api/astro/explain` | Traduction EN→FR (texte, ex. analyse Gemini) |
| GET/POST | `/api/astro/object` | Explication objet céleste (nom) |
| POST | `/api/chat` | Chat tuteur IA (Gemini / Groq) |

### SDR
| GET | `/api/sdr/status` | Statut pipeline SDR |
| GET | `/api/sdr/passes` | Passages NOAA |
| GET | `/api/sdr/stations` | Stations réceptrices |
| GET | `/api/sdr/captures` | Liste captures |

### SkyView / MAST
| GET | `/api/skyview/targets` | Cibles SkyView |
| POST | `/api/skyview/fetch` | Récupération image SkyView |
| GET | `/api/skyview/multiwave/<target_id>` | Multi-longueur d’onde |
| GET | `/api/skyview/list` | Liste |
| GET | `/api/mast/targets` | Cibles MAST |

### Catalogue / Ciel / Lune
| GET | `/api/catalog` | Catalogue (DSO) |
| GET | `/api/catalog/<obj_id>` | Objet catalogue |
| GET | `/api/tonight` | Ciel ce soir |
| GET | `/api/moon` | Lune |

### Santé / Shield / Divers
| GET | `/api/health` | Santé service |
| GET | `/api/aegis/status` | Statut AEGIS |
| GET | `/api/shield` | Shield |
| GET | `/api/telescope-hub` | Telescope hub |
| GET | `/api/classification/stats` | Stats classification |
| GET | `/api/meteo-spatiale` | Météo spatiale |
| GET | `/api/bepi/telemetry` | BepiColombo |
| GET | `/api/mars/weather` | Météo Mars |
| GET | `/api/neo` | NEO |
| GET | `/api/jwst/images` | Images JWST |

### Feeds (cache / agrégats)
| GET | `/api/feeds/voyager` | Feed Voyager |
| GET | `/api/feeds/neo` | Feed NEO |
| GET | `/api/feeds/solar` | Feed solaire |
| GET | `/api/feeds/solar_alerts` | Alertes solaires |
| GET | `/api/feeds/mars` | Feed Mars |
| GET | `/api/feeds/apod_hd` | APOD HD |
| GET | `/api/feeds/all` | Tous les feeds |

### PWA
| GET | `/sw.js` | Service Worker |
| GET | `/manifest.json` | Manifest PWA |
| POST | `/api/push/subscribe` | Abonnement push |

### Fichiers
| GET | `/static/<path>` | Fichiers statiques |

---

## 7. APIs externes utilisées (côté client ou serveur)

| Service | Usage |
|---------|--------|
| **wheretheiss.at** | Position ISS temps réel (satellite 25544) |
| **BigDataCloud** | Reverse geocode (latitude, longitude → pays/région, langue fr) |
| **NASA** | APOD, NEO (99942 Apophis), Mars rovers, InSight weather |
| **Le Système Solaire (API)** | Voyager 1/2 (bodies) |
| **MAST / STScI** | Hubble, JWST (téléchargement images) |
| **JPL Horizons** | BepiColombo (-121), Voyager (-31, -32), etc. |
| **Gemini (Google)** | Traduction, analyse images, chat (si clé) |
| **Groq** | Fallback chat IA (si clé) |

---

## 8. Données et caches

- **SQLite :** `observations`, `visits` (table visits : id, count).
- **JSON :** `shield_status.json`, `telescope_hub.json`, `sdr_status.json`, `sync_state.json`, TLE (NOAA, CelesTrak), `space_weather.json`, `voyager_live.json`, `passages_iss.json`.
- **Images :** `telescope_live/current_live.jpg`, `source_apod.jpg`, `source_hubble.jpg`, `static/earth_texture.jpg`.
- **Traduction :** Gemini (prioritaire), MyMemory en fallback ; pas de clé payante obligatoire.

---

## 9. Variables d’environnement (.env)

| Variable | Rôle |
|----------|------|
| `NASA_API_KEY` | NASA APOD, NEO, Mars, etc. (DEMO_KEY si absent) |
| `GEMINI_API_KEY` | Analyse IA, traduction, chat |
| `N2YO_API_KEY` | N2YO (optionnel) |
| `CESIUM_ION_TOKEN` | Cesium (optionnel) |
| `ANTHROPIC_API_KEY` | Optionnel |
| `GROQ_API_KEY` | Chat IA (fallback) |

---

## 10. Service systemd

- **Unité :** `astroscan.service`
- **Commande :** `/usr/bin/python3 /root/astro_scan/station_web.py`
- **Répertoire :** `/root/astro_scan`
- **Port :** 5000 (écoute 0.0.0.0)
- **Limites :** MemoryMax 512M, CPUQuota 80 %
- **Logs :** StandardOutput/Error append vers `/tmp/flask.log`
- **Redémarrage :** `systemctl restart astroscan`

---

## 11. Sécurité et bonnes pratiques

- Clés API dans `.env`, non versionné (`.gitignore`)
- Pas de clé en dur dans le code (NASA_KEY injecté dans le template pour le client)
- Timeouts sur les appels `curl` externes
- Gestion d’erreurs et fallbacks (traduction, sources image, géocodage ISS → LAT/LON si erreur)

---

*Fiche technique détaillée — Astro Scan ORBITAL-CHOHRA. Dernière mise à jour : mars 2026.*
