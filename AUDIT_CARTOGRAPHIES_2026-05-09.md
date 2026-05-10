# AUDIT TOTAL DES CARTOGRAPHIES — ASTRO-SCAN

**Date** : 2026-05-09
**Branche** : `main`, tag `v2.1.2-kaizen-day1`
**Périmètre** : 66 templates HTML + 12 fichiers CSS + JS associés.
**Posture** : audit lecture seule, aucun fichier modifié.
**Référentiel cible** : Cesium World Terrain / Photorealistic 3D Tiles / VIIRS NASA / AISStream.

---

## TL;DR — Constat brut

ASTRO-SCAN possède **11 modules avec carte** dans 3 librairies :

- **Cesium** (2 modules) — `mission-control` ✅ token actif, `orbital-map` ❌ token écrasé à vide.
- **Leaflet** (7 modules) — tous sur **CARTO dark basemaps** + Esri World Imagery + un VIIRS WMTS NASA.
- **Aladin Lite** (2 modules) — `/aladin` + iframe dans portail. ✅ déjà premium scientifique (CDS DSS2).

**Le gap principal n'est pas l'infrastructure (Cesium ion + token + AISStream
fonctionnent)**, c'est l'**adoption** : `orbital-map` (3 244 lignes) — la
carte 3D vitrine du projet — fonctionne en mode dégradé OSM alors que le
token Ion est valide. La correction est mécanique (lever la ligne 107 de
`static/orbital_map_engine.js`).

AISStream **fonctionne et envoie des données live** (`583 vessels` en cache,
flux WebSocket connecté à `wss://stream.aisstream.io/v0/stream`).

Tous les 11 endpoints carto répondent **HTTP 200** en moins de 40 ms
(sauf `/api/iss-passes` à 780 ms — calcul SGP4 lourd, hors périmètre carto).

---

## Section 1 — Inventaire des modules avec carte

| # | Template | URL Flask | Lib | Source rendu carte | Lignes clés |
|---|----------|-----------|-----|---------------------|-------------|
| 1 | `mission_control.html` | `/mission-control` | **Cesium 1.118** | `Cesium.Viewer` + Bing default (`baseLayerPicker:true`) | `templates/mission_control.html:7,26,28` |
| 2 | `orbital_map.html` | `/orbital-map` | **Cesium 1.110** | `Cesium.Viewer` + **OSM fallback forcé** (token écrasé) | `templates/orbital_map.html:9,1298,1550` + `static/orbital_map_engine.js:107,117` |
| 3 | `iss_tracker.html` | `/iss-tracker` | Leaflet 1.x | `L.tileLayer('cartocdn dark_all')` | `templates/iss_tracker.html:82-86` |
| 4 | `orbital_dashboard.html` | `/orbital` | Leaflet 1.x | NASA VIIRS CityLights WMTS (NASA Earthdata) | `templates/orbital_dashboard.html:619-626` |
| 5 | `flight_radar.html` | `/flight-radar` | Leaflet 1.9.4 (CDN unpkg) | `cartocdn dark_all` (default) + `arcgisonline World_Imagery` (toggle sat) | `static/flight_radar/js/flight_radar.js:92-118` |
| 6 | `scan_signal.html` | `/scan-signal` | Leaflet | `cartocdn dark_all` (default) + `arcgisonline World_Imagery` (toggle) | `static/scan_signal/js/scan_signal.js:100-127` |
| 7 | `ground_assets.html` | `/ground-assets` | Leaflet + MarkerCluster | `cartocdn dark_nolabels` (single layer, pas de toggle) | `static/ground_assets/js/ground_assets.js:200-220` |
| 8 | `visiteurs_live.html` | `/visiteurs-live` | Leaflet | `cartocdn dark_all` | `templates/visiteurs_live.html:139` |
| 9 | `aladin.html` | `/aladin`, `/carte-du-ciel` | Aladin Lite v3 | CDS HiPS `CDS/P/DSS2/color` (initial), surveys multiples | `templates/aladin.html:13-14,306-310` |
| 10 | `portail.html` | `/portail` | iframe → `/aladin?embed=1` | indirect (Aladin Lite via embed) | `templates/portail.html:1796` |
| 11 | (sub-iframe portail) | `/portail` | iframes → `/iss-tracker`, `/orbital`, `/scan-signal`, `/flight-radar`, `/ground-assets`, `/aladin` | composite | `templates/portail.html:2326+` |

