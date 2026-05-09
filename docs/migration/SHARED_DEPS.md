# SHARED DEPENDENCIES — station_web.py exports utilisés par `app/`

**Date :** 2026-05-07  
**Symboles distincts importés :** 52  
**Fichiers consommateurs :** 15 fichiers dans `app/`

Pattern actuel : **lazy import** dans le corps des fonctions (`from station_web import X`) pour éviter l'import circulaire ; `wsgi.py` pré-charge `station_web` AVANT `create_app()`.

## 1. Vue d'ensemble par catégorie

| Catégorie | Symboles | Total imports |
|---|---:|---:|
| **Paths / DB constants** | 7 | 23 |
| **TLE cache & helpers** | 12 | 20 |
| **Visitor / analytics** | 5 | 17 |
| **Logging** | 5 | 8 |
| **ISS** | 2 | 5 |
| **Lab module** | 2 | 5 |
| **Metrics / rate-limit** | 2 | 4 |
| **Misc** | 4 | 4 |
| **Scoring / accuracy** | 3 | 3 |
| **App lifecycle** | 2 | 3 |
| **Satellites** | 2 | 3 |
| **SEO / pages metadata** | 3 | 3 |
| **Owner / IPs** | 1 | 2 |
| **Skyview** | 2 | 2 |

## 2. Détail par catégorie

### App lifecycle

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `START_TIME` | 2 | blueprints/health/__init__.py |
| `server_ready` | 1 | blueprints/api/__init__.py |

### ISS

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `_fetch_iss_live` | 4 | blueprints/feeds/__init__.py, blueprints/iss/routes.py, blueprints/research/__init__.py |
| `_get_iss_crew` | 1 | blueprints/iss/routes.py |

### Lab module

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `MAX_LAB_IMAGE_BYTES` | 3 | blueprints/lab/__init__.py |
| `_lab_last_report` | 2 | blueprints/lab/__init__.py |

### Logging

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `_emit_diag_json` | 3 | blueprints/iss/routes.py, hooks.py |
| `log` | 2 | hooks.py |
| `system_log` | 1 | blueprints/iss/routes.py |
| `_http_request_log_allow` | 1 | hooks.py |
| `struct_log` | 1 | hooks.py |

### Metrics / rate-limit

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `_api_rate_limit_allow` | 3 | blueprints/lab/__init__.py, blueprints/main/__init__.py |
| `metrics_record_request` | 1 | hooks.py |

### Misc

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `_client_ip_from_request` | 1 | blueprints/main/__init__.py |
| `_start_lab_image_collector` | 1 | bootstrap.py |
| `translate_worker` | 1 | bootstrap.py |
| `_core_status_engine`` | 1 | services/status_engine.py |

### Owner / IPs

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `_invalidate_owner_ips_cache` | 2 | blueprints/analytics/__init__.py |

### Paths / DB constants

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `STATION` | 5 | blueprints/export/__init__.py, blueprints/health/__init__.py |
| `TLE_ACTIVE_PATH` | 4 | blueprints/api/__init__.py, blueprints/iss/routes.py, blueprints/satellites/__init__.py |
| `RAW_IMAGES` | 4 | blueprints/lab/__init__.py |
| `LAB_UPLOADS` | 3 | blueprints/lab/__init__.py, blueprints/research/__init__.py |
| `SPACE_IMAGE_DB` | 3 | blueprints/lab/__init__.py |
| `METADATA_DB` | 3 | blueprints/lab/__init__.py |
| `ANALYSED_IMAGES` | 1 | blueprints/lab/__init__.py |

### SEO / pages metadata

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `SEO_HOME_DESCRIPTION` | 1 | hooks.py |
| `PAGE_PATHS` | 1 | hooks.py |
| `_SESSION_TIME_SNIPPET` | 1 | hooks.py |

### Satellites

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `list_satellites` | 2 | blueprints/api/__init__.py, blueprints/satellites/__init__.py |
| `SATELLITES` | 1 | blueprints/satellites/__init__.py |

### Scoring / accuracy

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `_compute_human_score` | 1 | blueprints/analytics/__init__.py |
| `get_accuracy_history` | 1 | blueprints/api/__init__.py |
| `get_accuracy_stats` | 1 | blueprints/api/__init__.py |

### Skyview

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `_sync_skyview_to_lab` | 1 | blueprints/lab/__init__.py |
| `_start_skyview_sync` | 1 | bootstrap.py |

### TLE cache & helpers

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `_parse_tle_file` | 4 | blueprints/api/__init__.py, blueprints/iss/routes.py, blueprints/satellites/__init__.py |
| `TLE_CACHE` | 3 | blueprints/api/__init__.py, blueprints/iss/routes.py |
| `propagate_tle_debug` | 2 | blueprints/iss/routes.py, blueprints/satellites/__init__.py |
| `_TLE_FOR_PASSES` | 2 | blueprints/satellites/__init__.py |
| `TLE_CACHE`` | 2 | services/tle_cache.py |
| `_get_satellite_tle_by_name` | 1 | blueprints/satellites/__init__.py |
| `TLE_MAX_SATELLITES` | 1 | blueprints/satellites/__init__.py |
| `_telescope_nightly_tlemcen` | 1 | blueprints/telescope/__init__.py |
| `load_tle_cache_from_disk` | 1 | bootstrap.py |
| `fetch_tle_from_celestrak` | 1 | bootstrap.py |
| `tle_refresh_loop` | 1 | bootstrap.py |
| `_start_tle_collector` | 1 | bootstrap.py |

