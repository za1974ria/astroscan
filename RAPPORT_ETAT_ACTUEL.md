# Rapport détaillé — État actuel du système Orbital-Chohra / AstroScan

**Objectif :** Documenter l’état du projet pour assurer la continuité technique et la maintenance.  
**Dernière mise à jour :** 2026-03-15  
**Projet :** Astro-Scan · Orbital-Chohra · Station Hillsboro  

---

## 1. Vue d’ensemble

- **Stack :** Flask (backend), HTML/CSS/JS (frontend), pas de framework SPA.
- **Point d’entrée principal :** `/portail` → `templates/portail.html`.
- **Rôle du portail :** Shell de navigation (sidebar, barre du haut, splash) qui charge les modules dans des **iframes** via `navigate(page)`. Chaque module est une page Flask servie dans une iframe.
- **Fichier backend unique :** `station_web.py` (environ 2 700 lignes, routes + logique métier).

---

## 2. Architecture des fichiers clés

| Fichier / Dossier | Rôle |
|-------------------|------|
| **station_web.py** | Application Flask : routes, APIs, cache, helpers, chargement `.env`. |
| **templates/portail.html** | Interface principale : layout, sidebar, splash, iframes, scripts (i18n, ISS, SDR, Voyager, stats, navigate, PWA, System Health). |
| **templates/space.html** | Dashboard « Space Intelligence » : cartes ISS, satellites, Voyager, solaire, DSN, météo spatiale, APOD ; utilise `fetchAPI()` avec timeout 5 s. |
| **templates/mission_control.html** | Vue 3D Cesium (globe, ISS) ; chargée en iframe depuis le portail. |
| **templates/observatoire.html** | Observatoire (télescopes, modal sondes) ; charge `sondes_aegis.js` dans son propre template. |
| **templates/overlord_live.html** | Overlord Live ; charge aussi `sondes_aegis.js`. |
| **templates/galerie.html** | Archive stellaire (observations, stats). |
| **templates/vision.html** | Vision 2026. |
| **templates/research_dashboard.html** | Sert la route `/dashboard` (étiquette « Dashboard QG » dans le portail). |
| **static/** | Favicon, `voyager_live.json`, `space_weather.json`, `passages_iss.json`, `sondes_aegis.js`, `sondes.js`, PWA (sw.js, manifest.json, icons). |
| **data/** | SQLite `archive_stellaire.db`, fichiers JSON métier (shield, hub, SDR, etc.). |
| **modules/** | Logique métier (mission_control, sondes_module, space_intelligence_engine, digital_lab, research_center, live_feeds, catalog, etc.). |
| **.env** | Variables d’environnement (clés API, chemins, etc.). |

---

## 3. Portail et navigation (continuité critique)

### 3.1 Structure HTML

- **Sidebar (220px) :** Liens de navigation `navigate('home')`, `navigate('dashboard')`, `navigate('overlord')`, `navigate('galerie')`, `navigate('observatoire')`, `navigate('vision')`, `navigate('mission-control')` ; liens externes (MODE SCIENTIFIQUE, DIGITAL LAB, RESEARCH, etc.).
- **Zone de contenu :**
  - **#home-screen** : bloc « Accueil » (portal-hero + splash avec boutons et cartes). Affiché par défaut ; masqué quand un module est ouvert.
  - **#portal-pages** : conteneur des iframes. Une seule iframe visible à la fois (affichage géré en JS).
- **Iframes (toutes dans #portal-pages) :**
  - `id="frame-dashboard"`    → `data-src="/dashboard"`
  - `id="frame-overlord"`     → `data-src="/overlord_live"`
  - `id="frame-galerie"`      → `data-src="/galerie"`
  - `id="frame-observatoire"`→ `data-src="/observatoire"`
  - `id="frame-vision"`       → `data-src="/vision"`
  - `id="frame-mission-control"` → `data-src="/mission-control"`

### 3.2 Logique `navigate(page)`

- Début de fonction : mise à jour de l’item actif de la sidebar (`document.querySelectorAll(".nav-item").forEach(...)` puis `#nav-${page}.classList.add("active")`).
- Si `page === 'home'` : afficher `#home-screen`, masquer toutes les iframes, retour.
- Sinon : masquer `#home-screen`, masquer toutes les `.page-frame`, récupérer `frame = document.getElementById("frame-" + page)`.
- Si `frame` absent : `console.error("FRAME NOT FOUND:", page)` et return.
- Si `frame.src` vide ou `about:blank` : `frame.src = frame.dataset.src`.
- Afficher l’iframe : `frame.style.display = "block"`.
- **Exposition globale :** `window.navigate = navigate`.

Ne pas supprimer ni renommer les IDs `frame-*` et `nav-*` sans adapter `navigate()` et les `onclick`.

### 3.3 CSS important

- **#portal-pages** : `position:absolute; top:0; left:0; right:0; bottom:0; overflow:hidden;`
- **.page-frame** : `display:none; width:100%; height:100%; border:0; background:black;`
- **.content-area** : grille colonne 2, padding, `margin-right:0`.
- **.nav-item.active** : style pour l’item de navigation actif.

---

## 4. Backend — Cache et robustesse

### 4.1 Cache mémoire (station_web.py)

- **CACHE** : dictionnaire global.
- **cache_get(key, ttl)** : renvoie la valeur si présente et non expirée (âge < `ttl` secondes), sinon `None`.
- **cache_set(key, value)** : enregistre la valeur avec un timestamp.

### 4.2 Endpoints avec cache (TTL)

| Endpoint | Clé cache | TTL |
|----------|-----------|-----|
| /api/iss | `iss` | 15 s |
| /api/orbits/live | `orbits_live` | 30 s |
| /api/space-weather | `space_weather` | 60 s |
| /api/feeds/apod_hd | `apod_hd` | 3600 s |

Les réponses sont construites puis mises en cache (dict) ; en cas de cache valide, on renvoie `jsonify(cached)` sans refaire les appels externes ou la lecture fichier.

### 4.3 DSN (Deep Space Network)

- Route : **/api/dsn**. Appel externe vers NASA (eyes.nasa.gov/dsn/data/dsn.xml).
- En cas d’exception (timeout, 403, réseau) : **retour 200** avec un JSON de repli :
  - `stations` : liste de 3 stations (Goldstone USA, Madrid Spain, Canberra Australia) avec `friendlyName`, `name`, `dishes`.
  - `status` : `"fallback"`.
