# Rapport d’assurance de continuité — AstroScan

**Document :** Rapport détaillé pour l’assurance de continuité d’exploitation  
**Projet :** AstroScan (ORBITAL-CHOHRA)  
**Racine :** `/root/astro_scan`  
**Date de génération :** 2026-03-10  

---

## 1. Objet et périmètre du rapport

Ce document décrit de façon **exhaustive** l’architecture, les dépendances, les données et les points critiques du projet AstroScan afin de garantir la continuité de service en cas de changement d’équipe, de panne, de migration ou d’audit. Il ne modifie aucun code ni configuration.

**Périmètre couvert :**
- Structure des répertoires et fichiers critiques
- Tous les modules Python et leurs rôles précis
- Points d’entrée (Flask, scripts)
- Configuration et variables d’environnement
- Données persistantes (chemins, schémas implicites)
- Dépendances externes (obligatoires et optionnelles)
- Routes HTTP et APIs
- Chaînes d’appels (qui appelle qui)
- Points de défaillance unique et risques
- Procédures de reprise recommandées
- Lacunes (tests, documentation)

**Périmètre exclu :** Environnement virtuel `venv/`, binaires tiers, contenu des bases de données (structure uniquement).

---

## 2. Résumé exécutif

AstroScan est une **application web Flask** de type « station spatiale / observatoire » qui agrège :
- **Flux live** (APOD, Hubble, JWST, ISS, Voyager, météo spatiale, NEO, etc.)
- **Digital Lab** : pipeline d’analyse d’images (prétraitement, détection d’étoiles/objets, photométrie, détection d’astéroïdes/objets mobiles, validation TLE/MPC, motion tracking)
- **Research Center** : résumés recherche, logs, archive scientifique
- **Orbital Map** : carte Cesium avec TLE et passes satellites
- **Space Intelligence** : synthèse d’événements et alertes

**Risques principaux pour la continuité :**
- **Fichier unique** `station_web.py` (~3400+ lignes) : point de défaillance logique ; toute erreur peut impacter l’ensemble du service.
- **Dépendances non déclarées** dans `requirements.txt` : `opencv-python`, `sgp4`, `skyfield`, `astropy`, `scikit-image` sont utilisés mais absents du fichier ; une réinstallation propre (nouveau venv) peut casser le Lab et la détection.
- **Aucune suite de tests** : pas de `tests/` ni de `test_*.py` dédiés ; les régressions ne sont pas détectées automatiquement.
- **Configuration et secrets** : clés API (Cesium, NASA, Groq, Gemini) et chemins critiques dans `.env` et en dur dans `station_web.py` ; perte du `.env` ou migration de serveur nécessite une recette manuelle.
- **Données critiques** : SQLite (`archive_stellaire.db`), TLE (`data/tle/active.tle`), MPC (`data/mpc/asteroids.dat`), métadonnées Lab (`data/metadata/`), archive scientifique ; pas de procédure de backup documentée.

**Recommandation prioritaire :** Figer les dépendances complètes (y compris optionnelles) dans `requirements.txt`, documenter la procédure de backup/restauration des dossiers `data/` et `.env`, et introduire au moins des tests de smoke sur les routes principales et le pipeline Lab.

---

## 3. Architecture détaillée

### 3.1 Arborescence des répertoires (détail)

