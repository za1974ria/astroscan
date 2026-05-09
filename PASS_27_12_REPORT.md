# PASS 27.12 — Déduplication `_fetch_hubble` + `_fetch_swpc_alerts` via re-export aliasé

**Date** : 2026-05-09
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass27_12-pre` (avant) → `pass27_12-done` (après)
**Snapshot** : `/tmp/station_web_pre_pass27_12.py` + `/tmp/PASS_27_12_INVENTORY.md`
**Commit** : `f8d6c81`
**Cas détecté** : **CAS A** (les 2 fonctions sémantiquement identiques)

---

## Résumé

Suppression de 2 doublons morts orphelins dans `station_web.py` :
- `_fetch_hubble` (30 lignes, doublonnait `telescope_sources.fetch_hubble_images` depuis PASS 9)
- `_fetch_swpc_alerts` (76 lignes, doublonnait `external_feeds.fetch_swpc_alerts` depuis PASS 8)

Re-export aliasé `as _fetch_*` depuis le shim monolithe (pattern PASS 27.11). Aucun service touché. Sources de vérité `telescope_sources.py` et `external_feeds.py` inchangées.

| Métrique | Avant | Après |
|---|---:|---:|
| `station_web.py` | 2449 lignes | **2355 lignes** (−94 nettes) |
| `app/services/telescope_sources.py` | 138 | **138 (inchangé)** |
| `app/services/external_feeds.py` | 307 | **307 (inchangé)** |
| Bloc supprimé du monolithe | 106 lignes corps (2 fns) | 12 lignes (1 import re-export aliasé) |
| Tests `tests/unit/` | 29 PASS / 5 SKIPPED / 0 FAIL | **29 PASS / 5 SKIPPED / 0 FAIL** |
| Cap monolithe | < 2500 (PASS 27.11) | **< 2400 lignes franchi** |

Note métriques : le brief annonçait `~2107 lignes CAS A (-342 net)` en prévoyant `_fetch_hubble ~74 lignes` et `_fetch_swpc_alerts ~273 lignes`. Recompte précis = **30 + 76 = 106 lignes corps** (vs 347 estimées). Le brief sur-estimait par un facteur ~3,3 — pattern récurrent dans la série PASS 27.x.

---

## PHASE 1 — Verdict d'analyse de divergence

### `_fetch_hubble` (monolithe L1808-1837) vs `fetch_hubble_images` (telescope_sources L109-137)

**Verdict : IDENTIQUE sémantiquement → CAS A appliqué**

| Aspect | Monolithe | Service | Identique ? |
|---|---|---|---|
| Signature | `_fetch_hubble()` | `fetch_hubble_images()` | ✓ aucun argument, retourne `list[dict]` |
| Source 1 — URL | `https://api.nasa.gov/planetary/apod?api_key={NASA_KEY}&count=6` | identique | ✓ |
| Source 1 — timeout | 10s | 10s | ✓ |
| Source 1 — parsing | iter `items`, filtre `media_type == 'image'`, build `{title, url, date}` (priorité `hdurl > url`) | identique | ✓ |
| Source 2 — fallback | 6 images Webb hardcodées (Piliers, M51, Carène, Stephan, M31, M42) | identique (mêmes URLs, mêmes titres) | ✓ |
| Différences | quotes (`'NASA_KEY'`), pas de docstring | quotes (`"NASA_KEY"`), docstring `"""Liste de 6 images Hubble..."""` | cosmétique uniquement |

### `_fetch_swpc_alerts` (monolithe L1920-1995) vs `fetch_swpc_alerts` (external_feeds L236-307)

**Verdict : IDENTIQUE sémantiquement → CAS A appliqué**