- Le frontend ne reçoit jamais de 500 ; il affiche soit les données NASA soit le fallback.

### 4.4 Monitoring système

- **GET /api/system/status** : JSON avec `system` (Orbital-Chohra), `status` (online), `modules` (nombre), `apis` (10), plus `version`, `timestamp`, `modules_list`.
- Utilisé par le panneau **System Health** dans la sidebar du portail (rafraîchi toutes les 10 s).

---

## 5. Frontend — Robustesse (space.html)

- **fetchAPI(url)** : wrapper autour de `fetch` avec **AbortController** et **timeout 5 s**. En cas d’erreur ou timeout, retourne `{ error: true }` au lieu de faire planter l’UI.
- Les cartes Space Intelligence (ISS, satellites, Voyager, DSN, météo, APOD, etc.) utilisent `fetchAPI()` et gèrent `d.error` en affichant un message d’erreur.

---

## 6. Routes principales (à ne pas casser)

| Route | Méthode | Template / comportement |
|-------|---------|--------------------------|
| / | GET | Redirect → /observatoire |
| /portail | GET | portail.html |
| /dashboard | GET | research_dashboard.html |
| /overlord_live | GET | overlord_live.html |
| /galerie | GET | galerie.html |
| /observatoire | GET | observatoire.html |
| /vision | GET | vision.html |
| /mission-control | GET | mission_control.html |
| /space | GET | space.html |
| /favicon.ico | GET | send_from_directory('static', 'favicon.ico') |
| /api/iss | GET | JSON (cache 15 s) |
| /api/orbits/live | GET | JSON (cache 30 s) |
| /api/voyager-live | GET | Lecture static/voyager_live.json |
| /api/dsn | GET | JSON (NASA ou fallback) |
| /api/space-weather | GET | JSON (cache 60 s) |
| /api/feeds/apod_hd | GET | JSON (cache 3600 s) |
| /api/system/status | GET | JSON monitoring |
| /api/latest | GET | Stats archive (sidebar) |
| /module/<name> | GET | render_template(f"{name}.html") si le fichier existe |

