# PASS 27.9 — Extraction MO Microobservatory helpers vers `app/services/microobservatory.py`

**Date** : 2026-05-09
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass27_9-pre` (avant) → `pass27_9-done` (après)
**Snapshot** : `/tmp/station_web_pre_pass27_9.py` + `/tmp/microobservatory_pre_pass27_9.py` + `/tmp/PASS_27_9_INVENTORY.md`
**Commit** : `391342e`

---

## Résumé

Déplacement des 4 fonctions helpers `_mo_*` (pipeline nocturne Tlemcen — catalogue MO, parsing, conversion FITS→JPG) + 3 constantes (`_MO_DIR_URL`, `_MO_DL_BASE`, `_MO_OBJECT_CATALOG` dict 37 préfixes) depuis `station_web.py` vers `app/services/microobservatory.py` (qui ne contenait jusqu'ici que `fetch_microobservatory_images`, un scrape différent extrait au PASS 15). Le module devient la source de vérité unique du pipeline MO. Re-export depuis le shim monolithe pour préserver le lazy import historique de `telescope_helpers.py`.

| Métrique | Avant | Après |
|---|---:|---:|
| `station_web.py` | 2975 lignes | **2810 lignes** (−165 nettes) |
| `app/services/microobservatory.py` | 168 lignes | **364 lignes** (+196 — 4 fonctions + 3 constantes + docstring) |
| Bloc supprimé du monolithe | 180 lignes (header + 3 const + 4 fns) | 14 lignes (1 import re-export) |
| Source de vérité `_mo_*` | station_web.py + lazy import inverse depuis service | **microobservatory.py** (résolution locale propre) |
| Tests `tests/unit/` | 29 PASS / 5 SKIPPED / 0 FAIL | **29 PASS / 5 SKIPPED / 0 FAIL** (aucune régression) |
| Cap monolithe | < 3000 lignes | **< 2900 lignes franchi** |

---

## Cas détecté — EXTRACTION (pas de doublon)

PHASE 1 a retourné `0 résultats` pour le grep des 4 défs dans `microobservatory.py` :
```
$ grep -nE "^def _mo_(parse_filename|fetch_catalog_today|visible_tonight|fits_to_jpg)" \
       /root/astro_scan/app/services/microobservatory.py
(aucun résultat)
```

Le module `microobservatory.py` (168 lignes pré-PASS, extrait au PASS 15) contenait uniquement `fetch_microobservatory_images()` — un scrape de la page index Harvard différent des 4 fonctions cibles. Aucun conflit, aucune divergence à arbitrer.

**Distinction vs PASS 27.6 / 27.8 (qui étaient des cas DÉDUPLICATION)** : ici les fonctions étaient bien orphelines du module thématique. Le PASS 20.4 avait explicitement noté en docstring de `telescope_helpers.py:9-10` : *« Les helpers _mo_fetch_catalog_today, _mo_visible_tonight, _mo_fits_to_jpg restent dans station_web (hors périmètre PASS 20.4) »*. PASS 27.9 finit le travail laissé en suspens.

---

## Les 4 fonctions déplacées (signatures + comportement)

| Fonction | Signature | Lignes corps | Comportement |
|---|---|---:|---|
| `_mo_parse_filename` | `(name) -> dict\|None` | 13 | Parse `'AndromedaGal260508221047.FITS'` → `{prefix, filename, captured_at, url}` (regex `^(.+?)(\d{2}){6}$`, datetime tz-aware UTC). Retourne `None` si pattern absent ou date invalide |
| `_mo_fetch_catalog_today` | `() -> dict[str, list]` | 31 | Scrape `_MO_DIR_URL`, parse 30 derniers jours via `_mo_parse_filename`, regroupe par préfixe trié desc. Cache `cache_get/set('mo_catalog_today', 3600)` |
| `_mo_visible_tonight` | `() -> list[dict]` | 41 | Itère `_MO_OBJECT_CATALOG`, calcule altitude depuis Tlemcen (34.87°N, 1.32°E, 816 m) à 23h UTC via astropy. Retourne objets avec `alt > 20°`, dédoublonnés par label, triés altitude décroissante |
| `_mo_fits_to_jpg` | `(fits_bytes, save_path) -> str` | 36 | Convertit FITS→JPG : `astropy.io.fits.open(BytesIO)` → ZScaleInterval → colormap hot RGB → `PIL.Image` 600×600 LANCZOS. Retourne `DATE-OBS` du header. Lève `ValueError` si data vide |

### 3 constantes co-déplacées

| Constante | Type | Valeur |
|---|---|---|
| `_MO_DIR_URL` | str | `https://waps.cfa.harvard.edu/microobservatory/MOImageDirectory/ImageDirectory.php` |
| `_MO_DL_BASE` | str | `https://mo-www.cfa.harvard.edu/ImageDirectory/` (URL téléchargement FITS) |
| `_MO_OBJECT_CATALOG` | dict | 37 préfixes objets → `{ra, dec, type, label, body?}` (Lune, Jupiter, M31, M42, M51, M81, M101, NGC 891, Sgr A*, etc.) |