| Chemin | Rôle précis | Fichiers / sous-dossiers critiques |
|--------|-------------|-------------------------------------|
| **/** | Racine projet | `station_web.py`, `requirements.txt`, `.env`, scripts Python racine |
| **backup/** | Sauvegardes templates HTML | Copies de `ce_soir`, `galerie`, `observatoire`, etc. |
| **backups/** | Sauvegardes datées observatoire | Fichiers `observatoire_backup_*.html` |
| **core/** | Ancien code / backup | `eye_of_aegis.py.bak` uniquement |
| **data/** | **Données persistantes** | Voir tableau 3.2 |
| **data/images_espace/raw** | Images brutes Lab | Fichiers image (APOD, ESO, JWST, etc.) |
| **data/metadata** | Métadonnées Lab (JSON par image) | Un fichier `<nom_image>.json` par image raw |
| **data/tle** | Catalogue TLE satellites | `active.tle` (utilisé par orbital_map, catalog_crosscheck, API passes) |
| **data/mpc** | Catalogue astéroïdes MPC | `asteroids.dat` (asteroid_catalog_crosscheck) |
| **data/science_archive** | Archive scientifique | `reports/`, `objects/`, `discoveries/` |
| **data/research_logs** | Logs Research Center | Fichiers JSON (events, summaries) |
| **data/skyview** | Images téléchargées (SkyView) | Hubble, JWST, ESO, etc. |
| **data/sdr** | Données SDR | Ex. `noaa/` |
| **deploy/** | Déploiement | Vide |
| **docs/** | Documentation | Ce rapport et futurs docs |
| **logs/** | Fichiers de log applicatifs | `web`, `orbital_system`, `apod`, `telescope_feeds`, `voyager`, etc. |
| **modules/** | **Code Python métier** | Voir section 4 |
| **static/** | Assets web statiques | JSON (space_weather, voyager_live, passages_iss), JS (sondes, PWA), img/, manifest.json |
| **telescope_live/** | État live télescope | `current_live.jpg`, `current_title.txt`, `live_report.txt`, `sync_state.json`, `source_*` |
| **templates/** | Templates Jinja2 | Tous les .html servis par Flask |
| **venv/** | Environnement virtuel Python | Hors périmètre fonctionnel |

**Scripts à la racine (entrées possibles cron/systemd) :**
- `aegis_auto.py`, `calculateur_passages.py`, `ce_soir_module.py`, `deploy_obs.py`
- `nasa_feeder.py`, `news_module.py`, `noyau_orbital.py`, `orbital_shield.py`
- `pretranslate.py`, `skyview_module.py`, `space_weather_feeder.py`, `survol_terrestre.py`
- `telescope_feeds.py`, `voyager_tracker.py`

### 3.2 Données persistantes (chemins exacts et usage)

| Chemin ou fichier | Type | Rôle | Référence dans le code |
|-------------------|------|------|-------------------------|
| `data/archive_stellaire.db` | SQLite | Table `visits` (compteur visites), éventuellement autres tables | `station_web.py` : `DB_PATH`, `get_db()`, `_init_visits_table()` |
| `data/tle/active.tle` | Fichier TLE (3 lignes par satellite) | Catalogue satellites pour Cesium, cross-check TLE, API passes | `catalog_crosscheck.py` : `_default_tle_path()` ; `station_web.py` : téléchargement TLE, `api_tle_*`, `api_satellite_passes` |
| `data/mpc/asteroids.dat` | Fichier MPC (lignes texte) | Orbites astéroïdes pour cross-check MPC | `asteroid_catalog_crosscheck.py` : `_default_mpc_path()` |
| `data/shield_status.json` | JSON | État bouclier orbital | `station_web.py` : `SHIELD_F`, `api_shield` |
| `data/telescope_hub.json` | JSON | État hub télescope | `station_web.py` : `HUB_F`, `api_telescope_hub` |
| `data/sdr_status.json` | JSON | État SDR | `station_web.py` : `SDR_F`, `api_sdr_status` |
| `data/noaa_tle.json` | JSON | Cache TLE NOAA (passes SDR) | `station_web.py` : API passes SDR |
| `data/images_espace/raw/*` | Images (PNG, JPG, FITS) | Images brutes Lab ; pipeline les lit | `analysis_pipeline.py` : chemins dérivés de `image_source` |
| `data/metadata/<nom>.json` | JSON | Métadonnées par image (pointing, scale, asteroid_detection, moving_object_validation, motion_tracking) | `analysis_pipeline.py` : `_metadata_path_for_image()`, `_update_metadata_for_asteroids()` |
| `data/science_archive/reports/*` | JSON | Rapports Digital Lab datés | `report_saver.py`, `archive_manager.py` |
| `data/science_archive/objects/*` | JSON | Catalogues d’objets détectés | `object_cataloger.py` |
| `data/science_archive/discoveries/*` | JSON | Logs de découvertes | `discovery_saver.py` |
| `data/research_logs/*` | JSON | Événements et résumés Research Center | `research_logger.py` |
| `telescope_live/current_live.jpg` | Image | Image live affichée (télescope) | Routes `/api/telescope/live`, `/api/image` |
| `telescope_live/sync_state.json` | JSON | État de synchronisation des sources | `_sync_state_read/Write` |
| `static/space_weather.json`, `voyager_live.json`, `passages_iss.json` | JSON | Données servies aux pages (météo, Voyager, ISS) | Routes API et templates |

**Convention métadonnées Lab :**  
Pour une image `data/images_espace/raw/<fichier>`, les métadonnées sont dans `data/metadata/<fichier>.json`. Le chemin est résolu dans `analysis_pipeline.py` via `_metadata_path_for_image(image_path)` (recherche du segment `images_espace/raw` dans le path).

---

## 4. Inventaire des modules Python (détail du détail)

### 4.1 Package racine `modules/`

| Fichier | Rôle précis | Symboles publics | Dépendances externes | Dépendances internes |
|---------|--------------|------------------|----------------------|----------------------|
| `__init__.py` | Déclaration package | Aucun | Aucune | Aucune |
| `astro_validation.py` | Validation d’images astro (métadonnées, texte) | `is_valid_astro_image`, `normalize_metadata` | `re` | Aucune |
| `groq_ai.py` | Client Groq (clé dans env) ; analyse texte | `get_groq_client`, `run_text_analysis` | `os`, `groq` (optionnel) | Aucune |
| `image_science_engine.py` | Analyse simple d’images (étoiles, galaxies, anomalies) | `analyze_space_image` | `os`, `json`, `PIL` (optionnel), `math` | Aucune |
| `space_intelligence_engine.py` | Synthèse événements spatiaux → alertes / niveau de risque | `detect_space_event` | Aucune | Aucune |
| `astro_ai.py` | Explications statiques d’objets célestes (Mars, Jupiter, ISS, etc.) | `explain_object` | Aucune | Aucune |
| `mission_control.py` | Statut global mission (ISS, Mars, NEO, Voyager) | `get_global_mission_status` | Aucune | Aucune |
| `observation_planner.py` | Phase lunaire et objets à observer ce soir (subprocess + JSON) | `get_moon_phase`, `get_tonight_objects` | `subprocess`, `json`, `math`, `datetime` | Aucune |
| `catalog.py` | Catalogue Messier (recherche, get par id) | `search_catalog`, `get_object` | `json`, `os`, `subprocess` | Aucune |
| `sondes_module.py` | Télémétrie (Voyager JPL, ISS, rovers Mars) ; curl + JSON | `get_sondes_payload` | `os`, `json`, `subprocess`, `datetime` | Aucune |
| `live_feeds.py` | Flux live (Hubble, JWST, SpaceX, positions SS, news, ISS Tlemcen, Mars) | `get_hubble_images`, `get_jwst_images`, … | `subprocess`, `json`, `os` | Aucune |
| `orbit_engine.py` | Orbites ISS et Voyager (Skyfield, TLE) | `get_iss_precise`, `get_iss_crew`, `get_voyager_precise` | `subprocess`, `json`, `skyfield.api` | Aucune |
| `space_alerts.py` | Alertes NEO (NASA NeoWs), météo solaire (NOAA), débris | `get_asteroid_alerts`, `get_solar_weather`, `get_space_debris` | `subprocess`, `json`, `os`, `datetime` | Aucune |

### 4.2 Package `modules/astro_detection/`

| Fichier | Rôle précis | Symboles publics | Dépendances externes | Dépendances internes |
|---------|--------------|------------------|----------------------|----------------------|
| `__init__.py` | Réexport détection et validation | `detect_moving_objects`, `draw_detections`, `validate_moving_candidates`, `crosscheck_with_known_satellites`, `crosscheck_detections_with_tle`, `crosscheck_detections_with_mpc` | Aucune | asteroid_detector, object_validation, catalog_crosscheck, asteroid_catalog_crosscheck |
| `asteroid_detector.py` | Détection d’objets mobiles (2 images consécutives) : alignement, diff, contours | `detect_moving_objects`, `draw_detections` | `pathlib`, `typing`, `numpy`, `cv2`, `astropy.io.fits` (optionnel) | Aucune |
| `catalog_crosscheck.py` | Cross-check TLE : SGP4, conversion RA/Dec → pixels, matching | `crosscheck_detections_with_tle` | `logging`, `math`, `datetime`, `pathlib`, `typing`, `sgp4.api` (optionnel), `astropy` (optionnel) | Aucune |
| `asteroid_catalog_crosscheck.py` | Cross-check MPC : Kepler, propagation, RA/Dec, cache catalogue | `crosscheck_detections_with_mpc` | `logging`, `math`, `datetime`, `pathlib`, `typing`, `astropy.time`, `astropy.coordinates` (optionnel) | `catalog_crosscheck` (_ra_dec_to_pixel, _observation_time_from_metadata) |
| `object_validation.py` | Validation spatiale des candidats mobiles ; délégation TLE/MPC | `validate_moving_candidates`, `crosscheck_with_known_satellites` | `logging`, `math`, `typing` | `catalog_crosscheck` |
| `motion_tracker.py` | Pistes multi-images : association, vitesse, angle, classification (satellite/asteroid/artifact) | `track_moving_objects` | `logging`, `math`, `datetime`, `pathlib`, `typing` | Aucune (optionnel : asteroid_detector si pas de detections fournies) |
| `sky_change_detector.py` | Changements entre 2 images (alignement ORB/ECC, soustraction, sources) | `detect_sky_changes`, `align_images`, `normalize_background`, `subtract_images`, `detect_sources`, `classify_change` | `logging`, `pathlib`, `typing`, `numpy`, `cv2`, `astropy.io.fits` (optionnel) | Aucune |
| `discovery_engine.py` | Découvertes potentielles : combine motion tracking + cross-checks + sky changes → candidats astéroïde/supernova/transient | `run_discovery_engine`, `evaluate_motion_candidate`, `evaluate_transient` | `logging`, `typing` | Aucune (lit motion_tracking, moving_object_validation, sky_changes) |

### 4.3 Package `modules/digital_lab/`

| Fichier | Rôle précis | Symboles publics | Dépendances externes | Dépendances internes |
|---------|--------------|------------------|----------------------|----------------------|
| `__init__.py` | Réexport pipeline et chargement | `load_image`, `run_pipeline`, `generate_report` | Aucune | image_loader, analysis_pipeline, report_generator |
| `image_loader.py` | Chargement image (chemin ou bytes) → 2D float (FITS ou OpenCV) | `load_image` | `numpy`, `pathlib`, `cv2`, `astropy.io.fits` (optionnel) | Aucune |
| `astro_preprocessing.py` | Réduction bruit (bilateral ou skimage wavelet), normalisation [0,1] | `reduce_noise`, `normalize` | `numpy`, `cv2` ou `skimage.restoration` | Aucune |
| `object_detection.py` | Détection étoiles (blob_log ou cv2) et objets étendus (label/regionprops) | `detect_stars`, `detect_objects` | `numpy`, `skimage.feature`/`skimage.measure` ou `cv2` | Aucune |
| `photometry.py` | Luminosité (image, étoiles, objets) | `compute_brightness` | `numpy` | Aucune |
| `anomaly_detection.py` | Anomalies à partir image/étoiles/objets/brightness | `detect_anomalies` | `numpy` | Aucune |
| `report_generator.py` | Génération rapport (structure) depuis résultat pipeline | `generate_report` | Minimal | Aucune |
| `analysis_pipeline.py` | **Pipeline principal** : load → reduce_noise → stars/objects → brightness → anomalies → asteroid detection → validation TLE/MPC → motion tracking → metadata | `run_pipeline` | `pathlib`, `os`, `json` | image_loader, astro_preprocessing, object_detection, photometry, anomaly_detection, report_generator, asteroid_detector, object_validation, catalog_crosscheck, asteroid_catalog_crosscheck, motion_tracker |

### 4.4 Packages `science_archive_engine`, `research_center`, `space_analysis_engine`, `space_sources`

- **science_archive_engine** : `archive_manager`, `report_saver`, `object_cataloger`, `discovery_saver`, `archive_indexer` — sauvegarde rapports/objets/découvertes et index dans `data/science_archive/`.
- **research_center** : `research_engine`, `research_logger`, `solar_activity_monitor`, `asteroid_monitor`, `space_event_tracker` — résumés recherche, logs dans `data/research_logs/`.
- **space_analysis_engine** : `space_analyzer`, `discovery_engine`, `event_classifier`, `image_comparator`, `data_logger` — analyse résultat pipeline, comparaison, découvertes.
- **space_sources** : `telescope_downloader`, `robotic_telescopes` — téléchargement Hubble/JWST/ESO/LCO/etc. et connecteurs VO.

Les symboles publics et chemins de données sont décrits dans le rapport d’exploration (section 2) ; chaque module est référencé depuis `station_web.py` ou depuis un autre module (ex. analysis_pipeline → astro_detection).

---

## 5. Points d’entrée et exécution

### 5.1 Application web (production)

- **Fichier :** `station_web.py`
- **Création app :** `Flask(__name__, template_folder='templates', static_folder='static')`
- **Racine projet :** Variable `STATION = '/root/astro_scan'` (ou équivalent selon déploiement) ; tous les chemins (DB, images, logs, telescope_live, data/) en découlent.
- **Démarrage :** Bloc `if __name__ == '__main__':` :
  - Création des dossiers `logs/`, `data/`, `telescope_live/` si besoin
  - Initialisation table `visits` (SQLite)
  - Recherche d’un port libre (évite 80/443) via `_find_port(start=5000, count=20)`
  - `app.run(host='0.0.0.0', port=..., debug=False)` (ou équivalent)
- **Commande typique :** `python station_web.py` ou `python3 station_web.py` (avec venv activé).

### 5.2 Scripts susceptibles d’être lancés séparément (cron, systemd)

- `aegis_auto.py`, `calculateur_passages.py`, `ce_soir_module.py`, `deploy_obs.py`
- `nasa_feeder.py`, `news_module.py`, `noyau_orbital.py`, `orbital_shield.py`
- `pretranslate.py`, `skyview_module.py`, `space_weather_feeder.py`, `survol_terrestre.py`
- `telescope_feeds.py`, `voyager_tracker.py`

Leur rôle exact (génération de fichiers, mise à jour de `telescope_live/`, etc.) doit être vérifié dans chaque fichier si la continuité des tâches planifiées est critique.

---

## 6. Configuration et secrets

### 6.1 Fichiers de configuration

| Fichier | Rôle | Contenu typique (sans valeurs sensibles) |
|---------|------|------------------------------------------|
| **.env** (racine) | Variables d’environnement et clés API | `CESIUM_TOKEN`, `GROQ_API_KEY` ou `GROK_API_KEY`, `NASA_API_KEY`, `GEMINI_API_KEY`, `GEMINI_API_KEY_BACKUP` |
| **.env.save** | Sauvegarde de .env | Copie de sécurité |
| **requirements.txt** | Dépendances Python pip | Liste des packages (voir section 7) |

Aucun `pyproject.toml`, `setup.cfg`, ou `package.json` à la racine.

### 6.2 Variables et chemins en dur dans `station_web.py`

- `STATION` : racine du projet
- `DB_PATH` : base SQLite (ex. `data/archive_stellaire.db`)
- `IMG_PATH`, `TITLE_F`, `REPORT_F`, `SHIELD_F`, `HUB_F`, `SDR_F` : chemins vers fichiers d’état et images
- Chemins vers `logs/`, `telescope_live/`, `data/noaa_tle.json`, `LAB_UPLOADS`, `RAW_IMAGES` (Lab)
- Références à `static/` (ex. `f'{STATION}/static/...'`) pour JSON et assets

Pour une migration ou un nouveau serveur : adapter `STATION` et les chemins dérivés, et recréer `.env` avec les mêmes clés (ou désactiver les fonctionnalités dépendantes).

---

## 7. Dépendances

### 7.1 Dépendances déclarées (`requirements.txt`)

```
annotated-types==0.7.0
anyio==4.12.1
blinker==1.9.0
certifi==2026.2.25
charset-normalizer==3.4.6
click==8.3.1
distro==1.9.0
Flask==3.1.3
groq==1.1.1
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.11
itsdangerous==2.2.0
Jinja2==3.1.6
MarkupSafe==3.0.3
numpy==2.4.3
pillow==12.1.1
pydantic==2.12.5
pydantic_core==2.41.5
python-dotenv==1.2.2
requests==2.32.5
sniffio==1.3.1
typing-inspection==0.4.2
typing_extensions==4.15.0
urllib3==2.6.3
Werkzeug==3.1.6
```

### 7.2 Dépendances utilisées dans le code mais NON listées dans requirements.txt

| Package | Utilisation | Impact si absent |
|---------|-------------|------------------|
| **opencv-python** (cv2) | image_loader, astro_preprocessing, object_detection, asteroid_detector, sky_change_detector, annotations dans analysis_pipeline | Lab et détection astéroïdes / sky change inopérants |
| **sgp4** | catalog_crosscheck, station_web (passes satellite) | Cross-check TLE et calcul de passes satellites en échec |
| **skyfield** | orbit_engine (ISS, Voyager) | Orbites précises ISS/Voyager indisponibles |
| **astropy** | FITS (image_loader, asteroid_detector, sky_change_detector), temps/coordonnées (asteroid_catalog_crosscheck) | Chargement FITS et cross-check MPC dégradés ou en échec |
| **scikit-image** | object_detection (blob_log, denoise_wavelet, label, regionprops), astro_preprocessing (denoise) | Détection d’étoiles/objets et prétraitement dégradés (fallback cv2 si prévus) |
| **dateutil** | Parsing de dates (catalog_crosscheck, motion_tracker, etc.) | Parsing de dates peut échouer (fallback strptime selon les modules) |
| **photutils** | Optionnel dans sky_change_detector | Non critique |

**Recommandation :** Ajouter dans `requirements.txt` (ou dans un fichier `requirements-full.txt`) : `opencv-python`, `sgp4`, `skyfield`, `astropy`, `scikit-image`, `python-dateutil`, avec versions figées après tests.

---

## 8. Inventaire des routes Flask (détail)

Les routes sont définies dans `station_web.py` uniquement. Résumé par domaine fonctionnel.

### 8.1 Pages (HTML)

| Route | Méthode | Rôle |
|-------|---------|------|
| `/` | GET | Index |
| `/portail` | GET | Portail |
| `/dashboard` | GET | Dashboard |
| `/overlord_live` | GET | Overlord live |
| `/galerie` | GET | Galerie |
| `/observatoire` | GET | Observatoire |
| `/vision`, `/vision-2026` | GET | Vision |
| `/sondes` | GET | Sondes |
| `/scientific` | GET | Scientific |
| `/ce_soir` | GET | Ce soir |
| `/mission-control` | GET | Mission control |
| `/telescopes` | GET | Télescopes |
| `/globe` | GET | Globe |
| `/lab` | GET | Digital Lab |
| `/lab/dashboard` | GET | Dashboard Lab |
| `/research` | GET | Research |
| `/space` | GET | Space |
| `/space-intelligence`, `/space-intelligence-page` | GET | Space intelligence |
| `/research-center` | GET | Research Center |
| `/orbital-map` | GET | Carte orbitale |
| `/space-weather` | GET | Météo spatiale |
| `/favicon.ico` | GET | Favicon |
| `/module/<name>` | GET | Module dynamique |
| `/static/<path:filename>` | GET | Fichiers statiques |

### 8.2 API — Visites, sync, télescope, image live

| Route | Méthode | Rôle |
|-------|---------|------|
| `/api/visits` | GET | Compteur visites |
| `/api/visits/increment` | POST | Incrémenter visites |
| `/api/latest` | GET | Dernière image / infos |
| `/api/sync/state` | GET, POST | État sync télescope |
| `/api/telescope/sources` | GET | Sources télescope |
| `/api/telescope/live` | GET | Image live télescope |
| `/api/image` | GET | Image (paramètres query) |
| `/api/title` | GET | Titre courant |

### 8.3 API — ISS, TLE, passes, Voyager, météo spatiale

| Route | Méthode | Rôle |
|-------|---------|------|
| `/api/iss` | GET | Données ISS |
| `/api/v1/iss` | GET | ISS v1 |
| `/api/tle/sample` | GET | Échantillon TLE |
| `/api/tle/catalog` | GET | Catalogue TLE |
| `/api/tle/full` | GET | TLE complet |
| `/api/meteo-spatiale` | GET | Météo spatiale |
| `/api/passages-iss` | GET | Passes ISS |
| `/api/satellite/passes` | GET | Passes satellite (SGP4) |
| `/api/voyager-live` | GET | Voyager live |
| `/api/iss-passes` | GET | Passes ISS (autre format) |
| `/api/dsn` | GET | DSN |

### 8.4 API — Chat, traduction, explication, Aegis, hub, shield

| Route | Méthode | Rôle |
|-------|---------|------|
| `/api/chat` | POST | Chat (Gemini/Groq) |
| `/api/translate` | POST | Traduction |
| `/api/astro/explain` | POST | Explication objet astro |
| `/api/astro/object` | GET, POST | Objet astro |
| `/api/aegis/status` | GET | Statut Aegis |
| `/api/telescope-hub` | GET | Hub télescope |
| `/api/shield` | GET | Bouclier |
| `/api/classification/stats` | GET | Stats classification |
| `/api/mast/targets` | GET | Cibles MAST |

### 8.5 API — SDR, SkyView, PWA, catalog, ce soir, moon

| Route | Méthode | Rôle |
|-------|---------|------|
| `/api/sdr/status` | GET | Statut SDR |
| `/api/sdr/stations` | GET | Stations SDR |
| `/api/sdr/captures` | GET | Captures SDR |
| `/api/sdr/passes` | GET | Passes SDR |
| `/api/skyview/targets` | GET | Cibles SkyView |
| `/api/skyview/fetch` | POST | Fetch SkyView |
| `/api/skyview/multiwave/<target_id>` | GET | Multiwave SkyView |
| `/api/skyview/list` | GET | Liste SkyView |
| `/sw.js` | GET | Service Worker PWA |
| `/manifest.json` | GET | Manifest PWA |
| `/api/push/subscribe` | POST | Push subscription |
| `/api/catalog` | GET | Catalogue |
| `/api/catalog/<obj_id>` | GET | Objet catalogue |
| `/api/tonight` | GET | Objets ce soir |
| `/api/moon` | GET | Phase lunaire |

### 8.6 API — Mission control, news, microobservatory, v1 catalog/planets

| Route | Méthode | Rôle |
|-------|---------|------|
| `/api/mission-control` | GET | Mission control |
| `/api/news` | GET | News |
| `/api/microobservatory` | GET | MicroObservatory |
| `/api/v1/catalog` | GET | Catalogue v1 |
| `/api/v1/planets` | GET | Planètes v1 |

### 8.7 API — Asteroids, solar, tonight, feeds (Voyager, NEO, solar, Mars, APOD, all)

| Route | Méthode | Rôle |
|-------|---------|------|
| `/api/v1/asteroids` | GET | Astéroïdes v1 |
| `/api/v1/solar-weather` | GET | Météo solaire v1 |
| `/api/v1/tonight` | GET | Tonight v1 |
| `/api/feeds/voyager` | GET | Feed Voyager |
| `/api/feeds/neo` | GET | Feed NEO |
| `/api/feeds/solar` | GET | Feed solaire |
| `/api/feeds/solar_alerts` | GET | Alertes solaires |
| `/api/feeds/mars` | GET | Feed Mars |
| `/api/sondes` | GET | Sondes |
| `/api/feeds/apod_hd` | GET | APOD HD |
| `/api/feeds/all` | GET | Tous les feeds |
| `/api/health` | GET | Santé |

### 8.8 API — Hubble, JWST, Mars, Bepi, NEO, alerts, SpaceX, news, live

| Route | Méthode | Rôle |
|-------|---------|------|
| `/api/hubble/images` | GET | Images Hubble |
| `/api/jwst/images` | GET | Images JWST |
| `/api/mars/weather` | GET | Météo Mars |
| `/api/bepi/telemetry` | GET | BepiColombo |
| `/api/neo` | GET | NEO |
| `/api/alerts/asteroids` | GET | Alertes astéroïdes |
| `/api/alerts/solar` | GET | Alertes solaires |
| `/api/alerts/all` | GET | Toutes alertes |
| `/api/live/spacex` | GET | SpaceX live |
| `/api/live/news` | GET | News live |
| `/api/live/mars-weather` | GET | Météo Mars live |
| `/api/live/iss-passes` | GET | Passes ISS live |
| `/api/live/all` | GET | Tout live |
| `/api/survol` | GET | Survol |

### 8.9 API — Lab (upload, analyse, métadonnées, rapport, skyview sync)

| Route | Méthode | Rôle |
|-------|---------|------|
| `/lab/upload` | POST | Upload Lab |
| `/lab/images` | GET | Liste images Lab |
| `/api/lab/images` | GET | API liste images |
| `/lab/raw/<path:filename>` | GET | Fichier raw Lab |
| `/api/lab/metadata/<path:filename>` | GET | Métadonnées image |
| `/lab/analyze` | POST | Lancer analyse |
| `/api/lab/run_analysis` | POST | Run analysis |
| `/api/lab/skyview/sync` | GET | Sync SkyView → Lab |
| `/api/lab/upload` | POST | Upload Lab (API) |
| `/api/lab/analyze` | POST | Analyze (API) |
| `/api/lab/report` | GET | Rapport Lab |

### 8.10 API — Analysis (run, compare, discoveries)

| Route | Méthode | Rôle |
|-------|---------|------|
| `/api/analysis/run` | POST | Lancer analyse pipeline |
| `/api/analysis/compare` | POST | Comparer résultats |
| `/api/analysis/discoveries` | GET | Découvertes |

### 8.11 API — Research, archive, orbital, space-weather, science, missions, system

| Route | Méthode | Rôle |
|-------|---------|------|
| `/api/research/summary` | GET | Résumé recherche |
| `/api/research/events` | GET | Événements recherche |
| `/api/research/logs` | GET | Logs recherche |
| `/api/archive/reports` | GET, POST | Archive rapports |
| `/api/archive/objects` | GET, POST | Archive objets |
| `/api/archive/discoveries` | GET, POST | Archive découvertes |
| `/api/orbits/live` | GET | Orbites live (Cesium) |
| `/api/space-weather` | GET | Space weather |
| `/api/science/analyze-image` | POST | Analyse image (science) |
| `/api/missions/overview` | GET | Aperçu missions |
| `/api/space/intelligence` | GET, POST | Space intelligence |
| `/api/system/diagnostics` | GET | Diagnostics système |
| `/api/system/status` | GET | Statut système |

---

## 9. Chaînes d’appels critiques (qui appelle qui)

### 9.1 Pipeline Digital Lab (analyse d’une image)

1. **Route** `/lab/analyze` ou `/api/lab/analyze` ou `/api/analysis/run` → envoi de l’image (ou référence) au pipeline.
2. **`analysis_pipeline.run_pipeline(image_source)`** :
   - `load_image` (image_loader)
   - `reduce_noise`, `normalize` (astro_preprocessing)
   - `detect_stars`, `detect_objects` (object_detection)
   - `compute_brightness` (photometry)
   - `detect_anomalies` (anomaly_detection)
   - Si image sur disque : `_find_previous_image` → `detect_moving_objects` (asteroid_detector)
   - Puis : `validate_moving_candidates`, `crosscheck_with_known_satellites` (object_validation → catalog_crosscheck pour TLE)
   - Puis : `crosscheck_detections_with_mpc` (asteroid_catalog_crosscheck)
   - Puis : `_find_recent_images` → `track_moving_objects` (motion_tracker)
   - `_update_metadata_for_asteroids` (écriture metadata + motion_tracking)
   - `generate_report` (report_generator)
3. Résultat renvoyé (et éventuellement sauvegardé dans science_archive via d’autres routes).

### 9.2 Cross-check TLE et MPC

- **object_validation** appelle **catalog_crosscheck** (TLE) pour les positions satellites.
- **analysis_pipeline** appelle **asteroid_catalog_crosscheck** (MPC) ; celui-ci réutilise **catalog_crosscheck** pour `_ra_dec_to_pixel` et `_observation_time_from_metadata`.
- Aucun autre module ne modifie ces chaînes (Flask, Cesium, asteroid_detector, motion_tracker, sky_change_detector restent en dehors de cette chaîne).

### 9.3 Orbital Map (Cesium) et passes

- **station_web** : routes `/api/tle/*`, `/api/satellite/passes`, `/api/orbits/live` ; lecture de `data/tle/active.tle`, téléchargement TLE, calculs SGP4 (dans station_web ou via imports). Cesium côté client consomme ces APIs.
- **orbit_engine** : utilisé pour ISS et Voyager (Skyfield), pas pour la carte TLE complète.

---

## 10. Points de défaillance unique et risques

| Risque | Description | Mitigation recommandée |
|--------|-------------|--------------------------|
| **Fichier unique station_web.py** | Toute erreur ou modification peut impacter l’ensemble du service. | Extraire des blueprints Flask par domaine (lab, api_feeds, orbital, etc.) et documenter les contrats d’API. |
| **Absence de dépendances dans requirements.txt** | opencv, sgp4, skyfield, astropy, scikit-image non listés → échec silencieux ou ImportError après nouveau venv. | Compléter requirements.txt (ou requirements-full.txt) et tester dans un venv propre. |
| **Perte du fichier .env** | Clés API (Cesium, NASA, Groq, Gemini) perdues → fonctionnalités dégradées. | Sauvegarder .env de façon sécurisée ; documenter les clés nécessaires et les désactiver proprement si absentes. |
| **Perte de data/** | DB, TLE, MPC, metadata, science_archive, research_logs perdus. | Sauvegardes régulières (scripts ou cron) et procédure de restauration documentée. |
| **Corruption SQLite** | archive_stellaire.db corrompue → erreurs sur visites et toute route utilisant get_db(). | Backup quotidien ; possibilité de recréer une DB vide (table visits) si acceptable. |
| **TLE / MPC manquants ou vides** | active.tle ou asteroids.dat vides → cross-check et orbital map dégradés. | Vérifier présence des fichiers ; documenter les sources de téléchargement (TLE déjà téléchargé dans station_web). |
| **Aucun test automatisé** | Régressions non détectées. | Introduire tests de smoke (routes principales, run_pipeline sur une image test). |

---

## 11. Procédures de reprise (recommandations)

### 11.1 Backup

- **À sauvegarder régulièrement :**
  - `.env` (de façon sécurisée, hors dépôt)
  - `data/` dans son ensemble (DB, tle, mpc, metadata, images_espace, science_archive, research_logs)
  - `telescope_live/` si l’état live est critique
  - `templates/` et `static/` en cas de personnalisation
- **Fréquence suggérée :** Quotidienne pour `data/` (au moins DB, metadata, science_archive), hebdomadaire pour le reste selon criticité.

### 11.2 Restauration après incident

1. Restaurer le code (dépôt ou archive).
2. Recréer le venv et installer les dépendances : `pip install -r requirements.txt` (+ packages optionnels si documentés dans requirements-full.txt).
3. Restaurer `.env` et adapter `STATION` (ou équivalent) si le chemin racine a changé.
4. Restaurer `data/` (et `telescope_live/` si besoin).
5. Redémarrer l’application : `python station_web.py` (ou via systemd/gunicorn selon déploiement).
6. Vérifier les routes critiques : `/api/health`, `/lab`, `/api/lab/images`, `/orbital-map`, `/api/tle/catalog`.

### 11.3 Redémarrage du service

- **Commande :** Depuis la racine du projet, avec venv activé : `python station_web.py`.
- **Port :** Détecté automatiquement (défaut 5000, évite 80/443) ; pour fixer un port, modifier l’appel à `app.run()` dans `station_web.py`.
- **Logs :** Vérifier `logs/` en cas d’erreur au démarrage.

---

## 12. Tests et qualité

- **État actuel :** Aucun répertoire `tests/` à la racine ni sous `modules/`. Aucun fichier `test_*.py` dédié au projet (hors venv).
- **Recommandation :** Mettre en place une suite minimale : tests de smoke pour `GET /`, `GET /api/health`, `GET /lab`, et un test du pipeline `run_pipeline` sur une image de test (ou mock) pour valider la chaîne load → detect → validate → report.

---

## 13. Documentation existante et manquante

- **Existante :** `data/science_archive/README.md`, `modules/digital_lab/README.md` (dépendances optionnelles, résumé pipeline). Docstrings dans la plupart des modules.
- **Manquante :** README racine, description des routes (API), schéma des métadonnées Lab, procédure de déploiement, runbook opérationnel, politique de backup/restauration. Ce rapport comble une partie de ces lacunes pour la continuité.

---

## 14. Synthèse des recommandations pour l’assurance de continuité

1. **Dépendances :** Compléter `requirements.txt` (ou créer `requirements-full.txt`) avec opencv-python, sgp4, skyfield, astropy, scikit-image, python-dateutil ; figer les versions et tester un venv propre.
2. **Configuration :** Documenter dans un fichier (ex. `docs/CONFIG.md`) toutes les variables .env et les chemins critiques de `station_web.py` ; prévoir un `.env.example` sans valeurs réelles.
3. **Backup :** Définir une procédure écrite (fréquence, périmètre, stockage) et un script de backup pour `data/` et `.env`.
4. **Restauration :** Documenter la procédure de restauration (étapes 11.2) dans un runbook (ex. `docs/RUNBOOK.md`).
5. **Tests :** Ajouter une suite minimale de tests (smoke + pipeline) et l’exécuter avant chaque release ou déploiement.
6. **Code :** À moyen terme, découper `station_web.py` en blueprints ou sous-modules pour réduire le risque lié au fichier unique.
7. **Ce rapport :** Mettre à jour ce document lors de changements majeurs (nouvelles routes, nouveaux modules, changement de structure de données).

---

*Fin du rapport d’assurance de continuité AstroScan.*