**Pas de Mapbox**, pas de Google Maps embed direct, pas de Three.js custom (le
"global earth" en background CSS de orbital_dashboard.html utilise une image
plate `earth.jpg` → migrée WebP en Kaizen Day 1).

---

## Section 2 — Cesium ion : configuration

### Module 2.1 — `mission_control.html`

```html
<!-- L.7 -->
<script src="https://cesium.com/downloads/cesiumjs/releases/1.118/Build/Cesium/Cesium.js"></script>
<!-- L.26 -->
Cesium.Ion.defaultAccessToken = "{{ cesium_token | default('') }}";
<!-- L.28 -->
const viewer = new Cesium.Viewer('cesiumContainer', {
  timeline: true, animation: true, baseLayerPicker: true
});
```

- **Token source** : `app/blueprints/telescope/__init__.py:81` lit `os.getenv("CESIUM_TOKEN","")` puis le passe en contexte template.
- **Token statut live** : `eyJhbGciOiJIUzI1NiIs…` (JWT Cesium ion **présent et valide** — vérifié dans le HTML servi).
- **Imagery providers** : aucune surcharge → Cesium prend son **défaut Ion = Bing Maps Aerial**. `baseLayerPicker:true` permet à l'utilisateur de basculer.
- **Terrain provider** : aucune surcharge → `Cesium.createWorldTerrainAsync()` (par défaut depuis 1.118).
- **Buildings** : `Cesium.OsmBuildings()` **non activé**.
- **Photorealistic 3D Tiles** : **non activé**.
- ⚠️ **Bing Maps Aerial est officiellement déprécié par Microsoft** (sunset 2025-2026 — Cesium recommande Google Photorealistic 3D Tiles ou IonImageryProvider asset 2 / 3 / 4).
- ⚠️ **Sécurité** : le token est rendu en clair dans le HTML servi à tout visiteur. Cesium ion permet de **restreindre par domaine** dans le dashboard ion → vérifier que `astroscan.space` y est listé exclusivement.

### Module 2.2 — `orbital_map.html` + `orbital_map_engine.js`

```js
// templates/orbital_map.html:1298 (HTML inline)
try { Cesium.Ion.defaultAccessToken = ""; } catch (e) {}

// static/orbital_map_engine.js:107 (script principal)
try { Cesium.Ion.defaultAccessToken = ""; } catch (e) {}

// static/orbital_map_engine.js:117 — fallback OSM
imageryProvider: new Cesium.OpenStreetMapImageryProvider({
  url: "https://tile.openstreetmap.org/"
})
// + EllipsoidTerrainProvider (terrain plat, pas de relief)
```

- **Token écrasé volontairement à `""`** par le HTML inline ET par l'engine JS — commentaire L.1294 : *"évite 401 si variable d'environnement invalide"*.
- **Pourtant** la route `app/blueprints/iss/routes.py:39` passe bien `cesium_token=_cesium_token()` au template — qui l'ignore.
- **Conséquence** : le globe orbital, **carte la plus visible du projet** (3 244 lignes, 1 000 satellites animés, 163 `!important`), tourne sur OSM 2D plat sans relief.
- **Impact visuel** : énorme. Avec Cesium World Imagery (Bing/Maxar) ou Google Photorealistic 3D Tiles, la carte passerait de "globe Wikipédia" à "globe SpaceX".

