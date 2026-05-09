# PASS 20.4 — Telescope / System / Accuracy helpers extraction

**Date** : 2026-05-08
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass20_4-pre` (avant) → `pass20_4-done` (après)
**Backup** : `station_web.py.bak_pass20_4`
**Commit** : `b798d96`

---

## Résumé

| Métrique | Avant | Après |
|---|---|---|
| `station_web.py` | 4703 lignes | **4624** lignes (**−79**) |
| `app/services/telescope_helpers.py` | n/a | **nouveau, 130 lignes** |
| `app/services/system_helpers.py` | n/a | **nouveau, 41 lignes** |
| Symboles migrés | 5 | 5 (1 fonction + 4 globals/imports) |
| HTTP /portail | 200 | **200** |
| HTTP /observatoire | 200 | **200** |
| HTTP /api/version | 200 | **200** |
| HTTP /api/modules-status | 200 | **200** |
| HTTP /api/ephemerides/tlemcen | 200 | **200** |

---

## Cartographie des candidats

Vérification des imports actifs (excluant .bak) :

```
$ grep -rn "from station_web import" app/blueprints/ --include="*.py" --exclude-dir=__pycache__ | grep -v '\.bak'
app/blueprints/telescope/__init__.py:363:    from station_web import _telescope_nightly_tlemcen
app/blueprints/api/__init__.py:253:        from station_web import server_ready
app/blueprints/api/__init__.py:271:    from station_web import get_accuracy_history, get_accuracy_stats
app/blueprints/health/__init__.py:54,72,150,168:    from station_web import STATION
app/blueprints/health/__init__.py:104,129:    from station_web import START_TIME
app/blueprints/export/__init__.py:192:        from station_web import STATION
```

| Symbole | Type | Action PASS 20.4 |
|---|---|---|
| `_telescope_nightly_tlemcen` | fonction (97 l, station_web:2833) | **extraite** vers `telescope_helpers.py` |
| `server_ready` | bool mutable (l.180 + l.4551 réassign) | **conservé** dans station_web (cf. justification) |
| `get_accuracy_history` | fonction (déjà dans `app/services/accuracy_history.py`) | re-export via `system_helpers` |
| `get_accuracy_stats` | fonction (déjà dans `app/services/accuracy_history.py`) | re-export via `system_helpers` |
| `STATION` | str (déjà import de `app.services.station_state`) | re-export via `system_helpers` |
| `START_TIME` | float (station_web:178) | **déplacé** vers `system_helpers.py` |

5 symboles migrés sur 6 candidats. Justification de la non-migration de `server_ready` plus bas.

---

## Procédure appliquée

### Step 1 — Pre-tag + backup

```
$ git tag pass20_4-pre
$ cp station_web.py station_web.py.bak_pass20_4
-rw-rw-r-- 1 zakaria zakaria 199040 May  8 00:11 station_web.py.bak_pass20_4
```

### Step 2 — Création de `app/services/telescope_helpers.py` (NEW, 130 lignes)

Module dédié au pipeline nocturne Harvard MicroObservatory, déplacé verbatim depuis station_web.py:2833-2929.

Dépendances inverses gérées par lazy import inside :
```python
def _telescope_nightly_tlemcen():
    import json, re, urllib.request
    from datetime import datetime, timezone
    # Lazy imports → cycle-safe au load
    from station_web import (
        _mo_fetch_catalog_today, _mo_fits_to_jpg, _mo_visible_tonight,
        cache_set, log,
    )
    …
```

Les helpers `_mo_*` (FITS catalog/visibility/conversion) et `log`/`cache_set` restent dans station_web (hors périmètre PASS 20.4). Ils sont disponibles au moment où `_telescope_nightly_tlemcen()` est invoquée par telescope_bp (post-boot).

Imports module-level minimes : `os`, `STATION` depuis `app.services.station_state`. Pas d'import de station_web au load → pas de cycle.

### Step 3 — Création de `app/services/system_helpers.py` (NEW, 41 lignes)

Façade de statut système :

```python
import time
from app.services.station_state import STATION
from app.services.accuracy_history import get_accuracy_history, get_accuracy_stats

