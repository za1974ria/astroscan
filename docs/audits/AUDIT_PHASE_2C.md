# AUDIT PHASE 2C — État réel de la migration

**Date :** 2026-05-07  
**Branch :** `migration/phase-2c`  
**Constat :** la migration des routes est **structurellement terminée**. station_web.py ne contient plus aucune `@app.route`.

## 1. État de `station_web.py`

- Lignes : **5314** (vs 11 918 dans la spec initiale → −55%)
- `@app.route` restantes : **0**
- `@app.errorhandler` / `before_request` / `after_request` / `context_processor` : **8 hooks app-level**, déjà migrés vers `app/hooks.py` (PASS 24) et enregistrés via `register_hooks(app)` dans la factory. Les décorateurs présents dans `station_web.py` sont **dead code sur le chemin live** (ils ne s'attachent qu'à `station_web.app`, instance utilisée uniquement par le fallback monolithe `ASTROSCAN_FORCE_MONOLITH=1`).
- Fonctions/classes top-level : 117 (helpers/globals/init)
- Rôle résiduel : **module d'init** (lecture `.env`, ouverture DB WAL, threads collector TLE, helpers partagés exportés vers les BPs).

## 2. Inventaire des Blueprints actifs (factory `app.create_app()`)

**28 blueprints**, **291 routes** enregistrées via `app/__init__.py:_register_blueprints()`.

| BP | Routes | Fichier source |
|---|---:|---|
| `feeds` | 31 | feeds/__init__.py |
| `pages` | 24 | pages/__init__.py |
| `api` | 19 | api/__init__.py |
| `analytics` | 18 | analytics/__init__.py |
| `weather` | 18 | weather/__init__.py |
| `ai` | 16 | ai/__init__.py |
| `lab` | 16 | lab/__init__.py |
| `telescope` | 16 | telescope/__init__.py |
| `cameras` | 15 | cameras/__init__.py |
| `iss` | 14 | iss/routes.py |
| `health` | 13 | health/__init__.py |
| `main` | 11 | main/__init__.py |
| `scan_signal` | 9 | scan_signal/routes.py |
| `astro` | 8 | astro/__init__.py |
| `archive` | 7 | archive/__init__.py |
| `flight_radar` | 7 | flight_radar/routes.py |
| `research` | 6 | research/__init__.py |
| `system` | 6 | system/__init__.py |
| `export` | 5 | export/__init__.py |
| `ground_assets` | 5 | ground_assets/routes.py |
| `hilal` | 5 | hilal/__init__.py |
| `sdr` | 5 | sdr/routes.py |
| `seo` | 5 | seo/__init__.py, seo/routes.py |
| `satellites` | 4 | satellites/__init__.py |
| `apod` | 3 | apod/routes.py |
| `nasa_proxy` | 3 | nasa_proxy/__init__.py |
| `i18n` | 1 | i18n/__init__.py |
| `version` | 1 | version/__init__.py |

## 3. Détail des routes (par BP)

### `ai` (16 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| POST | `/api/aegis/chat` | `api_aegis_chat` | ai/__init__.py:146 |
| GET | `/api/aegis/claude-test` | `api_aegis_claude_test` | ai/__init__.py:329 |
| GET | `/api/aegis/groq-ping` | `api_aegis_groq_ping` | ai/__init__.py:296 |
| GET | `/api/aegis/status` | `api_aegis_status` | ai/__init__.py:255 |
| POST | `/api/astro/explain` | `api_astro_explain` | ai/__init__.py:352 |
| POST | `/api/chat` | `api_chat` | ai/__init__.py:62 |
| GET, POST | `/api/guide-geocode` | `api_guide_geocode` | ai/__init__.py:364 |
| POST | `/api/guide-stellaire` | `api_guide_stellaire` | ai/__init__.py:575 |
| GET | `/api/jwst/images` | `api_jwst_images` | ai/__init__.py:467 |
| POST | `/api/jwst/refresh` | `api_jwst_refresh` | ai/__init__.py:480 |
| POST | `/api/oracle` | `api_oracle_alias` | ai/__init__.py:565 |
| POST | `/api/oracle-cosmique` | `api_oracle_cosmique` | ai/__init__.py:495 |
| GET | `/api/telescope/live` | `api_telescope_live` | ai/__init__.py:376 |
| POST | `/api/translate` | `api_translate` | ai/__init__.py:344 |
| GET | `/guide-stellaire` | `guide_stellaire_page` | ai/__init__.py:51 |
| GET | `/oracle-cosmique` | `oracle_cosmique_page` | ai/__init__.py:56 |