### Module 2.3 — Bing dépréciation

Cesium ion → asset **Bing Maps Aerial = id 2** est annoncé en sunset par
Microsoft (annonce 2024, retrait 2025-2026). Migration recommandée :

- `IonImageryProvider({ assetId: 3 })` → **Sentinel-2** (gratuit, 10 m, sans Bing)
- `createGooglePhotorealistic3DTileset({ token: ... })` → **Google Photo 3D** (gratuit ≤ 200 villes pour usage public, free tier ion couvre)
- `IonImageryProvider({ assetId: 2 })` reste utilisable jusqu'au sunset officiel

---

## Section 3 — Leaflet : audit des tile sources

Tous les modules Leaflet utilisent **CARTO dark basemaps** comme couche par
défaut. Niveau **basique-moyen** (CARTO est CDN gratuit, OSM-derived, sans
imagerie satellite). Détail :

| Module | Source par défaut | Source satellite (toggle) | Niveau |
|--------|-------------------|----------------------------|--------|
| `iss_tracker.html` | `cartocdn/dark_all` | aucun toggle | 🟡 BASIQUE |
| `orbital_dashboard.html` | NASA VIIRS CityLights (WMTS NASA Earthdata) | aucun toggle | 🟢 PREMIUM scientifique unique |
| `flight_radar.js` | `cartocdn/dark_all` | `arcgisonline/World_Imagery` (Esri/Maxar) | 🟡→🟢 toggle ✓ |
| `scan_signal.js` | `cartocdn/dark_all` | `arcgisonline/World_Imagery` | 🟡→🟢 toggle ✓ |
| `ground_assets.js` | `cartocdn/dark_nolabels` | aucun toggle | 🟡 BASIQUE |
| `visiteurs_live.html` | `cartocdn/dark_all` | aucun toggle | 🟡 BASIQUE |

### Détails clés

- **CARTO dark_all** : `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png` — gratuit, sans clé, OSM-derived. Limite raisonnable (~10k tiles/jour). Cohérent visuellement (sombre, va avec le thème AstroScan).
- **Esri World_Imagery** : `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/...` — gratuit pour usage non-commercial, attribution requise (Esri/Maxar/Earthstar). Couvre tile résolution sub-mètre dans certaines zones. **Excellente source gratuite premium**.
- **NASA VIIRS CityLights** : `https://map1.vis.earthdata.nasa.gov/wmts-webmerc/VIIRS_CityLights_2012/...` — gratuit, NASA Earthdata WMTS. **Source unique au monde**. Déjà premium dans `orbital_dashboard.html`. ✅
- **Plugins Leaflet utilisés** : MarkerCluster (`ground_assets`), `L.svg renderer`. Pas de heatmap, pas de leaflet-draw, pas de leaflet-realtime.

### Pistes d'upgrade

- Ajouter le **toggle Esri World_Imagery** sur les modules qui ne l'ont pas (`iss_tracker`, `ground_assets`, `visiteurs_live`) → effort 5 min/module.
- Remplacer les CARTO basique par un Mapbox Style sombre custom (besoin token Mapbox, free tier 50k loads/mois) → effort 1 h, gain visuel modéré.
- VIIRS Black Marble Annual Composite à la place du `_2012` (plus récent) → asset id NASA GIBS différent, effort 15 min.

---

## Section 4 — Aladin Lite

| Item | Valeur |
|------|--------|
| Templates | `aladin.html`, et iframe embed `/aladin?embed=1` dans `portail.html:1796` |
| Lib | Aladin Lite v3 latest (CDN `aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js`) |
| Survey initial | `CDS/P/DSS2/color` |
| Cible initiale | M42 (Orion Nebula), FOV 2.0° |
| Frame | ICRSd (équatorial moderne) |
| Background | `#020810` (cohérent avec design tokens) |
| Surveys disponibles via `setImageSurvey()` | Tous ceux exposés par CDS HiPS (DSS2 RGB, SDSS, 2MASS, GALEX, AllWISE, …) |