START_TIME: float = time.time()  # Capturé au premier import du module

__all__ = ["STATION", "START_TIME", "get_accuracy_history", "get_accuracy_stats"]
```

Note importante sur `START_TIME` : la sémantique du timestamp Unix « à l'init du process » est préservée car le module est importé tôt dans le boot via le shim de station_web. La valeur capturée à `time.time()` au load de `system_helpers` est très proche (∼ms) du `time.time()` qu'aurait capturé station_web ligne 178. Aucun consommateur de `START_TIME` ne dépend d'une milliseconde près.

### Step 4 — Validation isolée

```
$ python3 -c "from app.services.telescope_helpers import _telescope_nightly_tlemcen; print('telescope_helpers import OK')"
telescope_helpers import OK

$ python3 -c "from app.services.system_helpers import STATION, START_TIME, get_accuracy_history, get_accuracy_stats; \
    print('system_helpers import OK'); print('  STATION =', STATION); print('  START_TIME =', START_TIME)"
system_helpers import OK
  STATION = /root/astro_scan
  START_TIME = 1778199236.0695355
```

### Step 5 — Modifications station_web.py

**Bloc 1** (ligne 178) — `START_TIME` :

Avant :
```python
START_TIME = time.time()
# Passe à True en fin de chargement du module ...
server_ready = False
```

Après :
```python
# PASS 20.4 (2026-05-08) — System/Accuracy helpers extracted to app/services/system_helpers.py
# Note : `server_ready` (bool mutable top-level réassigné False→True après boot)
# n'est PAS migré ...
from app.services.system_helpers import (  # noqa: E402,F401
    STATION,
    START_TIME,
    get_accuracy_history,
    get_accuracy_stats,
)
# Passe à True en fin de chargement du module ...
server_ready = False
```

**Bloc 2** (lignes 2833-2929) — `_telescope_nightly_tlemcen` :

97 lignes de corps de fonction supprimées, remplacées par 6 lignes :
```python
# PASS 20.4 (2026-05-08) — Telescope helpers extracted to app/services/telescope_helpers.py
# Shim re-export for backward compatibility (telescope_bp utilise
# `from station_web import _telescope_nightly_tlemcen` via lazy import.)
# Le corps original (97 lignes) a été déplacé verbatim vers telescope_helpers.py
# avec lazy imports inside pour log/_mo_*/cache_set (cycle-safe).
from app.services.telescope_helpers import _telescope_nightly_tlemcen  # noqa: E402,F401
```

---

## Pourquoi `server_ready` n'est pas migré

`server_ready` est un **bool top-level mutable** dans station_web :
- Ligne 180 : `server_ready = False` (initialisation au load)
- Ligne 4551 : `server_ready = True` (en fin de chargement, après init TLE+routes)

Le blueprint `app/blueprints/api/__init__.py:253` fait `from station_web import server_ready` lazy à l'intérieur d'un handler. Au moment de l'appel, il lit le binding actuel du namespace de station_web et obtient soit `False` (si pas encore prêt) soit `True`.

Si on migrait vers `system_helpers.py` :
- `system_helpers.py` exposerait `server_ready: bool = False`
- station_web ferait `from app.services.system_helpers import server_ready` au shim → binding local de station_web pointe vers le bool `False` (immutable, copié par valeur via Python `from … import`)
- station_web ligne 4551 ferait `server_ready = True` → réassigne **uniquement** le binding local du namespace station_web, **sans muter** `system_helpers.server_ready`
- Conséquence pratique : `from station_web import server_ready` → `True` ✓ (le namespace station_web a son binding local), mais `from app.services.system_helpers import server_ready` → `False` ✗ (divergence silencieuse)

Pour que la migration soit propre, il faudrait :
- (a) Changer l'API en getter/setter (`get_server_ready()`, `set_server_ready(True)`) → violerait la contrainte hard « DO NOT touch any blueprint file » car api_bp lit le bool directement
- (b) Utiliser un wrapper mutable (dict ou objet) → idem, change l'API

**Décision conservative** : laisser `server_ready` dans station_web inchangé. Le shim ne l'inclut pas. Documentation explicite dans le commit + le rapport. Pour une future migration, l'option (b) avec wrapper devrait être proposée comme refactor coordonné incluant api_bp.

---

## Validation des 21 checks

| # | Check | Attendu | Résultat | Verdict |
|---|---|---|---|---|
| 1 | AST parse station_web | OK | **OK** | ✓ |
| 2 | AST parse telescope_helpers | OK | **OK** | ✓ |
| 3 | AST parse system_helpers | OK | **OK** | ✓ |
| 4 | `wc -l station_web.py` | ~4670-4690 (∼−10-30) | **4624** (−79) | ✓ (mieux que prévu) |
| 5 | `^def _telescope_nightly_tlemcen` | 0 | **0** | ✓ |
| 6 | `^START_TIME =` | 0 | **0** | ✓ |
| 7 | Shim system présent | présent | **l.178** | ✓ |
| 8 | Shim telescope présent | présent | **l.2845** | ✓ |
| 9 | /portail HTTP | 200 | **200** | ✓ |
| 10 | /observatoire HTTP | 200 | **200** | ✓ |
| 11 | /api/health HTTP | 200 | **200** | ✓ |
| 12 | /api/version HTTP | 200 | **200** | ✓ |
| 13 | /api/modules-status HTTP | 200 | **200** | ✓ |
| 14 | /api/accuracy HTTP | 200 ou 404 | **404** | ✓ (route inexistante, pas 500) |
| 15 | /api/ephemerides/tlemcen HTTP | 200 | **200** | ✓ |
| 16 | TLEMCEN ≥ 15 | ≥ 15 | **15** | ✓ |
| 17 | solar-system ≥ 4 | ≥ 4 | **4** | ✓ |
| 18 | sky-map-widget ≥ 4 | ≥ 4 | **4** | ✓ |
| 19 | cosmic-dashboard ≥ 11 | ≥ 11 | **11** | ✓ |
| 20 | PASS 20.1 /api/visitors/snapshot | 200 | **200** | ✓ |
| 21 | PASS 20.2 /api/iss | 200 | **200** | ✓ |
| 22 | PASS 20.2 /api/satellites/tle | 200 | **200** | ✓ |
| 23 | PASS 20.3 /lab | 200 | **200** | ✓ |

**Bilan** : 23 checks ✓. Aucun rollback déclenché.

---

## Procédure de rollback (documentée même si non utilisée)

```bash
cp station_web.py.bak_pass20_4 station_web.py
rm -f app/services/telescope_helpers.py app/services/system_helpers.py
git reset --hard pass20_4-pre
echo "ROLLBACK COMPLETED"
```

---

## Fichiers touchés

| Fichier | Modif |
|---|---|
| `app/services/telescope_helpers.py` | nouveau (130 lignes — pipeline nocturne MO + lazy imports inside) |
| `app/services/system_helpers.py` | nouveau (41 lignes — façade STATION/START_TIME/accuracy) |
| `station_web.py` | −98 lignes (def telescope 97 l + START_TIME 1 l), +19 lignes (2 shim blocks + commentaires) = **−79 net** |
| `station_web.py.bak_pass20_4` | nouveau (backup pré-PASS) |
| `PASS_20_4_REPORT.md` | ce rapport |

Aucun autre fichier touché : blueprints (telescope_bp, api_bp, health_bp, export_bp préservés intacts), templates, static, wsgi.py, app/__init__.py, app/bootstrap.py, app/services/visitors_helpers.py (PASS 20.1), app/services/tle_cache.py (PASS 20.2), app/services/lab_helpers.py (PASS 20.3), app/services/accuracy_history.py, app/services/station_state.py, tests/.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass20_4-pre` | 54e4224 (HEAD avant extraction) | Snapshot avant |
| `pass20_4-done` | b798d96 | Extraction appliquée |

