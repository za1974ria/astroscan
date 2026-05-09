# PASS 22.1 — Weather DB helpers extraction

**Date** : 2026-05-08
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass22_1-pre` (avant) → `pass22_1-done` (après)
**Backup** : `station_web.py.bak_pass22_1`
**Commit** : `01d0a9c`

---

## Résumé

| Métrique | Avant | Après |
|---|---|---|
| `station_web.py` | 4335 lignes | **4130** lignes (**−205**) |
| `app/services/weather_db.py` | n/a | **nouveau, 295 lignes** |
| Symboles migrés | 11 | **3 constantes + 8 fonctions** |
| HTTP /portail, /observatoire, /api/health | 200 | **200** |
| HTTP /api/weather, /api/weather/history | 200 | **200** |
| Phases O-A à O-I | intactes | **intactes** |

> **Plus grosse réduction depuis PASS 19** : −205 lignes en une seule passe (le record précédent était −161 lignes au PASS 21.2). Les 8 fonctions étaient des blocs verbeux (~224 lignes au total : schéma SQL CREATE TABLE, INSERT VALUES avec 17 colonnes, cleanup loops).

---

## Audit pré-extraction

### Localisation

```
$ grep -nE "^WEATHER_DB_PATH|^WEATHER_HISTORY_DIR|^WEATHER_ARCHIVE_DIR|^def init_weather_db|^def _init_weather_history_dir|^def _cleanup_weather_history_files|^def _init_weather_archive_dir|^def _cleanup_weather_archive_files|^def save_weather_archive_json|^def save_weather_history_json|^def save_weather_bulletin" station_web.py
205:WEATHER_DB_PATH = os.path.join(STATION, "weather_bulletins.db")
206:WEATHER_HISTORY_DIR = f'{STATION}/data/weather_history'
207:WEATHER_ARCHIVE_DIR = f'{STATION}/data/weather_archive'
228:def init_weather_db():
271:def _init_weather_history_dir():
278:def _cleanup_weather_history_files():
298:def _init_weather_archive_dir():
305:def _cleanup_weather_archive_files():
325:def save_weather_archive_json(data):
347:def save_weather_history_json(data, score, status):
370:def save_weather_bulletin(data):
```

### Audit consommateurs externes

```
$ for sym in WEATHER_DB_PATH WEATHER_HISTORY_DIR WEATHER_ARCHIVE_DIR init_weather_db _init_weather_history_dir _cleanup_weather_history_files _init_weather_archive_dir _cleanup_weather_archive_files save_weather_archive_json save_weather_history_json save_weather_bulletin; do
    grep -rnE "from station_web import.*\\b$sym\\b" --include='*.py' .
  done | grep -v __pycache__ | grep -v '\.bak'
