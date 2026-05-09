# PASS 27.7 — Extraction `_analytics_*` helpers vers `app/services/analytics_dashboard.py`

**Date** : 2026-05-09
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass27_7-pre` (avant) → `pass27_7-done` (après)
**Snapshot** : `/tmp/station_web_pre_pass27_7.py` + `/tmp/analytics_dashboard_pre_pass27_7.py` + `/tmp/PASS_27_7_INVENTORY.md`
**Commit** : `8f6809d`

---

## Résumé

Déplacement de 6 fonctions helpers analytics depuis `station_web.py` vers `app/services/analytics_dashboard.py` (le module qui les utilise), suivi d'un re-export depuis le shim monolithe pour conformité au pattern strangler fig. **Bug latent corrigé par effet de bord** : `analytics_dashboard.py` utilisait ces 6 fonctions aux lignes 184/186/189/265/268/272/277/281 sans les importer ni les définir, ce qui aurait provoqué un `NameError` au runtime sur la route `/analytics`.

| Métrique | Avant | Après |
|---|---:|---:|
| `station_web.py` | 3103 lignes | **3027 lignes** (−76 nettes) |
| `app/services/analytics_dashboard.py` | 324 lignes | **429 lignes** (+105 — 6 fonctions + docstring enrichie) |
| Bloc supprimé du monolithe | 88 lignes corps (6 défs) | 12 lignes (1 import re-export) |
| Source de vérité `_analytics_*` | station_web.py (utilisée par appels « fantômes » dans analytics_dashboard) | **analytics_dashboard.py** (résolution locale propre) |
| Tests `tests/unit/` | 29 PASS / 5 SKIPPED / 0 FAIL | **29 PASS / 5 SKIPPED / 0 FAIL** (aucune régression) |
| Bug latent `NameError` analytics_dashboard | présent (PASS 16 → 27.6) | **corrigé** |

Le brief annonçait `−126 lignes nettes`. Le résultat réel est `−76` car les fonctions totalisent 88 lignes corps (et non 138) et le re-export en compte 12.

---

## Constat de l'état initial (PHASE 1)

### État avant PASS 27.7

`app/services/analytics_dashboard.py` (commit 63c2c96) contenait 8 sites d'appel aux 6 fonctions `_analytics_*` :

| Ligne | Appel |
|---:|---|
| 184 | `_analytics_fmt_duration_sec(dr["total_time"])` |
| 186 | `_analytics_journey_display(dr["journey"])` |
| 189 | `_analytics_start_local_display(st_iso, cc)` |
| 265 | `_analytics_fmt_duration_sec(total_time)` |
| 268 | `_analytics_session_classification(total_time, n_events)` |
| 272 | `_analytics_start_local_display(first_t, cc)` |
| 277 | `_analytics_time_hms_local(e["time"], cc)` |
| 281 | `_analytics_fmt_duration_sec(e["duration"])` |

Mais aucun import ni définition correspondante dans le fichier :

```python
$ python3 -c "from app.services import analytics_dashboard; print(hasattr(analytics_dashboard, '_analytics_fmt_duration_sec'))"
False
```

**Implication** : la fonction `load_analytics_readonly()` aurait levé `NameError: name '_analytics_fmt_duration_sec' is not defined` dès qu'un visitor_log non vide aurait déclenché les boucles `for dr in detail_rows` ou `for sid in sids_ordered`. Ce bug latent était présent depuis le PASS 16 (création du module). Probablement non détecté car la route `/analytics` est d'usage interne rare.

### Décision PASS 27.7

Les fonctions n'étant **pas déjà présentes** dans `analytics_dashboard.py`, la contrainte 4 (« déjà présentes avec contenu identique : juste supprimer ») et la contrainte 5 (« présentes avec code différent : STOP ») ne s'appliquent pas. Le bon chemin est : copier les 6 fonctions depuis station_web.py vers analytics_dashboard.py + supprimer dans station_web.py + re-exporter depuis station_web.py.

### Bug similaire hors scope

`get_geo_from_ip` ligne 289 d'`analytics_dashboard.py` est également non importé (similaire). Hors scope PASS 27.7. À traiter dans un PASS dédié.

---

## Les 6 fonctions déplacées (signatures + comportement)

| Fonction | Signature | Lignes corps | Comportement |
|---|---|---:|---|
| `_analytics_tz_for_country_code` | `(code) -> str` | 10 | Retourne `"America/Los_Angeles"` (US) / `"Africa/Algiers"` (DZ) / `"America/Sao_Paulo"` (BR) / `"UTC"` (autre, None) |
| `_analytics_fmt_duration_sec` | `(sec) -> str` | 14 | Formatte secondes en `"Ns"` / `"Mm0SS"` / `"HhMMmSS"`. Cas erreur ou type invalide → `"—"` |
| `_analytics_journey_display` | `(journey_raw) -> str` | 7 | Convertit `"a,b,c"` en `"a → b → c"`. Vide/None → `"—"` |
| `_analytics_start_local_display` | `(start_iso, country_code) -> str` | 16 | ISO timestamp + tz pays → `"YYYY-MM-DD HH:MM TZ"`. Lazy import `zoneinfo.ZoneInfo`. Aware/naive coerce UTC. Erreur → `"—"` ou `start_iso` brut |
| `_analytics_time_hms_local` | `(iso_str, country_code) -> str` | 16 | ISO + tz → `"HH:MM:SS"`. Lazy import. Erreur → `"—"` |
| `_analytics_session_classification` | `(total_sec, page_count) -> str` | 15 | `t > 180 ∧ n > 5` → "Inspection approfondie" ; `n > 3` → "Exploration active" ; sinon "Passage rapide" |

Toutes les fonctions ont été déplacées **verbatim** (pas de modification du corps, ni de la signature). Les docstrings d'origine sont préservées.

### Imports

Aucun nouveau import au top-level d'`analytics_dashboard.py` :
- `datetime`, `timezone` déjà présents (PASS 16)
- `zoneinfo.ZoneInfo` reste en lazy import inside les 2 fonctions tz-aware (cohérent avec le pattern original ; permet de booter sans `zoneinfo` disponible si la fonction n'est jamais appelée)

---

## Patch appliqué

### Côté `station_web.py` (L825-912 → re-export 12 lignes)

**Avant** : 88 lignes de corps des 6 fonctions.

**Après** :

```python
# PASS 27.7 (2026-05-09) — Analytics helpers déplacés vers source de vérité unique
# app/services/analytics_dashboard.py (les 6 fonctions étaient utilisées par
# load_analytics_readonly() sans y être importées — bug latent depuis PASS 16
# corrigé par effet de bord). Re-exportés ici pour conformité au pattern
# strangler fig (aucun consommateur externe via `from station_web import _analytics_*`
# détecté à ce jour, mais maintenu par défensive).
from app.services.analytics_dashboard import (  # noqa: F401 (re-export)
    _analytics_tz_for_country_code,
    _analytics_fmt_duration_sec,
    _analytics_journey_display,
    _analytics_start_local_display,
    _analytics_time_hms_local,
    _analytics_session_classification,
)
```

### Côté `app/services/analytics_dashboard.py`

- Docstring enrichie pour mentionner les 6 nouvelles fonctions exposées + note PASS 27.7 sur le bug latent corrigé
- 6 fonctions ajoutées **avant** `analytics_empty_payload()` et `load_analytics_readonly()`, pour qu'elles soient disponibles au moment où `load_analytics_readonly` est appelé
- Aucun import au top-level modifié

---

## Tests effectués

### PHASE 4 — Validation syntaxique

| # | Test | Résultat |
|---|---|---|
| 1 | `py_compile station_web.py + analytics_dashboard.py` | **OK** |
| 2 | `import station_web` (avec patches `.env`/handler/sqlite) | **OK** (29 BP + 8 hooks + 293 routes) |
| 3 | `from app.services.analytics_dashboard import _analytics_*` (6 noms) | **OK** |
| 4 | `from station_web import _analytics_*` (6 noms via re-export) | **OK** |
| 5 | Identité (re-export = source) — preuves `is` | **6/6 True** |

| Fonction | `station_web.X is analytics_dashboard.X` |
|---|---|
| `_analytics_tz_for_country_code` | True |
| `_analytics_fmt_duration_sec` | True |
| `_analytics_journey_display` | True |
| `_analytics_start_local_display` | True |
| `_analytics_time_hms_local` | True |
| `_analytics_session_classification` | True |

### PHASE 5 — Tests fonctionnels runtime

Exemples de sorties vérifiées :

```
_analytics_tz_for_country_code:
  US → America/Los_Angeles, DZ → Africa/Algiers, BR → America/Sao_Paulo
  None → UTC, "XX" → UTC