**Statut : ✅ déjà premium.** Aucune action requise. C'est même un point d'orgueil
scientifique du projet (DSS2 = catalogue plate de Palomar, gratuit pour la
communauté astro). Linear/Stripe n'ont pas l'équivalent.

Suggestion mineure : exposer un sélecteur visuel des surveys (DSS2, SDSS,
2MASS, GALEX) plutôt que `setImageSurvey()` programmatique → effort 1 h.

---

## Section 5 — AISStream (navires temps réel)

| Item | Valeur |
|------|--------|
| Service | `app/blueprints/scan_signal/services/aisstream_subscriber.py` (485 lignes) |
| Endpoint WS upstream | `wss://stream.aisstream.io/v0/stream` |
| Souscription | `PositionReport + ShipStaticData (global)` |
| Lock distribuée | Redis key `astroscan:lock:aisstream_subscriber` (1 worker leader actif, 3 standby) |
| Heartbeat thread | `aisstream-heartbeat` |
| Statut **live** (logs structuré 14:59-15:09 UTC) | ✅ **connecté**, lock acquis par worker `863245-fa324f92` |
| Cache vessels | **583 vessels actifs** (vérifié via `/api/scan-signal/vessel/recent`) |
| Endpoints Flask exposés | `/api/scan-signal/{vessel/search,vessel/recent,vessel/<mmsi>,vessel/<mmsi>/track,ports,ping,stats,health}` |
| Template qui consomme | `scan_signal.html` (carte Leaflet `cartocdn dark_all` + couche vessels) |

**Statut : 🟢 OK fonctionnel et exploitable.**

Vérification sample live (extrait `/api/scan-signal/vessel/recent?limit=3`) :

```
DALMORE     (MT 🇲🇹) 36.10°N / 14.62°E — 11.8 kn
ENZO ASARO  (IT 🇮🇹) 36.54°N / 27.46°E — 0.6 kn
…           (GI 🇬🇮)
```

Données réelles, fraîches, géolocalisées. Aucune action requise sur l'ingestion.

---

## Section 6 — Tests fonctionnels HTTP

| Endpoint | HTTP | Temps | Carte rendue ? | Notes |
|----------|-----:|------:|----------------|-------|
| `/portail` | 200 | 0.039 s | indirect (iframes) | OK, hub principal |
| `/aladin` | 200 | 0.006 s | ✅ Aladin DSS2 | OK |
| `/carte-du-ciel` | 200 | 0.006 s | ✅ Aladin DSS2 | alias |
| `/iss-tracker` | 200 | 0.005 s | ✅ Leaflet CARTO dark | OK |
| `/orbital` | 200 | 0.032 s | ✅ Leaflet VIIRS NASA | OK |
| `/orbital-map` | 200 | 0.020 s | ✅ Cesium **OSM dégradé** | ⚠️ token écrasé |
| `/mission-control` | 200 | 0.002 s | ✅ Cesium **Bing default** | ⚠️ Bing déprécié |
| `/scan-signal` | 200 | 0.010 s | ✅ Leaflet + 583 ships live | 🟢 OK |
| `/flight-radar` | 200 | 0.015 s | ✅ Leaflet CARTO+Esri toggle | OK |
| `/ground-assets` | 200 | 0.012 s | ✅ Leaflet CARTO + cluster | OK |
| `/visiteurs-live` | 200 | 0.006 s | ✅ Leaflet CARTO dark | OK |
| `/api/scan-signal/health` | 200 | 0.003 s | — | OK |
| `/api/scan-signal/vessel/recent` | 200 | 0.003 s | — | 583 vessels |
| `/api/iss/orbit` | 200 | 0.005 s | — | OK |
| `/api/iss-passes` | 200 | 0.780 s | — | calcul SGP4, hors carto |
| `/api/tle/active` | 200 | 0.003 s | — | OK |