(rien)
```

**Aucun consommateur externe** via `from station_web import …`. Les 11 symboles sont **100% internes** au monolithe :
- 3 constantes utilisées par les 8 fonctions du même module
- 8 fonctions utilisées par :
  - L'init synchrone au boot : `station_web.py:454-456` appelle `init_weather_db()`, `_init_weather_history_dir()`, `_init_weather_archive_dir()`
  - Le bouclage interne : `save_weather_archive_json` appelle `_init_weather_archive_dir` + `_cleanup_weather_archive_files` ; `save_weather_history_json` appelle `_init_weather_history_dir` + `_cleanup_weather_history_files` ; `save_weather_bulletin` utilise `WEATHER_DB_PATH`

Conséquence : le shim doit ré-exporter les 11 noms pour préserver la liaison au namespace de station_web (les appels au boot et les usages internes restent fonctionnels).

### Dépendances

| Symbole | Origine | Stratégie |
|---|---|---|
| `STATION` | `app/services/station_state.py` | **import canonique direct** (pas de cycle) |
| `sqlite3`, `os`, `json` | stdlib | imports module-level |
| `datetime`, `timedelta`, `timezone` | stdlib | imports module-level |
| `compute_weather_score`, `compute_reliability`, `generate_weather_bulletin` | `services/weather_service.py` | **lazy import inside `save_weather_bulletin`** |

Le prompt insistait : « STATION must come via lazy import or as a parameter (NOT from station_web at top) ». J'ai choisi l'option canonique : `from app.services.station_state import STATION` au top-level du nouveau module — `station_state.py` n'a aucune dépendance vers station_web, donc pas de cycle au load.

---

## Procédure appliquée

### Step 1 — Pre-tag + backup

```
$ git tag pass22_1-pre
$ cp station_web.py station_web.py.bak_pass22_1
```

### Step 2 — Création de `app/services/weather_db.py` (295 lignes)

Module complet avec :

1. **Imports module-level** : `json`, `os`, `sqlite3` + `datetime`/`timedelta`/`timezone` + `STATION` (canonique).
2. **3 constantes** au top-level utilisant `STATION` (calculées au load du module — STATION est déjà résolu via `station_state`).
3. **8 fonctions** déplacées **verbatim** depuis station_web :
   - `init_weather_db()` : 41 lignes (CREATE TABLE + 2 INDEX + 3 ALTER TABLE conditionnels)
   - `_init_weather_history_dir()` : 5 lignes
   - `_cleanup_weather_history_files()` : 19 lignes (rotation 365j)
   - `_init_weather_archive_dir()` : 5 lignes
   - `_cleanup_weather_archive_files()` : 19 lignes (rotation 365j)
   - `save_weather_archive_json(data)` : 19 lignes
   - `save_weather_history_json(data, score, status)` : 22 lignes
   - `save_weather_bulletin(data)` : 80 lignes (SELECT prev + INSERT 17 colonnes + DELETE >365j) **avec lazy import** des 3 helpers `weather_service` à l'intérieur de la fonction
4. **`__all__`** explicite avec les 11 noms.

### Step 3 — Validation isolée

```
$ python3 -c "from app.services.weather_db import (
    WEATHER_DB_PATH, WEATHER_HISTORY_DIR, WEATHER_ARCHIVE_DIR,
    init_weather_db, _init_weather_history_dir, _cleanup_weather_history_files,
    _init_weather_archive_dir, _cleanup_weather_archive_files,
    save_weather_archive_json, save_weather_history_json, save_weather_bulletin
  ); print('IMPORT OK — 11 symbols available'); print('  WEATHER_DB_PATH:', WEATHER_DB_PATH)"
IMPORT OK — 11 symbols available
  WEATHER_DB_PATH: /root/astro_scan/weather_bulletins.db