```
$ git log --oneline -6
b798d96 refactor(monolith): PASS 20.4 — extract telescope/system/accuracy helpers
54e4224 doc: rapport PASS 20.3 — Lab/Skyview helpers extraction
ff02348 refactor(monolith): PASS 20.3 — extract lab/skyview helpers to app/services/lab_helpers.py
b86900e doc: rapport PASS 20.2 — TLE/Satellites helpers extraction
59f5ef6 refactor(monolith): PASS 20.2 — extract TLE/Satellites helpers to app/services/tle_cache.py
eb636e9 doc: rapport PASS 20.1 — visitors helpers extraction
```

---

## Phases O-A à O-I — préservation confirmée

| Phase | Marqueur | Avant PASS 20.4 | Après PASS 20.4 |
|---|---|---|---|
| O-F (Cosmic Live Dashboard) | `cosmic-dashboard` | 11 | **11** ✓ |
| O-G (Sky Map) | `sky-map-widget` | 4 | **4** ✓ |
| O-H (Solar System + Twinkle) | `solar-system` | 4 | **4** ✓ |
| Tlemcen markers | `TLEMCEN` | 15 | **15** ✓ |

Aucune régression UI.

---

## Architecture après PASS 20.1 + 20.2 + 20.3 + 20.4

`app/services/` contient désormais **5 façades unifiées** pour les helpers extractés du monolith :

