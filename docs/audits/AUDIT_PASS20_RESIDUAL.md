# AUDIT MONOLITHE RÉSIDUEL — `station_web.py`

**Branche** : `migration/phase-2c`
**Date** : 2026-05-06
**Préparation** : PASS 20 (post-PASS 19 cleanup)
**Mode** : LECTURE SEULE — aucune modification de fichier source.

> Ce rapport cartographie ce qui reste réellement dans `station_web.py` après l'extraction de 21 Blueprints + 13 services + factory `create_app()` + hooks app-level (PASS 24) + bootstrap (PASS 25.1). Objectif : décider de la stratégie PASS 20.

---

## SECTION 1 — MÉTRIQUES GLOBALES

| Métrique | Valeur | Source |
| --- | ---: | --- |
| Lignes totales | **5 315** | `wc -l station_web.py` |
| Lignes vides | 698 | grep |
| Lignes de commentaires (`# …`) | 788 | grep |
| Lignes de code effectives | **3 829** | total − vides − commentaires |
| Fonctions définies (def + async def, tous niveaux) | **129** | AST `ast.walk` |
| Fonctions top-level | 102 | AST body |
| Classes | **1** (`_AstroScanJsonLogFormatter`, L580) | AST |
| Routes Flask actives `@app.route` | **0** | grep `^@app\.route` |
| Routes WebSocket actives `@_sock.route` | **2** (`/ws/status`, `/ws/view-sync`) | L4037, L4051 (bloc try/except L4032) |
| `@app.before_request` / `@app.after_request` / `@app.errorhandler` | **3 + 2 + 2 = 7** | grep |
| `@app.context_processor` | 1 | L473 |
| Threads / Timers démarrés au top-level | **3** (refresh_tle indirect via `refresh_tle_from_amsat()` + `_start_tle_collector` non-appelé top-level) | voir Section 7 |
| Threads / Timers démarrés DANS des fonctions | **5** | L4642, L4738, L4752, L5005, L5015 |
| Imports top-level (statements) | **33** | AST body |
| Statements top-level **exécutables** (hors imports/def/class) | ~70 | voir Section 7 |

> **Remarque** : la valeur "5 466 lignes" annoncée dans le brief est obsolète — le PASS 19 cleanup a ramené le fichier à **5 315 lignes**. La route `/static/<path:filename>` mentionnée n'est **plus présente** dans le fichier (Flask la sert nativement via `static_folder` du factory) ; ce qui reste comme « endpoint » est uniquement les 2 routes WebSocket Sock.

---

## SECTION 2 — INVENTAIRE DES IMPORTS TOP-LEVEL

### 2.1 — stdlib (14)

| Ligne | Import |
| ---: | --- |
| 18 | `import os` |
| 19 | `import sys` |
| 26 | `import json` |
| 27 | `import sqlite3` |
| 28 | `import re` |
| 29 | `import time` |
| 30 | `import random` |
| 31 | `import logging` |
| 32 | `import subprocess` |
| 33 | `import threading` |
| 35 | `import secrets` |
| 36 | `import fcntl` |
| 37 | `from logging.handlers import RotatingFileHandler` |
| 38 | `from pathlib import Path` |
| 39 | `from datetime import datetime, timezone, timedelta` |

### 2.2 — Flask / Werkzeug (1)

| Ligne | Import |
| ---: | --- |
| 44 | `from flask import Flask, render_template, jsonify, request, g` |

### 2.3 — Modules tiers (1)

| Ligne | Import |
| ---: | --- |
| 34 | `import requests` |

### 2.4 — Modules internes du projet (10 — niveau module)

| Ligne | Import | Catégorie |
| ---: | --- | --- |
| 59 | `from services.stats_service import get_global_stats` | re-export `# noqa: F401` |
| 60–62 | `from services.weather_service import compute_weather_score, generate_weather_bulletin, compute_reliability` | utilisé localement |
| 69–71 | `from services.orbital_service import compute_tle_risk_signal, build_final_core, normalize_celestrak_record` | utilisé localement |
| 74 | `from services.cache_service import cache_get, cache_set, get_cached` | utilisé localement |
| 78–81 | `from services.utils import _is_bot_user_agent, _parse_iso_to_epoch_seconds, _safe_json_loads, safe_ensure_dir` | utilisé localement |
| 84 | `from services.db import init_all_wal` | appelé top-level L191 |
| 87 | `from services.circuit_breaker import CB_TLE` | utilisé localement |

### 2.5 — Imports re-exportés `# noqa: F401` (servent uniquement de pont vers les BPs)

| Ligne | Import | Cible |
| ---: | --- | --- |
| 50 | `from app.services.orbit_sgp4 import propagate_tle_debug` | BPs |
| 51 | `from app.services.satellites import SATELLITES, list_satellites, get_satellite_tle_name_map` | BPs |
| 52 | `from app.services.accuracy_history import get_accuracy_history, get_accuracy_stats` | BPs |
| 59 | `from services.stats_service import get_global_stats` | analytics_bp |
| 169 | `from app.services.station_state import STATION` | BPs (re-export) |
| 525 | `from app.services.status_engine import _core_status_engine` | re-export |
| 782 | `from app.services.tle_cache import TLE_CACHE, TLE_CACHE_FILE` | BPs |
| 2666 | `from app.services.iss_live import _fetch_iss_live` | iss_bp |
| 5184 | `from app.services.db_visitors import _get_db_visitors` | analytics_bp |

### 2.6 — Imports conditionnels / lazy (mid-file)

| Ligne | Import | Statut |
| ---: | --- | --- |
| 444 | `from dotenv import load_dotenv` (try/except) | bootstrap env |
| 519 | `from core import data_engine as _core_data_engine` (try/except) | bootstrap data |
| 2942 | `from skyview_module import …` (try/except + fallback) | sourcing |
| 3416 | `from datetime import datetime as _dt_utc` | helper interne |
| 4032 | `from flask_sock import Sock` (try/except — déclare 2 routes WS) | side effect |
| `from view_sync_backend import …` | dans body ws_view_sync (L4067) | dépendance lazy |

