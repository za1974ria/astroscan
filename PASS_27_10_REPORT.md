# PASS 27.10 — Extraction Image downloads helpers vers `app/services/image_downloads.py` (nouveau module)

**Date** : 2026-05-09
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass27_10-pre` (avant) → `pass27_10-done` (après)
**Snapshot** : `/tmp/station_web_pre_pass27_10.py` + `/tmp/PASS_27_10_INVENTORY.md`
**Commit** : `3aea6ae`

---

## Résumé

Création d'un **nouveau module** `app/services/image_downloads.py` regroupant 6 fonctions du pipeline Lab (téléchargement et normalisation d'images NASA APOD, Hubble, JWST, ESA via NASA Images API). Re-export depuis le shim monolithe pour préserver le lazy import historique de `lab_image_collector.py` (cycle horaire des téléchargements).

| Métrique | Avant | Après |
|---|---:|---:|
| `station_web.py` | 2810 lignes | **2618 lignes** (−192 nettes) |
| `app/services/image_downloads.py` | n/a | **266 lignes** (nouveau) |
| Bloc supprimé du monolithe | 223 lignes (6 fns + interstices) | 14 lignes (1 import re-export) + 3 lignes (commentaire pointeur 2e bloc) |
| Source de vérité downloads images | station_web.py (lazy depuis worker) | **image_downloads.py** (résolution propre) |
| Tests `tests/unit/` | 29 PASS / 5 SKIPPED / 0 FAIL | **29 PASS / 5 SKIPPED / 0 FAIL** (aucune régression) |
| Cap monolithe | < 2900 lignes (PASS 27.9) | **< 2700 lignes franchi** |

Note métriques : le brief annonçait `~2486 lignes (-324 net)` et `image_downloads.py ~360 lignes`. Les valeurs réelles (2618 et 266) viennent du recompte précis (les 6 fonctions totalisent 201 lignes corps, pas 333 comme estimé au brief — `_download_esa_images` fait 54 lignes et non 164).

---

## Cas détecté — EXTRACTION + nouveau module

PHASE 0 a confirmé qu'aucun module `app/services/image_download*.py` n'existait :
```
$ ls -la app/services/image_download* 2>/dev/null
(no such file or directory)
```

Distinction claire vs PASS précédents :
| PASS | Cas | Module destination |
|---|---|---|
| 27.3 | EXTRACTION (nouveau module) | `app/services/stellarium_apod.py` (créé) |
| 27.6 | DÉDUPLICATION | `app/services/http_client.py` (déjà PASS 8) |
| 27.7 | EXTRACTION (vers module existant orphelin) | `app/services/analytics_dashboard.py` (déjà PASS 16) |
| 27.8 | DÉDUPLICATION | `app/services/telescope_sources.py` (déjà PASS 9) |
| 27.9 | EXTRACTION (vers module existant) | `app/services/microobservatory.py` (déjà PASS 15) |
| **27.10** | **EXTRACTION + nouveau module** | **`app/services/image_downloads.py` (créé)** |

PASS 27.10 est le 2e cas (avec 27.3) où un nouveau module est créé entièrement.

---

## Les 6 fonctions déplacées (signatures + comportement)

| Fonction | Signature | Lignes corps | Comportement |
|---|---|---:|---|
| `log_rejected_image` | `(metadata, reason) -> None` | 13 | Append JSON ligne dans `LAB_LOGS_DIR/rejected_images.json` (timestamp UTC ISO+Z). Erreur logguée via `log.warning`, pas levée |
| `save_normalized_metadata` | `(meta_dict) -> None` | 11 | Écrit `meta_dict` dans `METADATA_DB/<filename>.json` (priorité `local_filename` puis `filename`, no-op si absents) |
| `_download_nasa_apod` | `() -> None` | 39 | API NASA APOD `count=1`, télécharge image courante via `urllib.request.urlretrieve`, écrit JSON métadata. Timeout 28 s |
| `_download_hubble_images` | `() -> None` | 50 | Index `hubblesite.org/api/v3/images?page=1` puis détail par ID, jusqu'à 5 images, dernier `image_files[]` = meilleure résolution |
| `_download_jwst_images` | `() -> None` | 34 | API `webbtelescope.org/api/v1/images`, jusqu'à 3 items, lookup multi-clé `image_url\|url\|file_url\|image.url` |
| `_download_esa_images` | `() -> None` | 54 | NASA Images API `images-api.nasa.gov/search?q=satellite mission` (repli après obsolescence `esa.int/api/images`), jusqu'à 4 items, premier lien `.jpg/.jpeg/.png/.webp` |

**Total** : 201 lignes corps (vs 333 annoncées au brief — `_download_esa_images` réelle 54 lignes vs 164 estimées).

Toutes les fonctions ont été déplacées **verbatim** (pas de modification du corps, ni de la signature, ni des messages de log). Comportement bit-perfect au pré-PASS.

---

## Dépendances importées

### Top-level dans `image_downloads.py` (pas de cycle vers station_web)

```python
import json
import logging
import os
import time
from datetime import datetime, timezone