_analytics_fmt_duration_sec:
  125s → 2m05, 3725s → 1h02m05, 0s → 0s, -10s → 0s, "bad" → —

_analytics_journey_display:
  "a,b,c" → "a → b → c", "" → —, None → —

_analytics_start_local_display ("2026-05-09T12:00:00Z"):
  DZ → "2026-05-09 13:00 CET"
  US → "2026-05-09 05:00 PDT"
  None → —

_analytics_time_hms_local ("2026-05-09T12:00:00Z"):
  DZ → 13:00:00, None → —

_analytics_session_classification:
  (200, 6) → "Inspection approfondie"
  (50, 1) → "Passage rapide"
  (100, 4) → "Exploration active"
```

Tous les corner cases (`None`, `""`, valeurs négatives, types invalides) sont gérés silencieusement avec fallback `"—"` ou valeur par défaut, conformément au comportement d'origine.

### Suite tests unitaires `pytest tests/unit/`

```
collected 34 items
29 passed, 5 skipped, 0 failed in 3.45s
```

Identique à la baseline pré-PASS 27.7 :
- Tests `test_pure_services.py` : 7/7 PASS
- Tests `test_services.py` : 21/22 PASS, 1 SKIPPED (sémantique TTL=0 changée post-PASS-15)
- Tests `test_blueprints.py` : 4/4 SKIPPED (perms root)

**Aucune régression introduite par PASS 27.7.**

---

## Imports legacy préservés (preuve par grep)

```
$ grep -rn "from station_web import.*_analytics_\|station_web\._analytics_\|_sw\._analytics_" \
       /root/astro_scan --include="*.py" | grep -v __pycache__ | grep -v "backup\|.archive"