Toute suppression ou modification de ces routes impacte le portail ou Space Intelligence.

---

## 7. Fichiers statiques critiques

- **static/favicon.ico** : requis par le portail et la route `/favicon.ico`.
- **static/voyager_live.json** : format `voyager_1`, `voyager_2` avec `distance_km` (widget DSN du portail et Space Intelligence).
- **static/space_weather.json** : utilisé par `/api/space-weather`.
- **static/passages_iss.json** : utilisé par `/api/passages-iss`.
- **static/sondes_aegis.js** : chargé uniquement dans les templates qui en ont besoin (observatoire, overlord_live), **pas** dans le portail.

---

## 8. Scripts du portail (ordre et dépendances)

Dans **portail.html**, les scripts principaux (dans l’ordre) :

1. IIFE avec i18n, langue, hamburger, étoiles, horloge.
2. Chargement ISS (globe, lat/lon, crew, etc.) et visites.
3. SDR (passes, countdown, indicateur capture).
4. Hubble sidebar (images).
5. **PAGES** (mapping page → frame + label), **navigate(page)** (avec mise à jour sidebar active et home-screen).
6. **loadStats()** (api/latest → sb-total, sb-anomalies, sb-sources, sb-req, sb-bar).
7. PWA sync (bouton, vidage cache).
8. **syncVoyagerPortal()** (api/voyager-live → #voyager-live-container).
9. **loadSystemHealth()** (api/system/status → #system-health-status), appel initial + setInterval 10 s.

Modifier l’ordre ou supprimer un de ces blocs peut casser l’affichage ou la navigation.

---

## 9. Points de vigilance pour la maintenance

1. **Ne pas charger de script spécifique à un module (ex. sondes_aegis.js) dans le portail** : les modules sont dans des iframes ; le portail ne doit pas manipuler le DOM des iframes.
2. **Cohérence navigate / iframes** : tout nouvel onglet de navigation doit avoir un `id="nav-xxx"`, un `onclick="navigate('xxx')"` et une iframe `id="frame-xxx"` avec `data-src="/route_correspondante"`.
3. **DSN** : en environnement sans accès sortant, l’API renvoie le fallback ; pas d’obligation de réseau pour que le portail reste stable.
4. **Cache** : le cache est en mémoire ; il est réinitialisé à chaque redémarrage du processus Flask. Pour un cache persistant, il faudrait une couche type Redis ou fichier.
5. **Base de données** : `data/archive_stellaire.db` (observations, visites). À sauvegarder en cas de déploiement ou migration.

---

## 10. Rapports et documentation existants

- **SYSTEM_FINAL_CHECK.md** : vérification finale (navigation, APIs, fichiers, score de readiness).
- **READINESS_REPORT.md** : scan opérationnel (routes, iframes, liens, JS, CSS).
- **RAPPORT_NETTOYAGE_ARCHITECTURE.md** : refactorisation portail / modules / sondes.
- **FICHE_TECHNIQUE.md**, **RAPPORT_DETAILLE_ASTROSCAN.md** : documentation projet plus large.

---

## 11. Commandes utiles

- Démarrer le serveur :  
  `cd /root/astro_scan && python3 station_web.py`
- Arrêter :  
  `pkill -9 -f station_web`
- Vérifier une route (ex. status) :  
  `curl -s http://127.0.0.1:5000/api/system/status`

---

## 12. Résumé pour la continuité

| Élément | État actuel |
|--------|-------------|
| Portail | Shell avec sidebar 220px, 6 modules en iframes, splash, System Health. |
| Navigation | `navigate(page)` + mise à jour sidebar active + home-screen ; pas de conflit iframe. |
| APIs critiques | ISS, orbits, voyager-live, space-weather, apod_hd avec cache ; DSN avec fallback. |
| Space Intelligence | Page autonome `/space` avec fetchAPI (timeout 5 s) et cartes. |
| Robustesse | Cache backend, fallback DSN, timeout frontend, panneau System Health. |
| Fichiers sensibles | portail.html, station_web.py, static (favicon, JSON, sondes_aegis.js). |

En s’appuyant sur ce rapport et sur les fichiers listés, un nouveau développeur ou une nouvelle session peut reprendre la maintenance et les évolutions sans perdre la continuité fonctionnelle du système Orbital-Chohra.