```

### Step 4 — Modifications `station_web.py`

**Bloc 1** (lignes 205-207) — 3 constantes :

Remplacement direct par bloc shim qui ré-importe les 11 noms depuis `app.services.weather_db`.

**Bloc 2** (lignes 228-451 d'origine) — 8 fonctions (~224 lignes) :

Remplacement direct par commentaire pointeur :
```python
# PASS 22.1 (2026-05-08) — Les 8 fonctions weather DB ont été déplacées
# verbatim vers app/services/weather_db.py (ré-importées via le shim plus haut).
# L'init synchrone au boot est conservé : les fonctions sont fournies par le shim
# au moment où elles sont appelées (plus haut dans station_web).
init_weather_db()
_init_weather_history_dir()
_init_weather_archive_dir()
```

Les 3 appels d'init synchrone au boot sont **préservés tels quels** ; les fonctions `init_weather_db()`, `_init_weather_history_dir()`, `_init_weather_archive_dir()` sont fournies par le shim placé en amont (ligne 206 < ligne 248), donc elles sont déjà liées au namespace de station_web au moment de leur invocation.

---

## Validation des 21 checks

| # | Check | Attendu | Résultat | Verdict |
|---|---|---|---|---|
| 1 | AST parse station_web | OK | **OK** | ✓ |
| 2 | AST parse weather_db | OK | **OK** | ✓ |
| 3 | Import isolé 11 symboles | OK | **OK** | ✓ |
| 4 | `wc -l station_web.py` | (réduction significative) | **4130** (−205) | ✓ |
| 5-7 | 3 constantes disparues | 0 chacune | **0/0/0** | ✓ |
| 8-15 | 8 fonctions disparues | 0 chacune | **0/0/0/0/0/0/0/0** | ✓ |
| 16 | Shim block présent | présent | **l.206 + l.245** | ✓ |
| 17 | /portail HTTP | 200 | **200** | ✓ |
| 18 | /observatoire HTTP | 200 | **200** | ✓ |
| 19 | /api/health HTTP | 200 | **200** | ✓ |
| 20 | /api/weather HTTP | 200 | **200** | ✓ |
| 21 | /api/weather/history HTTP | 200 | **200** | ✓ |
| 22 | TLEMCEN ≥ 15 | ≥ 15 | **15** | ✓ |
| 23 | solar-system ≥ 4 | ≥ 4 | **4** | ✓ |
| 24 | sky-map-widget ≥ 4 | ≥ 4 | **4** | ✓ |
| 25 | cosmic-dashboard ≥ 11 | ≥ 11 | **11** | ✓ |
| 26 | PASS 20.1 /api/visitors/snapshot | 200 | **200** | ✓ |
| 27 | PASS 20.2 /api/iss | 200 | **200** | ✓ |
| 28 | PASS 20.2 /api/satellites/tle | 200 | **200** | ✓ |
| 29 | PASS 20.3 /lab | 200 | **200** | ✓ |
| 30 | PASS 20.3 /api/lab/images | 200 | **200** | ✓ |
| 31 | PASS 20.4 /api/version | 200 | **200** | ✓ |
| 32 | PASS 20.4 /api/modules-status | 200 | **200** | ✓ |

**Bilan** : 32 checks ✓. **Aucun rollback déclenché.**

Les checks 20-21 (`/api/weather`, `/api/weather/history`) sont les plus probants : ils exercent le blueprint `weather_bp` qui appelle indirectement les fonctions extraites (lecture SQLite, fichiers JSON dans `weather_history/`). Le 200 prouve que :
- `init_weather_db()` au boot a créé/maintenu le schéma SQLite
- `WEATHER_DB_PATH` pointe vers le bon fichier (lu par `weather_bp`)
- `WEATHER_HISTORY_DIR` est accessible (les snapshots JSON existent)

---

## Procédure de rollback (documentée même si non utilisée)

```bash
cp station_web.py.bak_pass22_1 station_web.py
rm -f app/services/weather_db.py
git reset --hard pass22_1-pre
echo "ROLLBACK COMPLETED"
```

---

## Fichiers touchés

| Fichier | Modif |
|---|---|
| `app/services/weather_db.py` | nouveau (295 lignes — 3 constantes + 8 fonctions + lazy imports + `__all__`) |
| `station_web.py` | −229 lignes (3 const + 8 def + corps), +24 lignes (shim détaillé + 3 appels init préservés) = **−205 net** |
| `station_web.py.bak_pass22_1` | nouveau (backup pré-PASS) |
| `PASS_22_1_REPORT.md` | ce rapport |

Aucun autre fichier touché : blueprints (weather_bp préservé intact), templates, static, wsgi.py, app/__init__.py, app/bootstrap.py, app/services/{visitors_helpers,tle_cache,lab_helpers,telescope_helpers,system_helpers}.py (PASS 20.x préservés), app/workers/* (PASS 21.x préservés), tests/.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass22_1-pre` | e88e479 (HEAD avant extraction) | Snapshot avant |
| `pass22_1-done` | 01d0a9c | Extraction appliquée |

```
$ git log --oneline -5
01d0a9c refactor(monolith): PASS 22.1 — extract Weather DB helpers to app/services/weather_db.py
e88e479 doc: rapport PASS 21.4 — Lab Image Collector (Last Thread Migrated)
f1a9590 refactor(monolith): PASS 21.4 — extract Lab image collector thread (FINAL thread) to app/workers/
7c04720 doc: rapport PASS 21.3 — Skyview sync thread extraction
dc5f252 refactor(monolith): PASS 21.3 — extract Skyview sync thread to app/workers/
```

---

## Phases O-A à O-I — préservation confirmée

| Phase | Marqueur | Avant PASS 22.1 | Après PASS 22.1 |
|---|---|---|---|
| O-F (Cosmic Live Dashboard) | `cosmic-dashboard` | 11 | **11** ✓ |
| O-G (Sky Map) | `sky-map-widget` | 4 | **4** ✓ |
| O-H (Solar System + Twinkle) | `solar-system` | 4 | **4** ✓ |
| Tlemcen markers | `TLEMCEN` | 15 | **15** ✓ |

