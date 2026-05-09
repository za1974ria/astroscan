# PASS 21.2 — TLE collector thread extraction vers `app/workers/`

**Date** : 2026-05-08
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass21_2-pre` (avant) → `pass21_2-done` (après)
**Backup** : `station_web.py.bak_pass21_2`
**Commit** : `d5b2b85`

---

## Résumé

| Métrique | Avant | Après |
|---|---|---|
| `station_web.py` | 4584 lignes | **4423** lignes (**−161**) |
| `app/workers/tle_collector.py` | n/a | **nouveau, 230 lignes** |
| Fonctions migrées | 5 | **5** |
| HTTP /portail, /observatoire, /api/health | 200 | **200** |
| `/api/satellites/tle` | 200 + données TLE | **200** + TLE réels (AO-07, UO-11) |
| Phases O-A à O-I | intactes | **intactes** |

---

## Audit pré-extraction

### Localisation des 5 fonctions

```
$ grep -nE "^def download_tle_now|^def refresh_tle|^def _download_tle_catalog|^def _run_tle_download_once|^def _start_tle_collector" station_web.py
4121:def download_tle_now():
4149:def refresh_tle_from_amsat():
4258:def _download_tle_catalog():
4285:def _run_tle_download_once():
4299:def _start_tle_collector():
```

| Fonction | Lignes | Rôle |
|---|---|---|
| `download_tle_now` | 4121-4146 (28) | Téléchargement rapide ARISS au boot |
| `refresh_tle_from_amsat` | 4149-4255 (109) | Fusion AMSAT nasabare + ARISS ISS, mutation `TLE_CACHE` |
| `_download_tle_catalog` | 4258-4273 (16) | Variante simple ARISS |
| `_run_tle_download_once` | 4285-4296 (12) | Cycle complet + re-schedule Timer 6h |
| `_start_tle_collector` | 4299-4305 (7) | Point d'entrée thread daemon (sleep 60s + cycle) |
| **Total** | **~185 lignes** | — |

### Pattern leader/standby ?

```
$ grep -nE "leader|standby|_TLE_LOCK|advisory|fcntl|flock|file_lock" station_web.py | grep -i tle
(rien)
```

**Aucun pattern leader/standby détecté pour TLE.** Le seul `fcntl.flock` du fichier (l.3993) est pour le lock `aegis_collector` (autre domaine). Le thread TLE est un simple thread daemon par worker Gunicorn ; les écritures concurrentes sur `data/tle/active.tle` sont idempotentes (le contenu est identique pour tous les workers, dernière écriture gagne).

### Consommateurs

```
$ for f in download_tle_now refresh_tle_from_amsat _download_tle_catalog _run_tle_download_once _start_tle_collector; do
    grep -rnE "from station_web import.*\\b$f\\b" --include='*.py' . | grep -v __pycache__ | grep -v '\.bak'
  done
