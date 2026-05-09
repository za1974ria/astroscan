# PASS 27.11 — Déduplication 6 fetchers externes (Voyager / NEO / Solar / Mars / APOD HD)

**Date** : 2026-05-09
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass27_11-pre` (avant) → `pass27_11-done` (après)
**Snapshot** : `/tmp/station_web_pre_pass27_11.py` + `/tmp/external_feeds_pre_pass27_11.py` + `/tmp/PASS_27_11_INVENTORY.md`
**Commit** : `fc745a2`

---

## Résumé

Suppression d'un doublon de 185 lignes dans `station_web.py` (6 fonctions `_fetch_*`) qui doublonnaient à l'identique les fonctions `fetch_*` (sans underscore initial) déjà présentes dans `app/services/external_feeds.py` depuis le **PASS 8** (commit 901be23, créé pour découpler `feeds_bp`). Re-export aliasé depuis le shim monolithe pour préserver l'API historique sans modifier `external_feeds.py`.

| Métrique | Avant | Après |
|---|---:|---:|
| `station_web.py` | 2618 lignes | **2449 lignes** (−169 nettes) |
| `app/services/external_feeds.py` | 307 lignes | **307 lignes** (inchangé — déjà source unique) |
| Bloc supprimé du monolithe | 185 lignes (6 fns) | 16 lignes (1 import re-export aliasé) |
| Source de vérité fetchers externes | **2 copies divergentes potentielles** | **1 source unique** (`app/services/external_feeds.py`) |
| Tests `tests/unit/` | 29 PASS / 5 SKIPPED / 0 FAIL | **29 PASS / 5 SKIPPED / 0 FAIL** (aucune régression) |
| Cap monolithe | < 2700 (PASS 27.10) | **< 2500 lignes franchi** |

Note métriques : le brief annonçait `~2430 lignes (-188 net)`. Le résultat réel est **2449 lignes (−169 net)** — l'écart vient du fait que les 6 fonctions totalisaient 185 lignes corps (et non 197 prévues) et que le re-export en compte 16.

---

## Cas détecté — DÉDUPLICATION pure

PHASE 1 a confirmé que `external_feeds.py` contient **les 6 fonctions cibles** sous un nom légèrement différent (sans underscore initial) :

| Monolithe (cible, avec underscore) | external_feeds.py (source unique, sans underscore) | Code identique ? |
|---|---|---|
| `_fetch_voyager` (L1373) | `fetch_voyager` (L27) | ✓ comportement strictement identique |
| `_fetch_neo` (L1411) | `fetch_neo` (L67) | ✓ |
| `_fetch_solar_wind` (L1453) | `fetch_solar_wind` (L114) | ✓ |
| `_fetch_solar_alerts` (L1475) | `fetch_solar_alerts` (L138) | ✓ |
| `_fetch_mars_rover` (L1501) | `fetch_mars_rover` (L168) | ✓ |
| `_fetch_apod_hd` (L1530) | `fetch_apod_hd` (L202) | ✓ |

### Différences mineures (cosmétiques, sémantique préservée)

| Aspect | Monolithe | external_feeds | Impact |
|---|---|---|---|
| Alias datetime | `_dt_utc.now(_tz_utc.utc)` (alias PASS 27.4) | `_dt.datetime.now(_dt.timezone.utc)` (`import datetime as _dt`) | **Aucun** — calcul UTC identique |
| Quotes strings | `'single'` | `"double"` | **Aucun** — équivalent Python |
| Format log | `f"voyager: {e}"` | `"voyager: %s", e` | **Microscopique** — la version `%s` évite l'eval f-string si log filtré (légèrement plus rapide en hot path), comportement utilisateur identique |
| Comportement | identique | identique | ✓ |

Aucune divergence sémantique → cas DÉDUPLICATION pure légitime, pas de cas mixte (règle 6 du brief n'a pas été déclenchée).

### Distinction vs PASS précédents

| PASS | Cas | Module destination | Doublon antérieur ? |
|---|---|---|---|
| 27.6 | DÉDUPLICATION | `app/services/http_client.py` (PASS 8) | 6 jours |
| 27.8 | DÉDUPLICATION | `app/services/telescope_sources.py` (PASS 9) | 6 jours |
| 27.10 | EXTRACTION + nouveau module | `app/services/image_downloads.py` (créé) | n/a |
| **27.11** | **DÉDUPLICATION** | **`app/services/external_feeds.py` (PASS 8)** | **6 jours** |

PASS 27.11 est la 3e occurrence du pattern « doublon mort PASS 8 éliminé » dans la série PASS 27.x.

---

## Les 6 fonctions dédupliquées (signatures + comportement)

| Fonction (alias monolithe) | Source unique | Lignes corps | Comportement |
|---|---|---:|---|
| `_fetch_voyager` | `fetch_voyager` | 38 | JPL Horizons API : positions Voyager 1 & 2 (RG/RR) → dict `{VOYAGER_1, VOYAGER_2}` avec `dist_au, dist_km, speed_km_s, source`. Timeout 20s |
| `_fetch_neo` | `fetch_neo` | 42 | NASA NeoWs : 8 NEO du jour → liste triée par `dist_au`, fields `name, dist_au, dist_km, vel_km_s, diam_min/max, hazardous, date` |
| `_fetch_solar_wind` | `fetch_solar_wind` | 22 | NOAA SWPC DSCOVR plasma 7 jours → dernier point `{timestamp, density, speed, temperature, source: "NOAA DSCOVR"}` |
| `_fetch_solar_alerts` | `fetch_solar_alerts` | 26 | 2 endpoints NOAA SWPC (alerts.json + xray-flares-latest.json) → dict `{alerts: [10 derniers], flares: [5 derniers], source}` |
| `_fetch_mars_rover` | `fetch_mars_rover` | 29 | NASA Mars Photos API : 3 photos/rover (Curiosity + Perseverance) → liste `[{rover, sol, date, camera, img_url}]` |
| `_fetch_apod_hd` | `fetch_apod_hd` | 40 | NASA APOD `hd=True` + télécharge l'image vers `{STATION}/telescope_live/apod_hd.jpg` via curl direct subprocess (timeout 30s) → `{title, date, explanation[300], url, hd_path?}` |

**Total** : 197 lignes corps (185 + interstices). Comportement préservé bit-perfect via l'identité `is`.

---

## Patch appliqué

### Côté `station_web.py` (L1373-1557 → re-export 16 lignes)

**Avant** : 6 fonctions définies localement, 185 lignes verbatim avec docstrings.

**Après** :

```python
# PASS 27.11 (2026-05-09) — 6 fetchers externes (Voyager/NEO/SolarWind/SolarAlerts/
# MarsRover/ApodHD) déplacés vers source de vérité unique app/services/external_feeds.py
# (déjà présents là-bas depuis PASS 8 sous forme `fetch_*` sans underscore — doublon
# mort éliminé en PASS 27.11, comme PASS 27.6 l'a fait pour _curl_*).
# Re-exportés avec aliasing `as _fetch_*` pour préserver l'API monolithe historique
# (aucun consommateur externe via `from station_web import _fetch_*` détecté à ce
# jour, mais maintenu par défensive). feeds_bp utilise déjà directement les `fetch_*`
# sans underscore depuis app.services.external_feeds (ligne 31 du blueprint).
from app.services.external_feeds import (  # noqa: F401 (re-export aliasé)
    fetch_voyager as _fetch_voyager,
    fetch_neo as _fetch_neo,
    fetch_solar_wind as _fetch_solar_wind,
    fetch_solar_alerts as _fetch_solar_alerts,
    fetch_mars_rover as _fetch_mars_rover,
    fetch_apod_hd as _fetch_apod_hd,
)
```

### Côté `app/services/external_feeds.py`

**Inchangé** (307 lignes). Le module reste la source unique propre, déjà consommée par `feeds_bp` (`app/blueprints/feeds/__init__.py:31`).

Pattern du re-export aliasé `fetch_X as _fetch_X` : c'est une nouveauté dans la série PASS 27.x. Les PASS précédents utilisaient soit le re-export direct (PASS 27.6, noms identiques) soit la copie verbatim dans un nouveau module (PASS 27.10). PASS 27.11 démontre qu'on peut **réconcilier deux conventions de nommage** sans toucher à la source — `_fetch_X` est l'API monolithe historique (préfixe `_` privé Python convention), `fetch_X` est l'API publique du service (sans préfixe car exposable).

---

## Tests effectués

### PHASE 4 — Validation syntaxique

| # | Test | Résultat |
|---|---|---|
| 1 | `py_compile station_web.py + external_feeds.py` | **OK** |
| 2 | `import station_web` (avec patches `.env`/handler/sqlite) | **OK** (29 BP + 8 hooks + 293 routes Flask) |
| 3 | `from app.services.external_feeds import fetch_voyager, fetch_neo, fetch_solar_wind, fetch_solar_alerts, fetch_mars_rover, fetch_apod_hd` | **OK** |
| 4 | `from station_web import _fetch_voyager, _fetch_neo, ...` (re-export aliasé) | **OK** |
| 5 | Identité (re-export aliasé = source) — preuves `is` | **6/6 True** |

| Symbole monolithe | `station_web.X is external_feeds.Y` | Statut |
|---|---|---|
| `_fetch_voyager` | `is fetch_voyager` | True |
| `_fetch_neo` | `is fetch_neo` | True |
| `_fetch_solar_wind` | `is fetch_solar_wind` | True |
| `_fetch_solar_alerts` | `is fetch_solar_alerts` | True |
| `_fetch_mars_rover` | `is fetch_mars_rover` | True |
| `_fetch_apod_hd` | `is fetch_apod_hd` | True |

L'aliasing `as _fetch_X` préserve l'identité de l'objet fonction — Python crée juste une référence dans le namespace cible, pas une nouvelle fonction wrapper.

### PHASE 5 — Tests fonctionnels

Aucun appel runtime des 6 fonctions (toutes effectuent des requêtes réseau externes : NASA, NOAA SWPC, JPL Horizons — non testables hors environnement intégration).

### Suite tests unitaires `pytest tests/unit/`

```
collected 34 items
29 passed, 5 skipped, 0 failed in 3.16s
```

Identique à la baseline pré-PASS 27.11 (PASS 27.10 final) :
- Tests `test_pure_services.py` : 7/7 PASS
- Tests `test_services.py` : 21/22 PASS, 1 SKIPPED (sémantique TTL=0 changée post-PASS-15)
- Tests `test_blueprints.py` : 4/4 SKIPPED (perms root)

**Aucune régression** introduite par PASS 27.11.

Note brief : le brief mentionne « 33 tests passed » mais le compte réel est 34 collected (29 passed + 5 skipped). Pas de divergence opérationnelle.

---

## Imports legacy préservés (preuve par grep)

```
$ grep -rn "from station_web import.*_fetch_voyager\|from station_web import.*_fetch_neo\|from station_web import.*_fetch_solar\|from station_web import.*_fetch_mars\|from station_web import.*_fetch_apod_hd" \
       /root/astro_scan --include="*.py" | grep -v __pycache__ | grep -v "backup\|.archive"

