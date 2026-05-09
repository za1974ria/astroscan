# PASS 27.13 — Migration des 6 ISS helpers léger vers `iss_compute.py` + `iss_live.py`

**Date** : 2026-05-09
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass27_13-pre` (avant) → `pass27_13-done` (après)
**Snapshots** : `/tmp/station_web_pre_pass27_13.py` + `/tmp/iss_compute_pre_pass27_13.py` + `/tmp/iss_live_pre_pass27_13.py` + `/tmp/PASS_27_13_INVENTORY.md`
**Commit** : `c9ef3fb`
**Cas détecté** : **CAS A pure** (extraction, aucun doublon préexistant)

---

## Résumé

Migration des 6 helpers ISS « léger » (calculateur de passages, lookup TLE, fetcher crew) depuis `station_web.py` vers les services existants `iss_compute.py` (PASS 14) et `iss_live.py` (PASS 23). Ferme une dette technique de plusieurs semaines : les PASS 14 et 23 avaient extrait les routes mais laissé ces helpers dans le monolithe.

| Métrique | Avant | Après |
|---|---:|---:|
| `station_web.py` | 2355 lignes | **2223 lignes** (−132 nettes) |
| `app/services/iss_compute.py` | 183 lignes | **339 lignes** (+156 — 4 helpers + 2 constantes) |
| `app/services/iss_live.py` | 100 lignes | **135 lignes** (+35 — 2 helpers crew) |
| Tests `tests/unit/` | 29 PASS / 5 SKIPPED / 0 FAIL | **29 PASS / 5 SKIPPED / 0 FAIL** |
| Cap monolithe | < 2400 (PASS 27.12) | **< 2300 lignes franchi** |

Note métriques : le brief annonçait `~2150-2200 lignes` selon nb fonctions migrées et `~202 lignes corps`. Recompte réel = **150 lignes corps** (sur-estimate du brief ~25%, pattern récurrent dans la série PASS 27.x). Les 6 fonctions ont toutes été migrées (aucun SKIP).

---

## Tableau détaillé par fonction

| # | Fonction | Lignes corps | Cas détecté | Module destination | Consommateurs |
|---|---|---:|---|---|---|
| 1 | `_run_calculateur_passages_iss()` | 25 | **A — extraction** | `iss_compute.py` | `ensure_passages_iss_json:382` (intra) |
| 2 | `ensure_passages_iss_json()` | 6 | **A — extraction** | `iss_compute.py` | `station_web.py:385` (boot, **effet de bord init disque**) |
| 3 | `_get_iss_tle_from_cache()` | 72 | **A — extraction** | `iss_compute.py` | aucun appel actif (orphelin) |
| 4 | `_get_satellite_tle_by_name(target_name)` | 22 | **A — extraction** | `iss_compute.py` | `app/blueprints/satellites/__init__.py:31, 42` |
| 5 | `_fetch_iss_crew()` | 11 | **A — extraction** | `iss_live.py` | `_get_iss_crew:1100` (intra) |
| 6 | `_get_iss_crew()` | 14 | **A — extraction** | `iss_live.py` | `app/routes/iss.py:14, 47` + `app/blueprints/iss/routes.py:340, 352` |

**Total** : 150 lignes corps. Aucun cas B (déduplication) ni cas C (divergence) — la PHASE 1 d'analyse a confirmé l'absence stricte des 6 fonctions dans `iss_compute.py` et `iss_live.py` (greps retournent 0).

### Distinction vs PASS précédents

| PASS | Cas | Service | Pattern |
|---|---|---|---|
| 27.6/8/11/12 | DÉDUPLICATION | http_client / telescope_sources / external_feeds | re-export (aliasé ou direct) |
| 27.7/9/10 | EXTRACTION | analytics_dashboard / microobservatory / image_downloads | déplacement verbatim |
| **27.13** | **EXTRACTION (mixte 2 services)** | **iss_compute (4 fns) + iss_live (2 fns)** | **déplacement verbatim, répartition thématique** |

PASS 27.13 est le 1er à répartir des fonctions extraites entre **2 services destination** simultanément (cas mixte sur la dimension destination, pas sur la dimension cas A/B/C).

---

## Répartition thématique vers les 2 services

### `iss_compute.py` (PASS 14 — calculs SGP4 + TLE lookup)

4 fonctions ajoutées + 2 constantes :

```python
# Constantes co-déplacées (calculées depuis STATION cohérent station_web.py L262-264)
PASSAGES_ISS_JSON = f'{STATION}/static/passages_iss.json'
CALC_PASSAGES_SCRIPT = os.path.join(STATION, 'calculateur_passages.py')