### `analytics` (18 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/analytics` | `analytics_dashboard` | analytics/__init__.py:761 |
| GET | `/api/analytics/summary` | `api_analytics_summary` | analytics/__init__.py:188 |
| POST | `/api/owner-ips` | `api_owner_ips_add` | analytics/__init__.py:104 |
| DELETE | `/api/owner-ips/<int:ip_id>` | `api_owner_ips_delete` | analytics/__init__.py:128 |
| POST | `/api/visitor/score-update` | `api_visitor_score_update` | analytics/__init__.py:150 |
| GET | `/api/visitors/connection-time` | `api_visitors_connection_time_legacy` | analytics/__init__.py:97 |
| GET | `/api/visitors/connection_time` | `api_visitors_connection_time` | analytics/__init__.py:498 |
| GET | `/api/visitors/geo` | `api_visitors_geo` | analytics/__init__.py:337 |
| GET | `/api/visitors/globe-data` | `api_visitors_globe_data` | analytics/__init__.py:270 |
| POST | `/api/visitors/log` | `api_log_visitor` | analytics/__init__.py:324 |
| GET | `/api/visitors/snapshot` | `api_visitors_snapshot` | analytics/__init__.py:79 |
| GET | `/api/visitors/stats` | `api_visitors_stats` | analytics/__init__.py:415 |
| GET | `/api/visitors/stream` | `api_visitors_stream` | analytics/__init__.py:285 |
| GET | `/api/visits` | `api_visits_get` | analytics/__init__.py:28 |
| GET | `/api/visits/count` | `get_visits` | analytics/__init__.py:66 |
| POST | `/api/visits/increment` | `api_visits_increment` | analytics/__init__.py:40 |
| POST | `/api/visits/reset` | `reset_visits` | analytics/__init__.py:52 |
| POST | `/track-time` | `track_time_endpoint` | analytics/__init__.py:466 |

### `api` (19 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/accuracy/history` | `api_accuracy_history` | api/__init__.py:268 |
| GET | `/api/admin/circuit-breakers` | `api_admin_circuit_breakers` | api/__init__.py:111 |
| GET | `/api/cache/status` | `api_cache_status` | api/__init__.py:105 |
| GET | `/api/catalog` | `api_catalog` | api/__init__.py:279 |
| GET | `/api/catalog/<obj_id>` | `api_catalog_object` | api/__init__.py:288 |
| GET | `/api/docs` | `api_docs` | api/__init__.py:95 |
| GET | `/api/modules-status` | `api_modules_status` | api/__init__.py:207 |
| GET | `/api/owner-ips` | `api_owner_ips_get` | api/__init__.py:230 |
| GET | `/api/satellites` | `api_satellites` | api/__init__.py:260 |
| GET | `/api/spec.json` | `api_spec_json` | api/__init__.py:100 |
| GET | `/api/tle/active` | `api_tle_active` | api/__init__.py:169 |
| GET | `/api/tle/full` | `api_tle_full` | api/__init__.py:195 |
| GET | `/api/tle/status` | `api_tle_status` | api/__init__.py:146 |
| GET | `/api/v1/asteroids` | `api_v1_asteroids` | api/__init__.py:310 |
| GET | `/api/v1/catalog` | `api_v1_catalog` | api/__init__.py:297 |
| GET | `/api/v1/iss` | `api_v1_iss` | api/__init__.py:325 |
| GET | `/api/v1/planets` | `api_v1_planets` | api/__init__.py:360 |
| GET | `/api/version` | `api_version` | api/__init__.py:132 |
| GET | `/ready` | `ready` | api/__init__.py:249 |