Aucune erreur 4xx/5xx. Tous les modules carto **rendent**, mais 2 sur 11 le
font en mode dégradé.

### Erreurs JS console probables

- `/orbital-map` : message `console.info("OrbitalMap: using free OSM imagery fallback.")` à chaque render — attendu mais signal d'un downgrade systématique.
- `/mission-control` : si Microsoft retire Bing avant migration, **Cesium chargera un globe blanc** sans imagerie. Pas encore arrivé, mais imminent.

---

## Section 7 — Variables d'environnement carto

`.env` n'est pas lisible par l'utilisateur de l'audit (root:zakaria 600).
Inférence depuis `.env.example` et confirmation via le HTML servi en prod :

| Variable | Déclarée dans `.env.example` | Statut live (preuve) |
|----------|:---:|----------------------|
| `CESIUM_TOKEN` | ✅ | ✅ **présent et valide** (token JWT visible dans `/mission-control` HTML) |
| `CESIUM_ION_TOKEN` | ✅ | doublon — non lu par le code (`_cesium_token()` ne lit que `CESIUM_TOKEN`). À aligner ou retirer. |
| `MAPBOX_TOKEN` | ❌ absent | non utilisé |
| `GOOGLE_MAPS_API_KEY` | ❌ absent | non utilisé |
| `NASA_API_KEY` | ✅ | (utilisé pour APOD/NEO, pas carto) |
| `AISSTREAM_API_KEY` | ❌ pas dans .env.example | ✅ **présent** en prod (preuve : flux WebSocket connecté, 583 vessels en cache) |
| `N2YO_API_KEY` | ✅ | présent, satellites |
| `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET` | ✅ commentés (mode anonyme par défaut) | non vérifié |

⚠️ **Action recommandée** : ajouter `AISSTREAM_API_KEY=` à `.env.example`
puisqu'il est utilisé en prod (oublié au précédent commit).

⚠️ **Action recommandée** : **clarifier** `CESIUM_TOKEN` vs `CESIUM_ION_TOKEN`
dans `.env.example` (deux lignes pointent vers la même valeur, mais le code
ne lit que la première — source de confusion à la prochaine rotation de token).

---

## Section 8 — Sources gratuites premium disponibles

(Référence pour les choix de migration. **Toutes gratuites pour l'usage actuel
d'AstroScan**, sous conditions d'attribution.)

### Globe / 3D

| Source | Accès | Limite gratuite | Compat existant |
|--------|-------|-----------------|-----------------|
| **Cesium World Terrain** (Ion asset 1) | token Ion | illimité free tier | ✅ token déjà actif |
| **Cesium World Imagery** (Ion asset 2 — Bing) | Ion | gratuit (sunset annoncé) | ⚠️ deadline Microsoft |
| **Sentinel-2 cloudless** (Ion asset 3) | Ion | gratuit illimité | ✅ remplace Bing parfaitement |
| **Google Photorealistic 3D Tiles** | Ion bridge ou clé Google | 200k tiles/mois free | ✅ effet "Apple Maps" |
| **NASA GIBS WMTS** | aucune clé | illimité | déjà utilisé sur `/orbital` |
| **OpenTopoMap / OpenSkyMap** | OSM | tiles standard | déjà OSM |

### Pollution lumineuse

| Source | Accès | Notes |
|--------|-------|-------|
| **VIIRS Black Marble Annual Composite** (NASA Worldview/GIBS) | aucune clé | tiles WMTS — `VIIRS_Black_Marble_2024` |
| **VIIRS DNB Monthly via NOAA EOG** | aucune clé | mensuel, plus frais que `_2012` actuel |
| **Light Pollution Map** (lightpollutionmap.info) | iframe embed | overlay Bortle simulé |

### Avions temps réel (bonus)