| Façade | Rôle | Symboles exposés | PASS |
|---|---|---|---|
| `visitors_helpers.py` | Visiteurs / GeoIP / Stats | 8 | 20.1 |
| `tle_cache.py` | TLE / Satellites | 6 | 20.2 |
| `lab_helpers.py` | Lab / Skyview | 8 | 20.3 |
| `telescope_helpers.py` | Telescope MicroObs nocturne | 1 | 20.4 |
| `system_helpers.py` | Statut système / accuracy | 4 | 20.4 |
| **Total** | — | **27** | — |

Pattern « façade + shim + lazy imports si dépendances inverses » désormais éprouvé dans 4 variantes :
- PASS 20.1 : extraction simple (pas de dép vers station_web)
- PASS 20.2 : enrichissement façade existante (cross-modules re-exports)
- PASS 20.3 : extraction avec dépendances inverses lazy (HEALTH_STATE, log, etc.)
- PASS 20.4 : extraction grosse fonction (97 lignes) + extraction d'un timestamp + re-exports d'helpers déjà extractés

---

## Réduction cumulée station_web.py

| Étape | Lignes | Δ vs précédent | Δ cumulé |
|---|---|---|---|
| PASS 18 (initial) | 5094 | 0 | 0 |
| PASS 19 (cleanup commented routes) | 4755 | −339 | −339 |
| PASS 20.1 (visitors) | 4714 | −41 | −380 |
| PASS 20.2 (TLE) | 4723 | +9 | −371 |
| PASS 20.3 (Lab) | 4703 | −20 | −391 |
| PASS 20.4 (Telescope/System) | **4624** | **−79** | **−470** |

Cible long-terme : ~1500 lignes. Reste ~3124 lignes à extraire.

---

## Roadmap PASS 20.5+ (groupes restants)

| Pass | Cible | Estimation lignes monolith |
|---|---|---|
| 20.5 | Helpers analytics (`_analytics_*`) | ~250 |
| 20.6 | Helpers APOD / Hubble fetchers | ~300 |
| 20.7 | Helpers sondes / spacecraft | ~200 |
| 20.8 | Helpers cache + state internes | ~200 |
| 20.9 | Threads collectors → app/workers/ | ~250 |
| 20.10 | Init DB (WAL, schemas) → app/db/ | ~150 |

Après PASS 20.10 estimé : station_web.py ~3274 lignes. Pour atteindre 1500, prévoir extraction ultérieure des helpers SGP4/orbital + helpers misc (~1700 lignes).