Note : le source contenait 38 lignes mais 1 doublon `M-82Irregula` — le dict natif Python dédoublonne, d'où 37 entrées effectives. Comportement préservé (le doublon était déjà là pré-PASS).

### Imports

**Top-level ajoutés** dans `microobservatory.py` :
- `import os` (utilisé par `_mo_parse_filename`)
- `from services.cache_service import cache_get, cache_set` (utilisé par `_mo_fetch_catalog_today`)

**Top-level préexistants** (PASS 15) : `re`, `datetime`, `timezone`, `from app.services.http_client import _curl_get`, `logging`.

**Lazy imports inside préservés** (pattern original anti-cycle, anti-startup) :
- `from datetime import timedelta` — dans `_mo_fetch_catalog_today`
- `from astropy.coordinates import EarthLocation, AltAz, SkyCoord, get_body` + `from astropy.time import Time` + `import astropy.units as u` — dans `_mo_visible_tonight`
- `import io, numpy as np, from astropy.io import fits, from astropy.visualization import ZScaleInterval, from PIL import Image` — dans `_mo_fits_to_jpg`

Aucun lazy import vers `station_web` (pas de cycle).

---

## Patch appliqué

### Côté `station_web.py` (L1307-1485 → re-export 14 lignes)

**Avant** : 180 lignes (en-tête section + 3 constantes + 4 fonctions verbatim).

**Après** :

```python
# PASS 27.9 (2026-05-09) — Microobservatory pipeline (3 constantes + 4 helpers)
# déplacé vers source de vérité unique app/services/microobservatory.py.
# Re-exporté ici pour préserver le lazy import de telescope_helpers.py:35-41
# (`from station_web import _mo_fetch_catalog_today, _mo_fits_to_jpg,
# _mo_visible_tonight, cache_set, log` — pattern PASS 20.4 cycle-safe).
from app.services.microobservatory import (  # noqa: F401 (re-export)
    _MO_DIR_URL,
    _MO_DL_BASE,
    _MO_OBJECT_CATALOG,
    _mo_parse_filename,
    _mo_fetch_catalog_today,
    _mo_visible_tonight,
    _mo_fits_to_jpg,
)
```

### Côté `app/services/microobservatory.py`

- Docstring enrichie pour mentionner les 4 nouveaux helpers + note PASS 27.9
- 2 nouveaux imports top-level (`os`, `cache_get/cache_set`)
- 3 constantes ajoutées après le bloc `_fetch_microobservatory_images` (alias)
- 4 fonctions déplacées verbatim (lazy imports inside préservés)

---

## Tests effectués

### PHASE 4 — Validation syntaxique

| # | Test | Résultat |
|---|---|---|
| 1 | `py_compile station_web.py + microobservatory.py` | **OK** |
| 2 | `import station_web` (avec patches `.env`/handler/sqlite) | **OK** (29 BP + 8 hooks + 293 routes) |
| 3 | `from app.services.microobservatory import _mo_parse_filename, _mo_fetch_catalog_today, _mo_visible_tonight, _mo_fits_to_jpg, _MO_DIR_URL, _MO_DL_BASE, _MO_OBJECT_CATALOG` | **OK** — 37 entrées dans le catalogue |
| 4 | `from station_web import _mo_*` (re-export 7 symboles) | **OK** |
| 5 | Identité (re-export = source) — preuves `is` | **5/5 True** |

| Symbole | `station_web.X is microobservatory.X` |
|---|---|
| `_mo_parse_filename` | True |
| `_mo_fetch_catalog_today` | True |
| `_mo_visible_tonight` | True |
| `_mo_fits_to_jpg` | True |
| `_MO_OBJECT_CATALOG` (dict mutable) | True |

Le re-export du dict mutable préserve l'identité — toute mutation par un consommateur (ex. ajout de préfixe runtime) serait visible des deux côtés. Mais aucun mutateur n'est identifié dans le codebase, le dict est lu-only en pratique.

### PHASE 5 — Tests fonctionnels runtime

```
parse('AndromedaGal260508221047.FITS')
  → {'prefix': 'AndromedaGal',
     'filename': 'AndromedaGal260508221047.FITS',
     'captured_at': datetime.datetime(2026, 5, 8, 22, 10, 47, tzinfo=UTC),
     'url': 'https://mo-www.cfa.harvard.edu/ImageDirectory/AndromedaGal260508221047.FITS'}