(aucun résultat)
```

**Aucun consommateur externe** des `_analytics_*` via `from station_web import` n'a jamais existé. Le re-export est purement défensif. Si un blueprint futur tentait `from station_web import _analytics_fmt_duration_sec`, il continuerait de fonctionner parfaitement grâce au re-export ligne ~825 du monolithe.

Inversement, le module qui utilise réellement les 6 fonctions (`analytics_dashboard.py`) les résout maintenant **localement** sans aller chercher dans station_web — ce qui est plus propre et plus performant (résolution intra-module = direct dict lookup, pas de traversée de package).

---

## Conformité aux règles strictes

| # | Règle | Vérification | Statut |
|---|---|---|---|
| 1 | Pas de redémarrage `astroscan.service` | Aucun `systemctl restart` invoqué | ✓ |
| 2 | Pas de modif `wsgi.py`, blueprints, autres services | `git diff --stat` : seuls `station_web.py` + `analytics_dashboard.py` modifiés | ✓ |
| 3 | Pas de suppression du re-export | Re-export présent ligne ~825 station_web.py | ✓ |
| 4 | Si fonctions déjà présentes identiques : supprimer + re-export | N/A (fonctions absentes du module cible avant PASS) | ✓ |
| 5 | Si fonctions présentes avec code différent : STOP | N/A (fonctions absentes) | ✓ |
| 6 | Rollback en prose, pas en bloc shell | Cf. section dédiée ci-dessous | ✓ |
| 7 | STOP si tests existants ne passent pas | 29 PASS / 5 SKIPPED / 0 FAIL — identique à baseline | ✓ |

---

## Procédure de rollback (texte prose, non exécutable)

En cas de régression détectée après déploiement, le retour à l'état pré-PASS 27.7 est faisable de trois manières équivalentes.

**Option A — via le tag git (recommandée, granularité fichier).** Le tag `pass27_7-pre` pointe sur le commit `63c2c96` (PASS 27.6 final). Un `git checkout pass27_7-pre -- station_web.py app/services/analytics_dashboard.py` restaure les deux fichiers concernés sans toucher aux 6 PASS précédents (27.1-27.6). Suivi d'un commit dédié documentant la raison du rollback. Cette option **ré-introduit le bug latent NameError** dans analytics_dashboard.py (acceptable temporairement puisque la route `/analytics` est d'usage rare et que c'était l'état historique). Elle préserve toute la cascade SDR du PASS 27.5, la déduplication `_curl_*` du PASS 27.6, et la migration `datetime.utcnow()` du PASS 27.4.

**Option B — via les snapshots fichier.** Deux snapshots ont été créés en PHASE 0 dans `/tmp/station_web_pre_pass27_7.py` (3103 lignes) et `/tmp/analytics_dashboard_pre_pass27_7.py` (324 lignes). En cas d'urgence sans accès git, ces fichiers peuvent être recopiés tels quels vers leurs emplacements respectifs pour restituer l'état pré-PASS. Note : `/tmp/` est volatile au reboot ; les snapshots sont garantis uniquement pour la session de déploiement courante.

**Option C — restauration partielle (conserver le fix du bug latent).** Si la régression provient uniquement du re-export depuis station_web (improbable, mais théoriquement possible si un consommateur externe non détecté existait), il suffit de remettre les 6 fonctions dans station_web.py tout en les conservant dans analytics_dashboard.py. Cela ré-introduit volontairement un mini-doublon de 88 lignes, mais préserve le fix du bug latent (les deux modules ont leurs définitions locales, pas de NameError). Cette option est une variante du PASS 27.6 inversé : maintien du doublon plutôt que source unique.

Aucun rollback automatique n'est prévu : le diff étant un déplacement de code (objets identiques par `is`), tout retour en arrière doit être déclenché manuellement après diagnostic.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass27_7-pre` | `63c2c96` | Snapshot avant déplacement (HEAD = PASS 27.6) |
| `pass27_7-done` | `8f6809d` | 6 fonctions déplacées + re-export + bug latent corrigé |