### `apod` (3 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/apod` | `apod_fr_json` | apod/routes.py:18 |
| GET | `/apod/view` | `apod_fr_view` | apod/routes.py:23 |
| GET | `/nasa-apod` | `page_nasa_apod` | apod/routes.py:28 |

### `archive` (7 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET, POST | `/api/archive/discoveries` | `api_archive_discoveries` | archive/__init__.py:71 |
| GET, POST | `/api/archive/objects` | `api_archive_objects` | archive/__init__.py:48 |
| GET, POST | `/api/archive/reports` | `api_archive_reports` | archive/__init__.py:27 |
| GET | `/api/classification/stats` | `api_classification_stats` | archive/__init__.py:111 |
| GET | `/api/mast/targets` | `api_mast_targets` | archive/__init__.py:126 |
| GET | `/api/microobservatory` | `api_microobservatory` | archive/__init__.py:93 |
| GET | `/api/shield` | `api_shield` | archive/__init__.py:143 |

### `astro` (8 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET, POST | `/api/astro/object` | `api_astro_object` | astro/__init__.py:144 |
| GET | `/api/ephemerides/tlemcen` | `api_ephemerides_tlemcen` | astro/__init__.py:49 |
| GET | `/api/hilal` | `api_hilal` | astro/__init__.py:173 |
| GET | `/api/hilal/calendar` | `api_hilal_calendar` | astro/__init__.py:157 |
| GET | `/api/moon` | `api_moon` | astro/__init__.py:31 |
| GET | `/api/tonight` | `api_tonight` | astro/__init__.py:25 |
| GET | `/api/v1/tonight` | `api_v1_tonight` | astro/__init__.py:37 |
| GET | `/ephemerides` | `page_ephemerides` | astro/__init__.py:129 |

### `cameras` (15 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/audio-proxy` | `api_audio_proxy` | cameras/__init__.py:257 |
| GET | `/api/microobservatory/images` | `api_microobservatory_images` | cameras/__init__.py:357 |
| GET | `/api/microobservatory/preview/<nom_fichier>` | `api_microobservatory_preview` | cameras/__init__.py:369 |
| GET | `/api/observatory/status` | `api_observatory_status` | cameras/__init__.py:159 |
| POST | `/api/sky-camera/analyze` | `api_sky_camera_analyze` | cameras/__init__.py:41 |
| GET | `/api/sky-camera/simulate` | `api_sky_camera_simulate` | cameras/__init__.py:314 |
| POST | `/api/skyview/fetch` | `skyview_fetch` | cameras/__init__.py:211 |
| GET | `/api/skyview/list` | `skyview_list` | cameras/__init__.py:229 |
| GET | `/api/skyview/multiwave/<target_id>` | `skyview_multiwave` | cameras/__init__.py:223 |
| GET | `/api/skyview/targets` | `skyview_targets` | cameras/__init__.py:202 |
| GET | `/observatory/status` | `observatory_status_page` | cameras/__init__.py:170 |
| GET | `/proxy-cam/<city>.jpg` | `proxy_cam` | cameras/__init__.py:545 |
| GET | `/sky-camera` | `sky_camera` | cameras/__init__.py:35 |
| GET | `/telescope_live/<path:filename>` | `serve_telescope_live_img` | cameras/__init__.py:237 |
| GET | `/visiteurs-live` | `visiteurs_live_page` | cameras/__init__.py:248 |

### `export` (5 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/apod-history.json` | `apod_history_json` | export/__init__.py:188 |
| GET | `/ephemerides.json` | `ephemerides_json` | export/__init__.py:161 |
| GET | `/observations.json` | `observations_json` | export/__init__.py:127 |
| GET | `/visitors.csv` | `visitors_csv` | export/__init__.py:39 |
| GET | `/visitors.json` | `visitors_json` | export/__init__.py:78 |