| Aspect | Monolithe | Service | Identique ? |
|---|---|---|---|
| Signature | `_fetch_swpc_alerts()` | `fetch_swpc_alerts()` | ✓ aucun argument, retourne `list[dict]` |
| Endpoint | `https://services.swpc.noaa.gov/products/alerts.json`, timeout 12s | identique | ✓ |
| Cutoff | 24h via `_dt.datetime.now(_dt.timezone.utc) - timedelta(hours=24)` | identique | ✓ |
| Parsing date | 2 patterns essayés : `'%Y-%m-%d %H:%M'` puis `'%Y-%m-%dT%H:%M'`, fallback `now(UTC)` | identique | ✓ |
| Catégories alertes | 4 (`GEOMAGNETIC`, `SOLAR FLARE/X-RAY`, `RADIATION STORM`, `RADIO BLACKOUT`) | identique | ✓ |
| Niveaux par catégorie | 5 chacun (G1-G5, S1-S5, R1-R5) | identique | ✓ |
| Regex spéciales | K-index `r'K-?index\s+of\s+(\d)'`, X-flare `r'\b([XMC]\d[\.\d]*)\b'` | identiques | ✓ |
| Tri final | desc par `issued_dt`, slice `[:10]` | identique | ✓ |
| Fields retournés | `{type, level, message[:300], issued, issued_dt}` | identique | ✓ |
| Différences | `import datetime as _dt` lazy inside, `import re as _re` lazy local, single quotes | top-level `import datetime as _dt`, top-level `import re`, double quotes | cosmétique uniquement |

**Conclusion PHASE 1** : aucune divergence sémantique sur les 2 fonctions. CAS A confirmé sans ambiguïté. La règle 4 du brief (« SI les fonctions divergent sémantiquement : SKIP ») n'a pas été déclenchée.

---

## Patch appliqué (CAS A)

### Côté `station_web.py`

**Avant** : 2 fonctions définies localement, 106 lignes corps cumulés (positions L1808-1837 + L1920-1995, séparées par ~80 lignes de commentaires `# MIGRATED TO ...` et un dict `_NEWS_TRADUCTIONS` + fonction `_apply_news_translations`).

**Après** :
- L1808 : 1 bloc d'import re-export aliasé (12 lignes) avec docstring expliquant la migration
- L1920 ancienne (position de `_fetch_swpc_alerts`) : remplacée par 3 lignes de commentaire pointeur :
  ```python
  # PASS 27.12 (2026-05-09) — _fetch_swpc_alerts déplacée vers
  # app.services.external_feeds.fetch_swpc_alerts (re-exportée plus haut via le
  # bloc d'aliasing PASS 27.12).
  ```

```python
# PASS 27.12 (2026-05-09) — _fetch_hubble + _fetch_swpc_alerts (~106 lignes corps
# cumulés) déduplication via re-export aliasé vers les services existants
# (pattern PASS 27.11). Sources de vérité :
#   - app.services.telescope_sources.fetch_hubble_images (PASS 9, identique)
#   - app.services.external_feeds.fetch_swpc_alerts (PASS 8, identique)
# Doublons morts orphelins éliminés (0 appel actif, 0 consommateur externe via
# `from station_web import _fetch_hubble | _fetch_swpc_alerts`).
from app.services.telescope_sources import fetch_hubble_images as _fetch_hubble  # noqa: F401
from app.services.external_feeds import fetch_swpc_alerts as _fetch_swpc_alerts  # noqa: F401
```

### Côté services

`telescope_sources.py` et `external_feeds.py` **inchangés**. Aucun touch sur la source unique.

---

## Tests effectués

### PHASE 4 — Validation syntaxique

| # | Test | Résultat |
|---|---|---|
| 1 | `py_compile station_web.py` | **OK** |
| 2 | `import station_web` (avec patches `.env`/handler/sqlite) | **OK** (29 BP + 8 hooks + 293 routes Flask) |
| 3 | `from station_web import _fetch_hubble, _fetch_swpc_alerts` | **OK** |
| 4 | Identité (re-export aliasé = source) — preuves `is` | **2/2 True** |

| Symbole monolithe | `station_web.X is service.Y` | Statut |
|---|---|---|
| `_fetch_hubble` | `is telescope_sources.fetch_hubble_images` | **True** |
| `_fetch_swpc_alerts` | `is external_feeds.fetch_swpc_alerts` | **True** |

### PHASE 5 — Suite tests unitaires `pytest tests/unit/`

```
collected 34 items
29 passed, 5 skipped, 0 failed in 3.25s
```

Identique à la baseline pré-PASS 27.12 (PASS 27.11 final). **Aucune régression**.

---

## Imports legacy préservés (preuve par grep)

```
$ grep -rn "from station_web import.*_fetch_hubble\|from station_web import.*_fetch_swpc_alerts" \
       /root/astro_scan --include="*.py" | grep -v __pycache__ | grep -v "backup\|.archive"

(aucun résultat)
```