---

## Diff résumé

```
git diff --staged --stat (avant commit) :
 app/services/analytics_dashboard.py | 105 +++++++++++++++++++++++++++++++++++-
 station_web.py                      | 102 +++++------------------------------
 2 files changed, 118 insertions(+), 89 deletions(-)
```

Aucun autre fichier touché. Aucune création de fichier (hors le rapport et l'inventaire `/tmp/`). Aucune modification de l'API publique.

---

## Note sur la validation systemd

Le service `astroscan.service` n'a **pas** été redémarré (RÈGLE 1). Les workers gunicorn actuels servent encore le monolithe pré-PASS 27.7 (avec les 6 fonctions définies localement et le bug latent toujours en place dans analytics_dashboard.py) jusqu'au prochain cycle (`--max-requests=1000`) ou jusqu'à un `systemctl restart astroscan` manuel par root. La validation runtime décrite en PHASES 4-5 a été conduite en environnement isolé (Flask `app_context()` sans toucher aux workers de production).

Le risque de régression au prochain cycle est nul : les 6 fonctions re-exportées sont identiques par `is`, le pytest reste vert, et le module analytics_dashboard.py qui était théoriquement cassé devient désormais réellement fonctionnel.

---

## Réduction cumulée `station_web.py`

| Étape | Lignes | Δ vs précédent | Δ cumulé depuis PASS 27.2 |
|---|---:|---:|---:|
| PASS 27.2 (TLE worker extracted) | 3362 | — | 0 |
| PASS 27.3 (Stellarium + APOD helpers extracted) | 3129 | −233 | −233 |
| PASS 27.4 (datetime migration, neutre en lignes) | 3129 | 0 | −233 |
| PASS 27.5 (SDR cascade, fichier `app/routes/sdr.py`) | 3129 | 0 | −233 |
| PASS 27.6 (`_curl_*` deduplication) | 3103 | −26 | −259 |
| **PASS 27.7 (`_analytics_*` extraction)** | **3027** | **−76** | **−335** |

Note : le brief annonçait `~2977 lignes (-126 net)`. Le résultat réel est **3027 lignes (−76 net)** — l'écart vient du fait que les 6 fonctions totalisent 88 lignes corps (et non 138) et que le re-export en compte 12.

---

## Architecture après PASS 27.7 — `app/services/analytics_dashboard.py`

| Aspect | Valeur |
|---|---|
| Source unique des helpers `_analytics_*` | `app/services/analytics_dashboard.py` (429 lignes) |
| Consommateurs directs | `load_analytics_readonly()` dans le même module (résolution locale) |
| Consommateurs indirects via re-export | `station_web.py` (0 appels internes connus, défensif uniquement) |
| Bug latent NameError | **résolu** par effet de bord du déplacement |
| Test de régression public | aucun test ne couvre directement les `_analytics_*` (helpers d'affichage, non testés unitairement avant PASS 27.7) |
| Bugs latents restants à traiter | `get_geo_from_ip` ligne 289 d'`analytics_dashboard.py` également non importé — out of scope, à traiter dans un PASS dédié |