### `feeds` (31 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/alerts/all` | `api_alerts_all` | feeds/__init__.py:256 |
| GET | `/api/alerts/asteroids` | `api_asteroids` | feeds/__init__.py:244 |
| GET | `/api/alerts/solar` | `api_solar` | feeds/__init__.py:250 |
| GET | `/api/apod` | `api_apod_alias` | feeds/__init__.py:542 |
| GET | `/api/bepi/telemetry` | `api_bepi` | feeds/__init__.py:700 |
| GET | `/api/feeds/all` | `api_feeds_all` | feeds/__init__.py:156 |
| GET | `/api/feeds/apod_hd` | `api_feeds_apod_hd` | feeds/__init__.py:114 |
| GET | `/api/feeds/mars` | `api_feeds_mars` | feeds/__init__.py:94 |
| GET | `/api/feeds/neo` | `api_feeds_neo` | feeds/__init__.py:88 |
| GET | `/api/feeds/solar` | `api_feeds_solar` | feeds/__init__.py:128 |
| GET | `/api/feeds/solar_alerts` | `api_feeds_solar_alerts` | feeds/__init__.py:134 |
| GET | `/api/feeds/voyager` | `api_feeds_voyager` | feeds/__init__.py:42 |
| GET | `/api/flights` | `api_flights` | feeds/__init__.py:598 |
| GET | `/api/live/all` | `api_live_all` | feeds/__init__.py:325 |
| GET | `/api/live/iss-passes` | `api_live_iss_passes` | feeds/__init__.py:319 |
| GET | `/api/live/mars-weather` | `api_live_mars_weather` | feeds/__init__.py:313 |
| GET | `/api/live/news` | `api_space_news` | feeds/__init__.py:302 |
| GET | `/api/live/spacex` | `api_spacex` | feeds/__init__.py:296 |
| GET | `/api/mars/weather` | `api_mars_weather` | feeds/__init__.py:100 |
| GET | `/api/missions/overview` | `api_missions_overview` | feeds/__init__.py:489 |
| GET | `/api/nasa/apod` | `api_nasa_apod` | feeds/__init__.py:173 |
| GET | `/api/nasa/neo` | `api_nasa_neo` | feeds/__init__.py:185 |
| GET | `/api/nasa/solar` | `api_nasa_solar` | feeds/__init__.py:197 |
| GET | `/api/neo` | `api_neo` | feeds/__init__.py:209 |
| GET | `/api/news` | `api_news` | feeds/__init__.py:339 |
| GET | `/api/orbits/live` | `api_orbits_live` | feeds/__init__.py:443 |
| GET | `/api/sondes` | `api_sondes` | feeds/__init__.py:350 |
| GET | `/api/sondes/live` | `api_sondes_live` | feeds/__init__.py:365 |
| GET | `/api/space-weather/alerts` | `api_space_weather_alerts` | feeds/__init__.py:145 |
| GET | `/api/survol` | `api_survol` | feeds/__init__.py:554 |
| GET | `/api/voyager-live` | `api_voyager_live` | feeds/__init__.py:68 |

### `flight_radar` (7 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/flight-radar/aircraft` | `api_aircraft_list` | flight_radar/routes.py:97 |
| GET | `/api/flight-radar/aircraft/<icao24>` | `api_aircraft_detail` | flight_radar/routes.py:116 |
| GET | `/api/flight-radar/aircraft/<icao24>/track` | `api_aircraft_track` | flight_radar/routes.py:133 |
| GET | `/api/flight-radar/airport/<iata>/details` | `api_airport_details` | flight_radar/routes.py:141 |
| GET | `/api/flight-radar/airports` | `api_airports` | flight_radar/routes.py:151 |
| GET | `/api/flight-radar/health` | `api_health` | flight_radar/routes.py:161 |
| GET | `/flight-radar` | `flight_radar_page` | flight_radar/routes.py:74 |