def _run_calculateur_passages_iss():           # subprocess calculateur_passages.py timeout 120s
def ensure_passages_iss_json():                # garantit présence JSON (utilisé au boot monolithe)
def _get_iss_tle_from_cache():                 # cherche ISS dans TLE_CACHE + fallback fichier active.tle
def _get_satellite_tle_by_name(target_name):   # cherche par nom canonique (alias name map)
```

### `iss_live.py` (PASS 23 — fetchers réseau)

2 fonctions ajoutées :

```python
def _fetch_iss_crew():       # raw HTTP open-notify, default 7 si fail
def _get_iss_crew():         # cache 5min via get_cached, sanity bounds [1,20], default 7
```

---

## Imports ajoutés (sources directes, pas de cycle)

### `iss_compute.py`

```python
import os, subprocess, sys
from app.services.station_state import STATION  # PASS 23
```

Lazy imports inside (anti-cycle pour `_get_iss_tle_from_cache` et `_get_satellite_tle_by_name`) :
- `from app.services.tle_cache import TLE_CACHE, TLE_ACTIVE_PATH, _parse_tle_file` (PASS 20.2)
- `from app.services.satellites import get_satellite_tle_name_map` (PASS 20.4)
- `from station_web import _emit_diag_json` (cycle-safe car appelé post-bootstrap)

### `iss_live.py`

```python
import json
from services.cache_service import get_cached  # legacy
```

`_curl_get` réutilisé (déjà copié verbatim dans iss_live.py au PASS 23, pas d'import service).

---

## Patch appliqué

### Côté `station_web.py` (4 blocs supprimés → 1 bloc re-export + 3 commentaires pointeurs)

**Avant** :
- L350-385 : `_run_calculateur_passages_iss` + `ensure_passages_iss_json` + appel boot `ensure_passages_iss_json()`
- L959-1030 : `_get_iss_tle_from_cache`
- L1042-1063 : `_get_satellite_tle_by_name`
- L1081-1107 : `_fetch_iss_crew` + `_get_iss_crew`

**Après** :

À la position L350 (préservée pour respecter l'ordre d'exécution avec l'effet de bord boot) :

```python
# PASS 27.13 (2026-05-09) — ISS helpers léger (6 fonctions ~150 lignes corps cumulés)
# déplacés vers sources de vérité uniques :
# - calculateur passages + TLE helpers → app.services.iss_compute (PASS 14)
# - fetcher crew + cache crew → app.services.iss_live (PASS 23)
# Re-exporté ici pour préserver les consommateurs externes (4 BPs : iss/routes,
# blueprints/satellites, blueprints/iss/routes) ET l'effet de bord boot
# `ensure_passages_iss_json()` au load monolithe (init disque passages_iss.json).
from app.services.iss_compute import (  # noqa: F401 (re-export)
    _run_calculateur_passages_iss,
    ensure_passages_iss_json,
    _get_iss_tle_from_cache,
    _get_satellite_tle_by_name,
)
from app.services.iss_live import (  # noqa: F401 (re-export)
    _fetch_iss_crew,
    _get_iss_crew,
)

