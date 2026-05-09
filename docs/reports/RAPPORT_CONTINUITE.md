# Rapport de continuité — AstroScan / Orbital-Chohra

**Objectif :** Documenter l’architecture actuelle pour assurer la continuité du projet sans régression.

**Dernière mise à jour :** Mars 2025

---

## 1. Vue d’ensemble

| Composant        | Rôle principal |
|------------------|----------------|
| **station_web.py** | Backend Flask unique : routes, APIs, logique métier. |
| **templates/**   | Pages HTML (portail, lab, orbital map, mission control, etc.). |
| **modules/**     | Packages Python (digital_lab, space_analysis_engine, research_center, etc.). |
| **data/**        | Données persistantes (DB, uploads lab, images_espace). |
| **static/**      | Fichiers statiques (JSON, assets). |

**Points critiques :**
- Ne pas renommer ni supprimer de routes déjà utilisées par le frontend.
- Ne pas modifier les réponses JSON des APIs sans adapter le frontend.
- Conserver la structure du portail (PAGES, ids des iframes, noms de pages).

---

## 2. Portail principal (`templates/portail.html`)

### 2.1 Navigation

Chaque entrée de menu est liée à une page par son **id de page** (clé dans `PAGES`).

| Id de page       | Label affiché     | URL chargée (iframe) |
|------------------|-------------------|----------------------|
| `home`           | Accueil           | (splash, pas d’iframe) |
| `dashboard`      | Dashboard QG      | `/dashboard` |
| `overlord`       | Overlord Live     | `/overlord_live` |
| `galerie`        | Archive Stellaire| `/galerie` |
| `observatoire`   | Observatoire Mondial | `/observatoire` |
| `vision`        | Vision 2026      | `/vision` |
| `mission-control` | Mission Control | `/mission-control` |
| `orbital-map`    | Orbital Map       | `/orbital-map` |

**À ne pas casser :**
- **Fonction `navigate(page)`** : reçoit l’id de page (ex. `'orbital-map'`), affiche l’iframe correspondant et met à jour la classe `active` sur le bon `nav-item`.
- **Objet `PAGES`** : chaque clé doit avoir `frame` (id de l’iframe, ex. `frame-orbital-map`) et `label`.
- **Ids des iframes** : `frame-<page>` (ex. `frame-orbital-map`). L’iframe a `data-src="/orbital-map"` et est chargée au premier `navigate('orbital-map')`.

**Pour ajouter une nouvelle page sans casser l’existant :**
1. Ajouter un `<div class="nav-item" id="nav-<page>" onclick="navigate('<page>')">` dans la sidebar.
2. Ajouter une iframe : `<iframe id="frame-<page>" class="page-frame" data-src="/<url>"></iframe>` dans `#portal-pages`.
3. Ajouter dans `PAGES` : `'<page>': { frame: 'frame-<page>', label: 'Nom affiché' }`.
4. Créer la route et le template côté backend si besoin.

---

## 3. Orbital Map 3D (`templates/orbital_map.html`)

**Fichier autonome :** tout le module est dans ce template (pas de JS externe labellisé « orbital » ailleurs).

### 3.1 Dépendances externes

- **Cesium 1.118** (script + widgets.css).
- **satellite.js** (unpkg) : SGP4 / TLE.
- **Cesium Ion** : token défini en début de script (`Cesium.Ion.defaultAccessToken`). Si absent, un `console.warn` est émis.

### 3.2 Données et APIs utilisées

| API / donnée      | Rôle |
|-------------------|------|
| **GET /api/iss**  | Position temps réel ISS (lat, lon, alt en km). |
| **GET /api/tle/catalog** | Liste de satellites avec TLE (name, tle1, tle2). |

**À ne pas modifier côté backend :**
- Réponse `/api/iss` : au minimum `lat`, `lon`, `alt` (alt en km).
- Réponse `/api/tle/catalog` : `{ "satellites": [ { "name", "tle1", "tle2" }, ... ] }`.

### 3.3 Structure logique (ordre dans le script)

1. **Viewer Cesium** + `enableLighting`, **PointPrimitiveCollection** (`satelliteLayer`), tableaux `satRecs`, `satPoints`.
2. **Observateur** : `observer = { lat, lon, height }` (ex. Tlemcen). `visibleSatellites`, `lastRadarUpdate`, `predictedPasses`.
3. **Fonctions** : `computeElevation()`, `predictPasses()`, `runPredictions()`, `updatePassUI()`, `updateRadarUI()`.
4. **Entités** : ISS (entity + trail), ellipse de couverture radar, marqueur « AstroScan Radar Station ».
5. **Catalogue** : `loadSatelliteCatalog()` → GET `/api/tle/catalog`, jusqu’à 500 satellites, création des points dans `satelliteLayer`.
6. **Boucles** : `updateSatellites()` (2 s), `updateISS()` (15 s), `runPredictions()` (5 min), `updateRadarUI()` (throttle 5 s).

**Risques de régression :**
- Changer les noms des variables globales (`observer`, `visibleSatellites`, `satRecs`, `satPoints`) peut casser les callbacks et le radar.
- Supprimer ou renommer `updateISS()` ou l’entité `iss` casse le suivi ISS.
- Modifier le format de `predictPasses()` ou de `predictedPasses` casse `updatePassUI()`.

---

## 4. Digital Lab (`/lab`, `templates/lab.html`)

### 4.1 Deux systèmes d’upload/analyse (ne pas les confondre)

| Système   | Upload              | Analyse              | Stockage |
|----------|----------------------|----------------------|----------|
| **Lab DB** | POST `/lab/upload`   | POST `/lab/analyze`  | `SPACE_IMAGE_DB` |
| **API legacy** | POST `/api/lab/upload` | POST `/api/lab/analyze` | `LAB_UPLOADS` |

- **Lab DB** : nom de fichier conservé, utilisé par le panneau « LAB DATABASE » et le collecteur automatique (APOD).
- **API legacy** : fichier enregistré avec un UUID, utilisé par le bouton « Upload (API) » et « Run analysis » (sans « Lab »).

**À ne pas casser :**
- Réponse `/api/lab/upload` : `{ id, path, uploaded }`.
- Réponse `/api/lab/analyze` : structure complète du pipeline (report, stars, objects, etc.).
- Réponse `/lab/upload` : `{ status: "saved", path }`.
- Réponse `/lab/analyze` : `{ stars_detected, objects_detected, brightness_mean, report }`.
- Réponse `/lab/dashboard` : `{ number_of_images, latest_images, sources }`.

### 4.2 Chemins et configuration

- **SPACE_IMAGE_DB** : répertoire des images du lab (uploads + APOD).  
  Défaut : `STATION/data/images_espace`.  
  Sur Windows : définir la variable d’environnement `SPACE_IMAGE_DB` (ex. `D:\images_espace`).
- **LAB_UPLOADS** : `STATION/data/lab_uploads` (uploads API legacy).
- **Métadonnées** : pour chaque image téléchargée (ex. APOD), un fichier `<filename>.meta.json` est créé avec `source`, `telescope`, `date`, `object_name`, `filename`. Le dashboard lit ces fichiers pour afficher les « sources ».

### 4.3 Collecteur automatique (telescope images)

- **Fonction** : `_download_images_from_space()` (NASA APOD uniquement dans l’implémentation actuelle).
- **Planification** : premier run 60 s après démarrage du serveur, puis toutes les 24 h via `threading.Timer` dans `_run_lab_image_collector_once()`.
- **Ne pas** désactiver ou renommer `_start_lab_image_collector()` si vous voulez garder les téléchargements automatiques.

### 4.4 Pipeline d’analyse (modules/digital_lab)

- **Entrée** : `run_pipeline(image_source)` avec `image_source` = chemin fichier ou bytes.
- **Étapes** : load_image → reduce_noise, normalize → detect_stars, detect_objects → compute_brightness → detect_anomalies → generate_report.
- **Sortie** : dict avec `stars`, `objects`, `brightness` (dont `global_mean`), `report`.
- `/lab/analyze` s’appuie sur ce pipeline et expose `stars_detected`, `objects_detected`, `brightness_mean`, `report`.

---

## 5. Routes backend critiques (à ne pas supprimer ni changer de contrat)

### 5.1 Portail / Orbital Map

- `GET /`  
- `GET /portail`  
- `GET /orbital-map` → `orbital_map.html`  
- `GET /api/iss` → `{ lat, lon, alt, ... }`  
- `GET /api/tle/catalog` → `{ satellites: [ { name, tle1, tle2 } ] }`  

### 5.2 Lab (nouveau système)

- `POST /lab/upload` (body: multipart, champ `image`)  
- `GET /lab/images` → `{ images: [...] }`  
- `POST /lab/analyze` (body: multipart, champ `image`) → `{ stars_detected, objects_detected, brightness_mean, report }`  
- `GET /lab/dashboard` → `{ number_of_images, latest_images, sources }`  

### 5.3 Lab (API legacy, utilisée par l’ancienne UI)

- `GET /lab` → `lab.html`  
- `POST /api/lab/upload`  
- `POST /api/lab/analyze` (fichier ou `upload_id` en JSON)  
- `GET /api/lab/report`  

### 5.4 Autres modules souvent utilisés

- Mission Control : `/mission-control`, `/api/mission-control`  
- Telescope / sync : `/api/telescope/*`, `/api/sync/state`  
- Santé : `/api/health`, `/api/system/status`  

---

## 6. Fichiers et dossiers sensibles

| Chemin / fichier        | Rôle | Action à éviter |
|------------------------|------|-------------------|
| `station_web.py`       | Toutes les routes et config lab/orbital | Supprimer des routes ou changer le type de réponse sans mettre à jour le frontend. |
| `templates/portail.html` | Navigation et iframes | Modifier `PAGES`, les ids `frame-*` ou `navigate()` sans cohérence. |
| `templates/orbital_map.html` | Carte 3D, radar, passes | Casser les noms d’APIs (`/api/iss`, `/api/tle/catalog`) ou les variables globales utilisées dans les callbacks. |
| `templates/lab.html`   | Upload, analyse, LAB DATABASE | Changer les ids des éléments (`astroFile`, `report`, `labDbStats`, etc.) ou les URLs `/lab/*` sans mettre à jour le JS. |
| `modules/digital_lab/` | Pipeline d’analyse d’images | Changer la signature ou le format de sortie de `run_pipeline()` sans adapter `/lab/analyze` et `/api/lab/analyze`. |
| `data/images_espace/` | Images et métadonnées lab | Supprimer en masse ou renommer le dossier sans mettre à jour `SPACE_IMAGE_DB`. |

---

## 7. Dépendances Python (hors requirements.txt)

Le pipeline digital_lab et l’analyse d’images utilisent en pratique :

- **numpy**  
- **opencv-python** (cv2) — chargé dans `image_loader`, `object_detection`  
- **scikit-image** — optionnel dans `object_detection` (sinon fallback OpenCV)  
- **astropy** — optionnel pour FITS dans `image_loader`  

Si vous déployez sur un nouvel environnement, installer ces paquets pour que `/lab/analyze` et `/api/lab/analyze` fonctionnent sans erreur d’import.

---

## 8. Checklist avant une mise en production ou un refactor

- [ ] Aucune route utilisée par le portail ou par Orbital Map n’a été supprimée ou renommée.
- [ ] Les réponses JSON des APIs appelées par le frontend n’ont pas changé de structure (champs requis présents et typés comme attendu).
- [ ] Dans `portail.html`, `PAGES` et les iframes correspondent bien aux nouvelles pages, et aucune entrée existante n’a été cassée.
- [ ] Dans `orbital_map.html`, les URLs `/api/iss` et `/api/tle/catalog` sont toujours utilisées et le backend renvoie le bon format.
- [ ] Lab : `SPACE_IMAGE_DB` (ou `LAB_UPLOADS` pour l’API legacy) existe et est accessible en écriture ; le collecteur automatique et le dashboard restent cohérents avec ces chemins.
- [ ] Les dépendances optionnelles (cv2, skimage, astropy) sont installées si vous utilisez le lab d’analyse d’images.

---

## 9. Résumé des points « ne pas casser »

1. **Portail** : garder `navigate()`, `PAGES`, et les ids d’iframes `frame-*` cohérents avec les nouveaux onglets.  
2. **Orbital Map** : ne pas modifier `/api/iss` ni `/api/tle/catalog` (format actuel). Ne pas supprimer l’entité ISS ni `updateISS()`.  
3. **Lab** : garder les deux systèmes (Lab DB vs API legacy) si les deux sont utilisés ; ne pas changer les réponses de `/lab/upload`, `/lab/analyze`, `/lab/dashboard`.  
4. **Chemins** : ne pas supprimer `SPACE_IMAGE_DB` ni le créateur de répertoire ; sur Windows, documenter `SPACE_IMAGE_DB` si utilisé.  
5. **Digital lab pipeline** : toute évolution de `run_pipeline()` doit être reflétée dans les routes qui l’appellent (`/lab/analyze`, `/api/lab/analyze`) pour ne pas casser le frontend.

Ce document peut être mis à jour à chaque ajout de module ou changement d’API majeur pour maintenir la continuité sans régression.