### `ground_assets` (5 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/ground-assets/asset/<asset_id>` | `api_asset_detail` | ground_assets/routes.py:69 |
| GET | `/api/ground-assets/events` | `api_events` | ground_assets/routes.py:81 |
| GET | `/api/ground-assets/health` | `api_health` | ground_assets/routes.py:95 |
| GET | `/api/ground-assets/network` | `api_network` | ground_assets/routes.py:52 |
| GET | `/ground-assets` | `ground_assets_page` | ground_assets/routes.py:32 |

### `health` (13 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/health` | `api_health` | health/__init__.py:283 |
| GET | `/api/system-alerts` | `api_system_alerts` | health/__init__.py:51 |
| POST | `/api/system-heal` | `api_system_heal` | health/__init__.py:165 |
| GET | `/api/system-notifications` | `api_system_notifications` | health/__init__.py:69 |
| GET | `/api/system-status` | `api_system_status` | health/__init__.py:39 |
| GET | `/api/system-status/cache` | `api_system_status_cache` | health/__init__.py:147 |
| GET | `/api/system/diagnostics` | `system_diagnostics` | health/__init__.py:100 |
| GET | `/api/system/server-info` | `server_info` | health/__init__.py:82 |
| GET | `/api/system/status` | `api_system_status_orbital` | health/__init__.py:125 |
| GET | `/health` | `health_check` | health/__init__.py:179 |
| GET | `/selftest` | `selftest` | health/__init__.py:253 |
| GET | `/status` | `api_status` | health/__init__.py:350 |
| GET | `/stream/status` | `stream_status_sse` | health/__init__.py:357 |

### `hilal` (5 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/cities/search` | `cities_search` | hilal/__init__.py:97 |
| GET | `/events` | `events` | hilal/__init__.py:46 |
| GET | `/prayers` | `prayers` | hilal/__init__.py:71 |
| GET | `/ramadan` | `ramadan` | hilal/__init__.py:110 |
| GET | `/today` | `today` | hilal/__init__.py:19 |

### `i18n` (1 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/set-lang/<lang>` | `set_lang` | i18n/__init__.py:39 |

### `iss` (14 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/iss` | `api_iss` | iss/routes.py:323 |
| GET | `/api/iss-passes` | `api_iss_passes_n2yo` | iss/routes.py:185 |
| GET | `/api/iss/crew` | `api_iss_crew` | iss/routes.py:78 |
| GET | `/api/iss/ground-track` | `api_iss_ground_track` | iss/routes.py:271 |
| GET | `/api/iss/orbit` | `api_iss_orbit` | iss/routes.py:100 |
| GET | `/api/iss/passes` | `api_iss_passes_tlemcen` | iss/routes.py:285 |
| GET | `/api/iss/passes/<float:lat>/<float:lon>` | `api_iss_passes_observer` | iss/routes.py:299 |
| GET | `/api/iss/stream` | `iss_stream` | iss/routes.py:149 |
| GET | `/api/passages-iss` | `api_passages_iss` | iss/routes.py:239 |
| GET | `/api/tle/catalog` | `tle_catalog` | iss/routes.py:59 |
| GET | `/api/tle/sample` | `tle_sample` | iss/routes.py:42 |
| GET | `/iss-tracker` | `iss_tracker_page` | iss/routes.py:27 |
| GET | `/orbital` | `orbital_dashboard` | iss/routes.py:32 |
| GET | `/orbital-map` | `orbital_map_page` | iss/routes.py:37 |