**Aucun consommateur externe** des 2 fonctions via `from station_web import`. Le brief mentionnait « preuve par grep des 7 appels `_fetch_hubble` si CAS A » — recompte réel = **0 appel actif**, 0 consommateur. Les 2 défs étaient orphelines depuis :
- `_fetch_hubble` : PASS 9 (route `/api/hubble/images` migrée vers `telescope_bp`, qui consomme `fetch_hubble_images` depuis le service)
- `_fetch_swpc_alerts` : PASS 8 (route `/api/space-weather/alerts` migrée vers `feeds_bp`, qui consomme `fetch_swpc_alerts` depuis le service)

Le commentaire monolithe L1841 le confirme explicitement :
> `# MIGRATED TO telescope_bp PASS 9 — /api/hubble/images → see app/blueprints/telescope/__init__.py (api_hubble_images)`

Le re-export aliasé reste **purement défensif** — préserve la rétro-compatibilité d'un import futur potentiel `from station_web import _fetch_hubble`.

---

## Conformité aux règles strictes

| # | Règle | Vérification | Statut |
|---|---|---|---|
| 1 | Pas de redémarrage `astroscan.service` | Aucun `systemctl restart` invoqué | ✓ |
| 2 | Pas de modif `telescope_sources.py` / `external_feeds.py` | `git diff --stat` : seul `station_web.py` modifié | ✓ |
| 3 | Pas de suppression du re-export | Re-export présent ligne ~1808 station_web.py (2 alias) | ✓ |
| 4 | SKIP si fonctions divergent | Aucune divergence — CAS A confirmé pour les 2 fonctions | ✓ |
| 5 | STOP si tests existants cassés | 29 PASS / 5 SKIPPED / 0 FAIL — identique à baseline | ✓ |
| 6 | Rollback en prose, pas en bloc shell | Cf. section dédiée ci-dessous | ✓ |
| 7 | CAS C (rien à faire) → pas de commit | N/A — CAS A applicable, commit légitime | ✓ |

---

## Procédure de rollback (texte prose, non exécutable)

En cas de régression détectée après déploiement, le retour à l'état pré-PASS 27.12 est faisable de trois manières équivalentes.

**Option A — via le tag git (recommandée).** Le tag `pass27_12-pre` pointe sur le commit `fc745a2` (PASS 27.11 final). Un `git checkout pass27_12-pre -- station_web.py` restaure le monolithe avec ses 2 fonctions définies localement, sans toucher aux 10 PASS précédents (27.1-27.11). Suivi d'un commit dédié documentant la raison du rollback. Cette option ré-introduit le doublon mort de 106 lignes (acceptable temporairement puisque c'était l'état pré-PASS qui n'avait pas causé de problème détecté en 6 jours d'exécution).

**Option B — via le snapshot fichier.** Un snapshot du `station_web.py` d'origine a été créé en PHASE 0 dans `/tmp/station_web_pre_pass27_12.py` (2449 lignes). En cas d'urgence sans accès git, ce fichier peut être recopié vers `/root/astro_scan/station_web.py` pour restituer l'état pré-PASS. Note : `/tmp/` est volatile au reboot ; le snapshot est garanti uniquement pour la session de déploiement courante. Aucun service à restaurer (`telescope_sources.py` et `external_feeds.py` n'ont pas été modifiés).