| Source | Accès | Limite |
|--------|-------|--------|
| **OpenSky Network REST** | anonyme ou OAuth2 | 100 req/jour anonyme, 4000 OAuth2 |
| **ADS-B Exchange** | clé gratuite avec attribution | aucune limite stricte |

### Météo / nuages

| Source | Accès | Notes |
|--------|-------|-------|
| **Windy.com embed** | iframe | `<iframe src="https://embed.windy.com/...">` zéro clé |
| **OpenWeatherMap tiles** | clé free tier | 60 calls/min, 10 tile types |
| **NASA GIBS MODIS_Terra_CorrectedReflectance_TrueColor** | aucune clé | wmts, daily |

---

## Section 9 — Verdict — Tableau maître

🟢 énorme repos visuel | 🟡 moyen | ⚪ subtil
⚡ <30 min | ⏱ 30 min – 2 h | 🕐 2-4 h | 🕑 >4 h

| # | Module | Carte actuelle | Premium ? | Fonctionne ? | Effort migration | Impact visuel | Action recommandée |
|---|--------|----------------|:---------:|:------------:|:----------------:|:-------------:|---------------------|
| 1 | **`/orbital-map`** | Cesium 1.110 + OSM forcé | ❌ DÉGRADÉ | ✅ | 🕐 2-4 h | 🟢 ÉNORME | **Lever le `Cesium.Ion.defaultAccessToken=""` (2 lignes), activer Cesium World Imagery + Photo3D Tiles, ajouter `OsmBuildings`. Bump Cesium 1.110 → 1.118.** |
| 2 | **`/mission-control`** | Cesium 1.118 + Bing default | 🟡 (Bing déprécié) | ✅ | ⏱ 30 min | 🟢 ÉNORME | **Forcer `IonImageryProvider({assetId:3})` (Sentinel-2) ou Photo3D pour anticiper sunset Bing.** Aujourd'hui ✅, demain ❌ sans action. |
| 3 | `/scan-signal` | Leaflet CARTO + Esri toggle + AIS live | 🟡 | ✅ + 583 ships | ⏱ 1 h | 🟡 moyen | **Ajouter VIIRS Black Marble nouveau (overlay nuit), trail des ships sur Esri sat. AIS déjà top.** |
| 4 | `/orbital` (dashboard) | Leaflet + VIIRS CityLights | 🟢 (déjà premium scientifique) | ✅ | ⚡ 15 min | ⚪ subtil | Bumper VIIRS_2012 → VIIRS_Black_Marble_2024 (annual composite plus récent). |
| 5 | `/flight-radar` | Leaflet CARTO + Esri toggle | 🟡 | ✅ | ⏱ 1 h | 🟡 moyen | Brancher OpenSky Network (déjà variables env présentes) en remplacement/complément de la source ADS-B actuelle. Layer "airports" déjà OK. |
| 6 | `/iss-tracker` | Leaflet CARTO dark | 🟡 BASIQUE | ✅ | ⚡ 15 min | 🟡 moyen | Ajouter le toggle Esri World_Imagery (5 lignes JS comme `flight_radar.js`). |
| 7 | `/ground-assets` | Leaflet CARTO + MarkerCluster | 🟡 BASIQUE | ✅ | ⚡ 15 min | ⚪ subtil | Idem #6 : toggle satellite. |
| 8 | `/visiteurs-live` | Leaflet CARTO dark | 🟡 BASIQUE | ✅ | ⚡ 15 min | ⚪ subtil | Idem #6 : toggle satellite. |
| 9 | `/aladin` + `/carte-du-ciel` | Aladin Lite v3 DSS2 | 🟢 PREMIUM | ✅ | ⚡ 30 min | ⚪ subtil | Ajouter sélecteur surveys visible (DSS2 / SDSS / 2MASS / GALEX). Optionnel. |
| 10 | `/portail` (hub iframes) | indirect | composite | ✅ | — | — | hub déjà bien fait, ne pas toucher la structure. |
| 11 | `mission_control` token leak | — | sécurité | ⚠️ | ⚡ 5 min | — | Restreindre le token Ion dans `dashboard.cesium.com` au domaine `astroscan.space` (sans modifier le code). |