> **Verdict imports** : 7 re-exports `# noqa: F401` constituent la dette principale. Tant qu'au moins 1 BP fait `from station_web import X`, le module reste un goulot d'étranglement. **17 fichiers BPs** importent encore depuis `station_web` (67 occurrences hors `.bak`).

---

## SECTION 3 — INVENTAIRE DES ROUTES FLASK RESTANTES

### 3.1 — `@app.route` actifs

**Aucun.** `grep "^@app\.route" station_web.py` → 0 résultat.

Toutes les routes HTTP ont été migrées vers les 21 Blueprints (PASS 1–17).
Les ~50 lignes commentées `# @app.route(…)` qui subsistent sont des marqueurs de migration (PASS 5–17) — **lecture seule**, donc non chargés par Flask.

### 3.2 — Routes WebSocket `@_sock.route` (Sock — Flask-Sock)

| Ligne | Méthode | Path | Fonction | Lignes occupées | Verdict |
| ---: | --- | --- | --- | --- | --- |
| 4037 | WS | `/ws/status` | `ws_status(ws)` | 4037–4049 | **À MIGRER** vers `app/blueprints/system/` (ou nouveau `realtime_bp`) |
| 4051 | WS | `/ws/view-sync` | `ws_view_sync(ws)` | 4051–4114 | **À MIGRER** vers nouveau `app/blueprints/realtime/` (orchestre `view_sync_backend`) |

