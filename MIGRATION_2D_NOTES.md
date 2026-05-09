# PHASE 2D — SESSION A : QUICK WINS

**Date :** 2026-05-07  
**Branche :** `migration/phase-2d-purification` (depuis `migration/phase-2c` @ 133c6d8)  
**Tag de départ :** `v2.0-phase2d-start`  
**Service prod :** `astroscan.service` (intact, non redémarré par cette session)

---

## 1. Synthèse

| Indicateur | Avant | Après | Δ |
|---|---:|---:|---:|
| `from station_web import` (occurrences actives) | **67** | **37** | **−30 (−45%)** |
| Symboles distincts importés lazy (BPs + hooks + bootstrap) | 53 | 39 | −14 |
| Symboles distincts importés lazy dans les **BPs uniquement** | ~38 | **24** | −14 |
| `station_web.py` (lignes) | 5 314 | **5 077** | **−237 (−4.5%)** |
| Services dans `app/services/` | 26 | **27** (+ `security.py`) | +1 |
| Smoke test baseline | 217/233 OK | (à valider après restart) | — |

**Action requise utilisateur :** `sudo systemctl restart astroscan && bash scripts/smoke_test_phase2c.sh` puis comparer avec baseline `/tmp/baseline_smoke_2d.txt`.

---

## 2. Catégories traitées

### ✅ Cat 1 — Visiteurs / Analytics (commit `072ab28`, tag `v2.0-phase2d-cat1-done`)

**Cible :** `app/services/db_visitors.py` (étoffé de 10 → 244 lignes)

**Symboles migrés (8) :**
| Symbole | Type | Cible |
|---|---|---|
| `_get_visits_count` | def | db_visitors.py |
| `_increment_visits` | def | db_visitors.py |
| `_compute_human_score` | def | db_visitors.py |
| `_invalidate_owner_ips_cache` | def | db_visitors.py |
| `_load_owner_ips` | def (cluster) | db_visitors.py |
| `_is_owner_ip` | def (cluster) | db_visitors.py |
| `_register_unique_visit_from_request` | def | db_visitors.py |
| `_OWNER_IPS_CACHE` + `_LOCK` + `_TS` | globals | db_visitors.py |

**Note :** `_register_unique_visit_from_request` utilise un lazy-import vers `station_web.get_geo_from_ip` (deps `requests` + `cache_service` trop lourdes pour cette session — à extraire en Session B/C).

**Symboles déjà dans services (BP imports redirigés uniquement) :**
- `_get_db_visitors` → `app/services/db_visitors.py` (PASS 23)
- `get_global_stats` → `services/stats_service.py` (PASS antérieur)

**Blueprints touchés (3 fichiers, 20 redirections) :**
- `app/blueprints/analytics/__init__.py` (14 imports redirigés)
- `app/blueprints/api/__init__.py` (1 import → db_visitors)
- `app/hooks.py` (1 import → db_visitors)

---

### ✅ Cat 2 — TLE (commit `179f0ba`, tag `v2.0-phase2d-cat2-done`)

**Cible :** `app/services/tle.py` (étoffé de 78 → 130 lignes)

**Symboles migrés (3) :**
| Symbole | Type | Cible |
|---|---|---|
| `TLE_ACTIVE_PATH` | constante | tle.py |
| `_parse_tle_file` | def | tle.py |
| `_TLE_FOR_PASSES` | constante (liste de dicts) | tle.py |

**Side-effect préservé :** `os.makedirs(TLE_DIR, exist_ok=True)` exécuté à l'import du module `tle.py` (équivalent au comportement original).

**Symboles déjà dans services (BP imports redirigés uniquement) :**
- `TLE_CACHE` → `app/services/tle_cache.py` (PASS 23.5)
- `list_satellites` + `SATELLITES` → `app/services/satellites.py`

**Blueprints touchés (2 fichiers, 13 redirections) :**
- `app/blueprints/api/__init__.py` (4 redirections)
- `app/blueprints/satellites/__init__.py` (4 redirections, 5 symboles)