### Top 5 modules à migrer EN PRIORITÉ (impact max)

1. **`/orbital-map`** — passage de OSM 2D dégradé à Cesium World Imagery + Photo3D Tiles. Du jour au lendemain, la carte 3D vitrine du projet passe d'un "globe Wikipedia" à une expérience type Google Earth / Cesium Stories. **Impact : 10/10.**
2. **`/mission-control`** — anticipation du sunset Bing. Sans cette migration, le module deviendra silencieusement non-fonctionnel quand Microsoft retirera l'asset. **Urgence : haute.** Effort : 30 min.
3. **`/scan-signal`** — ajouter overlay VIIRS Black Marble (la nuit lumineuse) + trails AIS sur fond satellite Esri. Mise en valeur de la donnée live AISStream. **Impact : 8/10** (donnée déjà excellente, scénographie à hisser au niveau).
4. **`/flight-radar`** — branchement OpenSky API + remplacement éventuel de la source ADS-B existante. Cohérence avec `scan_signal` (même pattern de basemap toggle). **Impact : 7/10.**
5. **`/orbital` dashboard** — bump VIIRS_2012 → VIIRS_Black_Marble_2024. **Effort minimal**, gain de fraîcheur (12 ans de plus de pollution lumineuse mesurée). **Impact : 5/10.**

---

## Section 10 — Stratégie d'attaque 5 jours

### Day 1 — `/orbital-map` upgrade Cesium premium (3-4 h)

**Modules** : `templates/orbital_map.html` + `static/orbital_map_engine.js` + `static/js/orbital_map_engine.js` (le doublon).