**Option C — restauration partielle (préserver le travail sur l'une des 2).** Si la régression provient uniquement d'un alias spécifique (extrêmement improbable étant donné l'identité préservée vérifiée par `is`), il suffit de retirer le nom problématique du re-export ligne ~1808 station_web.py et de redéfinir localement la fonction concernée. Par exemple, si `_fetch_hubble` posait problème, on retire la ligne `from app.services.telescope_sources import fetch_hubble_images as _fetch_hubble` et on copie verbatim la définition d'origine depuis le snapshot. Cela laisse `_fetch_swpc_alerts` continuer à utiliser la source unique. Réintroduction volontaire d'un mini-doublon ciblé.

Aucun rollback automatique n'est prévu : le diff étant une suppression de doublons morts + ajout d'aliases (objets identiques par `is`), tout retour en arrière doit être déclenché manuellement après diagnostic.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass27_12-pre` | `fc745a2` | Snapshot avant déduplication (HEAD = PASS 27.11) |
| `pass27_12-done` | `f8d6c81` | 2 doublons supprimés, 2 alias actifs |

---

## Diff résumé

```
git diff --staged --stat (avant commit) :
 station_web.py | 118 ++++++---------------------------------------------------
 1 file changed, 12 insertions(+), 106 deletions(-)
```

Aucun autre fichier touché. Aucune création de fichier (hors le rapport et l'inventaire `/tmp/`). Aucune modification de l'API publique des services.

---

## Note sur la validation systemd

Le service `astroscan.service` n'a **pas** été redémarré (RÈGLE 1). Les workers gunicorn actuels servent encore le monolithe pré-PASS 27.12 (avec les 2 copies locales `_fetch_hubble` L1808-1837 et `_fetch_swpc_alerts` L1920-1995) jusqu'au prochain cycle (`--max-requests=1000`) ou jusqu'à un `systemctl restart astroscan` manuel par root. La validation runtime décrite en PHASES 4-5 a été conduite en environnement isolé (Flask `app_context()` sans toucher aux workers de production).

Le risque de régression au prochain cycle est nul : les 2 fonctions re-exportées sont identiques par `is` (l'aliasing Python ne crée pas de wrapper), le pytest reste vert, les blueprints `telescope_bp` et `feeds_bp` consomment depuis les services directement (donc indépendants du re-export shim monolithe).

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
| **PASS 27.12 (`_fetch_hubble` + `_fetch_swpc_alerts` dédup, 2 fns)** | **2355** | **−94** | **−1007** |

Note brief : le brief annonçait `~2107 lignes CAS A (-342 net)`. Le résultat réel est **2355 lignes (−94 net)** — l'écart vient du recompte réel des lignes corps (106 vs 347 estimées au brief, cf. analyse PHASE 1).

Cap symbolique des **2400 lignes franchi** dans le monolithe. Cap des **−1000 lignes cumulées franchi** sur la série PASS 27.x.

---

## Synthèse pattern « DÉDUPLICATION doublons PASS 8 / 9 / 15 / 16 » sur la série PASS 27.x

| PASS | Service cible | Doublons supprimés | Nb fonctions/symboles | Lignes économisées |
|---|---|---|---:|---:|
| 27.6 | `app/services/http_client.py` (PASS 8) | `_curl_get`, `_curl_post`, `_curl_post_json` | 3 | 26 |
| 27.8 | `app/services/telescope_sources.py` (PASS 9) | `_source_path`, `_fetch_apod_live`, `_fetch_hubble_archive`, `_fetch_apod_archive_live`, `_fetch_hubble_live`, `_IMAGE_CACHE_TTL` | 5 + alias + const | 52 |
| 27.11 | `app/services/external_feeds.py` (PASS 8) | `_fetch_voyager`, `_fetch_neo`, `_fetch_solar_wind`, `_fetch_solar_alerts`, `_fetch_mars_rover`, `_fetch_apod_hd` | 6 | 169 |
| **27.12** | **`telescope_sources.py` + `external_feeds.py`** | **`_fetch_hubble`, `_fetch_swpc_alerts`** | **2** | **94** |
| **Total série déduplication** | **2 services** | **15+ symboles distincts** | **16** | **−341 lignes** |

Pattern cohérent : créer le module service en PASS X (typiquement PASS 8/9), puis supprimer le doublon monolithe en PASS 27.X plusieurs jours/semaines plus tard. Ces 4 PASS de déduplication représentent **~34% de la réduction totale** de la série PASS 27.x (−341 sur −1007).

---

## Architecture après PASS 27.12 — sources uniques consolidées

| Service | Fonctions exposées | Consommateurs directs |
|---|---|---|
| `app/services/telescope_sources.py` | `_source_path`, `_fetch_apod_live`, `_fetch_hubble_archive` (alias `_fetch_hubble_live`), `_fetch_apod_archive_live`, `fetch_hubble_images`, `_IMAGE_CACHE_TTL` | `app/blueprints/telescope/__init__.py` |
| `app/services/external_feeds.py` | `fetch_voyager`, `fetch_neo`, `fetch_solar_wind`, `fetch_solar_alerts`, `fetch_mars_rover`, `fetch_apod_hd`, `fetch_swpc_alerts` | `app/blueprints/feeds/__init__.py` |
| `station_web.py` (shim) | re-exports défensifs (`_curl_*`, `_fetch_*`, `_source_path`, `_IMAGE_CACHE_TTL`...) | (aucun consommateur actuel — défensif pour future rétro-compat) |

**Aucun doublon connu restant** entre `station_web.py` et les services `telescope_sources.py` / `external_feeds.py`. La série PASS 27.x a complété la déduplication de l'ensemble des fetchers externes extraits aux PASS 8/9.