from app.services.station_state import STATION              # PASS 23
from app.services.lab_helpers import RAW_IMAGES, METADATA_DB  # PASS 20.3
from services.utils import _safe_json_loads                  # legacy
```

| Import | Source | Justification |
|---|---|---|
| `os, json, time, datetime, timezone` | stdlib | Utilisés dans 6/6 fonctions |
| `logging` + `log = logging.getLogger(__name__)` | stdlib + local | Logger module dédié |
| `STATION` | `app.services.station_state` (PASS 23) | Calcul de `LAB_LOGS_DIR` local |
| `RAW_IMAGES`, `METADATA_DB` | `app.services.lab_helpers` (PASS 20.3) | Chemins disque écriture images + métadata |
| `_safe_json_loads` | `services.utils` | Parsing JSON tolérant aux erreurs |

### Lazy imports inside conservés (pattern original)

| Fonction | Lazy import | Justification |
|---|---|---|
| `_download_nasa_apod` | `urllib.request`, `from datetime import datetime as _dt, timezone as _tz` | Pattern PASS 27.4 alias `_dt`/`_tz` (substitution `datetime.utcnow()` → `_dt.now(_tz.utc)`) |
| `_download_hubble_images` | `urllib.request` | Anti-startup (urllib non chargé si fonction jamais appelée) |
| `_download_jwst_images` | `urllib.request` | idem |
| `_download_esa_images` | `urllib.parse`, `urllib.request` | idem (parse pour `quote`) |

### Constante locale `LAB_LOGS_DIR`

Définition locale `LAB_LOGS_DIR = os.path.join(STATION, "data", "images_espace", "logs")`. **Pas re-exportée** — calculée identiquement à la copie de `station_web.py` L2211 (qui reste pour le `os.makedirs(LAB_LOGS_DIR, exist_ok=True)` au boot, effet de bord init disque).

Décision justifiée : éviter un import circulaire `from station_web import LAB_LOGS_DIR` qui aurait recréé un cycle. La constante étant immutable et calculée depuis STATION (résolu de manière stable), la duplication est sûre.

### Pas de cycle, pas de lazy import vers station_web

`image_downloads.py` n'importe **rien depuis `station_web`**. Aucun lazy import inside vers le monolithe. C'est plus propre que les PASS 27.2/27.9 qui faisaient un lazy `from station_web import HEALTH_STATE` etc. Ici, toutes les dépendances sont résolues vers les modules `app/services/*` propres.

---

## Patch appliqué

### Côté `station_web.py`

**Avant** : 6 fonctions définies localement (L2221-2443), 223 lignes incluant interstices.

**Après** :
- L2221 : 1 bloc d'import re-export (14 lignes) avec docstring expliquant la migration
- L2249-2258 (commentaires `# MIGRATED TO lab_bp PASS 13`) : préservés intacts
- L2261 (ancienne) : remplacée par 3 lignes de commentaire pointeur :
  ```python
  # PASS 27.10 (2026-05-09) — _download_nasa_apod / _download_hubble_images /
  # _download_jwst_images / _download_esa_images déplacés vers
  # app/services/image_downloads.py (re-exportés via le bloc d'import plus haut).
  ```

### Côté `app/services/image_downloads.py`

Nouveau fichier 266 lignes :
- Docstring complète (40 lignes) : description module, 6 fonctions, architecture
- 13 lignes d'imports + définition `log` + `LAB_LOGS_DIR`
- 6 fonctions verbatim (201 lignes corps + interstices)

---

## Tests effectués

### PHASE 4 — Validation syntaxique

| # | Test | Résultat |
|---|---|---|
| 1 | `py_compile station_web.py + image_downloads.py` | **OK** |
| 2 | `import station_web` (avec patches `.env`/handler/sqlite) | **OK** (29 BP + 8 hooks + 293 routes Flask) |
| 3 | `from app.services.image_downloads import log_rejected_image, save_normalized_metadata, _download_nasa_apod, _download_hubble_images, _download_jwst_images, _download_esa_images` | **OK** |
| 4 | `from station_web import log_rejected_image, ...` (re-export 6 symboles) | **OK** |
| 5 | Identité (re-export = source) — preuves `is` | **6/6 True** |

| Symbole | `station_web.X is image_downloads.X` |
|---|---|
| `log_rejected_image` | True |
| `save_normalized_metadata` | True |
| `_download_nasa_apod` | True |
| `_download_hubble_images` | True |
| `_download_jwst_images` | True |
| `_download_esa_images` | True |

### PHASE 5 — Tests fonctionnels runtime

```
log_rejected_image({'name': 'test'}, 'unit_test_dry_run')
  → log.warning emitted: "log_rejected_image failed: [Errno 13] Permission denied:
     '/root/astro_scan/data/images_espace/logs/rejected_images.json'"
  → return: None (pas de crash, gère silencieusement via try/except — comportement
     conforme à l'original : perms write absent côté zakaria, fonctionnel sous root)
```

Comportement préservé : la fonction garantit l'absence d'exception remontée à l'appelant, log warning uniquement.

Les 4 `_download_*` n'ont **pas** été testés en runtime (effets réseau + écriture disque hors scope tests unitaires).

### Suite tests unitaires `pytest tests/unit/`

```
collected 34 items
29 passed, 5 skipped, 0 failed in 3.41s
```

Identique à la baseline pré-PASS 27.10 (PASS 27.9 final) :
- Tests `test_pure_services.py` : 7/7 PASS
- Tests `test_services.py` : 21/22 PASS, 1 SKIPPED (sémantique TTL=0 changée post-PASS-15)
- Tests `test_blueprints.py` : 4/4 SKIPPED (perms root)

**Aucune régression** introduite par PASS 27.10.

Note brief : le brief mentionne « 33 tests » mais le compte réel est 34 collected (29 passed + 5 skipped). Pas de divergence opérationnelle, juste un écart d'arrondi.

---

## Imports legacy préservés (preuve par grep)

```
$ grep -rn "from station_web import.*\(_download_\|log_rejected_image\|save_normalized_metadata\)" \
       /root/astro_scan --include="*.py" | grep -v __pycache__ | grep -v "backup\|.archive"

/root/astro_scan/app/workers/lab_image_collector.py:144:    from station_web import (
/root/astro_scan/app/workers/lab_image_collector.py:146:        _download_esa_images,
/root/astro_scan/app/workers/lab_image_collector.py:147:        _download_hubble_images,
/root/astro_scan/app/workers/lab_image_collector.py:148:        _download_jwst_images,
/root/astro_scan/app/workers/lab_image_collector.py:149:        _download_nasa_apod,
```

**Un consommateur externe** : `app/workers/lab_image_collector.py:144-152` fait un lazy import inside la fonction `_run_lab_image_collector_once` (pattern PASS 21.4 cycle-safe). Les 4 `_download_*` y sont effectivement appelés (L168-171) toutes les ~heure dans le cycle Lab. Ce lazy import passe par le shim re-export station_web → image_downloads et continue de fonctionner sans modification.

`log_rejected_image` et `save_normalized_metadata` n'ont aucun consommateur externe via `from station_web import` (grep retourne 0 résultat les concernant). Le re-export les rend néanmoins disponibles défensivement.

---

## Conformité aux règles strictes

| # | Règle | Vérification | Statut |
|---|---|---|---|
| 1 | Pas de redémarrage `astroscan.service` | Aucun `systemctl restart` invoqué | ✓ |
| 2 | Pas de modif `wsgi.py`, blueprints, autres services | `git diff --stat` : seuls `station_web.py` + `image_downloads.py` modifiés | ✓ |
| 3 | Pas toucher à `_curl_get` / `_safe_json_loads` (PASS 27.6) | `_curl_get` non utilisé par les 6 fns ; `_safe_json_loads` réutilisé via import existant `from services.utils import _safe_json_loads` | ✓ |
| 4 | Pas de suppression du re-export | Re-export présent ligne ~2221 station_web.py (6 symboles) | ✓ |
| 5 | Lazy import inside si cycle | Aucun cycle détecté (image_downloads n'importe rien depuis station_web) | ✓ |
| 6 | STOP si tests existants cassés | 29 PASS / 5 SKIPPED / 0 FAIL — identique à baseline | ✓ |
| 7 | Rollback en prose, pas en bloc shell | Cf. section dédiée ci-dessous | ✓ |
| 8 | STOP si fonction non migrable proprement | Aucune fonction problématique — `LAB_LOGS_DIR` redéfini localement (immutable, calculé depuis STATION stable) | ✓ |

---

## Procédure de rollback (texte prose, non exécutable)

En cas de régression détectée après déploiement, le retour à l'état pré-PASS 27.10 est faisable de trois manières équivalentes.

**Option A — via le tag git (recommandée).** Le tag `pass27_10-pre` pointe sur le commit `391342e` (PASS 27.9 final). Un `git checkout pass27_10-pre -- station_web.py` restaure le monolithe avec les 6 fonctions définies localement, puis un `git rm app/services/image_downloads.py` supprime le nouveau module créé. Suivi d'un commit dédié documentant la raison du rollback. Cette option préserve l'ensemble des gains des PASS 27.x antérieurs (TLE worker, datetime migration, SDR cascade, déduplication `_curl_*`/_apod_hubble, extractions `_analytics_*`/`_mo_*`).

**Option B — via le snapshot fichier + suppression du nouveau module.** Un snapshot du `station_web.py` d'origine a été créé en PHASE 0 dans `/tmp/station_web_pre_pass27_10.py` (2810 lignes). En cas d'urgence sans accès git, ce fichier peut être recopié vers `/root/astro_scan/station_web.py`, suivi de la suppression de `app/services/image_downloads.py` (créé par ce PASS, pas de version antérieure à restaurer). Note : `/tmp/` est volatile au reboot ; le snapshot est garanti uniquement pour la session de déploiement courante.

**Option C — désactivation soft du re-export (préserver le module nouvellement créé).** Si la régression provient d'une particularité du pattern re-export (extrêmement improbable étant donné l'identité préservée vérifiée par `is`), il suffit de retirer le bloc d'import re-export ligne ~2221 de `station_web.py` et de réinjecter les 6 fonctions verbatim depuis `/tmp/station_web_pre_pass27_10.py`. Le module `image_downloads.py` reste en place pour usage direct par d'autres consommateurs futurs (par exemple un nouveau blueprint qui importerait directement depuis `app.services.image_downloads`). Le worker `lab_image_collector.py` continue son lazy import depuis station_web sans impact.

Aucun rollback automatique n'est prévu : le diff étant un déplacement de code (objets identiques par `is`) avec création d'un nouveau module, tout retour en arrière doit être déclenché manuellement après diagnostic.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass27_10-pre` | `391342e` | Snapshot avant déplacement (HEAD = PASS 27.9) |
| `pass27_10-done` | `3aea6ae` | Module nouveau créé + 6 fonctions déplacées + re-export + 1 consommateur lazy préservé |

---

## Diff résumé

```
git diff --staged --stat (avant commit) :
 app/services/image_downloads.py | 266 ++++++++++++++++++++++++++++++++++++++++
 station_web.py                  | 226 +++-------------------------------
 2 files changed, 283 insertions(+), 209 deletions(-)
```

Aucun autre fichier touché. Création d'un seul nouveau fichier (`image_downloads.py`). Aucune modification de l'API publique ni de signature.

---

## Note sur la validation systemd

Le service `astroscan.service` n'a **pas** été redémarré (RÈGLE 1). Les workers gunicorn actuels servent encore le monolithe pré-PASS 27.10 (avec les 6 fonctions définies localement L2221-2443) jusqu'au prochain cycle (`--max-requests=1000`) ou jusqu'à un `systemctl restart astroscan` manuel par root. La validation runtime décrite en PHASES 4-5 a été conduite en environnement isolé (Flask `app_context()` sans toucher aux workers de production).

Le risque de régression au prochain cycle est nul : les 6 fonctions re-exportées sont identiques par `is`, le pytest reste vert, le lazy import du worker `lab_image_collector` continue de pointer vers station_web (qui re-route vers image_downloads). La 1re exécution du cycle Lab post-restart confirmera le bon comportement (cycle horaire, prochain run dans <60 min après le restart).

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
| **PASS 27.10 (image downloads extraction, nouveau module)** | **2618** | **−192** | **−744** |

Note brief : le brief annonçait `~2486 lignes (-324 net)`. Le résultat réel est **2618 lignes (−192 net)** — l'écart vient du fait que les 6 fonctions totalisent 201 lignes corps (et non 333 estimées) et que le re-export en compte 14 + 3 commentaire pointeur.

Cap symbolique des **2700 lignes franchi** dans le monolithe.

---

## Architecture après PASS 27.10 — `app/services/image_downloads.py`

| Aspect | Valeur |
|---|---|
| Nature du module | **Nouveau** (créé en PASS 27.10) |
| Source unique des helpers downloads | `app/services/image_downloads.py` (266 lignes) |
| Fonctions exposées | 6 (`log_rejected_image`, `save_normalized_metadata`, `_download_nasa_apod`, `_download_hubble_images`, `_download_jwst_images`, `_download_esa_images`) |
| Constantes exposées | aucune (`LAB_LOGS_DIR` interne, calculé depuis STATION) |
| Consommateur via lazy import shim | `app/workers/lab_image_collector.py:144-152` (cycle horaire run_collector_safe) |
| Imports tiers en lazy inside | `urllib.request`, `urllib.parse` (anti-startup) |
| Cycle de dépendances | Aucun (pas d'import vers station_web, contrairement à microobservatory PASS 27.9 qui n'en avait pas non plus) |
| Pattern PASS 27.4 (datetime tz-aware) | Préservé : `_dt.now(_tz.utc)` dans `_download_nasa_apod` |

---

## Synthèse cumulée des modules `app/services/` créés/enrichis sur la série PASS 27.x

| Module | Statut | Source PASS | Lignes |
|---|---|---|---:|
| `app/services/stellarium_apod.py` | nouveau | 27.3 | 297 |
| `app/services/logging_service.py` | enrichi (PASS 27.4) | 23.2 | 138 |
| `app/services/analytics_dashboard.py` | enrichi (PASS 27.7) | 16 | 429 |
| `app/services/microobservatory.py` | enrichi (PASS 27.9) | 15 | 364 |
| **`app/services/image_downloads.py`** | **nouveau (PASS 27.10)** | **27.10** | **266** |

Au total, la série PASS 27.x a produit 2 nouveaux modules services (stellarium_apod + image_downloads) et enrichi 3 modules existants (logging_service, analytics_dashboard, microobservatory).