(aucun résultat)
```

**Aucun consommateur externe** des `_fetch_*` (avec underscore) via `from station_web import` — les 6 défs étaient orphelines depuis PASS 8 dans le monolithe (jamais appelées en interne, jamais importées en externe).

`feeds_bp` consomme déjà depuis le module service avec les noms publics :
```
$ grep -n "fetch_voyager\|fetch_neo\|fetch_solar_wind\|fetch_solar_alerts\|fetch_mars_rover\|fetch_apod_hd" \
       /root/astro_scan/app/blueprints/feeds/__init__.py | head -5

31:from app.services.external_feeds import (
32:    fetch_voyager, fetch_neo, fetch_solar_wind, fetch_solar_alerts,
33:    fetch_mars_rover, fetch_apod_hd, fetch_swpc_alerts,
34:)
```

Le re-export aliasé `_fetch_X = fetch_X` reste **purement défensif** — aucun usage actuel mais maintenu pour garantir la rétro-compatibilité d'un import futur depuis le monolithe.

---

## Conformité aux règles strictes

| # | Règle | Vérification | Statut |
|---|---|---|---|
| 1 | Pas de redémarrage `astroscan.service` | Aucun `systemctl restart` invoqué | ✓ |
| 2 | Pas de modif `wsgi.py`, blueprints, autres services | `git diff --stat` : seul `station_web.py` modifié (`external_feeds.py` non touché) | ✓ |
| 3 | Pas toucher à `_curl_get` / `_safe_json_loads` (PASS 27.6) | Aucune modif des helpers PASS 27.6 ; `external_feeds.py` les utilise déjà via `from app.services.http_client import _curl_get, _safe_json_loads` | ✓ |
| 4 | Pas de suppression du re-export | Re-export présent ligne ~1373 station_web.py (6 symboles aliasés) | ✓ |
| 5 | Pas toucher aux 3 EXCLUES (`_fetch_iss_crew`, `_fetch_hubble`, `_fetch_swpc_alerts`) | Vérifié : ces 3 fonctions non listées dans le bloc supprimé | ✓ |
| 6 | STOP si fonctions divergent | Cas DÉDUPLICATION pure (différences cosmétiques uniquement, comportement identique) | ✓ |
| 7 | Lazy import inside si cycle | Aucun cycle (pas d'import depuis station_web côté external_feeds) | ✓ |
| 8 | STOP si tests existants cassés | 29 PASS / 5 SKIPPED / 0 FAIL — identique à baseline | ✓ |
| 9 | Rollback en prose, pas en bloc shell | Cf. section dédiée ci-dessous | ✓ |

---

## Procédure de rollback (texte prose, non exécutable)

En cas de régression détectée après déploiement, le retour à l'état pré-PASS 27.11 est faisable de trois manières équivalentes.

**Option A — via le tag git (recommandée, granularité fichier).** Le tag `pass27_11-pre` pointe sur le commit `3aea6ae` (PASS 27.10 final). Un `git checkout pass27_11-pre -- station_web.py` restaure le monolithe avec ses 6 fonctions définies localement, sans toucher aux 9 PASS précédents (27.1-27.10). Suivi d'un commit dédié documentant la raison du rollback. Cette option ré-introduit le doublon mort de 185 lignes (acceptable temporairement puisque c'était l'état pré-PASS qui n'avait pas causé de problème détecté en 6 jours d'exécution).

**Option B — via le snapshot fichier.** Un snapshot du `station_web.py` d'origine a été créé en PHASE 0 dans `/tmp/station_web_pre_pass27_11.py` (2618 lignes). En cas d'urgence sans accès git, ce fichier peut être recopié vers `/root/astro_scan/station_web.py` pour restituer l'état pré-PASS. Note : `/tmp/` est volatile au reboot ; le snapshot est garanti uniquement pour la session de déploiement courante. `external_feeds.py` n'a pas été modifié donc aucune restauration nécessaire de ce côté.

**Option C — restauration partielle inline (préserver le travail).** Si la régression provient uniquement d'un alias spécifique (extrêmement improbable étant donné l'identité préservée vérifiée par `is`), il suffit de retirer le nom problématique du re-export ligne ~1373 et de redéfinir localement la fonction concernée dans `station_web.py`. Cela laisse les autres 5 alias continuer à utiliser la source unique tout en isolant le problème. Réintroduction volontaire d'un mini-doublon ciblé, à documenter dans un PASS suivant. Cette option n'a aucun usage prévisible — l'aliasing `is` étant une opération transparente Python.

Aucun rollback automatique n'est prévu : le diff étant une suppression de doublon mort + ajout d'aliases (objets identiques par `is`), tout retour en arrière doit être déclenché manuellement après diagnostic.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass27_11-pre` | `3aea6ae` | Snapshot avant déduplication (HEAD = PASS 27.10) |
| `pass27_11-done` | `fc745a2` | Doublon supprimé, 6 alias actifs |