app/bootstrap.py:70:        from station_web import _start_tle_collector
```

Un seul consommateur externe : `app/bootstrap.py:70` qui importe `_start_tle_collector` pour démarrer le thread.

Côté **interne station_web** : le bloc try/except à la ligne 4296 d'origine appelle `refresh_tle_from_amsat()` au boot (init synchrone). Ce bloc reste en place ; la fonction est désormais fournie par le shim.

### Globals associés

```
$ grep -nE "^COLLECTOR_LAST_RUN|^TLE_REFRESH|^CURRENT_TLE_REFRESH|^TLE_CONSECUTIVE|^TLE_LAST_TIMEOUT|^TLE_DEFAULT_REFRESH" station_web.py
198:COLLECTOR_LAST_RUN = 0
773:TLE_REFRESH_SECONDS = 900  # legacy constant
774:TLE_DEFAULT_REFRESH_SECONDS = 900
776:CURRENT_TLE_REFRESH_SECONDS = TLE_DEFAULT_REFRESH_SECONDS
777:TLE_CONSECUTIVE_FAILURES = 0
778:TLE_LAST_TIMEOUT_LOG_TS = 0
```

**Décision** : laisser ces globals dans station_web (hors scope PASS 21.2). Ils sont mutés par d'autres helpers du monolithe (`fetch_tle_from_celestrak` et fonctions associées aux lignes 1115-1466) qui ne font pas partie du périmètre PASS 21.2. Aucune des 5 fonctions extraites ne fait `global X` sur ces noms — pas de conflit de mutation.

---

## Procédure appliquée

### Step 1 — Pre-tag + backup

```
$ git tag pass21_2-pre
$ cp station_web.py station_web.py.bak_pass21_2
-rw-rw-r-- 1 zakaria zakaria 194678 May  8 00:29 station_web.py.bak_pass21_2
```

### Step 2 — Création de `app/workers/tle_collector.py` (NEW, 230 lignes)

Module dédié regroupant les 5 fonctions déplacées **verbatim** depuis station_web.py:4121-4305, avec ces ajustements :

1. **Imports module-level minimes** : `os`, `threading`, `time`, `urllib.request`, `datetime` + `timezone`. Tous des stdlib safe — pas de cycle.
2. **Lazy imports inside chaque fonction** :
   - `from app.services.tle_cache import TLE_ACTIVE_PATH, TLE_CACHE, _parse_tle_file` (façade unifiée PASS 20.2)
   - `from station_web import HEALTH_STATE, log` (cycle-safe : appel post-bootstrap)
3. **`requests` retiré du module-level** : était importé localement dans `download_tle_now()` avec fallback `urllib.request` si ImportError. Conservation de cette logique (utile en environnement minimal).
4. **`__all__`** explicite avec les 5 noms.

Aucune modification de logique — copie verbatim.

### Step 3 — Validation isolée

```
$ python3 -c "from app.workers.tle_collector import download_tle_now, refresh_tle_from_amsat, _download_tle_catalog, _run_tle_download_once, _start_tle_collector; print('IMPORT OK — 5 symbols available')"
IMPORT OK — 5 symbols available
```

### Step 4 — Modification `station_web.py`

Bloc avant (lignes 4121-4305, ~185 lignes) :
```python
def download_tle_now():
    """Download Celestrak active TLE at startup ..."""
    ...

def refresh_tle_from_amsat():
    """Refresh TLE from AMSAT + ARISS ..."""
    ...

def _download_tle_catalog():
    """Télécharge le catalogue TLE actif ..."""
    ...

# PASS 2D Cat 2 ... (commentaire conservé)
# MIGRATED TO satellites_bp ... (commentaire conservé)

def _run_tle_download_once():
    ...

def _start_tle_collector():
    ...
```

Bloc après (~24 lignes) :
```python
# PASS 21.2 (2026-05-08) — TLE collector thread extracted to app/workers/tle_collector.py
# Shim re-exports for backward compatibility (app/bootstrap.py:70 imports
# `from station_web import _start_tle_collector` to start the thread.)
# Les 5 fonctions (~185 lignes corps) ont été déplacées verbatim avec
# lazy imports inside pour TLE_CACHE/TLE_ACTIVE_PATH/_parse_tle_file
# (depuis app.services.tle_cache PASS 20.2) et HEALTH_STATE/log
# (depuis station_web — cycle-safe).
from app.workers.tle_collector import (  # noqa: E402,F401
    download_tle_now,
    refresh_tle_from_amsat,
    _download_tle_catalog,
    _run_tle_download_once,
    _start_tle_collector,
)

