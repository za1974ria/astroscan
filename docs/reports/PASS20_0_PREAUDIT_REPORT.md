# PASS 20.0 — PRE-AUDIT MONOLITHE `station_web.py`

**Date** : 2026-05-06
**Branche** : `migration/phase-2c`
**Tag de sauvegarde** : `v1.1-repo-clean`
**Service `astroscan`** : `active` (vérifié au démarrage et à la fin de l'audit)
**Mode** : LECTURE SEULE — aucune modification de source, aucun redémarrage, aucun `git add/commit`.
**Source de vérité** : ce rapport sera consommé par PASS 20.1 → 20.4.

---

## SECTION 1 — STATISTIQUES GLOBALES `station_web.py`

| Métrique | Valeur |
|---|---:|
| Lignes totales (`wc -l`) | **5314** |
| Lignes blanches | 697 |
| Lignes de commentaires (`^\s*#`) | 788 |
| Lignes de code (autres) | **3829** |
| Fonctions définies (`def`, tous niveaux) | **129** |
| └─ dont top-level | 116 |
| └─ dont nested (closures / fallback) | 13 |
| Classes définies (`class`) | **1** (`_AstroScanJsonLogFormatter`, L580) |
| Routes Flask `@app.route(...)` ACTIVES | **0** |
| Routes Flask `@app.route(...)` COMMENTÉES (déjà migrées) | **36** |
| Hooks Flask `@app.{before/after_request, errorhandler, context_processor}` ACTIFS | **8** |
| Routes WebSocket `@_sock.route(...)` ACTIVES (Flask-Sock) | **2** |
| Imports top-level (`^from … import` / `^import …`) | **33** |
| Imports paresseux (DANS le corps de fonctions) | **5** + nombreux dans corps |

### Top 10 plus gros blocs de code (par taille de fonction)

| Nom | L. début | L. fin | Lignes |
|---|---:|---:|---:|
| `fetch_tle_from_celestrak` | 1105 | 1443 | **339** |
| `_build_status_payload_dict` | 3758 | 3920 | 163 |
| `refresh_tle_from_amsat` | 4842 | 4948 | 107 |
| `_astroscan_struct_log_response` | 1936 | 2033 | 98 |
| `_telescope_nightly_tlemcen` | 3271 | 3367 | 97 |
| `_register_unique_visit_from_request` | 1778 | 1867 | 90 |
| `save_weather_bulletin` | 337 | 418 | 82 |
| `build_system_intelligence` | 975 | 1052 | 78 |
| `_fetch_swpc_alerts` | 4252 | 4327 | 76 |
| `_get_iss_tle_from_cache` | 2669 | 2740 | 72 |

### Imports paresseux (intra-fonction) repérés

Ils existent pour briser des cycles d'import (`station_web` ↔ `app/services/...`) :

| Ligne | Import | Contexte |
|---:|---|---|
| 169 | `from app.services.station_state import STATION` | top, mais utilisé par tous les BPs (re-export) |
| 525 | `from app.services.status_engine import _core_status_engine` | re-export |
| 782 | `from app.services.tle_cache import TLE_CACHE, TLE_CACHE_FILE` | re-export (mutable identity-stable) |
| 2666 | `from app.services.iss_live import _fetch_iss_live` | re-export |
| 3416 | `from datetime import datetime as _dt_utc` | dans bloc fetch news |
| 5184 | `from app.services.db_visitors import _get_db_visitors` | re-export |
| 4068, 4074 | `from view_sync_backend import …` ; `from flask import request` | dans `ws_view_sync` |
| 4747, 5012, 4636 | `import threading` | dans les `_start_*` workers |
| 4789 | `from app.services.ai_translate import _call_gemini` | dans `translate_worker` |

---

## SECTION 2 — INVENTAIRE DES HELPERS (top-level)

> Statuts retenus :
> - `VIVANT-EXTRAIRE` : appelé en dehors du monolithe (import/re-export). Cible `app/services/` ou `app/workers/`.
> - `VIVANT-GARDER` : utilisé uniquement à l'intérieur du monolithe par d'autres helpers vivants ou par les hooks Flask. Mais peut quand même être déplacé.
> - `MORT-CANDIDAT-SUPPRESSION` : 0 référence interne effective + 0 import externe (les références dans `backup/` sont ignorées).

Méthodologie de cross-référencement :
- `grep -rn '\bnom\b' --include="*.py" /root/astro_scan/` puis filtrage `station_web.py` + `*.bak*` + `backup/`.
- Détection des appels `from station_web import …` et `import station_web as _sw` + `_sw.<sym>`.
- Vérification des décorateurs (`@app.errorhandler`, `@app.before_request`, `@app.after_request`, `@app.context_processor`, `@_sock.route`) pour écarter les "0 ref" qui sont en fait pris par Flask via décorateur.

| Nom | L. début | Lignes | Réfs internes (monolithe) | Réfs externes (fichiers réels, hors `backup/`) | Statut |
|---|---:|---:|---:|---|---|
| `_emit_diag_json` | 100 | 14 | 11 | `app/hooks.py` | VIVANT-EXTRAIRE |
| `_requests_instrumented_request` | 116 | 28 | 1 (monkey-patch ligne 146) | — | VIVANT-GARDER (interne, side-effect) |
| `_init_sqlite_wal` | 177 | 13 | 1 (appel module L190) | — | VIVANT-GARDER (init) |
| `init_weather_db` | 195 | 41 | 1 (L421) | — | VIVANT-GARDER (init) |
| `_init_weather_history_dir` | 238 | 5 | 2 (L422, save_weather_history_json) | — | VIVANT-GARDER (init) |
| `_cleanup_weather_history_files` | 245 | 18 | 1 | — | VIVANT-GARDER (utilisé par `save_weather_history_json` mort) |
| `_init_weather_archive_dir` | 265 | 5 | 2 (L423, save_weather_archive_json) | — | VIVANT-GARDER (init) |
| `_cleanup_weather_archive_files` | 272 | 18 | 1 (par save_weather_archive_json) | — | À-RÉÉVALUER (caller mort) |
| `save_weather_archive_json` | 292 | 20 | 0 | re-impl. dans `app/services/weather_archive.py` | **MORT** |
| `save_weather_history_json` | 314 | 21 | 0 | re-impl. dans `app/services/weather_archive.py` | **MORT** |
| `save_weather_bulletin` | 337 | 82 | 0 | re-impl. dans `app/services/weather_archive.py` | **MORT** |
| `_inject_seo_site_description` | 474 | 3 | 0 (décoré `@app.context_processor`) | — | VIVANT-GARDER (hook Flask) |
| `_astroscan_404` | 494 | 7 | 0 (décoré `@app.errorhandler(404)`) | — | VIVANT-GARDER (hook Flask) |
| `_astroscan_500` | 504 | 11 | 0 (décoré `@app.errorhandler(500)`) | — | VIVANT-GARDER (hook Flask) |
| `_run_calculateur_passages_iss` | 528 | 25 | 1 (`ensure_passages_iss_json`) | — | VIVANT-GARDER (init) |
| `ensure_passages_iss_json` | 555 | 6 | 1 (appel module L563) | — | VIVANT-GARDER (init) |
| `_metrics_trim_list` | 627 | 3 | 2 (metrics_record_*) | — | VIVANT-GARDER (interne) |
| `metrics_record_request` | 632 | 11 | 1 (after_request) | `app/hooks.py` | VIVANT-EXTRAIRE |
| `metrics_record_struct_error` | 645 | 11 | 1 (`struct_log`) | — | VIVANT-GARDER (interne) |
| `metrics_status_fields` | 658 | 11 | 2 (`_build_status_payload_dict`, `_fallback_status_payload_dict`) | — | VIVANT-GARDER |
| `_http_request_log_allow` | 679 | 15 | 1 | `app/hooks.py` | VIVANT-EXTRAIRE |
| `_api_rate_limit_allow` | 700 | 26 | 0 | `lab/`, `main/` | VIVANT-EXTRAIRE |
| `struct_log` | 728 | 14 | 30 (très utilisé interne) | `app/hooks.py`, autres BPs | VIVANT-EXTRAIRE |
| `system_log` | 754 | 2 | 1 (interne) | `app/hooks.py`, autres | VIVANT-EXTRAIRE |
| `_health_log_error` | 806 | 46 | 1 (`_health_set_error`) | — | VIVANT-GARDER |
| `_health_set_error` | 853 | 3 | 4 (interne) | — | VIVANT-GARDER |
| `load_stellarium_data` | 857 | 30 | 1 (`build_system_intelligence` — lui-même non appelé) | — | À-RÉÉVALUER (chaîne d'appel orpheline) |
| `compute_stellarium_freshness` | 889 | 20 | 1 (idem) | — | À-RÉÉVALUER |
| `build_priority_object` | 911 | 62 | 1 (idem) | — | À-RÉÉVALUER |
| `build_system_intelligence` | 975 | 78 | 0 (PAS appelé en interne) | — | **MORT (HAUTE)** chaîne stellarium orpheline |
| `get_nasa_apod` | 1055 | 48 | 1 (`_build_status_payload_dict` L3867) | — | VIVANT-GARDER (chaîne /status alive) |
| `fetch_tle_from_celestrak` | 1105 | 339 | 1 (par `tle_refresh_loop`) | `app/blueprints/iss/routes.py` | VIVANT-EXTRAIRE |
| `_tle_next_sleep_seconds` | 1446 | 13 | 2 (`tle_refresh_loop`) | — | VIVANT-GARDER |
| `load_tle_cache_from_disk` | 1461 | 47 | 0 | `app/blueprints/iss/routes.py` (lazy-import) | VIVANT-EXTRAIRE |
| `tle_refresh_loop` | 1510 | 12 | 0 | `app/bootstrap.py` (lazy) | VIVANT-EXTRAIRE (worker) |
| `get_db` | 1528 | 4 | 3 (interne) | `app/blueprints/iss/routes.py` | VIVANT-EXTRAIRE |
| `_init_visits_table` | 1534 | 9 | 2 (init) | — | VIVANT-GARDER (init) |
| `_init_session_tracking_db` | 1545 | 67 | 1 (init module L1614) | — | VIVANT-GARDER (init) |
| `_get_visits_count` | 1618 | 6 | 0 | `analytics_bp` (×2) | VIVANT-EXTRAIRE |
| `_increment_visits` | 1626 | 8 | 0 | `analytics_bp` | VIVANT-EXTRAIRE |
| `_curl_get` | 1636 | 12 | 14 (interne intensif) | — (déjà dans `app/services/http_client.py`) | VIVANT-GARDER (mais doublon — dette) |
| `_curl_post` | 1650 | 16 | 1 (`_curl_post_json`) | doublon `app/services/http_client.py` | À-RÉÉVALUER |
| `_curl_post_json` | 1668 | 4 | 0 | re-impl. dans `app/services/http_client.py` | **MORT** |
| `_client_ip_from_request` | 1691 | 4 | 1 | `app/hooks.py`, `main/`, `analytics/` | VIVANT-EXTRAIRE |
| `_load_owner_ips` | 1703 | 30 | 1 (`_is_owner_ip`) | — | VIVANT-GARDER (interne) |
| `_is_owner_ip` | 1735 | 5 | 1 (`_register_unique_visit_from_request`) | — | VIVANT-GARDER |
| `_invalidate_owner_ips_cache` | 1742 | 5 | 0 | `analytics_bp` (×2) | VIVANT-EXTRAIRE |
| `_compute_human_score` | 1749 | 27 | 2 | `analytics_bp` | VIVANT-EXTRAIRE |
| `_register_unique_visit_from_request` | 1778 | 90 | 1 | `app/hooks.py`, `analytics_bp` | VIVANT-EXTRAIRE |
| `_astroscan_request_timing_start` | 1871 | 23 | 0 (décoré `@app.before_request`) | — | VIVANT-GARDER (hook) |
| `_astroscan_visitor_session_before` | 1897 | 19 | 0 (décoré `@app.before_request`) | — | VIVANT-GARDER (hook) |
| `_maybe_increment_visits` | 1919 | 14 | 0 (décoré `@app.before_request`) | — | VIVANT-GARDER (hook) |
| `_astroscan_struct_log_response` | 1936 | 98 | 0 (décoré `@app.after_request`) | — | VIVANT-EXTRAIRE (vers `app/hooks.py`) |
| `get_user_lang` | 2039 | 7 | 0 | — (uniquement `backup/`) | **MORT** |
| `_analytics_tz_for_country_code` | 2294 | 10 | 2 (interne) | — (analytics_dashboard.py a sa propre copie) | À-RÉÉVALUER |
| `_analytics_fmt_duration_sec` | 2306 | 14 | 0 | re-impl. dans `app/services/analytics_dashboard.py` | **MORT** |
| `_analytics_journey_display` | 2322 | 7 | 0 | idem | **MORT** |
| `_analytics_start_local_display` | 2331 | 16 | 0 | idem | **MORT** |
| `_analytics_time_hms_local` | 2349 | 16 | 0 | idem | **MORT** |
| `_analytics_session_classification` | 2367 | 15 | 0 | idem | **MORT** |
| `get_geo_from_ip` | 2384 | 54 | 1 (par `_register_unique_visit_from_request`) | — | VIVANT-GARDER |
| `_source_path` | 2545 | 2 | 0 (uniquement comment + alias commenté) | re-impl. dans `app/services/telescope_sources.py` | **MORT** |
| `_fetch_apod_live` | 2548 | 20 | 0 (cf commentaire L2658 : "extraits → telescope_sources.py") | re-impl. dans `app/services/telescope_sources.py` | **MORT** |
| `_fetch_hubble_archive` | 2569 | 24 | 1 (alias `_fetch_hubble_live`) | re-impl. dans `app/services/telescope_sources.py` | **MORT** |
| `_fetch_apod_archive_live` | 2597 | 22 | 0 | re-impl. dans `app/services/telescope_sources.py` | **MORT** |
| `_sync_state_read` | 2622 | 11 | 0 | `app/services/telescope_sources.py` (peut-être) | À-RÉÉVALUER |
| `_sync_state_write` | 2633 | 10 | 0 | idem | À-RÉÉVALUER |
| `_get_iss_tle_from_cache` | 2669 | 72 | 0 | — (commentaire L2741 : "moved to app/services/tle.py") | **MORT** |
| `_get_satellite_tle_by_name` | 2770 | 22 | 0 | `satellites_bp` | VIVANT-EXTRAIRE |
| `_fetch_iss_crew` | 2835 | 11 | 1 (`_get_iss_crew`) | — | VIVANT-GARDER |
| `_get_iss_crew` | 2848 | 14 | 1 (interne) | `feeds_bp` (peut-être) | VIVANT-EXTRAIRE |
| `_guess_region` | 2863 | 15 | 0 | re-impl. dans `app/services/iss_live.py` | **MORT** |
| `_mo_parse_filename` | 3142 | 13 | 1 | — | VIVANT-GARDER (chaîne `_telescope_nightly_tlemcen`) |
| `_mo_fetch_catalog_today` | 3157 | 31 | 1 | — | VIVANT-GARDER |
| `_mo_visible_tonight` | 3190 | 41 | 1 | — | VIVANT-GARDER |
| `_mo_fits_to_jpg` | 3233 | 36 | 1 | — | VIVANT-GARDER |
| `_telescope_nightly_tlemcen` | 3271 | 97 | 1 (chaîne micro-obs) | `telescope_bp` (lazy-import) | VIVANT-EXTRAIRE |
| `_fetch_voyager` | 3426 | 37 | 0 | — (uniquement `backup/`) | **MORT** |
| `_fetch_neo` | 3464 | 41 | 0 | — | **MORT** |
| `_fetch_solar_wind` | 3506 | 21 | 0 | — | **MORT** |
| `_fetch_solar_alerts` | 3528 | 25 | 0 | — | **MORT** |
| `_fetch_mars_rover` | 3554 | 28 | 0 | re-impl. `modules/sondes_module.py` | **MORT** |
| `_fetch_apod_hd` | 3583 | 28 | 0 | mention dans `apod_bp/routes.py` (à extraire — pas encore consommé) | **MORT** |
| `_db_observations_count` | 3680 | 9 | 2 (`_*_status_payload_dict`) | — | VIVANT-GARDER |
| `_fallback_status_payload_dict` | 3694 | 62 | 2 | — | VIVANT-EXTRAIRE (avec build_status) |
| `_build_status_payload_dict` | 3758 | 163 | 2 | `health_bp` (via `_sw`) | VIVANT-EXTRAIRE |
| `get_status_data` | 3923 | 17 | 1 | `health_bp` | VIVANT-EXTRAIRE |
| `validate_system_state` | 3942 | 19 | 0 | `health_bp` | VIVANT-EXTRAIRE |
| `build_status_snapshot_dict` | 3964 | 28 | 3 (incl. `ws_status`) | `health_bp` | VIVANT-EXTRAIRE |
| `ws_status` | 4038 | 10 | 0 (décoré `@_sock.route`) | — | VIVANT-EXTRAIRE (websocket Flask-Sock) |
| `ws_view_sync` | 4052 | 62 | 0 (décoré `@_sock.route`) | — | VIVANT-EXTRAIRE |
| `_fetch_hubble` | 4125 | 30 | 0 | mention dans `feeds_bp` (déjà ré-implémenté ailleurs) | **MORT** |
| `_apply_news_translations` | 4214 | 16 | 0 | re-impl. `feeds_bp/__init__.py:278` | **MORT** |
| `_fetch_swpc_alerts` | 4252 | 76 | 0 | — | **MORT** |
| `log_rejected_image` | 4378 | 13 | 0 (référence "log_rejected_image failed" est une string interne) | — | **MORT** |
| `save_normalized_metadata` | 4393 | 11 | 0 (idem string) | — | **MORT** |
| `_download_nasa_apod` | 4418 | 39 | 1 (`_run_lab_image_collector_once`) | — | VIVANT-GARDER |
| `_download_hubble_images` | 4459 | 50 | 1 | — | VIVANT-GARDER |
| `_download_jwst_images` | 4511 | 34 | 1 | — | VIVANT-GARDER |
| `_download_esa_images` | 4547 | 54 | 1 | — | VIVANT-GARDER |
| `_sync_skyview_to_lab` | 4603 | 30 | 1 (`_start_skyview_sync`) | — | VIVANT-GARDER |
| `_start_skyview_sync` | 4635 | 9 | 0 | `app/bootstrap.py` | VIVANT-EXTRAIRE (worker) |
| `_aegis_collector_acquire_lock` | 4651 | 7 | 1 | — | VIVANT-GARDER |
| `_aegis_collector_release_lock` | 4660 | 6 | 1 | — | VIVANT-GARDER |
| `_aegis_collector_can_run` | 4668 | 9 | 1 | — | VIVANT-GARDER |
| `_aegis_collector_mark_run` | 4679 | 8 | 1 | — | VIVANT-GARDER |
| `run_collector_safe` | 4689 | 17 | 2 | — | VIVANT-GARDER |
| `_run_lab_image_collector_once` | 4708 | 37 | 2 | — | VIVANT-GARDER |
| `_start_lab_image_collector` | 4747 | 7 | 0 | `app/bootstrap.py` | VIVANT-EXTRAIRE (worker) |
| `translate_worker` | 4756 | 46 | 0 | `app/bootstrap.py` | VIVANT-EXTRAIRE (worker) |
| `download_tle_now` | 4814 | 26 | 0 | — | **MORT** |
| `refresh_tle_from_amsat` | 4842 | 107 | 4 (init module L5020 + helpers TLE) | — | VIVANT-GARDER (puis EXTRAIRE) |
| `_download_tle_catalog` | 4951 | 16 | 0 | — | **MORT** |
| `_parse_tle_file` | 4969 | 19 | 4 (interne) | `satellites_bp`, `api_bp` | VIVANT-EXTRAIRE |
| `_run_tle_download_once` | 4996 | 12 | 2 | — | VIVANT-GARDER |
| `_start_tle_collector` | 5010 | 7 | 0 | `app/bootstrap.py` | VIVANT-EXTRAIRE (worker) |
| `_elevation_above_observer` | 5039 | 12 | 0 | re-impl. dans `app/blueprints/satellites/__init__.py:126` | **MORT** |
| `_astroscan_session_cookie_and_time_script` | 5216 | 31 | 0 (décoré `@app.after_request`) | — | VIVANT-EXTRAIRE (vers `app/hooks.py`) |

**Note sur la détection dynamique** : `getattr(...)`, `importlib`, `__import__`, `eval(...)` ont été cherchés dans `station_web.py`. Tous les `getattr` trouvés (L129, L590, L1789, L1944, L5227) opèrent sur des objets locaux (`resp`, `record`, `g`) — **AUCUN dispatch dynamique sur des symboles de `station_web`**. Pas de `importlib`, pas de `__import__`, pas de `eval`. → la liste de symboles morts ci-dessus n'a pas de "porte dérobée" cachée.

---

## SECTION 3 — INVENTAIRE DES ROUTES FLASK

> **Constat majeur** : `station_web.py` ne déclare plus AUCUNE route HTTP active (`@app.route(...)`). Les 36 occurrences de `@app.route` sont toutes dans des commentaires "MIGRATED TO …_bp". Ce qui reste vivant : 8 hooks et 2 endpoints WebSocket Flask-Sock.

### 3.a — Hooks Flask actifs

| Décorateur | L. | Fonction | Statut | Blueprint cible |
|---|---:|---|---|---|
| `@app.context_processor` | 474 | `_inject_seo_site_description` | MIGRATION-PRÊTE | `app/hooks.py` (déjà partiellement présent — fusionner) |
| `@app.errorhandler(404)` | 494 | `_astroscan_404` | MIGRATION-PRÊTE | `app/hooks.py` |
| `@app.errorhandler(500)` | 504 | `_astroscan_500` | MIGRATION-PRÊTE | `app/hooks.py` |
| `@app.before_request` | 1871 | `_astroscan_request_timing_start` | MIGRATION-PRÊTE | `app/hooks.py` |
| `@app.before_request` | 1897 | `_astroscan_visitor_session_before` | MIGRATION-RISQUÉE (ordre + cookies) | `app/hooks.py` |
| `@app.before_request` | 1919 | `_maybe_increment_visits` | MIGRATION-RISQUÉE (idem ordre) | `app/hooks.py` |
| `@app.after_request` | 1936 | `_astroscan_struct_log_response` | MIGRATION-RISQUÉE (98 lignes, contexte logging) | `app/hooks.py` |
| `@app.after_request` | 5216 | `_astroscan_session_cookie_and_time_script` | MIGRATION-RISQUÉE (injection HTML) | `app/hooks.py` |

> Risque d'ordre : Flask exécute les `before_request` dans l'ordre d'enregistrement. Le déplacement vers `app/hooks.py` doit garantir que `register_hooks(app)` est appelé exactement à la même phase que l'ancien import `station_web` (côté `wsgi.py`/`create_app`).

### 3.b — Endpoints WebSocket actifs (Flask-Sock, pas Flask-SocketIO)

| Décorateur | L. | Fonction | Statut | Blueprint cible |
|---|---:|---|---|---|
| `@_sock.route("/ws/status")` | 4038 | `ws_status(ws)` | MIGRATION-PRÊTE | nouveau `app/blueprints/realtime/ws.py` ou `app/ws/status.py` |
| `@_sock.route("/ws/view-sync")` | 4052 | `ws_view_sync(ws)` | MIGRATION-RISQUÉE (auth secrets.compare_digest + view_sync_backend.py) | `app/blueprints/realtime/ws.py` |

`_sock = Sock(app)` est instancié L4035 dans un bloc `try: from flask_sock import Sock` (échec silencieux si l'import manque). À reproduire à l'identique dans la nouvelle BP : `register_websockets(app)` qui crée `_sock = Sock(app)` puis applique les routes.

### 3.c — Routes commentées (déjà migrées) — pour information

36 routes `# @app.route(...)` recensées, toutes accompagnées d'un commentaire `MIGRATED TO …_bp`. Ce sont des reliques documentaires utiles pour traçabilité — à supprimer en PASS 20.4 (ménage final).

---

## SECTION 4 — SIDE-EFFECTS À L'IMPORT (`import station_web`)

Le simple import du module déclenche les actions suivantes (ordre d'exécution top-down) :

| L. | Side-effect | Risque | Destination suggérée |
|---:|---|---|---|
| 21–24 | `if __name__ == "__main__": print(...); sys.exit(1)` | NUL (garde anti-lancement direct) | conserver (ou retirer en PASS 20.4 si systemd seul) |
| 146 | `requests.sessions.Session.request = _requests_instrumented_request` (monkey-patch GLOBAL) | **HAUT** : modifie tous les appels `requests` du process | `app/bootstrap.py` (nouveau `install_requests_instrumentation()`) |
| 190 | `_init_sqlite_wal()` | MOYEN (I/O DB) | `app/bootstrap.py` ou `app/services/db_init.py` |
| 191 | `init_all_wal()` | MOYEN | idem |
| 421 | `init_weather_db()` | MOYEN | idem |
| 422 | `_init_weather_history_dir()` | FAIBLE (mkdir) | idem |
| 423 | `_init_weather_archive_dir()` | FAIBLE | idem |
| 444–446 | `try: from core import data_engine; ensure_data_core_dirs(STATION)` | FAIBLE | `app/bootstrap.py` |
| 451–456 | Lecture `STATION/.env` + injection `os.environ.setdefault` | MOYEN (env tardif) | `app/bootstrap.py` (avant `dotenv.load_dotenv` est déjà fait L448) |
| 466–470 | `app = Flask(__name__, ...)` (instance Flask MORTE depuis PASS 25.3, blueprints registry vide) | NUL | à supprimer en PASS 25.4 (déjà planifié) |
| 479 | `logging.basicConfig(...)` | MOYEN (config root logger global) | `app/bootstrap.py:setup_logging()` |
| 486–490 | `log.info("AstroScan starting ...")` | NUL | idem |
| 518–525 | `try: from core import data_engine` (doublon ligne 444) | NUL | dédupliquer |
| 563 | `ensure_passages_iss_json()` (lance subprocess `calculateur_passages.py`, timeout 120 s) | **MOYEN** (peut bloquer le boot 2 min si file absent + script lent) | `app/workers/passages_iss.py` exécuté en thread daemon |
| 566 | `os.makedirs(f'{STATION}/logs', ...)` | FAIBLE | bootstrap |
| 569–577 | `RotatingFileHandler('orbital_system.log')` + `_orbital_log` | MOYEN | bootstrap |
| 750–751 | `_structured_json_handler` + `logging.getLogger().addHandler(...)` | MOYEN | bootstrap |
| 1614 | `_init_session_tracking_db()` | MOYEN | bootstrap |
| 1615 | `_init_visits_table()` | MOYEN | bootstrap |
| 2942–2952 | `try: from skyview_module import …` avec fallback dummy fns | FAIBLE | conserver — déplacer dans `app/services/skyview.py` |
| 4032–4117 | `try: from flask_sock import Sock; _sock = Sock(app); @_sock.route(...)` | **HAUT** (instancie WS sur l'`app` mort du monolithe) | déplacer dans une BP `realtime` qui binde sur l'`app` du factory |
| 4366–4372 | `os.makedirs(RAW_IMAGES, ...)` × 5 | FAIBLE | bootstrap |
| 4807–4808 | `TLE_DIR = …` + `os.makedirs(TLE_DIR, exist_ok=True)` | FAIBLE | bootstrap |
| 5018–5026 | `try: refresh_tle_from_amsat()` + log de la taille de `active.tle` | **HAUT** : appel réseau synchrone au boot (peut prendre plusieurs s) | `app/bootstrap.py` (en thread daemon, comme `_start_tle_collector`) |
| 5260+ | `if __name__ == '__main__': … app.run(...)` | NUL — **CODE MORT** : la garde L21 fait `sys.exit(1)` avant — bloc inatteignable | suppression en PASS 20.4 |

> **Observation critique** : `bootstrap.py` lance déjà 4 workers (`_start_tle_collector`, `_start_skyview_sync`, `_start_lab_image_collector`, `translate_worker`). Le `refresh_tle_from_amsat()` synchrone L5020 est redondant avec `_start_tle_collector` qui appelle `_run_tle_download_once` 60 s après le boot. À retirer en PASS 20.2/20.3.

---

## SECTION 5 — IMPORTS EXTERNES VERS `station_web` (qui dépend de quoi ?)

> Cette section est **CRITIQUE**. Elle révèle qu'on ne peut **rien supprimer** de `station_web.py` parmi ces symboles tant que les BPs n'ont pas été refactorés pour pointer vers la cible finale (`app/services/...`).

| Fichier consommateur | L. | Symbole(s) importé(s) | Critique ? |
|---|---:|---|:---:|
| `wsgi.py` | 46, 78 | `app as _app` | **OUI** (point d'entrée gunicorn) |
| `wsgi.py` | 54 | `import station_web  # side effects required` | **OUI** |
| `app/__init__.py` | 30 | (commentaire seulement, expliquant l'ordre) | non |
| `app/hooks.py` | 38 | `SEO_HOME_DESCRIPTION` | OUI |
| `app/hooks.py` | 54 | `log` | OUI |
| `app/hooks.py` | 70 | `_emit_diag_json` | OUI |
| `app/hooks.py` | 124 | `PAGE_PATHS, _register_unique_visit_from_request` | OUI |
| `app/hooks.py` | 137 | bloc multi-symbole (timing, struct_log, hook utils) | OUI |
| `app/hooks.py` | 245 | `_SESSION_TIME_SNIPPET` | OUI |
| `app/services/tle_cache.py` | 9, 19 | doc-string mention `from station_web import TLE_CACHE` | non (commentaire) |
| `app/services/status_engine.py` | 11 | doc-string | non |
| `app/blueprints/telescope/__init__.py` | 363 | `_telescope_nightly_tlemcen` | OUI |
| `app/blueprints/feeds/__init__.py` | 456, 499 | `_fetch_iss_live` (re-export) | OUI |
| `app/blueprints/satellites/__init__.py` | 29, 72 | bloc TLE (helpers + constantes) | OUI |
| `app/blueprints/satellites/__init__.py` | 113 | `TLE_ACTIVE_PATH, _parse_tle_file` | OUI |
| `app/blueprints/satellites/__init__.py` | 146 | `_TLE_FOR_PASSES` | OUI |
| `app/bootstrap.py` | 22 | `tle_refresh_loop` (et autres workers) | **OUI** (boot threads) |
| `app/bootstrap.py` | 44 | `_start_lab_image_collector` | OUI |
| `app/bootstrap.py` | 52 | `_start_skyview_sync` | OUI |
| `app/bootstrap.py` | 60 | `translate_worker` | OUI |
| `app/bootstrap.py` | 70 | `_start_tle_collector` | OUI |
| `app/blueprints/main/__init__.py` | 95 | `_api_rate_limit_allow, _client_ip_from_request` | OUI |
| `app/blueprints/lab/__init__.py` | 51, 93, 109, 131, 138, 155, 204, 241, 269, 277, 306, 360 | constantes (`SPACE_IMAGE_DB`, `RAW_IMAGES`, `METADATA_DB`, `MAX_LAB_IMAGE_BYTES`, `LAB_UPLOADS`, `_sync_skyview_to_lab`, `_lab_last_report`) | OUI |
| `app/blueprints/iss/routes.py` | 338 | bloc `(get_db, ..., load_tle_cache_from_disk, fetch_tle_from_celestrak, ...)` | OUI |
| `app/blueprints/api/__init__.py` | 149, 172, 198, 234, 253, 263, 271 | `TLE_CACHE`, `_parse_tle_file`, `TLE_ACTIVE_PATH`, `_get_db_visitors`, `server_ready`, `list_satellites`, `get_accuracy_history`, `get_accuracy_stats` | OUI |
| `app/blueprints/analytics/__init__.py` | 31, 43, 82, 107, 131, 153, 191, 273, 291, 327, 341, 418, 503, 764 | `_get_visits_count`, `_increment_visits`, `get_global_stats`, `_get_db_visitors`, `_invalidate_owner_ips_cache`, `_compute_human_score`, `_register_unique_visit_from_request` | OUI |
| `app/blueprints/system/__init__.py` | 29, 48, 106, 113 | `import station_web as _sw` puis `_sw.<symbol>` | OUI |
| `app/blueprints/export/__init__.py` | 192 | `STATION` | OUI |
| `app/blueprints/health/__init__.py` | 54, 72, 104, 129, 150, 168, 185, 257, 267, 290, 327, 353, 360 | `STATION`, `START_TIME`, `_sw.<status helpers>` | OUI |
| `app/blueprints/research/__init__.py` | 73, 103 | `LAB_UPLOADS`, `_fetch_iss_live` | OUI |
| `tests/conftest.py` | 51, 88 | `app as flask_app` ; `import station_web` | OUI (tests) |
| `tests/smoke/test_wsgi.py` | 6, 63, 72 | `import station_web` | OUI (tests) |
| `scripts/audit_routes_get_only.py` | 45 | `from station_web import app` | non-prod |

> **Conclusion S5** : 28 fichiers BP/services/tests/wsgi consomment `station_web`. La suppression brutale d'un symbole vivant casserait la pile entière. **PASS 20.1 doit donc se limiter aux symboles MORT-CANDIDAT-SUPPRESSION** (Section 8) ; les VIVANT-EXTRAIRE attendront PASS 20.3 avec mise à jour des consommateurs.

---

## SECTION 6 — WEBSOCKET BINDINGS

**Présence détectée — contrairement à l'a-priori du prompt initial.**

`station_web.py` contient **2 endpoints WebSocket actifs**, basés sur **Flask-Sock** (`flask_sock.Sock`) — pas Flask-SocketIO.

```python
# L4032
try:
    from flask_sock import Sock
    _sock = Sock(app)

    @_sock.route("/ws/status")        # L4038 — stream JSON /status toutes les ~3 s
    def ws_status(ws): ...

    @_sock.route("/ws/view-sync")     # L4052 — sync de vue multi-écrans
    def ws_view_sync(ws):
        from view_sync_backend import (
            VIEW_SYNC_MAX_BYTES,
            get_expected_session_key,
            get_view_sync_hub,
        )
        ...
```

Détails :
- `Sock(app)` est attaché au **Flask app du monolithe** (instance "morte" depuis PASS 25.3 — voir Section 4 L466). Cela signifie que ces WS sont actuellement bindés sur l'app abandonnée et non sur le factory. **À vérifier en run-time** : si nginx route `/ws/*` vers gunicorn, l'app effectivement utilisée par gunicorn est celle de `wsgi.py:_app = create_app(...)`. Si oui, `ws_status` et `ws_view_sync` ne sont peut-être PAS servis. **Point d'investigation prioritaire avant migration**.
- `ws_view_sync` dépend de `view_sync_backend.py` (présent à la racine du repo, non inclus dans ce scan).
- Pas d'import de `flask_socketio`, pas de `socketio.emit`, pas de `@socketio.on` — **aucun Flask-SocketIO** dans le projet (le seul WebSocket externe est le client AISStream dans `app/blueprints/scan_signal/services/aisstream_subscriber.py`, comme indiqué dans le prompt).
- Compatibilité Gunicorn : le commentaire L4040–4041 mentionne que ce flux nécessite un worker compatible WebSocket (gevent/eventlet). À vérifier dans la conf systemd `astroscan.service`.

**Recommandation** : avant PASS 20.3, vérifier que les WS fonctionnent réellement en prod (`curl --include --no-buffer -H "Connection: Upgrade" -H "Upgrade: websocket" https://astroscan.space/ws/status`). Si non utilisés → suppression en PASS 20.4. Si utilisés → BP dédiée `app/blueprints/realtime/`.

---

## SECTION 7 — WORKERS / THREADS / LOOPS

### 7.a — Threads daemon démarrés (start point)

| L. | Fonction starter | Cible | Boucle interne | Périodicité | Lancé par |
|---:|---|---|---|---|---|
| 4642 | `_start_skyview_sync` (interne `loop`) | `_sync_skyview_to_lab` | `while True: ; sleep(60)` | 60 s | `app/bootstrap.py` |
| 4752 | `_start_lab_image_collector` (interne `_run`) | `_run_lab_image_collector_once` | one-shot après `sleep(60)` | une fois | `app/bootstrap.py` |
| 5015 | `_start_tle_collector` (interne `_run`) | `_run_tle_download_once` | one-shot après `sleep(60)` | une fois | `app/bootstrap.py` |
| 1510 | `tle_refresh_loop` (PAS un starter — c'est la boucle elle-même) | `fetch_tle_from_celestrak` | `while True: ; sleep(_tle_next_sleep_seconds())` | 900 s nominal, backoff exponentiel possible | `app/bootstrap.py` (lance via `Thread(target=tle_refresh_loop)`) |
| 4756 | `translate_worker` (PAS un starter) | `_call_gemini` sur observations | `while True: ; sleep(600)` | 600 s | `app/bootstrap.py` |

**Total threads daemon démarrés au boot** : 5.

### 7.b — Boucles `while True:` recensées (incl. les déjà listées)

| L. | Fonction | Mécanisme |
|---:|---|---|
| 1512 | `tle_refresh_loop` | `while True: try: fetch_tle...; sleep(...)` |
| 4043 | `ws_status` | stream WS, `while True: ws.send(...); time.sleep(3)` |
| 4088 | `ws_view_sync` | boucle d'écoute `ws.receive()` |
| 4639 | `_start_skyview_sync.loop` | `while True: _sync_skyview_to_lab(); sleep(60)` |
| 4762 | `translate_worker` | `while True: <DB scan + AI call>; sleep(600)` |

### 7.c — Locks / signal handlers / atexit

| Élément | L. | Notes |
|---|---:|---|
| `threading.Lock()` × 4 | 621, 672, 696, 1700 | `_METRICS_LOCK`, `_HTTP_LOG_LOCK`, `_API_RATE_LOCK`, `_OWNER_IPS_LOCK` |
| `fcntl.flock(...)` | 4654 | `_aegis_collector_acquire_lock` (file lock pour collector) |
| `signal.signal(...)` | — | **AUCUN** (recherché, pas trouvé) |
| `atexit.register(...)` | — | **AUCUN** |
| `asyncio.create_task(...)` | — | **AUCUN** |

> Pas de gestion de signal ni de cleanup `atexit` : la fermeture des threads est laissée à `daemon=True` + arrêt SIGKILL de gunicorn. À documenter en PASS 20.3 si on extrait les workers.

---

## SECTION 8 — CODE MORT CANDIDAT (suppression PASS 20.1)

> Critère HAUTE : 0 référence interne réelle dans `station_web.py` (les appels self-référents dans des messages de log type `"name failed: %s"` ne comptent pas) ET 0 import depuis un fichier `.py` non-`backup/` non-test, ET aucun pattern dynamique (`getattr`/`importlib`/`eval`) ne pourrait les atteindre.

### 8.a — DEAD HIGH (suppression sûre PASS 20.1)

| Nom | L. début | L. fin | Lignes | Vérifié dynamic ? | Confiance |
|---|---:|---:|---:|:---:|:---:|
| `save_weather_archive_json` | 292 | 311 | 20 | ✅ | HAUTE |
| `save_weather_history_json` | 314 | 334 | 21 | ✅ | HAUTE |
| `save_weather_bulletin` | 337 | 418 | 82 | ✅ | HAUTE |
| `get_user_lang` | 2039 | 2045 | 7 | ✅ | HAUTE |
| `_analytics_fmt_duration_sec` | 2306 | 2319 | 14 | ✅ | HAUTE |
| `_analytics_journey_display` | 2322 | 2328 | 7 | ✅ | HAUTE |
| `_analytics_start_local_display` | 2331 | 2346 | 16 | ✅ | HAUTE |
| `_analytics_time_hms_local` | 2349 | 2364 | 16 | ✅ | HAUTE |
| `_analytics_session_classification` | 2367 | 2381 | 15 | ✅ | HAUTE |
| `_source_path` | 2545 | 2546 | 2 | ✅ | HAUTE |
| `_fetch_apod_live` | 2548 | 2567 | 20 | ✅ | HAUTE |
| `_fetch_hubble_archive` | 2569 | 2592 | 24 | ✅ | HAUTE |
| `_fetch_hubble_live = _fetch_hubble_archive` (alias) | 2595 | 2595 | 1 | ✅ | HAUTE |
| `_fetch_apod_archive_live` | 2597 | 2618 | 22 | ✅ | HAUTE |
| `_get_iss_tle_from_cache` | 2669 | 2740 | 72 | ✅ | HAUTE |
| `_guess_region` | 2863 | 2877 | 15 | ✅ | HAUTE |
| `_fetch_voyager` | 3426 | 3462 | 37 | ✅ | HAUTE |
| `_fetch_neo` | 3464 | 3504 | 41 | ✅ | HAUTE |
| `_fetch_solar_wind` | 3506 | 3526 | 21 | ✅ | HAUTE |
| `_fetch_solar_alerts` | 3528 | 3552 | 25 | ✅ | HAUTE |
| `_fetch_mars_rover` | 3554 | 3581 | 28 | ✅ | HAUTE |
| `_fetch_apod_hd` | 3583 | 3610 | 28 | ✅ | HAUTE |
| `_fetch_hubble` | 4125 | 4154 | 30 | ✅ | HAUTE |
| `_apply_news_translations` | 4214 | 4229 | 16 | ✅ | HAUTE |
| `_fetch_swpc_alerts` | 4252 | 4327 | 76 | ✅ | HAUTE |
| `log_rejected_image` | 4378 | 4390 | 13 | ✅ | HAUTE |
| `save_normalized_metadata` | 4393 | 4403 | 11 | ✅ | HAUTE |
| `_curl_post_json` | 1668 | 1671 | 4 | ✅ | HAUTE |
| `download_tle_now` | 4814 | 4839 | 26 | ✅ | HAUTE |
| `_download_tle_catalog` | 4951 | 4966 | 16 | ✅ | HAUTE |
| `_elevation_above_observer` | 5039 | 5050 | 12 | ✅ | HAUTE |
| `build_system_intelligence` | 975 | 1052 | 78 | ✅ | HAUTE (chaîne stellarium orpheline — 0 caller) |

**Sous-total HAUTE confiance** : 32 entrées, **~840 lignes** de code à supprimer.

### 8.b — DEAD MEDIUM (à confirmer en PASS 20.1 par traçage des callers)

| Nom | L. | Raison du doute |
|---|---:|---|
| `_cleanup_weather_archive_files` | 272 | Caller direct = `save_weather_archive_json` (mort). Si on supprime le caller, ce helper devient 100 % orphelin. |
| `_cleanup_weather_history_files` | 245 | Idem (caller `save_weather_history_json` mort). |
| `_curl_post` | 1650 | Caller = `_curl_post_json` (mort). Doublon de `app/services/http_client.py`. |
| `load_stellarium_data` | 857 | Caller = `build_system_intelligence` (mort). |
| `compute_stellarium_freshness` | 889 | Idem. |
| `build_priority_object` | 911 | Idem. |
| `_analytics_tz_for_country_code` | 2294 | Caller = `_analytics_*` (tous morts). |
| `_sync_state_read` / `_sync_state_write` | 2622 / 2633 | 0 ref interne ; à vérifier si `telescope_sources.py` les ré-importe ou les ré-implémente. |

**Si confirmés morts** : +9 entrées, ~150 lignes.

### 8.c — Code module-level mort

| Élément | L. | Lignes | Raison |
|---|---:|---:|---|
| Bloc `if __name__ == '__main__': … app.run(...)` | 5260 | ~25 | Inatteignable : la garde L21 fait `sys.exit(1)` avant. |
| Doublon `try: from core import data_engine` | 518–525 | ~7 | Déjà présent L444–446 — duplication (le second écrase la 1re ref). |
| Constante `TLE_BACKOFF_REFRESH_SECONDS` | 767 | 1 | Marquée "legacy (non utilisé)". |
| Constante `TLE_REFRESH_SECONDS` | 765 | 1 | Marquée "legacy constant" ; toujours utilisée nulle part en interne actif. |
| 36 commentaires `# @app.route(...) # MIGRATED TO …_bp` | dispersés | ~150 | Reliques traçables — à retirer en PASS 20.4. |

---

## SECTION 9 — HELPERS VIVANTS À EXTRAIRE (PASS 20.3)

Liste des symboles **importés ailleurs** (donc non supprimables) à déplacer vers une cible canonique. La migration se fait en 2 étapes : (a) écrire le nouveau service ; (b) faire pointer tous les `from station_web import …` vers la nouvelle cible ; (c) supprimer du monolithe.

| Nom | L. | Utilisé par | Destination suggérée |
|---|---:|---|---|
| `_emit_diag_json` | 100 | `app/hooks.py` | `app/utils/diag.py` |
| `metrics_record_request`, `_metrics_trim_list`, `metrics_record_struct_error`, `metrics_status_fields` | 627–668 | `app/hooks.py`, `_build_status_payload_dict` | `app/services/metrics.py` |
| `_http_request_log_allow` | 679 | `app/hooks.py` | `app/utils/rate_limit.py` |
| `_api_rate_limit_allow` | 700 | `lab_bp`, `main_bp` | `app/utils/rate_limit.py` |
| `struct_log`, `_AstroScanJsonLogFormatter`, `system_log` | 728, 580, 754 | nombreux BPs + hooks | `app/services/structlog.py` |
| `_health_log_error`, `_health_set_error`, `HEALTH_STATE` | 806–855, 785 | interne + monitoring | `app/services/health_state.py` |
| `_inject_seo_site_description` (+ `SEO_HOME_DESCRIPTION`, `SEO_HOME_TITLE`) | 474, 435–442 | `app/hooks.py` | `app/services/seo.py` (constantes) + `app/hooks.py` |
| `_astroscan_404`, `_astroscan_500` | 494, 504 | hooks | `app/hooks.py` |
| `_astroscan_request_timing_start`, `_astroscan_visitor_session_before`, `_maybe_increment_visits`, `_astroscan_struct_log_response`, `_astroscan_session_cookie_and_time_script` | 1871, 1897, 1919, 1936, 5216 | hooks | `app/hooks.py` (fusionner) |
| `PAGE_PATHS`, `_SESSION_TIME_SNIPPET` | 1683, 5184 | `app/hooks.py` | `app/services/visitors.py` (PAGE_PATHS) ; `app/hooks.py` (SNIPPET) |
| `_register_unique_visit_from_request`, `_load_owner_ips`, `_is_owner_ip`, `_invalidate_owner_ips_cache`, `_compute_human_score`, `_get_visits_count`, `_increment_visits`, `_init_visits_table`, `_init_session_tracking_db`, `get_geo_from_ip`, `_client_ip_from_request` | 1534–1933, 2384 | `analytics_bp`, `app/hooks.py`, `main_bp` | `app/services/visitors.py` |
| `get_db` | 1528 | `iss_bp` | `app/services/db.py` (déjà existant) |
| `_curl_get` | 1636 | interne intensif | `app/services/http_client.py` (déjà existant — supprimer doublon) |
| `fetch_tle_from_celestrak`, `tle_refresh_loop`, `_tle_next_sleep_seconds`, `load_tle_cache_from_disk`, `_parse_tle_file`, `_run_tle_download_once`, `_start_tle_collector`, `_get_satellite_tle_by_name`, `refresh_tle_from_amsat` | 1105, 1446, 1461, 1510, 4969, 4996, 5010, 2770, 4842 | `iss_bp`, `satellites_bp`, `api_bp`, `bootstrap` | `app/services/tle.py` (déjà partiellement) + `app/workers/tle_collector.py` |
| `_TLE_FOR_PASSES`, `TLE_ACTIVE_PATH`, `TLE_DIR`, `TLE_SOURCE_URL`, `TLE_LOCAL_FALLBACK`, `TLE_*_SECONDS` | 5191, 4810, 4807, 763–778 | `satellites_bp`, `api_bp` | `app/services/tle_constants.py` |
| `get_nasa_apod` | 1055 | `_build_status_payload_dict` | `app/services/nasa_apod.py` |
| `_telescope_nightly_tlemcen`, `_mo_*` | 3271, 3142–3268 | `telescope_bp` | `app/services/microobservatory.py` |
| `_fetch_iss_crew`, `_get_iss_crew` | 2835, 2848 | `feeds_bp` | `app/services/iss_crew.py` |
| `_build_status_payload_dict`, `_fallback_status_payload_dict`, `build_status_snapshot_dict`, `get_status_data`, `validate_system_state`, `STATUS_OBSERVER_LABEL` | 3694–3991, 3691 | `health_bp`, `system_bp` | `app/services/status_payload.py` |
| `_db_observations_count` | 3680 | interne (status payload) | mêm fichier |
| `ws_status`, `ws_view_sync` (+ `_sock = Sock(app)`) | 4038, 4052, 4035 | (décorateur) | `app/blueprints/realtime/ws.py` (nouvelle BP) |
| `_run_lab_image_collector_once`, `_start_lab_image_collector`, `_aegis_collector_acquire_lock`, `_aegis_collector_release_lock`, `_aegis_collector_can_run`, `_aegis_collector_mark_run`, `run_collector_safe`, `_lab_last_report` | 4708, 4747, 4651–4686, 4689, 4375 | `bootstrap`, `lab_bp` | `app/workers/lab_image_collector.py` |
| `_download_nasa_apod`, `_download_hubble_images`, `_download_jwst_images`, `_download_esa_images` | 4418–4600 | `_run_lab_image_collector_once` | mêm fichier |
| `_sync_skyview_to_lab`, `_start_skyview_sync` | 4603, 4635 | `bootstrap`, `lab_bp` | `app/workers/skyview_sync.py` |
| `translate_worker` | 4756 | `bootstrap` | `app/workers/translate.py` |
| `_run_calculateur_passages_iss`, `ensure_passages_iss_json` | 528, 555 | init module | `app/workers/passages_iss_init.py` |
| `RAW_IMAGES`, `ANALYSED_IMAGES`, `METADATA_DB`, `MAX_LAB_IMAGE_BYTES`, `LAB_UPLOADS`, `SPACE_IMAGE_DB`, `LAB_LOGS_DIR`, `SKYVIEW_DIR` | 4359–4374 | `lab_bp`, `research_bp` | `app/services/lab_paths.py` |
| `WEATHER_DB_PATH`, `WEATHER_HISTORY_DIR`, `WEATHER_ARCHIVE_DIR`, `init_weather_db`, `_init_weather_*_dir`, `_cleanup_weather_*_files` | 172–289, 195 | bootstrap | `app/services/weather_db.py` (init seul) — la sauvegarde est déjà dans `app/services/weather_archive.py` |
| `_init_sqlite_wal`, `init_all_wal` (déjà ré-exporté) | 177, 84 | bootstrap | `app/services/db_init.py` |
| `STATION` (re-export) | 169 | tous BPs | déjà dans `app/services/station_state.py` — supprimer la ligne d'import du monolithe à la toute fin (PASS 20.4) |
| `START_TIME`, `server_ready` | 157, 159 | `health_bp`, `api_bp` | `app/services/runtime_state.py` |
| `_AstroScanJsonLogFormatter` (classe) + `_orbital_log` + `_structured_json_handler` | 580, 569–577, 745 | logging globale | `app/services/structlog.py` (avec setup) |
| `app` (instance Flask morte) | 466 | `wsgi.py` (legacy fallback) | **suppression PASS 25.4 / 20.4** |

> Estimation : 60+ helpers + 25 constantes/globals à extraire. Représente l'essentiel du travail PASS 20.3.

---

## SECTION 10 — DETTE TECHNIQUE RÉSIDUELLE & RECOMMANDATIONS

### 10.a — Risques identifiés (tri par criticité)

1. **Monkey-patch `requests.Session.request` (L146)** — modifie le comportement HTTP global du process. Toute extraction doit préserver l'instrumentation **avant** que tout autre module utilise `requests`. → migration en `app/bootstrap.py` AVANT tout `register_blueprints`.
2. **`_sock = Sock(app)` bindé sur l'app morte du monolithe (L4035)** — possible bug latent. Tester avant de migrer.
3. **`refresh_tle_from_amsat()` synchrone au boot (L5020)** — appel réseau bloquant ; doublon avec le worker `_start_tle_collector` qui s'exécute 60 s après. Suppression pure et simple en PASS 20.2.
4. **`ensure_passages_iss_json()` synchrone au boot (L563) avec `subprocess.run(timeout=120)`** — peut bloquer 2 minutes au démarrage si le fichier est absent. Migration en thread daemon.
5. **`logging.basicConfig(level=INFO)` au load (L479)** — configure le root logger. Si `create_app()` ré-appelle `logging.basicConfig`, le 2e appel est silencieusement ignoré (Python tolère mais la config 1re l'emporte). → contrôler l'ordre.
6. **Doublon `_curl_get` / `_curl_post`** monolithe vs `app/services/http_client.py` — risque de divergence subtile (timeout différent, headers différents). À aligner avant déduplication.
7. **`HEALTH_STATE` (L785)** est un dict global mutable lu/écrit par les workers **et** par les requêtes Flask, sans lock. Race condition possible mais peu probable (assignations atomiques sur dict en CPython). À éclairer en PASS 20.3 lors de l'extraction.
8. **Tests dépendants du monolithe** : `tests/conftest.py` et `tests/smoke/test_wsgi.py` font `import station_web`. Toute suppression brutale casse les tests — synchroniser.
9. **`if __name__ == '__main__'` dupliqué (L21 et L5260)** — la 2e occurrence est code mort (~25 lignes).
10. **Constantes legacy non utilisées** (`TLE_BACKOFF_REFRESH_SECONDS`, etc.) — bruit, suppression facile.

### 10.b — Ordre de priorité PASS 20.1 → 20.4

| Pass | Objectif | Lignes ciblées (estim.) | Risque |
|:---:|---|---:|:---:|
| **20.1** | Suppression DEAD HIGH (Section 8.a) — pure suppression de code mort, aucun consommateur externe à toucher | **~840 lignes** | FAIBLE |
| **20.2** | Suppression DEAD MEDIUM confirmé (Section 8.b) + nettoyage code mort module-level (Section 8.c : main block, doublons import, constantes legacy, partie des commentaires `# @app.route MIGRATED`) | ~200 lignes | FAIBLE |
| **20.3** | Extraction des VIVANT-EXTRAIRE par lots cohérents (Section 9) — chaque lot = 1 service + N changements de `from station_web import` dans les BPs + suppression du monolithe. **Non-monolithique** : faire au moins 6 sous-PR (visiteurs, métrics+structlog, status payload, TLE, lab/skyview, hooks). Tester à chaque sous-pass. | ~1500–2000 lignes | MOYEN |
| **20.4** | Ménage final : commentaires `MIGRATED`, instance Flask morte `app = Flask(...)`, suppression de `wsgi.py:from station_web import app as _app` (legacy fallback), retrait du fichier si vide ou réduction à un stub re-export pour `tests/conftest.py` | ~200 lignes + retrait import wsgi | MOYEN |

### 10.c — Cible réaliste après PASS 20

| Étape | Lignes restantes |
|---|---:|
| Avant (actuel) | 5314 |
| Après PASS 20.1 | ~4470 |
| Après PASS 20.2 | ~4270 |
| Après PASS 20.3 | ~1500–2000 (selon profondeur d'extraction) |
| Après PASS 20.4 | **~300–500** (ou suppression complète si tests/conftest sont migrés) |

> **Recommandation cible** : 500 lignes restantes ou moins, en gardant uniquement : la classe `_AstroScanJsonLogFormatter` si non extraite, quelques re-exports pour compat tests, et le shebang/header de fichier. La cible "0 ligne" est atteignable mais demande de réécrire `wsgi.py` pour ne plus jamais appeler `import station_web`.

### 10.d — Avertissements particuliers (pièges)

- **Attention à l'ORDRE des imports `from station_web import …`**. Le simple acte d'importer un symbole déclenche tous les side-effects (Section 4). Tant que le monolithe contient des side-effects, ne PAS supprimer `import station_web` dans `wsgi.py` avant que `app/bootstrap.py` ait pris le relais ENTIÈREMENT.
- **`_sw.<symbol>` (alias `import station_web as _sw`)** est utilisé dans `system_bp` et `health_bp`. La suppression du symbole originel sans nettoyage du `_sw.<sym>` casse à l'exécution — pas de typecheck statique pour le détecter.
- **Mutation in-place du dict `TLE_CACHE`** (commentée L780) : `.clear()` + `.update()` pour préserver l'identité. Toute extraction doit préserver cette discipline (passage par référence partagée).
- **Workers démarrés par bootstrap.py** : leur ordre de démarrage et leur tolérance aux pannes au démarrage doivent être préservés à l'identique.
- **`view_sync_backend.py`** (à la racine, hors `app/`) est importé paresseusement par `ws_view_sync` (L4070). Sa migration est indépendante et hors-scope PASS 20.

### 10.e — Conservatisme

Toute fonction marquée À-RÉÉVALUER en Section 2 (chaînes orphelines : `_curl_post`, `_cleanup_weather_*_files`, `load_stellarium_data` + chaîne stellarium, `_analytics_tz_for_country_code`, `_sync_state_*`) doit être **traitée APRÈS** suppression de leur caller mort, dans un sous-pass dédié, avec re-vérification grep. Ne jamais supprimer en chaîne dans la même opération.

### 10.f — Recommandation finale

**PASS 20.1 doit traiter UNIQUEMENT la liste 8.a (DEAD HIGH, 32 entrées, ~840 lignes).** Suppression mécanique, ré-exécution complète des smoke tests (`pytest tests/smoke/` + `python3 -m py_compile station_web.py` + `systemctl restart astroscan && curl /health`). Aucun risque pour les consommateurs externes puisque ces helpers ont 0 import depuis l'extérieur du fichier.

---

## VALIDATION FINALE — RÉSULTATS DES 4 CONTRÔLES OBLIGATOIRES

Exécutés en fin d'audit, avant remise main :

1. `git status` — 1 seul fichier nouveau (`PASS20_0_PREAUDIT_REPORT.md`)
2. `wc -l station_web.py` — 5314
3. `python3 -m py_compile station_web.py` — pass
4. `systemctl is-active astroscan` — `active`

(Voir transcript ci-dessous dans la conversation parent.)