> Les 2 routes WS sont attachées à `station_web.app` (l'instance Flask **dead** — voir wsgi.py / `_register_blueprints` côté factory ne les voit pas). Conséquence : si la factory réussit, **`/ws/status` et `/ws/view-sync` ne sont pas servis sur le chemin live**. À traiter en priorité PASS 20.

### 3.3 — Override Flask `/static/<path:filename>`

**Absent du fichier.** Le brief mentionnait cette route — elle a été retirée en PASS 25.2 (commentaire L48–49). Flask sert `/static/*` nativement via `static_folder` configuré dans `app/__init__.py` (factory) **et** dans `station_web.app` (L460–462). **Aucune action requise**.

---

## SECTION 4 — DÉCORATEURS GLOBAUX

> Tous ces hooks sont attachés à `station_web.app`. **Le PASS 24 a déjà copié verbatim les 7 hooks dans `app/hooks.py`** (`register_hooks(app)` appelé par `create_app`), donc sur le chemin live (factory), les hooks de `station_web.py` sont **dead code**. Les conserver brièvement est utile pour le fallback monolithe (`ASTROSCAN_FORCE_MONOLITH=1`).

| L | Type | Fonction | Range | Verdict |
| ---: | --- | --- | ---: | --- |
| 473 | `@app.context_processor` | `_inject_seo_site_description` | 473–476 | **DÉJÀ MIGRÉ** vers `app/hooks.py` — supprimer après PASS 20 (suppression fallback monolithe) |
| 493 | `@app.errorhandler(404)` | `_astroscan_404` | 493–500 | **DÉJÀ MIGRÉ** vers `app/hooks.py` |
| 503 | `@app.errorhandler(500)` | `_astroscan_500` | 503–514 | **DÉJÀ MIGRÉ** vers `app/hooks.py` |
| 1870 | `@app.before_request` | `_astroscan_request_timing_start` | 1870–1893 | **DÉJÀ MIGRÉ** |
| 1896 | `@app.before_request` | `_astroscan_visitor_session_before` | 1896–1915 | **DÉJÀ MIGRÉ** |
| 1918 | `@app.before_request` | `_maybe_increment_visits` | 1918–1932 | **DÉJÀ MIGRÉ** |
| 1935 | `@app.after_request` | `_astroscan_struct_log_response` | 1935–2033 | **DÉJÀ MIGRÉ** |
| 5215 | `@app.after_request` | `_astroscan_session_cookie_and_time_script` | 5215–5246 | **DÉJÀ MIGRÉ** (fonction L5216) |

**Conclusion Section 4** : 7/7 hooks app-level sont déjà dans `app/hooks.py`. Aucun travail d'extraction restant ; juste de la suppression différée.

---

## SECTION 5 — INVENTAIRE DES FONCTIONS RESTANTES (top-level, 102)

> Pour la lisibilité, les fonctions sont regroupées par catégorie. La colonne `↗ refs` indique combien de fichiers sous `app/` ou `services/` font `from station_web import <nom>` (hors `.bak*`).

### 5.1 — INIT / BOOTSTRAP (à extraire vers `app/bootstrap.py` ou `app/init/`)

| L | Fonction | Lignes | ↗ refs | Verdict |
| ---: | --- | ---: | ---: | --- |
| 100 | `_emit_diag_json` | 14 | 1 (hooks.py) | **EXTRAIRE** vers `app/services/observability.py` |
| 116 | `_requests_instrumented_request` | 28 | 0 | **EXTRAIRE** vers `app/services/observability.py` (instrumente `requests.Session.request` — side-effect L146) |
| 177 | `_init_sqlite_wal` | 13 | 0 | **EXTRAIRE** vers `app/init/db.py` (déjà partiellement présent dans `app/__init__.py:_init_sqlite_wal`) |
| 195 | `init_weather_db` | 41 | 0 | **EXTRAIRE** vers `app/init/weather.py` |
| 238 | `_init_weather_history_dir` | 5 | 0 | idem |
| 245 | `_cleanup_weather_history_files` | 18 | 0 | idem |
| 265 | `_init_weather_archive_dir` | 5 | 0 | idem |
| 272 | `_cleanup_weather_archive_files` | 18 | 0 | idem |
| 528 | `_run_calculateur_passages_iss` | 25 | 0 | **EXTRAIRE** vers `app/init/passages.py` |
| 555 | `ensure_passages_iss_json` | 6 | 0 | idem |

### 5.2 — RE-EXPORT POUR BPs (helpers utilisés par ≥ 1 fichier `app/`)

| L | Fonction | Lignes | ↗ refs | Verdict |
| ---: | --- | ---: | ---: | --- |
| 292 | `save_weather_archive_json` | 20 | 0 | **EXTRAIRE** vers `app/services/weather_archive.py` (existe déjà — déplacer le corps) |
| 314 | `save_weather_history_json` | 21 | 0 | idem |
| 337 | `save_weather_bulletin` | 82 | 0 | idem |
| 632 | `metrics_record_request` | 11 | 1 (hooks.py) | **EXTRAIRE** vers `app/services/metrics.py` |
| 645 | `metrics_record_struct_error` | 11 | 0 | idem |
| 658 | `metrics_status_fields` | 11 | 0 | idem |
| 679 | `_http_request_log_allow` | 15 | 1 (hooks.py) | idem |
| 700 | `_api_rate_limit_allow` | 26 | 2 | **EXTRAIRE** vers `app/services/rate_limit.py` |
| 728 | `struct_log` | 14 | 1 (hooks.py) | **EXTRAIRE** vers `app/services/struct_log.py` |
| 754 | `system_log` | 2 | 0 | idem (orbital_log) |
| 806 | `_health_log_error` | 46 | 0 | **EXTRAIRE** vers `app/services/health.py` |
| 853 | `_health_set_error` | 3 | 0 | idem |
| 857 | `load_stellarium_data` | 30 | 0 | **EXTRAIRE** vers `app/services/stellarium.py` |
| 889 | `compute_stellarium_freshness` | 20 | 0 | idem |
| 911 | `build_priority_object` | 62 | 0 | idem |
| 975 | `build_system_intelligence` | 78 | 0 | **EXTRAIRE** vers `app/services/fusion_engine.py` |
| 1055 | `get_nasa_apod` | 48 | 0 | **EXTRAIRE** vers `app/services/nasa_apod.py` |
| 1105 | `fetch_tle_from_celestrak` | 339 | 1 (bootstrap.py) | **EXTRAIRE** vers `app/services/tle_fetch.py` (le plus gros morceau du fichier) |
| 1446 | `_tle_next_sleep_seconds` | 13 | 0 | idem |
| 1461 | `load_tle_cache_from_disk` | 47 | 1 (bootstrap.py) | idem |
| 1510 | `tle_refresh_loop` | 12 | 1 (bootstrap.py) | idem |
| 1528 | `get_db` | 4 | 0 | **SUPPRIMER** (mort, BPs utilisent `app.utils.db`) |
| 1534 | `_init_visits_table` | 9 | 0 | **EXTRAIRE** vers `app/init/visits.py` |
| 1545 | `_init_session_tracking_db` | 67 | 0 | idem |
| 1618 | `_get_visits_count` | 6 | 1 | **EXTRAIRE** vers `app/services/visits.py` |
| 1626 | `_increment_visits` | 8 | 1 | idem |
| 1636 | `_curl_get` | 12 | 0 | **SUPPRIMER** (cherry-pick : sondage usages restants — sinon dead) |
| 1650 | `_curl_post` | 16 | 0 | idem |
| 1668 | `_curl_post_json` | 4 | 0 | idem |
| 1691 | `_client_ip_from_request` | 4 | 1 (analytics_bp) | **EXTRAIRE** vers `app/utils/request_meta.py` |
| 1703 | `_load_owner_ips` | 30 | 0 | **EXTRAIRE** vers `app/services/owner_ips.py` |
| 1735 | `_is_owner_ip` | 5 | 0 | idem |
| 1742 | `_invalidate_owner_ips_cache` | 5 | 1 (analytics_bp) | idem |
| 1749 | `_compute_human_score` | 27 | 1 (analytics_bp) | **EXTRAIRE** vers `app/services/visitor_score.py` |
| 1778 | `_register_unique_visit_from_request` | 90 | 2 (hooks.py + analytics_bp) | **EXTRAIRE** vers `app/services/visits.py` |
| 2039 | `get_user_lang` | 7 | 0 | **EXTRAIRE** vers `app/blueprints/i18n/` (déjà présent ailleurs ?) |
| 2294 | `_analytics_tz_for_country_code` | 10 | 0 | **EXTRAIRE** vers `app/services/analytics_format.py` |
| 2306 | `_analytics_fmt_duration_sec` | 14 | 0 | idem |
| 2322 | `_analytics_journey_display` | 7 | 0 | idem |
| 2331 | `_analytics_start_local_display` | 16 | 0 | idem |
| 2349 | `_analytics_time_hms_local` | 16 | 0 | idem |
| 2367 | `_analytics_session_classification` | 15 | 0 | idem |
| 2384 | `get_geo_from_ip` | 54 | 0 | **EXTRAIRE** vers `app/services/geoip.py` |

### 5.3 — HELPERS images / téléscope / collecteurs

| L | Fonction | Lignes | ↗ refs | Verdict |
| ---: | --- | ---: | ---: | --- |
| 2545 | `_source_path` | 2 | 0 | **EXTRAIRE** vers `app/services/image_archive.py` |
| 2548 | `_fetch_apod_live` | 20 | 0 | idem |
| 2569 | `_fetch_hubble_archive` | 24 | 0 | idem |
| 2597 | `_fetch_apod_archive_live` | 22 | 0 | idem |
| 2622 | `_sync_state_read` | 11 | 0 | **EXTRAIRE** vers `app/services/sync_state.py` |
| 2633 | `_sync_state_write` | 10 | 0 | idem |
| 2669 | `_get_iss_tle_from_cache` | 72 | 0 | **EXTRAIRE** vers `app/services/iss_tle.py` |
| 2770 | `_get_satellite_tle_by_name` | 22 | 0 | **EXTRAIRE** vers `app/services/satellites.py` (existe) |
| 2835 | `_fetch_iss_crew` | 11 | 0 | **EXTRAIRE** vers `app/services/iss_live.py` (existe) |
| 2848 | `_get_iss_crew` | 14 | 0 | idem |
| 2863 | `_guess_region` | 15 | 0 | **EXTRAIRE** vers `app/services/geoip.py` |
| 3142 | `_mo_parse_filename` | 13 | 0 | **EXTRAIRE** vers `app/services/microobservatory.py` (existe) |
| 3157 | `_mo_fetch_catalog_today` | 31 | 0 | idem |
| 3190 | `_mo_visible_tonight` | 41 | 0 | idem |
| 3233 | `_mo_fits_to_jpg` | 36 | 0 | idem |
| 3271 | `_telescope_nightly_tlemcen` | 97 | 1 (telescope_bp) | **EXTRAIRE** vers `app/services/telescope_nightly.py` |
| 3426 | `_fetch_voyager` | 37 | 0 | **EXTRAIRE** vers `app/services/external_feeds.py` (existe) |
| 3464 | `_fetch_neo` | 41 | 0 | idem |
| 3506 | `_fetch_solar_wind` | 21 | 0 | idem |
| 3528 | `_fetch_solar_alerts` | 25 | 0 | idem |
| 3554 | `_fetch_mars_rover` | 28 | 0 | idem |
| 3583 | `_fetch_apod_hd` | 28 | 0 | idem |
| 3680 | `_db_observations_count` | 9 | 0 | **EXTRAIRE** vers `app/services/observations_db.py` |
| 3694 | `_fallback_status_payload_dict` | 62 | 0 | **EXTRAIRE** vers `app/services/status_engine.py` (existe) |
| 3758 | `_build_status_payload_dict` | 163 | 0 | idem |
| 3923 | `get_status_data` | 17 | 0 | idem |
| 3942 | `validate_system_state` | 19 | 0 | idem |
| 3964 | `build_status_snapshot_dict` | 28 | 0 | idem |
| 4125 | `_fetch_hubble` | 30 | 0 | **EXTRAIRE** vers `app/services/external_feeds.py` |
| 4214 | `_apply_news_translations` | 16 | 0 | **EXTRAIRE** vers `app/services/news_translate.py` |
| 4252 | `_fetch_swpc_alerts` | 76 | 0 | **EXTRAIRE** vers `app/services/space_weather.py` |
| 4378 | `log_rejected_image` | 13 | 0 | **EXTRAIRE** vers `app/services/lab_collector.py` |
| 4393 | `save_normalized_metadata` | 11 | 0 | idem |
| 4418 | `_download_nasa_apod` | 39 | 0 | idem |
| 4459 | `_download_hubble_images` | 50 | 0 | idem |
| 4511 | `_download_jwst_images` | 34 | 0 | idem |
| 4547 | `_download_esa_images` | 54 | 0 | idem |
| 4603 | `_sync_skyview_to_lab` | 30 | 0 | idem |
| 4635 | `_start_skyview_sync` | 9 | 1 (bootstrap.py) | **EXTRAIRE** vers `app/workers/skyview.py` |
| 4651 | `_aegis_collector_acquire_lock` | 7 | 0 | **EXTRAIRE** vers `app/services/lab_collector.py` |
| 4660 | `_aegis_collector_release_lock` | 6 | 0 | idem |
| 4668 | `_aegis_collector_can_run` | 9 | 0 | idem |
| 4679 | `_aegis_collector_mark_run` | 8 | 0 | idem |
| 4689 | `run_collector_safe` | 17 | 0 | idem |
| 4708 | `_run_lab_image_collector_once` | 37 | 0 | idem |
| 4747 | `_start_lab_image_collector` | 7 | 1 (bootstrap.py) | **EXTRAIRE** vers `app/workers/lab.py` |
| 4756 | `translate_worker` | 46 | 1 (bootstrap.py) | **EXTRAIRE** vers `app/workers/translate.py` |
| 4814 | `download_tle_now` | 26 | 0 | **EXTRAIRE** vers `app/services/tle_fetch.py` |
| 4842 | `refresh_tle_from_amsat` | 107 | 0 | idem |
| 4951 | `_download_tle_catalog` | 16 | 0 | idem |
| 4969 | `_parse_tle_file` | 19 | 2 (api_bp + satellites_bp) | idem |
| 4996 | `_run_tle_download_once` | 12 | 0 | idem |
| 5010 | `_start_tle_collector` | 7 | 1 (bootstrap.py) | **EXTRAIRE** vers `app/workers/tle.py` |
| 5039 | `_elevation_above_observer` | 12 | 0 | **EXTRAIRE** vers `app/services/satellites.py` (helper passes) |
| 5216 | `_astroscan_session_cookie_and_time_script` | 31 | 0 | **DEAD** (déjà migré dans `app/hooks.py`) |

### 5.4 — Catégorisation finale

| Catégorie | # | Stratégie |
| --- | ---: | --- |
| INIT/BOOTSTRAP | 11 | → `app/init/` ou conserver dans `bootstrap.py` |
| RE-EXPORT POUR BPs | 11 (refs ≥ 1) | → `app/services/<X>.py`, supprimer les re-exports `# noqa` |
| HELPERS UTILITAIRES (refs = 0) | 70+ | → `app/services/legacy/` (poubelle d'attente) puis tri ciblé |
| THREAD WORKERS | 4 (`_start_*`, `translate_worker`) | → `app/workers/` |
| CALLBACKS FLASK | 7 hooks + 2 errorhandlers + 1 ctx_processor + 2 WS routes | hooks déjà migrés ; WS routes à migrer PASS 20 |
| CLASSES | 1 (`_AstroScanJsonLogFormatter`) | → `app/services/log_format.py` |

---

## SECTION 6 — VARIABLES GLOBALES & ÉTAT MUTABLE

### 6.1 — Constantes immutables (déplaçables sans danger)

| L | Nom | Type | ↗ refs | Verdict |
| ---: | --- | --- | ---: | --- |
| 94–96 | `_REQ_DEFAULT_TIMEOUT`, `_REQ_SLOW_MS`, `_REQ_VERY_SLOW_MS` | int | 0 | EXTRAIRE → `app/services/observability.py` |
| 97 | `_REQ_ORIGINAL_REQUEST` | bound method | 0 | idem (avant monkey-patch L146) |
| 150–154 | `TRANSLATE_TTL_SECONDS`, `MAX_CACHE_SIZE` | int | 0 | EXTRAIRE → `app/workers/translate.py` |
| 162–163 | `CLAUDE_MAX_CALLS`, `CLAUDE_80_WARNING_SENT` | int/bool | 0 | EXTRAIRE → `app/services/llm_quota.py` |
| 170–174 | `DB_PATH`, `WEATHER_DB_PATH`, `WEATHER_HISTORY_DIR`, `WEATHER_ARCHIVE_DIR` | str | 0 | MIGRER VERS `create_app()` config |
| 425–432 | `IMG_PATH`, `TITLE_F`, `REPORT_F`, `SHIELD_F`, `HUB_F`, `SDR_F`, `PASSAGES_ISS_JSON`, `CALC_PASSAGES_SCRIPT` | str | 0 | idem |
| 435–441 | `SEO_HOME_TITLE`, `SEO_HOME_DESCRIPTION` | str | 1 (hooks.py) | EXTRAIRE → `app/services/seo.py` |
| 458 | `CESIUM_TOKEN` | str | 0 | MIGRER VERS `create_app()` config |
| 763–778 | `TLE_*` (12 constantes) | int/str/float | 0 | EXTRAIRE → `app/services/tle_fetch.py` |
| 803–804 | `STALE_DATA_THRESHOLD_SEC`, `AGING_DATA_THRESHOLD_SEC` | int | 0 | EXTRAIRE → `app/services/health.py` |
| 1683 | `PAGE_PATHS` | set | 1 (hooks.py) | EXTRAIRE → `app/services/visits.py` |
| 2037 | `SUPPORTED_LANGS` | set | 0 | DOUBLON — déjà dans `create_app()` config |
| 2085 | `API_SPEC` | dict | 0 | EXTRAIRE → `app/services/api_spec.py` |
| 2544 | `_IMAGE_CACHE_TTL` | int | 0 | EXTRAIRE → `app/services/image_archive.py` |
| 2621 | `SYNC_STATE_F` | Path | 0 | idem |
| 2974 | `FETES_ISLAMIQUES` | list[dict] | 0 | EXTRAIRE → `app/services/hilal_compute.py` (existe) |
| 3096–3097 | `_MO_DIR_URL`, `_MO_DL_BASE` | str | 0 | EXTRAIRE → `app/services/microobservatory.py` |
| 3100 | `_MO_OBJECT_CATALOG` | dict | 0 | idem |
| 3691 | `STATUS_OBSERVER_LABEL` | str | 0 | EXTRAIRE → `app/services/status_engine.py` |
| 4203 | `_NEWS_TRADUCTIONS` | dict | 0 | EXTRAIRE → `app/services/news_translate.py` |
| 4359–4374 | `LAB_UPLOADS`, `RAW_IMAGES`, `ANALYSED_IMAGES`, `MAX_LAB_IMAGE_BYTES`, `METADATA_DB`, `LAB_LOGS_DIR`, `SKYVIEW_DIR`, `SPACE_IMAGE_DB` | str/int | 1–2 (lab_bp) | EXTRAIRE → `app/services/lab_paths.py` |
| 4646–4648 | `LOCK_FILE`, `LAST_RUN_FILE`, `COOLDOWN_SECONDS` | str/int | 0 | EXTRAIRE → `app/services/lab_collector.py` |
| 4807–4811 | `TLE_DIR`, `TLE_ACTIVE_PATH`, `TLE_MAX_SATELLITES` | str/int | 2 (api_bp + satellites_bp) | EXTRAIRE → `app/services/tle_fetch.py` |
| 5033 | `_TLE_FOR_PASSES` | list[dict] | 1 (satellites_bp) | EXTRAIRE → `app/services/satellites.py` |
| 5197 | `_SESSION_TIME_SNIPPET` | str | 1 (hooks.py) | EXTRAIRE → `app/services/session_snippet.py` |

### 6.2 — État mutable / locks (sensible à l'identité)

| L | Nom | Type | ↗ refs | Verdict |
| ---: | --- | --- | ---: | --- |
| 149 | `TRANSLATE_CACHE` | dict | 0 | EXTRAIRE → `app/workers/translate.py` |
| 151 | `TRANSLATE_LAST_REQUEST_TS` | float (mutable via `global`) | 0 | idem |
| 153 | `TRANSLATION_CACHE` | dict | 0 | idem |
| 157 | `START_TIME` | float | 1 | MIGRER VERS `app/state.py` (re-export) |
| 159 | `server_ready` | bool | 1 | MIGRER VERS `app/state.py` (mais piégé par `global` patterns) |
| 161,164,165 | `CLAUDE_CALL_COUNT`, `GROQ_CALL_COUNT`, `COLLECTOR_LAST_RUN` | int (mutable) | 0 | EXTRAIRE → `app/state.py` |
| 621–624 | `_METRICS_LOCK`, `_METRICS_REQUEST_TIMES`, `_METRICS_ERROR_TIMES`, `_METRICS_MAX_REQ_BUFFER` | Lock + list | 0 | EXTRAIRE → `app/services/metrics.py` |
| 672–676 | `_HTTP_LOG_LOCK`, `_HTTP_LOG_TOKENS`, `_HTTP_LOG_MAX`, `_HTTP_LOG_REFILL_PER_SEC`, `_HTTP_LOG_LAST_MONO` | Lock + float | 0 | idem |
| 696–697 | `_API_RATE_LOCK`, `_API_RATE_HITS` | Lock + dict | 0 | EXTRAIRE → `app/services/rate_limit.py` |
| 785 | `HEALTH_STATE` | dict (lecture/écriture multi-thread) | 0 | EXTRAIRE → `app/services/health.py` (Thread-safe wrapper) |
| 1698–1700 | `_OWNER_IPS_CACHE`, `_OWNER_IPS_CACHE_TS`, `_OWNER_IPS_LOCK` | set + Lock | 0 | EXTRAIRE → `app/services/owner_ips.py` |
| 4375 | `_lab_last_report` | dict | 1 (lab_bp) | EXTRAIRE → `app/services/lab_state.py` |
| 460 | `app` | Flask instance | (dead — la factory crée une autre instance) | À SUPPRIMER après PASS 20 (plan PASS 25.4 mentionné L470) |

> **Risque identifié** : `TLE_CACHE` (importé depuis `app.services.tle_cache`, L782) doit conserver son **identité d'objet** (mutation `.clear() + .update()` plutôt que réassignation) car les BPs en lisent l'état mutable via re-export. Idem pour `HEALTH_STATE`.

---

## SECTION 7 — THREADS & SIDE-EFFECTS À L'IMPORT

> Tout ce qui suit s'exécute **au chargement** de `import station_web` (avant `create_app()` côté wsgi.py).

### 7.1 — Threads / Timers démarrés au top-level

| L | Action | Verdict |
| ---: | --- | --- |
| 5019–5025 | `try: refresh_tle_from_amsat()` (synchrone — peut bloquer ~10 s) | **DÉPLACER** dans `app/bootstrap.py` (déjà partiellement fait — la fonction est ré-appelée par `_start_tle_collector` 60 s après start) |
| 5026–5029 | `if os.path.isfile(TLE_ACTIVE_PATH): log.info(...)` | DÉPLACER dans `app/bootstrap.py` |

> **Note importante** : aucun `threading.Thread().start()` direct au top-level. Les 5 threads listés en Section 1 sont tous **dans des fonctions** (`_start_lab_image_collector`, `_start_skyview_sync`, `_start_tle_collector`, `tle_refresh_loop`, `translate_worker`) appelées via `app/bootstrap.py:start_background_threads()` — ce qui est l'architecture cible. Les fonctions, elles, sont encore définies dans `station_web.py`.

### 7.2 — Connexions DB ouvertes au top-level

| L | Action | Verdict |
| ---: | --- | --- |
| 190 | `_init_sqlite_wal()` (ouvre DB_PATH, exécute `PRAGMA journal_mode=WAL`) | DÉPLACER dans `create_app()` (déjà présent — DOUBLON à supprimer) |
| 191 | `init_all_wal()` (services/db.py — toutes les bases) | idem (DOUBLON avec `app/__init__.py`) |
| 421 | `init_weather_db()` | DÉPLACER dans `app/init/weather.py` |
| 1614 | `_init_session_tracking_db()` | DÉPLACER dans `app/init/visits.py` |
| 1615 | `_init_visits_table()` | idem |

### 7.3 — Appels réseau au top-level

| L | Action | Verdict |
| ---: | --- | --- |
| 5019 | `refresh_tle_from_amsat()` (HTTP GET vers SatNOGS, timeout 10 s) | DÉPLACER dans `app/bootstrap.py` |

### 7.4 — Init env / config

| L | Action | Verdict |
| ---: | --- | --- |
| 444–448 | `load_dotenv(...)` | DÉPLACER dans `wsgi.py` (avant `create_app`) |
| 450–456 | Parseur `.env` legacy (loop ligne par ligne) | **SUPPRIMER** (doublon de `load_dotenv`) |
| 458 | `CESIUM_TOKEN = os.getenv(...)` | MIGRER VERS `create_app()` config |

### 7.5 — Création de dossiers

| L | Action | Verdict |
| ---: | --- | --- |
| 422 | `_init_weather_history_dir()` | → `app/init/weather.py` |
| 423 | `_init_weather_archive_dir()` | idem |
| 521 | `_core_data_engine.ensure_data_core_dirs(STATION)` (try/except) | → `app/init/data_core.py` |
| 563 | `ensure_passages_iss_json()` (peut spawn `subprocess.run`, timeout 120 s) | → `app/init/passages.py` |
| 566 | `os.makedirs(f'{STATION}/logs', exist_ok=True)` | → `create_app()` |
| 4366–4374 | `os.makedirs(RAW_IMAGES, …)` × 5 | → `app/init/lab.py` |
| 4808 | `os.makedirs(TLE_DIR, exist_ok=True)` | → `app/init/tle.py` |

### 7.6 — Side-effects logger / handler

| L | Action | Verdict |
| ---: | --- | --- |
| 146 | `requests.sessions.Session.request = _requests_instrumented_request` | DÉPLACER dans `create_app()` (monkey-patch global — exécuter une seule fois) |
| 479–484 | `logging.basicConfig(...)` | DÉPLACER dans `create_app()` ou `wsgi.py` |
| 567–577 | `_orbital_handler` + `_orbital_log` (RotatingFileHandler) | EXTRAIRE → `app/services/struct_log.py:setup_orbital_log()` |
| 744–751 | `_structured_json_handler` + `addHandler` sur root logger | idem |

### 7.7 — Init Flask app top-level

| L | Action | Verdict |
| ---: | --- | --- |
| 460–465 | `app = Flask(__name__, …)` + `app.config[...]` | **SUPPRIMER** après PASS 20 (instance dead — confirmée par commentaire L468–470) |

### 7.8 — Signal handlers

**Aucun** détecté (`signal.signal(...)`) au top-level.

### 7.9 — Synthèse Section 7

Le « weight » résiduel à l'import se résume à :
- **1 appel réseau** synchrone (`refresh_tle_from_amsat`) — 10 s timeout dans le pire cas
- **5 ouvertures SQLite WAL** dont 2 doublons avec la factory
- **5 init dirs** + **1 subprocess** (`calculateur_passages.py`, 120 s timeout)
- **2 monkey-patches** logger root + `requests.Session.request`
- **0 thread démarré directement** (tous via bootstrap.py côté factory ✓)

---

## SECTION 8 — RECOMMANDATION STRATÉGIQUE PASS 20

### 8.1 — Diagnostic

| Indicateur | Valeur |
| --- | ---: |
| Lignes restantes | 5 315 |
| Lignes de code effectif | 3 829 |
| Routes HTTP actives | **0** |
| Routes WS actives | 2 (à migrer) |
| Hooks app-level (déjà migrés vers `app/hooks.py`) | 7 |
| Fonctions top-level | 102 |
| Fonctions référencées par BPs/services | ~16 |
| Fonctions dead (refs = 0, helpers locaux d'anciennes routes) | ~80 |
| Globales | ~70 |
| Fichiers BPs important encore depuis `station_web` | 17 |
| Occurrences `from station_web import …` (hors `.bak`) | 67 |

### 8.2 — Choix : **OPTION C — Hybride pragmatique**

**Justification du rejet de A et B :**
- **OPTION A (Bootstrap minimal)** est trompeuse : les ~80 fonctions « refs = 0 » ne sont pas du bootstrap, ce sont des helpers d'anciennes routes déjà migrées et **jamais nettoyées en PASS 17–19**. Garder un bootstrap.py de 1 500 L laisserait 60 % de dead code certifié.
- **OPTION B (Découpe complète)** sous-estime le couplage : 16 helpers actifs sont importés par 17 BPs (67 occurrences). Tout extraire d'un coup = 3+ semaines de PR risquées + pic de régressions sur la chaîne d'import circulaire (`station_web` → `app.services.tle_cache` → tle_refresh_loop).

**Plan retenu (Option C)** : faire **PASS 20 = nettoyage chirurgical en 3 sous-passes**, en exploitant le fait que les hooks et threads sont déjà côté factory.

### 8.3 — Plan PASS 20 — 3 sous-passes ordonnées

#### **PASS 20.1 — Suppression du dead code certifié** (estimé : 1 jour)

Cible : ramener le fichier sous **3 000 L** sans toucher aux re-exports.

1. Supprimer les 50+ lignes `# @app.route(...)` commentées (marqueurs de migration PASS 5–17).
2. Supprimer les 8 hooks/handlers `@app.X` (L473–514, L1870–2033, L5215–5246) — déjà migrés dans `app/hooks.py`.
3. Supprimer les fonctions « refs = 0 » qui n'étaient appelées que par les routes commentées :
   - `_curl_get`, `_curl_post`, `_curl_post_json` (L1636–1671)
   - `get_db` (L1528, alias mort)
   - `get_user_lang` (L2039 — déjà dupliqué dans i18n_bp)
   - les 6 helpers `_analytics_*` (L2294–2381) — utilisés uniquement par anciennes routes
   - les helpers `_mo_*` (L3142–3268) — déjà copiés dans `app/services/microobservatory.py`
   - `_fetch_voyager`, `_fetch_neo`, `_fetch_solar_wind`, `_fetch_solar_alerts`, `_fetch_mars_rover`, `_fetch_apod_hd`, `_fetch_hubble`, `_fetch_swpc_alerts` — déjà dans `services/external_feeds.py` (vérifier au cas par cas)
4. Supprimer le bloc Flask app dead (L460–465) **uniquement après** confirmation que le fallback monolithe n'est plus utilisé en production (suivre les logs `[WSGI] Monolith fallback loaded` sur 7 jours — si 0, supprimer).
5. Supprimer le parseur `.env` legacy L450–456 (doublon de `load_dotenv`).

**Critère de succès 20.1** : `wc -l station_web.py` < 3 000 ; `grep "from station_web import"` count inchangé ; `gunicorn wsgi:app` démarre sans warning ; smoke-test 5 routes critiques (`/`, `/api/iss/now`, `/api/tle/status`, `/space-weather`, `/portail`).

#### **PASS 20.2 — Migration WS routes + monkey-patches** (estimé : 0.5 jour)

1. Créer `app/blueprints/realtime/__init__.py` avec `/ws/status` et `/ws/view-sync` (reprendre verbatim L4032–4115).
2. Inscrire le BP dans `app/__init__.py:_register_blueprints`.
3. Déplacer le monkey-patch `requests.sessions.Session.request` (L94–146) dans `app/services/observability.py:install_requests_instrumentation()` appelé une seule fois au début de `create_app()`.
4. Déplacer `init_weather_db`, `_init_session_tracking_db`, `_init_visits_table`, `init_all_wal` vers `app/init/db.py` ; appeler depuis `create_app()` après `_init_sqlite_wal` (déduplication).
5. Déplacer `ensure_passages_iss_json()` dans `app/bootstrap.py:start_background_threads()` (lazy — ne plus bloquer l'import).

**Critère de succès 20.2** : routes `/ws/status` et `/ws/view-sync` répondent ; aucune init DB n'est exécutée 2× au boot (vérifier les logs `[WAL]`).

#### **PASS 20.3 — Migration ciblée des 16 helpers actifs** (estimé : 1.5 jour)

Migrer un par un, par lot fonctionnel cohérent :

| Lot | Cible | Helpers concernés | BPs impactés |
| --- | --- | --- | --- |
| A | `app/services/visits.py` | `_get_visits_count`, `_increment_visits`, `_register_unique_visit_from_request`, `PAGE_PATHS` | analytics_bp, hooks |
| B | `app/services/owner_ips.py` | `_load_owner_ips`, `_is_owner_ip`, `_invalidate_owner_ips_cache`, `_OWNER_IPS_*` | analytics_bp |
| C | `app/services/visitor_score.py` | `_compute_human_score`, `_client_ip_from_request` | analytics_bp |
| D | `app/services/metrics.py` | `metrics_record_request`, `metrics_record_struct_error`, `metrics_status_fields`, `_METRICS_*`, `_HTTP_LOG_*`, `_http_request_log_allow` | hooks |
| E | `app/services/struct_log.py` | `struct_log`, `_emit_diag_json`, `system_log`, `_AstroScanJsonLogFormatter`, `_orbital_log`, `_structured_json_handler` | hooks |
| F | `app/services/tle_fetch.py` | `fetch_tle_from_celestrak`, `tle_refresh_loop`, `load_tle_cache_from_disk`, `_tle_next_sleep_seconds`, `refresh_tle_from_amsat`, `download_tle_now`, `_parse_tle_file`, `TLE_*` constantes | api_bp, satellites_bp, bootstrap |
| G | `app/services/lab_paths.py` | `LAB_UPLOADS`, `RAW_IMAGES`, etc. | lab_bp |
| H | `app/workers/{tle,lab,skyview,translate}.py` | `_start_*`, `translate_worker` | bootstrap |
| I | `app/services/seo.py` + `app/services/session_snippet.py` | `SEO_HOME_DESCRIPTION`, `_SESSION_TIME_SNIPPET` | hooks |
| J | `app/services/api_spec.py` | `API_SPEC` | system_bp (si exposé) |
| K | `app/services/satellites.py` (existe) | `_telescope_nightly_tlemcen`, `_TLE_FOR_PASSES`, `_elevation_above_observer` | telescope_bp, satellites_bp |
| L | `app/state.py` (nouveau) | `START_TIME`, `server_ready`, compteurs LLM | api_bp |

Pour chaque lot : **(1)** créer le fichier cible avec copie verbatim ; **(2)** mettre à jour les imports BPs (`from app.services.X import Y` → remplace `from station_web import Y`) ; **(3)** retirer la définition de `station_web.py` ; **(4)** smoke-test ; **(5)** commit isolé.

**Critère de succès 20.3** : `grep "from station_web import"` dans `app/` retourne **0**. `station_web.py` ne contient plus que la coquille de `app = Flask(...)` (à supprimer en PASS 20.4) ou est carrément vidé.

### 8.4 — Risques identifiés

| # | Risque | Probabilité | Impact | Mitigation |
| -: | --- | --- | --- | --- |
| 1 | Import circulaire `station_web` ↔ `app.services.tle_cache` (TLE_CACHE identity-stable) | Moyenne | App ne boot plus | Conserver l'identité du dict via `.clear() + .update()` ; tests d'identité (`id(TLE_CACHE) == id(app.services.tle_cache.TLE_CACHE)`) |
| 2 | Monkey-patch `requests.Session.request` exécuté 2× | Faible | Logs duplicate | Idempotence : sentinelle `_REQUESTS_INSTRUMENTED = True` |
| 3 | Hooks app-level dupliqués (factory + monolithe fallback) | Moyenne tant que `ASTROSCAN_FORCE_MONOLITH` existe | Compteurs visites doublés | Supprimer `ASTROSCAN_FORCE_MONOLITH` en PASS 20.1 (avec fenêtre d'observation 7 j) |
| 4 | Routes WS `/ws/*` non re-attachées au factory app | Élevée si oubli | Feature view-sync cassée | **Bloque PASS 20.2** — test E2E view-sync obligatoire avant merge |
| 5 | DB `weather_bulletins.db` initialisée 2× (chemin différent absolu vs relatif) | Faible | Schémas divergents | `WEATHER_DB_PATH` normalisé via `os.path.join(STATION, ...)` (déjà fait L172) ; auditer fichier sur disque |
| 6 | Régression silencieuse sur un helper supprimé en 20.1 | Moyenne | 500 sur route exotique | Smoke-test élargi : `curl` sur les 269 endpoints listés dans `app.url_map` |
| 7 | Perte du `server_ready` global (utilisé par `/ready`) | Faible | Probe k8s/systemd échoue | Migrer vers `app/state.py` avant suppression de la variable monolithe |

### 8.5 — Rollback strategy

- **Branche dédiée** : chaque sous-pass (20.1, 20.2, 20.3, 20.4) sur sa propre branche `migration/phase-2c-pass20-X`.
- **Tag intermédiaire** : `git tag pass19-stable` avant le démarrage de PASS 20 → rollback immédiat via `git reset --hard pass19-stable && systemctl restart astroscan`.
- **Fallback monolithe (`ASTROSCAN_FORCE_MONOLITH=1`)** conservé pendant **toute** la durée de PASS 20.1 et 20.2. Supprimé seulement en fin de 20.4 après 7 jours sans alerte.
- **Backup automatique** des `__init__.py` modifiés (suivre la convention `*.bak_pre_pass20`) — déjà appliqué dans le repo.
- **Smoke-test obligatoire après chaque sous-pass** :
  - Boot factory : `curl http://127.0.0.1:5003/health` retourne 200.
  - 5 routes critiques : `/`, `/api/iss/now`, `/api/tle/status`, `/space-weather`, `/portail`.
  - WS : `wscat /ws/status` reçoit un payload < 5 s.
  - Logs : `journalctl -u astroscan | grep "Monolith fallback loaded"` doit rester vide.

### 8.6 — Critère de succès final PASS 20

| Mesure | Cible |
| --- | ---: |
| Lignes `station_web.py` | **< 200** (ou fichier supprimé) |
| `grep "from station_web import" app/ services/` | **0** |
| Routes HTTP servies par factory | ≥ 269 (== current) |
| Routes WS servies par factory | 2 (`/ws/status`, `/ws/view-sync`) |
| `gunicorn wsgi:app --workers 4` boot time | < 3 s (vs ~5 s actuels) |
| `ASTROSCAN_FORCE_MONOLITH=1` | retiré de wsgi.py + .env.example |
| Tests E2E (visites, view-sync, TLE refresh) | 100 % pass |
| Aucune duplication de hooks (factory ne pose plus 2× les mêmes handlers) | confirmé via `app.url_map.iter_rules()` |

---

## ANNEXE — DETTE TECHNIQUE RÉSIDUELLE HORS PASS 20

À traiter en post-PASS 20 :
- **17 fichiers `*.bak*`** dans `app/blueprints/` et `app/__init__.py.bak*` — à supprimer une fois PASS 20 stabilisé (1 mois sans rollback).
- **Re-exports `# noqa: F401` dans `app/services/`** : 7 modules ont conservé l'import de `station_web` pour back-compat — devenus inutiles dès que les BPs n'importent plus depuis le monolithe.
- **`/static/css/fixes.css`** ajouté en hot-fix (status A) — auditer ce qui justifie son existence séparée de `components.css`.

---

**Fin du rapport.**