### Visitor / analytics

| Symbole | # imports | Fichiers consommateurs |
|---|---:|---|
| `_get_db_visitors` | 9 | blueprints/analytics/__init__.py, blueprints/api/__init__.py |
| `get_global_stats` | 3 | blueprints/analytics/__init__.py |
| `_get_visits_count` | 2 | blueprints/analytics/__init__.py |
| `_register_unique_visit_from_request` | 2 | blueprints/analytics/__init__.py, hooks.py |
| `_increment_visits` | 1 | blueprints/analytics/__init__.py |

## 3. Fichiers consommateurs (top)

| Fichier | Symboles importés |
|---|---:|
| `app/blueprints/lab/__init__.py` | 9 |
| `app/hooks.py` | 9 |
| `app/blueprints/api/__init__.py` | 8 |
| `app/blueprints/iss/routes.py` | 8 |
| `app/blueprints/satellites/__init__.py` | 8 |
| `app/blueprints/analytics/__init__.py` | 7 |
| `app/bootstrap.py` | 7 |
| `app/blueprints/health/__init__.py` | 2 |
| `app/blueprints/main/__init__.py` | 2 |
| `app/blueprints/research/__init__.py` | 2 |
| `app/blueprints/export/__init__.py` | 1 |
| `app/blueprints/feeds/__init__.py` | 1 |
| `app/blueprints/telescope/__init__.py` | 1 |
| `app/services/status_engine.py` | 1 |
| `app/services/tle_cache.py` | 1 |

## 4. Recommandations

- **Court terme** : conserver le pattern lazy-import. Stable, fonctionnel, zéro risque.
- **Moyen terme** : extraire les groupes auto-portants vers `app/services/` :
  - `app/services/tle_cache.py` ← `TLE_CACHE`, `_parse_tle_file`, `TLE_ACTIVE_PATH`, `_TLE_FOR_PASSES`, `load_tle_cache_from_disk`, `fetch_tle_from_celestrak`
  - `app/services/visitor_log.py` ← `_get_db_visitors`, `_register_unique_visit_from_request`, `_increment_visits`, `get_global_stats`, `_get_visits_count`
  - `app/services/diag_log.py` ← `log`, `struct_log`, `system_log`, `_emit_diag_json`
  - `app/services/paths.py` ← `STATION`, `RAW_IMAGES`, `ANALYSED_IMAGES`, `SPACE_IMAGE_DB`, `METADATA_DB`, `LAB_UPLOADS`
- **Long terme** : suppression complète de `station_web.py` quand toutes les sources d'init seront extraites (lecture `.env`, init DB WAL, threads collector).