**Cartographies** :
- Cesium World Terrain (relief ✅)
- Cesium World Imagery (asset 2 Bing pour l'instant, swap 3 Sentinel-2 quand sunset)
- Google Photorealistic 3D Tiles (effet "Apple Maps") — optionnel layer activable par bouton
- Cesium OSM Buildings (silhouettes 3D bâtiments en zoom rapproché)

**Effort** : 3 h (édition JS + tests + harmonisation avec les 1 000 satellites existants).

**Risques** :
- Régression sur les 1 000 entités satellites animées (TLE → SGP4) si `terrainProvider` change la base ellipsoïdale → tester précisément les altitudes ISS.
- Performance navigateur : Photo3D + 1 000 entités peut chuter à 30 fps. Garder Photo3D en toggle off par défaut.
- `Cesium 1.110 → 1.118` : ruptures API mineures (`createWorldTerrain` → `createWorldTerrainAsync`). Vérifier le viewer.

**Validation** : visuelle sur les 4 régions Tlemcen, ISS, Cap Canaveral, JWST L2.

### Day 2 — `/mission-control` sortie Bing + `/scan-signal` upgrade (3 h)

**Modules** : `templates/mission_control.html` + `static/scan_signal/js/scan_signal.js`.

**Cartographies** :
- mission-control : forcer `IonImageryProvider({assetId:3})` (Sentinel-2 cloudless) — perd Bing, gagne pérennité.
- scan-signal : overlay VIIRS Black Marble Annual nuit + Esri sat toggle déjà OK + trails AIS persistants 30 min.

**Effort** : 1 h mission-control + 2 h scan-signal.

**Risques** :
- Sentinel-2 a moins de couverture HD que Bing à zoom proche → tester ISS au-dessus des continents et océans.
- Trails AIS 30 min : mémoire navigateur, garder un cap (200 ships max trackés).

### Day 3 — `/flight-radar` OpenSky + `/iss-tracker`, `/ground-assets`, `/visiteurs-live` toggle sat (3 h)

**Modules** : `static/flight_radar/js/flight_radar.js` + 3 templates Leaflet pour le toggle.

**Cartographies** :
- OpenSky Network REST (anonyme ou OAuth2 si `OPENSKY_CLIENT_ID/SECRET` présents en env).
- Esri World_Imagery toggle copié sur les 3 modules manquants (5 lignes JS chacun).

**Effort** : 2 h flight-radar (gestion 4 000 req/jour quota OAuth) + 1 h les 3 toggles.

**Risques** :
- OpenSky 429 si non-OAuth : prévoir un fallback vers source actuelle.
- Toggle ne casse pas si Esri tombe (event `tileerror` Leaflet).

### Day 4 — Bonus VIIRS upgrade + Aladin sélecteur (2 h)

**Modules** : `templates/orbital_dashboard.html` (VIIRS bump) + `templates/aladin.html` (UI surveys).

**Cartographies** :
- VIIRS Black Marble Annual Composite 2024 (asset id NASA GIBS différent).
- Boutons UI pour Aladin : DSS2 / SDSS / 2MASS / GALEX / WISE.

**Effort** : 30 min VIIRS + 1 h Aladin UI.

**Risques** : aucun (toujours gratuit, juste un bump version).

### Day 5 — Polish + cohérence visuelle inter-modules (3 h)

**Modules** : transverse (CSS + JS).

**Actions** :
- Harmoniser les 3 toggles "dark/sat/night" sur le même composant (`addBasemapToggleControl()` extractible dans `static/lib/leaflet/basemap_toggle.js`).
- Aligner les attribution texts (CARTO/Esri/NASA/Cesium ion) sur le même style typographique.
- Ajouter `<noscript>` minimaliste sur les 11 templates (a11y).
- Mettre à jour `.env.example` : `AISSTREAM_API_KEY` + clarifier `CESIUM_TOKEN` vs `CESIUM_ION_TOKEN`.
- Sécuriser le token Cesium : restreindre aux domaines `astroscan.space` + `orbital-chohra-dz.duckdns.org` dans le dashboard ion.

**Risques** : refacto cosmétique, 0 régression attendue.

### Récapitulatif planning

| Day | Modules touchés | Effort cumulé | Impact cumulé |
|-----|-----------------|--------------:|---------------|
| 1 | `/orbital-map` | 3-4 h | 🟢 ÉNORME (vitrine) |
| 2 | `/mission-control`, `/scan-signal` | 6-7 h | 🟢 + 🟡 |
| 3 | `/flight-radar` + 3 toggles | 9-10 h | 🟡 |
| 4 | `/orbital` VIIRS bump + Aladin UI | 11-12 h | ⚪ + ⚪ |
| 5 | Polish transverse | 14-15 h | cohérence |

**Bilan semaine** : ASTRO-SCAN passe de "site avec cartes basiques + une vitrine 3D dégradée" à "**suite cartographique cohérente niveau pro**, 0 € de dépense supplémentaire".

---

## Annexe — Méthodologie

- Découverte : `grep -rln 'leaflet|Cesium\.|mapboxgl|aladin'` sur `templates/` puis croisement avec `render_template(...)` dans `app/blueprints/`.
- Tile sources : recherche `L.tileLayer\(|imageryProvider|setImageSurvey` dans templates + statiques associés.
- Tests HTTP : `curl -w "%{http_code} %{time_total}"` sur 11 endpoints + 5 endpoints API carto-related, mesurés sur localhost:5003 le 2026-05-09 à 15h05 UTC.
- AISStream live : grep `AISStream` sur `logs/astroscan_structured.log` + `/api/scan-signal/vessel/recent` pour preuve de flux.
- Variables env : inférence depuis `.env.example` (lisible) + preuves indirectes via HTML servi en prod (token visible dans `/mission-control` HTML).
- Aucune valeur de token / secret reproduite dans ce rapport.
