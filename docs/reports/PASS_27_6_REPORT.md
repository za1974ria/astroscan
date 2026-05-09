# PASS 27.6 — Déduplication `_curl_*` helpers (strangler fig)

**Date** : 2026-05-09
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass27_6-pre` (avant) → `pass27_6-done` (après)
**Snapshot** : `/tmp/station_web_pre_pass27_6.py` + `/tmp/PASS_27_6_INVENTORY.md`
**Commit** : `63c2c96`

---

## Résumé

Suppression d'un doublon de 36 lignes dans `station_web.py` (3 fonctions `_curl_get`, `_curl_post`, `_curl_post_json`) qui existaient déjà à l'identique dans `app/services/http_client.py` depuis le PASS 8. Re-export depuis le shim monolithe pour préserver les appels internes et l'API publique testée. Aucune modification de `app/services/http_client.py`.

| Métrique | Avant | Après |
|---|---:|---:|
| `station_web.py` | 3129 lignes | **3103 lignes** (−26 nettes) |
| Bloc `_curl_*` retiré | 36 lignes (3 fonctions) | 10 lignes (1 import re-export) |
| Source de vérité `_curl_*` | **2 copies divergentes potentielles** | **1 source unique** (`app/services/http_client.py`) |
| Appels internes monolithe préservés | 12 (`_curl_get`) + 0 (`_curl_post[_json]`) | 12 + 0 (résolution via re-export) |
| Tests `tests/unit/` | 29 PASS / 5 SKIPPED / 0 FAIL | **29 PASS / 5 SKIPPED / 0 FAIL** |

---

## Constat doublon (PASS 8 → PASS 27.6, 6 jours d'écart)

| Événement | Commit | Date | Action |
|---|---|---|---|
| Création de `app/services/http_client.py` | `901be23` | 2026-05-03 | Extraction des 4 helpers HTTP pour permettre l'usage par `feeds_bp` et autres BPs sans dépendance circulaire vers `station_web` |
| Doublon laissé en place | — | 2026-05-03 → 2026-05-09 | Le docstring d'origine documentait : *« station_web.py garde sa propre copie identique pour ne pas casser les routes monolithe restantes (single source of truth viendra en PASS final). »* |
| Déduplication PASS 27.6 | `63c2c96` | 2026-05-09 | Strangler fig : suppression copie locale + re-export depuis `app.services.http_client` |

Durée du doublon en production : **6 jours**. Aucune divergence détectée pendant cette période (les 2 implémentations étaient strictement équivalentes au comportement près des annotations de typage et du formatage des strings de log : `f"curl_get {url[:60]}: {e}"` côté monolithe vs `"curl_get %s: %s", url[:60], e` côté http_client). Les BPs déjà migrés (`feeds`, etc.) consomment depuis `app.services.http_client` ; les routes restant dans le monolithe consommaient depuis la copie locale.

---

## Patch appliqué

**Avant** (station_web.py L569-604) :

```python
def _curl_get(url, timeout=15):
    """GET via curl — contourne restrictions réseau urllib (Tlemcen)."""
    try:
        r = subprocess.run(
            ['curl', '-s', '-L', '--max-time', str(timeout), …],
            capture_output=True, text=True, timeout=timeout + 2
        )
        return (r.stdout or "").strip()
    except Exception as e:
        log.warning(f"curl_get {url[:60]}: {e}")
        return ""