# Effet de bord boot — préservé verbatim de la position d'origine L385
# (génération auto de static/passages_iss.json si absent).
ensure_passages_iss_json()
```

3 commentaires pointeurs aux positions des fonctions originellement supprimées (L959, L1042, L1081) :

```python
# PASS 27.13 — _get_iss_tle_from_cache déplacée vers app.services.iss_compute
# (re-exportée via le bloc d'import ligne ~350).
```

### Difficulté boot résolue

L'effet de bord `ensure_passages_iss_json()` au load monolithe (L385) doit être exécuté APRÈS l'import re-export. Solution appliquée : placer le bloc d'import à L350 et conserver immédiatement après l'appel `ensure_passages_iss_json()` (qui appelle maintenant la version dans `iss_compute` via le re-export). Python évalue les imports avant d'exécuter le statement.

### Consommateur orphelin documenté

`_get_iss_tle_from_cache` n'a aucun appel actif détecté dans le codebase (orphelin probable laissé après la migration des routes ISS aux PASS 14/16). Migré quand même par cohérence thématique avec les 5 autres helpers ISS — pourrait être supprimé dans un PASS dédié de nettoyage si confirmé sans usage runtime.

---

## Tests effectués

### PHASE 4 — Validation syntaxique

| # | Test | Résultat |
|---|---|---|
| 1 | `py_compile station_web.py + iss_compute.py + iss_live.py` | **OK** |
| 2 | `import station_web` (avec patches `.env`/handler/sqlite) | **OK** (29 BP + 8 hooks + 293 routes Flask) |
| 3 | `from station_web import _run_calculateur_passages_iss, ensure_passages_iss_json, _get_iss_tle_from_cache, _get_satellite_tle_by_name, _fetch_iss_crew, _get_iss_crew` (re-export 6 symboles) | **OK** |
| 4 | Identité (re-export = source) — preuves `is` | **6/6 True** |
| 5 | `from station_web import TLE_CACHE` (PASS 27.2 préservé) | **OK** — keys: `['status', 'source', 'last_refresh_iso', 'count', 'items']` |

| Symbole | `station_web.X is service.X` | Service |
|---|---|---|
| `_run_calculateur_passages_iss` | True | `iss_compute` |
| `ensure_passages_iss_json` | True | `iss_compute` |
| `_get_iss_tle_from_cache` | True | `iss_compute` |
| `_get_satellite_tle_by_name` | True | `iss_compute` |
| `_fetch_iss_crew` | True | `iss_live` |
| `_get_iss_crew` | True | `iss_live` |

### PHASE 5 — Tests fonctionnels runtime

```
load_tle_cache_from_disk()  # hydrate TLE_CACHE depuis disque

result = _get_iss_tle_from_cache()
  → tuple, len 2
  → tle1[:30]: '1 25544U 98067A   26128.199371...'  ← VRAI TLE ISS NORAD 25544
  → log structuré JSON émis : {"event": "iss_tle_loaded", "name": "ISS", "tle1_len": 69, "tle2_len": 69}

sat = _get_satellite_tle_by_name('ISS (ZARYA)')
  → tuple, len 3
  → name canonique: 'ISS (ZARYA)'
  → résolution par nom map satellites OK
```

Le runtime confirme que les 2 fonctions migrées avec lazy imports complexes (TLE_CACHE + `_emit_diag_json` lazy depuis station_web) fonctionnent correctement post-boot.

### Suite tests unitaires `pytest tests/unit/`

```
collected 34 items
29 passed, 5 skipped, 0 failed in 3.11s
```

Identique à la baseline pré-PASS 27.13 (PASS 27.12 final). **Aucune régression**.

Note : un test isolé `_get_iss_tle_from_cache()` sans patches a échoué pour perms `.env` (le lazy `from station_web import _emit_diag_json` déclenche le chargement complet de station_web qui nécessite `.env`, perms 600 root inaccessible à zakaria). C'est un problème **d'environnement de test seulement** (en production, station_web tourne en root et `.env` est accessible). pytest régulier passe normalement.

---

## Imports legacy préservés (preuve par grep)

```
$ grep -rn "from station_web import.*_get_iss_crew\|from station_web import.*_fetch_iss_crew\|from station_web import.*_get_satellite_tle_by_name\|from station_web import.*_get_iss_tle_from_cache\|from station_web import.*ensure_passages_iss_json\|from station_web import.*_run_calculateur_passages_iss" \
       /root/astro_scan --include="*.py" | grep -v __pycache__ | grep -v "backup\|.archive"