# PASS 21.2 (2026-05-08) — refresh_tle_from_amsat, _download_tle_catalog,
# _run_tle_download_once, _start_tle_collector déplacés vers
# app/workers/tle_collector.py (ré-importés via le shim plus haut).
# PASS 2D Cat 2 ... (commentaire conservé)
# MIGRATED TO satellites_bp ... (commentaires conservés)
```

Le bloc try/except ligne 4308 d'origine (init synchrone `refresh_tle_from_amsat()` au boot) est conservé tel quel : la fonction est désormais fournie par le shim à la position du shim.

---

## Validation des 22 checks

| # | Check | Attendu | Résultat | Verdict |
|---|---|---|---|---|
| 1 | AST parse station_web | OK | **OK** | ✓ |
| 2 | AST parse tle_collector | OK | **OK** | ✓ |
| 3 | Import isolé 5 symboles | OK | **OK** | ✓ |
| 4 | `wc -l station_web.py` | (réduction attendue) | **4423** (−161) | ✓ |
| 5 | `^def download_tle_now` | 0 | **0** | ✓ |
| 6 | `^def refresh_tle_from_amsat` | 0 | **0** | ✓ |
| 7 | `^def _download_tle_catalog` | 0 | **0** | ✓ |
| 8 | `^def _run_tle_download_once` | 0 | **0** | ✓ |
| 9 | `^def _start_tle_collector` | 0 | **0** | ✓ |
| 10 | Shim block présent | présent | **l.4121** | ✓ |
| 11 | /portail HTTP | 200 | **200** | ✓ |
| 12 | /observatoire HTTP | 200 | **200** | ✓ |
| 13 | /api/health HTTP | 200 | **200** | ✓ |
| 14 | /api/iss HTTP | 200 | **200** | ✓ |
| 15 | /api/satellites/tle HTTP | 200 | **200** | ✓ |
| 16 | TLE_CACHE populé (TLE réels) | données | **AO-07, UO-11, …** | ✓ |
| 17 | TLEMCEN ≥ 15 | ≥ 15 | **15** | ✓ |
| 18 | solar-system ≥ 4 | ≥ 4 | **4** | ✓ |
| 19 | sky-map-widget ≥ 4 | ≥ 4 | **4** | ✓ |
| 20 | cosmic-dashboard ≥ 11 | ≥ 11 | **11** | ✓ |
| 21 | PASS 20.1 /api/visitors/snapshot | 200 | **200** | ✓ |
| 22 | PASS 20.3 /lab | 200 | **200** | ✓ |
| 23 | PASS 20.3 /api/lab/images | 200 | **200** | ✓ |
| 24 | PASS 20.4 /api/version | 200 | **200** | ✓ |
| 25 | PASS 20.4 /api/modules-status | 200 | **200** | ✓ |
| 26 | PASS 20.4 /api/ephemerides/tlemcen | 200 | **200** | ✓ |

**Bilan** : 26 checks ✓. **Aucun rollback déclenché.**

Le check #16 est particulièrement probant :

```
$ curl -s http://127.0.0.1:5003/api/satellites/tle | head -c 250
{"format":"tle","group":"active","satellites":[{"name":"AO-07","tle1":"1 07530U 74089B   26127.27544473 -.00000048  00000-0 -11946-4 0  9996","tle2":"2 07530 101.9922 140.0931 0012076 207.6155 163.8880 12.53697398355393"},{"name":"UO-11","tle1":"1 14...
```

Cela confirme :
- `refresh_tle_from_amsat()` extrait exécute correctement le merge AMSAT + ARISS
- `TLE_CACHE.update(...)` mute bien le dict shared d'`app.services.tle_cache`
- Le blueprint `satellites_bp` lit le même dict via son lazy import → données réelles servies
- L'identité du dict mutable est préservée (pattern documenté par PASS 20.2)

---

## Procédure de rollback (documentée même si non utilisée)

```bash
cp station_web.py.bak_pass21_2 station_web.py
rm -f app/workers/tle_collector.py
git reset --hard pass21_2-pre
echo "ROLLBACK COMPLETED"
```

---

## Fichiers touchés

| Fichier | Modif |
|---|---|
| `app/workers/tle_collector.py` | nouveau (230 lignes — 5 fonctions + lazy imports + `__all__`) |
| `station_web.py` | −185 lignes (5 fonctions corps) + 24 lignes (shim + commentaires) = **−161 net** |
| `station_web.py.bak_pass21_2` | nouveau (backup pré-PASS) |
| `PASS_21_2_REPORT.md` | ce rapport |

Aucun autre fichier touché : blueprints (satellites_bp, iss_bp préservés intacts via shim), templates, static, wsgi.py, app/__init__.py, app/bootstrap.py (consommateur préservé via shim), app/services/* (PASS 20.1-20.4 préservés), app/workers/translate_worker.py (PASS 21.1 préservé), tests/.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass21_2-pre` | 0773613 (HEAD avant extraction) | Snapshot avant |
| `pass21_2-done` | d5b2b85 | Extraction appliquée |

```
$ git log --oneline -5
d5b2b85 refactor(monolith): PASS 21.2 — extract TLE collector thread to app/workers/
0773613 doc: rapport PASS 21.1 — translate_worker extraction vers app/workers/
4c9299a refactor(monolith): PASS 21.1 — extract translate_worker to app/workers/
bda0320 doc: rapport PASS 20.4 — Telescope/System/Accuracy helpers extraction
b798d96 refactor(monolith): PASS 20.4 — extract telescope/system/accuracy helpers
```

---

## Phases O-A à O-I — préservation confirmée

| Phase | Marqueur | Avant PASS 21.2 | Après PASS 21.2 |
|---|---|---|---|
| O-F (Cosmic Live Dashboard) | `cosmic-dashboard` | 11 | **11** ✓ |
| O-G (Sky Map) | `sky-map-widget` | 4 | **4** ✓ |
| O-H (Solar System + Twinkle) | `solar-system` | 4 | **4** ✓ |
| Tlemcen markers | `TLEMCEN` | 15 | **15** ✓ |

Aucune régression UI.

---

## Architecture après PASS 20.1-20.4 + 21.1 + 21.2

`app/services/` (5 façades helpers) + `app/workers/` (2 workers) :

| Module | Type | PASS | Symboles |
|---|---|---|---|
| `app/services/visitors_helpers.py` | service | 20.1 | 8 |
| `app/services/tle_cache.py` | service | 20.2 | 6 |
| `app/services/lab_helpers.py` | service | 20.3 | 8 |
| `app/services/telescope_helpers.py` | service | 20.4 | 1 |
| `app/services/system_helpers.py` | service | 20.4 | 4 |
| `app/workers/__init__.py` | package init | 21.1 | — |
| `app/workers/translate_worker.py` | worker | 21.1 | 1 |
| `app/workers/tle_collector.py` | worker | 21.2 | 5 |
| **Total** | — | — | **33 symboles** |

Pattern « shim + lazy imports » désormais éprouvé sur deux workers (translate_worker simple, tle_collector multi-fonctions avec mutations cross-modules). Les workers à venir (skyview_sync, AIS subscriber, flight radar) hériteront du même squelette + spécificités (locks, websockets, etc.).

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
| **PASS 21.2 (tle_collector)** | **4423** | **−161** | **−671** |

Cible long-terme : ~1500 lignes. Reste ~2923 lignes à extraire.

PASS 21.2 est la **plus grosse extraction depuis PASS 19** (−161 lignes en une passe), grâce à 5 fonctions consolidables dans un même worker.

---

## Roadmap restante

| Pass | Cible | Complexité | Estimation lignes |
|---|---|---|---|
| 21.3 | `_start_skyview_sync()` thread (24 l) | simple | ~30 |
| 21.4 | AISStream subscriber thread | moyenne (websocket) | ~100 |
| 21.5 | Flight radar poll loop | simple | ~80 |
| 21.6 | Lab image collector (`_run_lab_image_collector_once`) | simple | ~50 |
| 21.7 | Aegis collector lock + run wrapper | sensible (fcntl.flock) | ~80 |
| 20.5 | Helpers analytics (`_analytics_*`) | simple | ~250 |
| 20.6 | Helpers APOD/Hubble fetchers (`_fetch_apod_*`, `_fetch_hubble_*`) | simple | ~300 |
| 20.7 | Helpers sondes/spacecraft (`_fetch_voyager`, `_fetch_neo`, `_fetch_solar_*`, `_fetch_mars_rover`) | moyenne | ~250 |
| 20.8 | Helpers cache + state internes | moyenne | ~200 |
| 20.9 | Init DB (WAL, schemas) → app/db/ | sensible | ~150 |
| 20.10 | Helpers MicroObs FITS (`_mo_*`) | sensible (FITS+JPG) | ~200 |

Après ces 11 passes, station_web.py estimé ~2733 lignes. Reste ~1230 lignes à extraire pour atteindre 1500 (helpers SGP4/orbital + helpers misc).