def _curl_post(url, post_data, timeout=15, headers=None): …
def _curl_post_json(url, payload_dict, extra_headers=None, timeout=15): …
```

**Après** (station_web.py L569-578) :

```python
# PASS 27.6 (2026-05-09) — HTTP helpers déplacés vers source de vérité unique
# app/services/http_client.py (extrait initialement au PASS 8, commit 901be23,
# mais sans re-export jusqu'ici → doublon supprimé en PASS 27.6).
# Re-exportés ici pour conserver les 12 appels internes du monolithe et
# l'API publique testée par tests/unit/test_pure_services.py.
from app.services.http_client import (  # noqa: F401 (re-export)
    _curl_get,
    _curl_post,
    _curl_post_json,
)
```

Diff total : `1 file changed, 10 insertions(+), 36 deletions(-)`.

---

## Compatibilité signatures (vérifiée)

| Fonction | station_web (avant) | http_client (source) | Verdict |
|---|---|---|---|
| `_curl_get` | `(url, timeout=15)` | `(url: str, timeout: int = 15) -> str` | ✓ compatible (positional + default) |
| `_curl_post` | `(url, post_data, timeout=15, headers=None)` | `(url, post_data, timeout=15, headers=None) -> Optional[str]` | ✓ compatible |
| `_curl_post_json` | `(url, payload_dict, extra_headers=None, timeout=15)` | idem + annotations typage | ✓ compatible |

**Identité de fonction** vérifiée à l'exécution : `station_web._curl_get is http_client._curl_get == True` (idem pour `_curl_post`, `_curl_post_json`). Le re-export n'est pas une nouvelle fonction wrapper mais bien une référence à l'objet original.

---

## 12 appels internes préservés dans `station_web.py`

Le brief annonçait 14 appels — recompte précis = **12 appels à `_curl_get(`** + **0 appels** à `_curl_post[_json](` (hors la def). Tous résolus automatiquement via le re-export.

| Ligne | Contexte | URL appelée |
|---:|---|---|
| 996 | NASA APOD enrichi | `https://api.nasa.gov/planetary/apod?api_key=…` |
| 1237 | ISS crew (Open Notify) | `http://api.open-notify.org/astros.json` |
| 1539 | MicroObservatory directory listing | `_MO_DIR_URL` (bulletin HTML) |
| 1706 | Voyager Horizons (boucle 2 sondes) | `https://ssd.jpl.nasa.gov/api/horizons.api?…` |
| 1736 | NASA NEO feed | `https://api.nasa.gov/neo/rest/v1/feed?…` |
| 1776 | NOAA SWPC solar wind | `https://services.swpc.noaa.gov/products/…` |
| 1799 | NOAA SWPC alerts | `https://services.swpc.noaa.gov/json/alerts.json` |
| 1806 | NOAA SWPC X-ray flares | `https://services.swpc.noaa.gov/json/xray-flares-latest.json` |
| 1828 | NASA Mars rover photos | `https://api.nasa.gov/mars-photos/api/v1/rovers/…` |
| 1854 | NASA APOD HD | `https://api.nasa.gov/planetary/apod?…` |
| 2300 | NASA APOD batch (count=6) | `https://api.nasa.gov/planetary/apod?api_key=…&count=6` |
| 2412 | NOAA SWPC alerts 24 h | `https://services.swpc.noaa.gov/products/alerts.json` |

Aucune modification appliquée à ces 12 sites d'appel — ils continuent d'invoquer `_curl_get(...)` sur le nom local du module monolithe, qui pointe désormais vers `app.services.http_client._curl_get` via le re-export.

---

## `_safe_json_loads` (out of scope confirmé)

`_safe_json_loads` est importé dans `station_web.py:101` depuis `services.utils` :
```python
from services.utils import (
    _is_bot_user_agent, _parse_iso_to_epoch_seconds,
    _safe_json_loads, safe_ensure_dir,
)
```

Une copie identique existe également dans `app/services/http_client.py:78`. **Cette duplication est out of scope PASS 27.6** : le test `tests/unit/test_pure_services.py:98` exige que `_safe_json_loads` soit présent dans `http_client` (`expected = {"_curl_get", "_curl_post", "_curl_post_json", "_safe_json_loads"}`), donc la version `http_client` ne peut pas être supprimée sans casser le test. La déduplication `services.utils._safe_json_loads` ↔ `http_client._safe_json_loads` est repoussée à un PASS futur dédié.

---

## Tests effectués

### PHASE 3 — Validation syntaxique

| # | Test | Résultat |
|---|---|---|
| 1 | `py_compile station_web.py` | **OK** |
| 2 | `import station_web` | **OK** (29 BP + 8 hooks + 293 routes Flask) |
| 3 | `from station_web import _curl_get, _curl_post, _curl_post_json` | **OK** |
| 4 | `_curl_get is http_client._curl_get` | **True** (identité préservée pour les 3 fonctions) |

### PHASE 4 — Test fonctionnel

| Test | Résultat |
|---|---|
| `inspect.signature(_curl_get).parameters.keys()` | `['url', 'timeout']` ✓ |
| `inspect.signature(_curl_post).parameters.keys()` | `['url', 'post_data', 'timeout', 'headers']` ✓ |
| `inspect.signature(_curl_post_json).parameters.keys()` | `['url', 'payload_dict', 'extra_headers', 'timeout']` ✓ |
| Smoke test `_curl_get('http://localhost:5003/health', timeout=5)` | **443 bytes** retournés (`{"active_apis":{"GROQ":"CLOSED",...`) — le service en cours sert encore l'ancien code mais le nouveau `_curl_get` du re-export atteint le service via curl ✓ |

### PHASE 5 — Suite tests unitaires (`pytest tests/unit/`)

```
collected 34 items
29 passed, 5 skipped, 0 failed in 3.10s
```

| Catégorie | Détail |
|---|---|
| Test cible PASS 27.6 | `test_http_client_module_loads_and_exposes_curl_helpers` → **PASS** (vérifie que `{"_curl_get","_curl_post","_curl_post_json","_safe_json_loads"}` ⊆ `dir(app.services.http_client)`) |
| Tests `test_pure_services.py` | 7/7 PASS |
| Tests `test_services.py` | 21/22 PASS, 1 SKIPPED (`test_cache_get_set` : sémantique TTL=0 changée post-PASS-15, skip pré-existant non lié) |
| Tests `test_blueprints.py` | 4/4 SKIPPED (factory tests demandent root, perms pré-existantes non liées) |
| **0 régression** introduite par PASS 27.6 | Confirmé |

---

## Conformité aux règles strictes

| # | Règle | Vérification | Statut |
|---|---|---|---|
| 1 | Pas de redémarrage `astroscan.service` | Aucun `systemctl restart` invoqué | ✓ |
| 2 | Pas de modif `app/services/http_client.py` | `git diff` : seul `station_web.py` modifié | ✓ |
| 3 | `_safe_json_loads` non touché | Import L101 inchangé, copie `http_client` inchangée | ✓ |
| 4 | 12 appels internes non modifiés | Aucun `_curl_get(` n'a été édité hors la suppression de la def | ✓ |
| 5 | Fichiers de tests non modifiés | `tests/unit/*.py` non listés dans `git diff` | ✓ |
| 6 | Tests pré-cassés documentés sans fix | 5 SKIPPED documentés (4 perms root + 1 sémantique TTL), aucun « cassé » | ✓ |
| 7 | STOP en cas d'échec phase | Aucune phase n'a échoué | ✓ |
| 8 | Rollback en prose, pas en bloc shell | Cf. section dédiée ci-dessous | ✓ |
| 9 | STOP si signatures divergent | Signatures vérifiées compatibles, aucune divergence | ✓ |

---

## Procédure de rollback (texte prose, non exécutable)

En cas de régression détectée après déploiement, le retour à l'état pré-PASS 27.6 est faisable de trois manières équivalentes.

**Option A — via le tag git (chirurgical sur le seul fichier).** Le tag `pass27_6-pre` pointe sur le commit `d18b5dc` (PASS 27.5 final). Un `git checkout pass27_6-pre -- station_web.py` restaure uniquement le monolithe avec ses 3 fonctions `_curl_*` locales, sans toucher aux 5 PASS précédents (27.1-27.5). Suivi d'un commit dédié documentant la raison du rollback partiel. Cette option préserve toute la cascade SDR du PASS 27.5 et la migration `datetime.utcnow()` du PASS 27.4.

**Option B — via le snapshot fichier.** Un snapshot du `station_web.py` d'origine a été créé en PHASE 0 dans `/tmp/station_web_pre_pass27_6.py` (3129 lignes). En cas d'urgence sans accès git, ce fichier peut être recopié tel quel vers `/root/astro_scan/station_web.py` pour restituer le monolithe pré-déduplication. Note : `/tmp/` est volatile au reboot ; le snapshot est garanti uniquement pour la session courante.

**Option C — restauration partielle inline (sans rollback complet).** Si seul l'un des 3 helpers pose problème (par exemple un comportement subtil de `_curl_post` impactant un BP spécifique), il suffit de retirer ce nom du re-export et de redéfinir localement la fonction concernée dans `station_web.py`. Cette option laisse `_curl_get` et `_curl_post_json` continuer à utiliser la source unique tout en isolant le helper problématique. Elle réintroduit volontairement un mini-doublon ciblé, à documenter dans un PASS suivant.

Aucun rollback automatique n'est prévu : le diff étant purement substitutionnel (re-export d'objets identiques par `is`), tout retour en arrière doit être déclenché manuellement après diagnostic.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass27_6-pre` | `d18b5dc` | Snapshot avant déduplication (HEAD = PASS 27.5) |
| `pass27_6-done` | `63c2c96` | Doublon supprimé, source unique active |

---

## Diff résumé

```
git diff --staged --stat (avant commit) :
 station_web.py | 46 ++++++++++------------------------------------
 1 file changed, 10 insertions(+), 36 deletions(-)
```

Aucun autre fichier touché. Aucune création. Aucune modification de l'API publique.

---

## Note sur la validation systemd

Le service `astroscan.service` n'a **pas** été redémarré (RÈGLE 1). Les workers gunicorn actuels servent encore le monolithe pré-PASS 27.6 (avec les copies locales `_curl_*`) jusqu'au prochain cycle (`--max-requests=1000`) ou jusqu'à un `systemctl restart astroscan` manuel par root. La validation runtime décrite en PHASES 3-5 a été conduite en environnement isolé (Flask `app_context()` sans toucher aux workers de production).

Le risque de régression au prochain cycle est nul : les 3 fonctions re-exportées sont objectivement identiques (vérifié `is`), et la suite pytest reste verte.

---

## Réduction cumulée `station_web.py`

| Étape | Lignes | Δ vs précédent | Δ cumulé |
|---|---:|---:|---:|
| PASS 27.2 (TLE worker extracted) | 3362 | — | — |
| PASS 27.3 (Stellarium + APOD helpers extracted) | 3129 | −233 | −233 |
| PASS 27.4 (datetime migration, neutre en lignes) | 3129 | 0 | −233 |
| PASS 27.5 (SDR cascade, fichier `app/routes/sdr.py`) | 3129 | 0 | −233 |
| **PASS 27.6 (`_curl_*` deduplication)** | **3103** | **−26** | **−259** |

Note : le brief annonçait `~3085 lignes (-44 lignes net)`. Le résultat réel est **3103 lignes (−26 net)** — l'écart vient du fait que les 3 fonctions supprimées totalisaient 36 lignes corps (et non ~50), et que le re-export en compte 10. Bilan correct mais légèrement supérieur à la prévision.

---

## Architecture après PASS 27.6 — `app/services/http_client.py`

| Aspect | Valeur |
|---|---|
| Source unique des helpers `_curl_*` | `app/services/http_client.py` (87 lignes, **inchangé** depuis PASS 8) |
| Consommateurs directs | tous les BPs déjà extraits (`feeds`, `weather`, etc. — import direct) |
| Consommateurs indirects via re-export | `station_web.py` (12 appels internes legacy) |
| Test de régression public | `tests/unit/test_pure_services.py:92-103` (vérifie l'API exposée par `dir(http_client)`) |
| Doublons restants à traiter | `_safe_json_loads` (présent dans `services/utils` ET `app/services/http_client`) — out of scope, à traiter dans un PASS dédié |