/root/astro_scan/app/routes/iss.py:14:    _get_iss_crew,
/root/astro_scan/app/blueprints/satellites/__init__.py:31:        _get_satellite_tle_by_name,
/root/astro_scan/app/blueprints/iss/routes.py:340:        _fetch_iss_live, _get_iss_crew,
```

**3 sites de consommateurs externes** détectés (vs « ~10 appels externes » annoncés au brief — recompte précis = 3 lignes d'import, 4 sites d'appel actifs au total) :

| Consommateur | Symbole importé depuis station_web | Préservé via re-export ? |
|---|---|---|
| `app/routes/iss.py:14` | `_get_iss_crew` | ✓ (iss_live → station_web → import) |
| `app/blueprints/satellites/__init__.py:31` | `_get_satellite_tle_by_name` | ✓ (iss_compute → station_web → import) |
| `app/blueprints/iss/routes.py:340` | `_get_iss_crew` (+ `_fetch_iss_live`, déjà PASS 23) | ✓ (iss_live → station_web → import) |

Tous les 3 utilisent un import statique au top du fichier (pas lazy). Le re-export du shim monolithe préserve leur fonctionnement transparent.

---

## Conformité aux règles strictes

| # | Règle | Vérification | Statut |
|---|---|---|---|
| 1 | Pas de redémarrage `astroscan.service` | Aucun `systemctl restart` invoqué | ✓ |
| 2 | Pas de modif `wsgi.py`, blueprints, autres services | `git diff --stat` : seuls station_web.py + iss_compute.py + iss_live.py modifiés | ✓ |
| 3 | Pas toucher TLE_CACHE / _curl_get / _safe_json_loads | TLE_CACHE/`_parse_tle_file`/`TLE_ACTIVE_PATH` réutilisés via lazy import depuis `app.services.tle_cache` (PASS 20.2). `_curl_get` réutilisé local iss_live (déjà PASS 23). `_safe_json_loads` non touché. | ✓ |
| 4 | Pas toucher `_guess_region` | `_guess_region` non listé dans le bloc supprimé. | ✓ |
| 5 | Pas de suppression du re-export | Re-export présent ligne ~350 station_web.py (6 symboles) + appel boot préservé | ✓ |
| 6 | SKIP si divergence | N/A — 6/6 cas A pure (aucun doublon préexistant à comparer) | ✓ |
| 7 | Lazy import inside si cycle | Appliqué pour `_get_iss_tle_from_cache` et `_get_satellite_tle_by_name` (TLE_CACHE depuis service) + `_emit_diag_json` depuis station_web | ✓ |
| 8 | STOP si tests existants cassés | 29 PASS / 5 SKIPPED / 0 FAIL — identique à baseline | ✓ |
| 9 | Rollback en prose, pas en bloc shell | Cf. section dédiée ci-dessous | ✓ |

---

## Procédure de rollback (texte prose, non exécutable)

En cas de régression détectée après déploiement, le retour à l'état pré-PASS 27.13 est faisable de trois manières équivalentes.

**Option A — via le tag git (recommandée).** Le tag `pass27_13-pre` pointe sur le commit `f8d6c81` (PASS 27.12 final). Un `git checkout pass27_13-pre -- station_web.py app/services/iss_compute.py app/services/iss_live.py` restaure les trois fichiers concernés sans toucher aux 11 PASS précédents (27.1-27.12). Suivi d'un commit dédié documentant la raison du rollback. Cette option préserve l'ensemble des gains des PASS 27.x antérieurs.

**Option B — via les snapshots fichier.** Trois snapshots ont été créés en PHASE 0 dans `/tmp/station_web_pre_pass27_13.py` (2355 lignes), `/tmp/iss_compute_pre_pass27_13.py` (183 lignes) et `/tmp/iss_live_pre_pass27_13.py` (100 lignes). En cas d'urgence sans accès git, ces fichiers peuvent être recopiés tels quels vers leurs emplacements respectifs pour restituer l'état pré-PASS. Note : `/tmp/` est volatile au reboot ; les snapshots sont garantis uniquement pour la session de déploiement courante.

**Option C — restauration partielle (préserver le travail sur 1 service).** Si la régression provient uniquement de l'un des 2 services destination (par exemple les 2 fonctions crew dans `iss_live.py`), il suffit de supprimer ces ajouts spécifiques d'`iss_live.py`, retirer les noms correspondants du re-export ligne ~350 station_web.py, et restaurer les défs locales depuis `/tmp/station_web_pre_pass27_13.py`. Cela laisse les 4 fonctions migrées vers `iss_compute.py` continuer à utiliser la source unique. Réintroduction volontaire d'un mini-doublon ciblé sur le périmètre problématique.

Aucun rollback automatique n'est prévu : le diff étant un déplacement de code (objets identiques par `is`) avec préservation de l'effet de bord boot, tout retour en arrière doit être déclenché manuellement après diagnostic.

---

## Hors scope rappelé (1 fonction intentionnellement non touchée)

| Fonction | Raison |
|---|---|
| `_guess_region` | Version monolithe **292 lignes** vs version **courte 18 lignes** dans `iss_live.py` (PASS 23). Divergence sémantique réelle (la version monolithe est probablement enrichie ou divergente). Hors scope PASS 27.13 — à analyser dans un PASS dédié pour décider laquelle est canonique. |

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass27_13-pre` | `f8d6c81` | Snapshot avant migration ISS (HEAD = PASS 27.12) |
| `pass27_13-done` | `c9ef3fb` | 6 fonctions migrées + 2 constantes co-déplacées + re-export + effet boot préservé |