Aucune régression UI.

---

## Architecture après PASS 20.x + 21.x + 22.1

`app/services/` (6 façades helpers) + `app/workers/` (4 workers) :

| Module | Type | PASS | Symboles | Lignes |
|---|---|---|---|---|
| `app/services/visitors_helpers.py` | service | 20.1 | 8 | 100 |
| `app/services/tle_cache.py` | service | 20.2 | 6 | 47 |
| `app/services/lab_helpers.py` | service | 20.3 | 8 | 95 |
| `app/services/telescope_helpers.py` | service | 20.4 | 1 | 130 |
| `app/services/system_helpers.py` | service | 20.4 | 4 | 41 |
| **`app/services/weather_db.py`** | **service** | **22.1** | **11** | **295** |
| `app/workers/__init__.py` | package init | 21.1 | — | 12 |
| `app/workers/translate_worker.py` | worker | 21.1 | 1 | 78 |
| `app/workers/tle_collector.py` | worker | 21.2 | 5 | 230 |
| `app/workers/skyview_sync.py` | worker | 21.3 | 1 | 47 |
| `app/workers/lab_image_collector.py` | worker | 21.4 | 10 | 211 |
| **Total** | — | — | **55 symboles** | **1286 lignes** |

PASS 22.x ouvre une nouvelle famille : extraction des **services métier persistants** (DB, files I/O), à distinguer des helpers stateless (PASS 20.x) et des workers (PASS 21.x).

---

## Réduction cumulée station_web.py

| Étape | Lignes | Δ vs précédent | Δ cumulé |
|---|---|---|---|
| PASS 18 (initial) | 5094 | 0 | 0 |
| PASS 19 (cleanup commented routes) | 4755 | −339 | −339 |
| PASS 20.1 (visitors) | 4714 | −41 | −380 |
| PASS 20.2 (TLE) | 4723 | +9 | −371 |
| PASS 20.3 (Lab) | 4703 | −20 | −391 |
| PASS 20.4 (Telescope/System) | 4624 | −79 | −470 |
| PASS 21.1 (translate_worker) | 4584 | −40 | −510 |
| PASS 21.2 (tle_collector) | 4423 | −161 | −671 |
| PASS 21.3 (skyview_sync) | 4420 | −3 | −674 |
| PASS 21.4 (lab_image_collector) | 4335 | −85 | −759 |
| **PASS 22.1 (weather_db)** | **4130** | **−205** | **−964** |

**−205 lignes** : PASS 22.1 est la 2ème plus grosse extraction (après PASS 19 qui était du cleanup massif de commentaires). En extraction de code actif, c'est le **record absolu** (PASS 21.2 était à −161).

Cible long-terme : ~1500 lignes. Reste **2630 lignes** à extraire (≈18.9 % du chemin restant déjà fait par les PASS post-19).

---

## Roadmap restante

| Pass | Cible | Complexité | Estimation lignes |
|---|---|---|---|
| 22.2 | Helpers analytics (`_analytics_*`) → app/services/analytics.py | simple | ~250 |
| 22.3 | Helpers APOD/Hubble/JWST/ESA fetchers (`_download_*`, `_fetch_apod_*`) → app/services/apod_fetchers.py | simple | ~300 |
| 22.4 | Helpers sondes/spacecraft (`_fetch_voyager`, `_fetch_neo`, `_fetch_solar_*`, `_fetch_mars_rover`) → app/services/space_fetchers.py | moyenne | ~250 |
| 22.5 | Helpers cache + state internes → app/services/cache_state.py | moyenne | ~200 |
| 22.6 | Init DB monolith principal (WAL, schemas archive_stellaire) → app/db/main_db.py | sensible | ~150 |
| 22.7 | Helpers MicroObs FITS (`_mo_*`) → app/services/microobs_fits.py | sensible | ~200 |

Après ces 6 passes, station_web.py estimé ~2780 lignes. Reste ~1280 lignes à extraire (helpers SGP4 + helpers misc) pour atteindre la cible 1500.