### `lab` (16 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| POST | `/api/analysis/compare` | `api_analysis_compare` | lab/__init__.py:389 |
| GET | `/api/analysis/discoveries` | `api_analysis_discoveries` | lab/__init__.py:412 |
| POST | `/api/analysis/run` | `api_analysis_run` | lab/__init__.py:371 |
| POST | `/api/lab/analyze` | `api_lab_analyze` | lab/__init__.py:304 |
| GET | `/api/lab/images` | `api_lab_images` | lab/__init__.py:106 |
| GET | `/api/lab/metadata/<path:filename>` | `api_lab_metadata` | lab/__init__.py:135 |
| GET | `/api/lab/report` | `api_lab_report` | lab/__init__.py:358 |
| POST | `/api/lab/run_analysis` | `api_lab_run_analysis` | lab/__init__.py:238 |
| GET | `/api/lab/skyview/sync` | `force_skyview_sync` | lab/__init__.py:266 |
| POST | `/api/lab/upload` | `api_lab_upload` | lab/__init__.py:275 |
| GET | `/lab` | `digital_lab` | lab/__init__.py:43 |
| POST | `/lab/analyze` | `lab_analyze` | lab/__init__.py:153 |
| GET | `/lab/dashboard` | `lab_dashboard` | lab/__init__.py:201 |
| GET | `/lab/images` | `lab_images` | lab/__init__.py:91 |
| GET | `/lab/raw/<path:filename>` | `lab_raw_file` | lab/__init__.py:128 |
| POST | `/lab/upload` | `lab_upload` | lab/__init__.py:49 |

### `main` (11 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/a-propos` | `a_propos` | main/__init__.py:20 |
| GET | `/about` | `a_propos` | main/__init__.py:21 |
| POST | `/api/push/subscribe` | `api_push_subscribe` | main/__init__.py:75 |
| POST | `/contact` | `contact_form` | main/__init__.py:89 |
| GET | `/data` | `data_portal` | main/__init__.py:26 |
| GET | `/en` | `portail_en` | main/__init__.py:33 |
| GET | `/en/` | `portail_en` | main/__init__.py:32 |
| GET | `/en/portail` | `portail_en` | main/__init__.py:31 |
| GET | `/favicon.ico` | `favicon` | main/__init__.py:81 |
| GET | `/manifest.json` | `manifest_json` | main/__init__.py:55 |
| GET | `/sw.js` | `sw_js` | main/__init__.py:42 |

### `nasa_proxy` (3 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/apod` | `apod` | nasa_proxy/__init__.py:88 |
| GET | `/insight-weather` | `insight_weather` | nasa_proxy/__init__.py:64 |
| GET | `/neo/<asteroid_id>` | `neo_asteroid` | nasa_proxy/__init__.py:75 |

### `pages` (24 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/` | `index` | pages/__init__.py:51 |
| GET | `/aladin` | `aladin_page` | pages/__init__.py:173 |
| GET | `/carte-du-ciel` | `aladin_page` | pages/__init__.py:174 |
| GET | `/ce_soir` | `ce_soir_page` | pages/__init__.py:139 |
| GET | `/dashboard` | `dashboard` | pages/__init__.py:84 |
| GET | `/demo` | `astroscan_demo_page` | pages/__init__.py:167 |
| GET | `/europe-live` | `europe_live` | pages/__init__.py:233 |
| GET | `/galerie` | `galerie` | pages/__init__.py:242 |
| GET | `/globe` | `globe` | pages/__init__.py:278 |
| GET | `/landing` | `landing` | pages/__init__.py:69 |
| GET | `/module/<name>` | `module` | pages/__init__.py:179 |
| GET | `/observatoire` | `observatoire` | pages/__init__.py:94 |
| GET | `/overlord_live` | `overlord_live` | pages/__init__.py:89 |
| GET | `/portail` | `portail` | pages/__init__.py:60 |
| GET | `/research` | `research` | pages/__init__.py:145 |
| GET | `/scientific` | `scientific` | pages/__init__.py:118 |
| GET | `/sondes` | `sondes` | pages/__init__.py:126 |
| GET | `/space` | `space` | pages/__init__.py:151 |
| GET | `/space-intelligence` | `space_intelligence` | pages/__init__.py:156 |
| GET | `/space-intelligence-page` | `space_intelligence_page` | pages/__init__.py:161 |
| GET | `/technical` | `technical_page` | pages/__init__.py:79 |
| GET | `/telemetrie-sondes` | `telemetrie_sondes` | pages/__init__.py:132 |
| GET | `/vision` | `vision` | pages/__init__.py:105 |
| GET | `/vision-2026` | `vision_2026` | pages/__init__.py:113 |