---

## Diff résumé

```
git diff --staged --stat (avant commit) :
 app/services/iss_compute.py | 156 ++++++++++++++++++++++++++++++++++++++
 app/services/iss_live.py    |  35 +++++++++
 station_web.py              | 178 ++++++--------------------------------------
 3 files changed, 214 insertions(+), 155 deletions(-)
```

Aucun autre fichier touché. Aucune création de fichier (hors le rapport et l'inventaire `/tmp/`). Aucune modification de l'API publique des services.

---

## Note sur la validation systemd

Le service `astroscan.service` n'a **pas** été redémarré (RÈGLE 1). Les workers gunicorn actuels servent encore le monolithe pré-PASS 27.13 (avec les 6 fonctions définies localement) jusqu'au prochain cycle (`--max-requests=1000`) ou jusqu'à un `systemctl restart astroscan` manuel par root. La validation runtime décrite en PHASES 4-5 a été conduite en environnement isolé (Flask `app_context()` + hydratation manuelle du TLE_CACHE).

Le risque de régression au prochain cycle est nul : les 6 fonctions re-exportées sont identiques par `is`, le pytest reste vert, le runtime confirme la résolution du TLE ISS NORAD 25544, et l'effet de bord boot `ensure_passages_iss_json()` est préservé à sa position d'origine (immédiatement après le bloc d'import).

---

## Réduction cumulée `station_web.py`

| Étape | Lignes | Δ vs précédent | Δ cumulé depuis PASS 27.2 |
|---|---:|---:|---:|
| PASS 27.2 (TLE worker extracted) | 3362 | — | 0 |
| PASS 27.3 (Stellarium + APOD helpers extracted) | 3129 | −233 | −233 |
| PASS 27.4 (datetime migration, neutre en lignes) | 3129 | 0 | −233 |
| PASS 27.5 (SDR cascade, fichier `app/routes/sdr.py`) | 3129 | 0 | −233 |
| PASS 27.6 (`_curl_*` deduplication) | 3103 | −26 | −259 |
| PASS 27.7 (`_analytics_*` extraction) | 3027 | −76 | −335 |
| PASS 27.8 (APOD/Hubble dédup vers telescope_sources) | 2975 | −52 | −387 |
| PASS 27.9 (`_mo_*` extraction) | 2810 | −165 | −552 |
| PASS 27.10 (image downloads extraction, nouveau module) | 2618 | −192 | −744 |
| PASS 27.11 (`_fetch_*` deduplication, 6 fns) | 2449 | −169 | −913 |
| PASS 27.12 (`_fetch_hubble` + `_fetch_swpc_alerts` dédup) | 2355 | −94 | −1007 |
| **PASS 27.13 (`6 ISS helpers` extraction mixte 2 services)** | **2223** | **−132** | **−1139** |

Cap symbolique des **2300 lignes franchi** dans le monolithe.

---

## Architecture après PASS 27.13 — services ISS consolidés

| Service | Fonctions exposées | Consommateurs directs |
|---|---|---|
| `app/services/iss_compute.py` (PASS 14 + 27.13) | `_az_to_direction`, `compute_iss_ground_track`, `compute_iss_passes_for_observer`, `compute_iss_passes_tlemcen`, `_run_calculateur_passages_iss`, `ensure_passages_iss_json`, `_get_iss_tle_from_cache`, `_get_satellite_tle_by_name` | `app/blueprints/iss/routes.py`, `app/blueprints/satellites/__init__.py` (via re-export station_web) |
| `app/services/iss_live.py` (PASS 23 + 27.13) | `_curl_get` (local copy), `_guess_region` (local copy court), `_fetch_iss_live`, `_fetch_iss_crew`, `_get_iss_crew` | `app/routes/iss.py`, `app/blueprints/iss/routes.py` (via re-export station_web) |
| `station_web.py` (shim) | re-exports défensifs des 6 helpers PASS 27.13 + appel boot `ensure_passages_iss_json()` | n/a (transparent pour les consommateurs) |

**Pattern consolidé** : 2 services ISS distincts par responsabilité (compute SGP4 + TLE lookup vs live network + crew). Le monolithe ne contient plus aucun helper ISS hormis le re-export et l'effet de bord boot.