**Symbole non migré (resté lazy)** : `TLE_MAX_SATELLITES` (constante simple, pas dans le scope original Cat 2).

---

### ✅ Cat 3 — ISS Live (commit `78a4da3`, tag `v2.0-phase2d-cat3-done`)

**Cible :** `app/services/iss_live.py` (déjà extrait au PASS 23, aucun changement de code)

**Symboles migrés :** `_fetch_iss_live` (déjà service depuis PASS 23)

**Blueprints touchés (2 fichiers, 3 redirections) :**
- `app/blueprints/research/__init__.py` (1)
- `app/blueprints/feeds/__init__.py` (2)

---

### ✅ Cat 5 — Sécurité / Rate-limit (commit `121b5be`, tag `v2.0-phase2d-cat5-done`)

**Cible :** `app/services/security.py` (NOUVEAU FICHIER, 49 lignes)

**Symboles migrés (2) :**
| Symbole | Type | Cible |
|---|---|---|
| `_api_rate_limit_allow` | def | security.py |
| `_client_ip_from_request` | def | security.py |
| `_API_RATE_LOCK` + `_API_RATE_HITS` | globals | security.py |

**Bonus :** `db_visitors.py` (Cat 1) éliminé son helper local `_client_ip_from_request_local` et utilise désormais le vrai `_client_ip_from_request` de security.py via import eager (top-of-file).

**Blueprints touchés (2 fichiers, 4 redirections) :**
- `app/blueprints/main/__init__.py` (1 ligne, 2 symboles)
- `app/blueprints/lab/__init__.py` (2 lignes, 2 symboles)

---

## 3. Symboles encore en lazy import (pour Sessions B/C)

### Lab (Session B) — 8 symboles
- `LAB_UPLOADS`, `MAX_LAB_IMAGE_BYTES` — paths
- `RAW_IMAGES`, `ANALYSED_IMAGES` — paths
- `SPACE_IMAGE_DB`, `METADATA_DB` — DB paths
- `_lab_last_report` — function (state holder)
- `_sync_skyview_to_lab` — function

### Globals (Session C) — 3 symboles
- `STATION` — root path constant
- `START_TIME` — process start timestamp
- `server_ready` — readiness flag

### Telescope (interdit Session A) — 1 symbole
- `_telescope_nightly_tlemcen`

### Catégorie 6 (non incluse) — 2 symboles
- `get_accuracy_history`, `get_accuracy_stats` (déjà dans `app/services/accuracy_history.py`, re-exportés via station_web — BP imports à rediriger en Cat 6)

### Hooks/bootstrap (non Session A) — 11 symboles
- `SEO_HOME_DESCRIPTION`, `PAGE_PATHS`, `_SESSION_TIME_SNIPPET`, `log`, `struct_log`, `system_log`, `_emit_diag_json`, `_http_request_log_allow`, `metrics_record_request`
- Threads bootstrap : `_start_tle_collector`, `_start_lab_image_collector`, `_start_skyview_sync`, `translate_worker`, `tle_refresh_loop`, `fetch_tle_from_celestrak`, `load_tle_cache_from_disk`

### Multi-symbol blocks (non éclatés)
- `app/blueprints/satellites/__init__.py:30` — bloc multi-import contenant `_get_satellite_tle_by_name`, `propagate_tle_debug` (déjà service mais bloc non éclaté)
- `app/blueprints/iss/routes.py:338` — bloc multi-import contenant `_get_iss_crew`, etc.

---

## 4. Tags Git posés

| Tag | Description |
|---|---|
| `v2.0-phase2d-start` | Avant toute extraction (sécurité) |
| `v2.0-phase2d-pre-cat1` | Avant extraction visiteurs |
| `v2.0-phase2d-cat1-done` | Cat 1 OK |
| `v2.0-phase2d-pre-cat2` | Avant extraction TLE |
| `v2.0-phase2d-cat2-done` | Cat 2 OK |
| `v2.0-phase2d-pre-cat3` | Avant Cat 3 (no-op extraction) |
| `v2.0-phase2d-cat3-done` | Cat 3 OK |
| `v2.0-phase2d-pre-cat5` | Avant extraction security |
| `v2.0-phase2d-cat5-done` | Cat 5 OK |