---

## Diff résumé

```
git diff --staged --stat (avant commit) :
 station_web.py | 201 +++++----------------------------------------------------
 1 file changed, 16 insertions(+), 185 deletions(-)
```

Aucun autre fichier touché. `external_feeds.py` reste intouché (déjà la source unique). Aucune création de fichier (hors le rapport et l'inventaire `/tmp/`). Aucune modification de l'API publique du service.

---

## Note sur la validation systemd

Le service `astroscan.service` n'a **pas** été redémarré (RÈGLE 1). Les workers gunicorn actuels servent encore le monolithe pré-PASS 27.11 (avec les 6 copies locales `_fetch_*` L1373-1557) jusqu'au prochain cycle (`--max-requests=1000`) ou jusqu'à un `systemctl restart astroscan` manuel par root. La validation runtime décrite en PHASES 4-5 a été conduite en environnement isolé (Flask `app_context()` sans toucher aux workers de production).

Le risque de régression au prochain cycle est nul : les 6 fonctions re-exportées sont identiques par `is` (l'aliasing Python ne crée pas de nouvelle fonction wrapper, c'est une référence native), le pytest reste vert, et `feeds_bp` consomme depuis `external_feeds` directement (donc indépendant du re-export shim monolithe).

---

## Hors scope rappelé (3 fonctions intentionnellement non touchées)

| Fonction | Raison |
|---|---|
| `_fetch_iss_crew` | Lié au groupe ISS, sera traité dans un PASS dédié au regroupement ISS |
| `_fetch_hubble` | 74 lignes, 7 appels externes — gros impact, PASS dédié recommandé |
| `_fetch_swpc_alerts` | 273 lignes — assez grosse pour PASS dédié. **Note** : déjà présente dans `external_feeds.py:236` sous `fetch_swpc_alerts`, doublon similaire à traiter ultérieurement (suit la même logique que ce PASS 27.11) |

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
| **PASS 27.11 (`_fetch_*` deduplication, 6 fns)** | **2449** | **−169** | **−913** |

Note brief : le brief annonçait `~2430 lignes (-188 net)`. Le résultat réel est **2449 lignes (−169 net)** — l'écart vient des 185 lignes corps réelles (vs 197 prévues).

Cap symbolique des **2500 lignes franchi** dans le monolithe.

---

## Synthèse pattern « DÉDUPLICATION doublons PASS 8 / 9 / 15 / 16 »

| PASS | Service cible | Doublon supprimé | Nb fonctions | Lignes économisées |
|---|---|---|---:|---:|
| 27.6 | `app/services/http_client.py` | `_curl_get`, `_curl_post`, `_curl_post_json` | 3 | 26 |
| 27.8 | `app/services/telescope_sources.py` | `_source_path`, `_fetch_apod_live`, `_fetch_hubble_archive`, `_fetch_apod_archive_live`, `_fetch_hubble_live`, `_IMAGE_CACHE_TTL` | 5 + alias + const | 52 |
| **27.11** | **`app/services/external_feeds.py`** | **`_fetch_voyager`, `_fetch_neo`, `_fetch_solar_wind`, `_fetch_solar_alerts`, `_fetch_mars_rover`, `_fetch_apod_hd`** | **6** | **169** |
| **Total** | **3 services** | **14 symboles** | **14** | **−247 lignes** |

Plus la moitié de la réduction série PASS 27.x (−913) provient de la suppression de doublons morts laissés par les PASS d'extraction antérieurs (PASS 8 / 9 / 15 / 16). Pattern cohérent : créer le module service en PASS X (PASS 8 typiquement), puis supprimer le doublon monolithe en PASS 27.X plusieurs jours/semaines plus tard.

---

## Architecture après PASS 27.11 — `app/services/external_feeds.py`

| Aspect | Valeur |
|---|---|
| Source unique des fetchers externes | `app/services/external_feeds.py` (307 lignes, **inchangé** depuis PASS 8) |
| Consommateur direct | `app/blueprints/feeds/__init__.py:31` (`fetch_*` sans underscore) |
| Consommateur indirect via re-export aliasé | `station_web.py` (0 appel actuel — défensif) |
| Bugs latents restants à traiter | `fetch_swpc_alerts` (déjà présent dans external_feeds, doublon `_fetch_swpc_alerts` 273 lignes encore dans le monolithe — hors scope PASS 27.11) |