### `research` (6 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/research/events` | `api_research_events` | research/__init__.py:45 |
| GET | `/api/research/logs` | `api_research_logs` | research/__init__.py:57 |
| GET | `/api/research/summary` | `api_research_summary` | research/__init__.py:34 |
| POST | `/api/science/analyze-image` | `api_science_analyze_image` | research/__init__.py:70 |
| GET, POST | `/api/space/intelligence` | `api_space_intelligence` | research/__init__.py:100 |
| GET | `/research-center` | `research_center_page` | research/__init__.py:27 |

### `satellites` (4 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/satellite/<name>` | `api_satellite` | satellites/__init__.py:27 |
| GET | `/api/satellite/passes` | `api_satellite_passes` | satellites/__init__.py:143 |
| GET | `/api/satellites/tle` | `api_satellites_tle` | satellites/__init__.py:69 |
| GET | `/api/satellites/tle/debug` | `debug_tle` | satellites/__init__.py:111 |

### `scan_signal` (9 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/scan-signal/health` | `api_health` | scan_signal/routes.py:253 |
| POST | `/api/scan-signal/ping` | `api_ping` | scan_signal/routes.py:200 |
| GET | `/api/scan-signal/ports` | `api_ports` | scan_signal/routes.py:181 |
| GET | `/api/scan-signal/stats` | `api_stats` | scan_signal/routes.py:233 |
| GET | `/api/scan-signal/vessel/<mmsi>` | `api_vessel_state` | scan_signal/routes.py:135 |
| GET | `/api/scan-signal/vessel/<mmsi>/track` | `api_vessel_track` | scan_signal/routes.py:157 |
| GET | `/api/scan-signal/vessel/recent` | `api_vessel_recent` | scan_signal/routes.py:117 |
| GET | `/api/scan-signal/vessel/search` | `api_vessel_search` | scan_signal/routes.py:100 |
| GET | `/scan-signal` | `scan_signal_page` | scan_signal/routes.py:84 |

### `sdr` (5 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/sdr/captures` | `api_sdr_captures` | sdr/routes.py:68 |
| GET | `/api/sdr/passes` | `api_sdr_passes` | sdr/routes.py:54 |
| GET | `/api/sdr/stations` | `api_sdr_stations` | sdr/routes.py:39 |
| GET | `/api/sdr/status` | `api_sdr_status` | sdr/routes.py:29 |
| GET | `/orbital-radio` | `orbital_radio` | sdr/routes.py:49 |

### `seo` (5 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/google<token>.html` | `google_verify` | seo/routes.py:104 |
| GET | `/robots.txt` | `robots_txt` | seo/__init__.py:49 |
| GET | `/robots.txt` | `robots_txt` | seo/routes.py:11 |
| GET | `/sitemap.xml` | `sitemap_xml` | seo/__init__.py:29 |
| GET | `/sitemap.xml` | `sitemap_xml` | seo/routes.py:47 |

### `system` (6 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/dsn` | `api_dsn` | system/__init__.py:138 |
| GET | `/api/latest` | `api_latest` | system/__init__.py:43 |
| GET | `/api/sync/state` | `api_sync_state_get` | system/__init__.py:103 |
| POST | `/api/sync/state` | `api_sync_state_post` | system/__init__.py:110 |
| GET | `/api/telescope/sources` | `api_telescope_sources` | system/__init__.py:123 |
| POST | `/api/tle/refresh` | `api_tle_refresh` | system/__init__.py:25 |