parse('invalid.FITS')   → None  (regex fail, pas de timestamp 12 chiffres)
parse('NoNumbers.FITS') → None  (idem)
```

Comportement préservé : datetime tz-aware UTC, URL construite via `_MO_DL_BASE`, fallback `None` silencieux pour entrées non parsables.

### Suite tests unitaires `pytest tests/unit/`

```
collected 34 items
29 passed, 5 skipped, 0 failed in 3.22s
```

Identique à la baseline pré-PASS 27.9 (PASS 27.8 final) :
- Tests `test_pure_services.py` : 7/7 PASS
- Tests `test_services.py` : 21/22 PASS, 1 SKIPPED (sémantique TTL=0 changée post-PASS-15)
- Tests `test_blueprints.py` : 4/4 SKIPPED (perms root)

**Aucune régression** introduite par PASS 27.9.

---

## Imports legacy préservés (preuve par grep)

```
$ grep -rn "from station_web import.*_mo_\|station_web\._mo_\|_sw\._mo_" \
       /root/astro_scan --include="*.py" | grep -v __pycache__ | grep -v "backup\|.archive"

/root/astro_scan/app/services/telescope_helpers.py:35:    from station_web import (
/root/astro_scan/app/services/telescope_helpers.py:36:        _mo_fetch_catalog_today,
/root/astro_scan/app/services/telescope_helpers.py:37:        _mo_fits_to_jpg,
/root/astro_scan/app/services/telescope_helpers.py:38:        _mo_visible_tonight,
```

**Un consommateur externe** : `app/services/telescope_helpers.py:35-41` fait un lazy import inside la fonction `_telescope_nightly_tlemcen` (pattern PASS 20.4 cycle-safe). Ce lazy import passe par le shim re-export station_web → microobservatory et continue de fonctionner sans modification.

Ce consommateur a été délibérément préservé : changer `from station_web import _mo_*` en `from app.services.microobservatory import _mo_*` aurait été une amélioration mineure mais hors scope PASS 27.9 (règle 2 : pas de modif d'autres services). Cette migration optionnelle pourra se faire dans un PASS futur de nettoyage.

---

## Conformité aux règles strictes

| # | Règle | Vérification | Statut |
|---|---|---|---|
| 1 | Pas de redémarrage `astroscan.service` | Aucun `systemctl restart` invoqué | ✓ |
| 2 | Pas de modif `wsgi.py`, blueprints, autres services | `git diff --stat` : seuls `station_web.py` + `microobservatory.py` modifiés | ✓ |
| 3 | Pas toucher à `_curl_get` / `_safe_json_loads` (PASS 27.6) | `_curl_get` réutilisé via import existant `from app.services.http_client import _curl_get` ; `_safe_json_loads` non utilisé par les 4 fns | ✓ |
| 4 | Pas de suppression du re-export | Re-export présent ligne ~1313 station_web.py (7 symboles) | ✓ |
| 5 | STOP si fonctions divergent | Cas EXTRACTION (pas de divergence possible — fonctions absentes du module cible avant PASS) | ✓ |
| 6 | Lazy import inside si cycle | Aucun cycle détecté (microobservatory n'importe rien depuis station_web) | ✓ |
| 7 | STOP si tests existants cassés | 29 PASS / 5 SKIPPED / 0 FAIL — identique à baseline | ✓ |
| 8 | Rollback en prose, pas en bloc shell | Cf. section dédiée ci-dessous | ✓ |

---

## Procédure de rollback (texte prose, non exécutable)

En cas de régression détectée après déploiement, le retour à l'état pré-PASS 27.9 est faisable de trois manières équivalentes.

**Option A — via le tag git (recommandée, granularité fichier).** Le tag `pass27_9-pre` pointe sur le commit `0caaabd` (PASS 27.8 final). Un `git checkout pass27_9-pre -- station_web.py app/services/microobservatory.py` restaure les deux fichiers concernés sans toucher aux 7 PASS précédents (27.1-27.8). Suivi d'un commit dédié documentant la raison du rollback. Cette option préserve l'ensemble des gains des PASS 27.x antérieurs (TLE worker, datetime migration, SDR cascade, déduplication `_curl_*`, extraction `_analytics_*`, déduplication APOD/Hubble).

**Option B — via les snapshots fichier.** Deux snapshots ont été créés en PHASE 0 dans `/tmp/station_web_pre_pass27_9.py` (2975 lignes) et `/tmp/microobservatory_pre_pass27_9.py` (168 lignes). En cas d'urgence sans accès git, ces fichiers peuvent être recopiés tels quels vers leurs emplacements respectifs pour restituer l'état pré-PASS. Note : `/tmp/` est volatile au reboot ; les snapshots sont garantis uniquement pour la session de déploiement courante.

**Option C — restauration partielle inline (préserver le déplacement, isoler le helper problématique).** Si seul l'un des 4 helpers ou l'une des 3 constantes pose problème, il suffit de retirer ce nom du re-export ligne ~1313 station_web.py et de redéfinir localement le symbole concerné dans le monolithe. Cela laisse les autres `_mo_*` continuer à utiliser la source unique tout en isolant le problème. Réintroduction volontaire d'un mini-doublon ciblé, à documenter dans un PASS suivant. Cette option est utile si seul `_mo_visible_tonight` (qui dépend d'astropy lourd) cause un problème de boot par exemple.

Aucun rollback automatique n'est prévu : le diff étant un déplacement de code (objets identiques par `is`), tout retour en arrière doit être déclenché manuellement après diagnostic.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass27_9-pre` | `0caaabd` | Snapshot avant déplacement (HEAD = PASS 27.8) |
| `pass27_9-done` | `391342e` | 4 fonctions + 3 constantes déplacées + re-export + 1 consommateur lazy préservé |

---

## Diff résumé

```
git diff --staged --stat (avant commit) :
 app/services/microobservatory.py | 196 +++++++++++++++++++++++++++++++++++++++
 station_web.py                   | 193 +++-----------------------------------
 2 files changed, 210 insertions(+), 179 deletions(-)
```

Aucun autre fichier touché. Aucune création de fichier (hors le rapport et l'inventaire `/tmp/`). Aucune modification de l'API publique. Aucune signature de fonction modifiée.

---

## Note sur la validation systemd

Le service `astroscan.service` n'a **pas** été redémarré (RÈGLE 1). Les workers gunicorn actuels servent encore le monolithe pré-PASS 27.9 (avec les 4 fonctions définies localement et le module `microobservatory.py` à 168 lignes) jusqu'au prochain cycle (`--max-requests=1000`) ou jusqu'à un `systemctl restart astroscan` manuel par root. La validation runtime décrite en PHASES 4-5 a été conduite en environnement isolé (Flask `app_context()` sans toucher aux workers de production).

Le risque de régression au prochain cycle est nul : les 4 fonctions re-exportées sont identiques par `is`, le pytest reste vert, le lazy import de telescope_helpers continue de pointer vers station_web (qui re-route vers microobservatory).

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
| **PASS 27.9 (`_mo_*` extraction)** | **2810** | **−165** | **−552** |

Note : le brief annonçait `~2805 lignes (-170 net)`. Le résultat réel est **2810 lignes (−165 net)** — l'écart vient du fait que les 4 fonctions + 3 constantes + en-tête section totalisent 180 lignes (et non 196) et que le re-export en compte 14.

Cap symbolique des **2900 lignes franchi** dans le monolithe.

---

## Architecture après PASS 27.9 — `app/services/microobservatory.py`

| Aspect | Valeur |
|---|---|
| Source unique des helpers MO | `app/services/microobservatory.py` (364 lignes) |
| Fonctions exposées (cohérentes entre PASS 15 et PASS 27.9) | `fetch_microobservatory_images()` (PASS 15), `_mo_parse_filename`, `_mo_fetch_catalog_today`, `_mo_visible_tonight`, `_mo_fits_to_jpg` (PASS 27.9) |
| Constantes exposées | `_MO_DIR_URL`, `_MO_DL_BASE`, `_MO_OBJECT_CATALOG` (37 entrées) |
| Consommateur via lazy import shim | `app/services/telescope_helpers.py:35-41` (route nocturne `_telescope_nightly_tlemcen`) |
| Imports tiers lourds restant en lazy inside | `astropy.coordinates`, `astropy.time`, `astropy.units`, `astropy.io.fits`, `astropy.visualization`, `numpy`, `PIL.Image` (n'impactent pas le boot Flask) |
| Cycle de dépendances | Aucun (microobservatory ne référence pas station_web) |