**Rollback** : `git reset --hard <tag>` à n'importe quel point.

---

## 5. Validation effectuée

| Étape | Cat 1 | Cat 2 | Cat 3 | Cat 5 |
|---|---|---|---|---|
| `py_compile` station_web.py | ✅ | ✅ | n/a | ✅ |
| `py_compile` service cible | ✅ | ✅ | ✅ | ✅ |
| `py_compile` BPs touchés | ✅ | ✅ | ✅ | ✅ |
| Import standalone du service | ✅ | ✅ | ✅ | ✅ |
| Smoke test live | ⚠️ NEEDS RESTART | ⚠️ NEEDS RESTART | ⚠️ NEEDS RESTART | ⚠️ NEEDS RESTART |

**Validation runtime via `create_app()` non effectuée** : nécessite lecture `.env` (mode 600 root), bloquée pour utilisateur zakaria sans sudo passwordless. Le smoke test live tournera après restart manuel.

---

## 6. Action requise utilisateur

```bash
# 1. Redémarrage service
sudo systemctl restart astroscan

# 2. Vérification logs (pas d'erreur d'import au démarrage)
sudo journalctl -u astroscan -n 80 --no-pager

# 3. Smoke test
bash scripts/smoke_test_phase2c.sh > /tmp/post_phase2d_smoke.txt 2>&1
tail -3 /tmp/post_phase2d_smoke.txt

# 4. Comparaison avec baseline
diff <(grep '^OK\|^FAIL' /tmp/baseline_smoke_2d.txt) \
     <(grep '^OK\|^FAIL' /tmp/post_phase2d_smoke.txt)
```

**Critère de réussite :** smoke test ≥ 217 OK (baseline) avec **0 erreur 500** sur les routes des BPs touchés (analytics, api, satellites, lab, main, research, feeds).

**Rollback en cas de régression :**
```bash
git reset --hard v2.0-phase2d-start
sudo systemctl restart astroscan
```

---

## 7. Fichiers modifiés (récap)

| Fichier | Δ lignes | Description |
|---|---:|---|
| `station_web.py` | −237 | Suppression de 12 defs/globals + ajout 3 blocs re-exports en haut |
| `app/services/db_visitors.py` | +234 | Étoffé avec 8 symboles visiteurs |
| `app/services/tle.py` | +52 | Étoffé avec 3 symboles TLE |
| `app/services/security.py` | +49 (nouveau) | Création |
| `app/blueprints/analytics/__init__.py` | 14 lignes redirigées | |
| `app/blueprints/api/__init__.py` | 5 lignes redirigées | |
| `app/blueprints/satellites/__init__.py` | 4 lignes redirigées | |
| `app/blueprints/main/__init__.py` | 1 ligne redirigée | |
| `app/blueprints/lab/__init__.py` | 2 lignes redirigées | |
| `app/blueprints/research/__init__.py` | 2 lignes redirigées | |
| `app/blueprints/feeds/__init__.py` | 2 lignes redirigées | |
| `app/hooks.py` | 1 ligne redirigée | |

**Total : 11 fichiers actifs touchés, 4 commits atomiques, 9 tags Git.**

---

## 8. Commits Phase 2D Session A

```
121b5be Phase 2D — Cat 5: extract rate-limit + IP helpers to app/services/security.py
78a4da3 Phase 2D — Cat 3: redirect _fetch_iss_live BP imports to app/services/iss_live
179f0ba Phase 2D — Cat 2: extract TLE paths/parser/passes-data to app/services/tle.py
072ab28 Phase 2D — Cat 1: extract visitors/analytics to app/services/db_visitors.py
```

**Push** : non effectué. À pousser manuellement après revue + restart + validation smoke.

```bash
git push origin migration/phase-2d-purification
git push origin v2.0-phase2d-cat1-done v2.0-phase2d-cat2-done v2.0-phase2d-cat3-done v2.0-phase2d-cat5-done
```