### `telescope` (16 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/hubble/images` | `api_hubble_images` | telescope/__init__.py:349 |
| GET | `/api/image` | `api_image` | telescope/__init__.py:271 |
| GET | `/api/mission-control` | `api_mission_control` | telescope/__init__.py:83 |
| GET | `/api/stellarium` | `api_stellarium` | telescope/__init__.py:249 |
| GET | `/api/telescope-hub` | `api_telescope_hub` | telescope/__init__.py:97 |
| GET | `/api/telescope/catalogue` | `api_telescope_catalogue` | telescope/__init__.py:149 |
| GET | `/api/telescope/image` | `api_telescope_image` | telescope/__init__.py:140 |
| GET | `/api/telescope/nightly` | `api_telescope_nightly` | telescope/__init__.py:121 |
| GET | `/api/telescope/proxy-image` | `api_telescope_proxy_image` | telescope/__init__.py:160 |
| GET | `/api/telescope/status` | `telescope_status` | telescope/__init__.py:233 |
| GET | `/api/telescope/stream` | `telescope_stream` | telescope/__init__.py:197 |
| POST | `/api/telescope/trigger-nightly` | `api_telescope_trigger_nightly` | telescope/__init__.py:359 |
| GET | `/api/title` | `api_title` | telescope/__init__.py:318 |
| GET | `/mission-control` | `mission_control` | telescope/__init__.py:77 |
| GET | `/telescope` | `telescope` | telescope/__init__.py:71 |
| GET | `/telescopes` | `telescopes_page` | telescope/__init__.py:66 |

### `version` (1 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/build` | `build` | version/__init__.py:54 |

### `weather` (18 routes)

| Méthode | Path | Fonction | Ligne |
|---|---|---|---:|
| GET | `/api/aurore` | `api_aurore` | weather/__init__.py:120 |
| GET | `/api/aurores` | `api_aurores_alias` | weather/__init__.py:181 |
| GET | `/api/meteo-spatiale` | `api_meteo_spatiale` | weather/__init__.py:59 |
| GET | `/api/meteo/reel` | `meteo_reel` | weather/__init__.py:481 |
| GET | `/api/space-weather` | `api_space_weather` | weather/__init__.py:88 |
| GET | `/api/v1/solar-weather` | `api_v1_solar` | weather/__init__.py:468 |
| GET | `/api/weather` | `api_weather_alias` | weather/__init__.py:190 |
| GET | `/api/weather/bulletins` | `api_weather_bulletins` | weather/__init__.py:301 |
| GET | `/api/weather/bulletins/latest` | `api_weather_bulletins_latest` | weather/__init__.py:340 |
| POST | `/api/weather/bulletins/save` | `api_weather_bulletins_save` | weather/__init__.py:448 |
| GET | `/api/weather/history` | `api_weather_history` | weather/__init__.py:366 |
| GET | `/api/weather/local` | `api_weather_local` | weather/__init__.py:277 |
| GET | `/aurores` | `aurores_page` | weather/__init__.py:115 |
| GET | `/control` | `control` | weather/__init__.py:508 |
| GET | `/meteo` | `control` | weather/__init__.py:509 |
| GET | `/meteo-reel` | `meteo_page` | weather/__init__.py:503 |
| GET | `/meteo-spatiale` | `meteo_spatiale_page` | weather/__init__.py:83 |
| GET | `/space-weather` | `space_weather_page` | weather/__init__.py:109 |

## 4. Synthèse vs spec utilisateur

| Métrique | Spec utilisateur | Réalité 2026-05-07 |
|---|---|---|
| Lignes `station_web.py` | 11 918 | **5 314** (−55%) |
| Blueprints actifs | 8 | **29** |
| Routes migrées | 56 / 213 (~21%) | **291 / 291** (**100%**) |
| Hooks app-level dans station_web | présents | dead code (migrés vers `app/hooks.py`) |
| Service systemd | `astroscan-web` | `astroscan.service` (le `-web` est masked) |

## 5. Travail restant identifié

- **Cleanup mineur** : retirer les 8 décorateurs `@app.X` dead-code dans station_web.py (PASS 25 historiquement planifié). Risque : régression du fallback monolithe (`ASTROSCAN_FORCE_MONOLITH=1`). Recommandation : conserver tant que le fallback est filet de sécurité actif.
- **Helpers partagés** : 52 symboles importés depuis station_web par 15 fichiers de `app/` (voir `SHARED_DEPS.md`). Extraction possible vers `app/services/` ou `app/shared/` mais à valeur ajoutée faible — déjà fonctionnel via lazy-import.
- **Aucune route à migrer** : objectif Phase 2C atteint.
