# PASS 27.4 — Migration `datetime.utcnow()` → `datetime.now(timezone.utc)`

**Date** : 2026-05-09
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass27_4-pre` (avant) → `pass27_4-done` (après)
**Snapshot** : `/tmp/pass27_4_snapshot/` (station_web.py + app/ + services/ + modules/ + 5 racines)
**Commit** : `34a7808`

---

## Résumé

Python 3.12 deprecate `datetime.utcnow()` en faveur de `datetime.now(timezone.utc)`. Migration atomique, directe, sans abstraction (pas de helper `now_utc()` introduit). Pattern de remplacement officiel Python.

| Métrique | Avant | Après |
|---|---|---|
| `.utcnow()` (hors venv/backup/.archive/recovery) | **58** | **0** |
| `.now(timezone.utc)` + variantes alias | 107 | **165** |
| Fichiers modifiés | — | **29** |
| Lignes diff (substitution iso) | — | **+79 / −79** |
| Imports `from station_web` legacy | OK | **OK** |
| 29 blueprints + 8 hooks + 293 routes Flask | OK | **OK** |

Note : le brief annonçait 59 occurrences sur ~25 fichiers. Le grep réel a retourné 58 sur 29 fichiers. Deux fichiers (`ce_soir_module.py`, `apod_translator.py`) absents de la liste du brief mais présents dans le grep ont été inclus pour atteindre 0 résiduel comme exigé en PHASE 3.

---

## Patterns d'import gérés

| Pattern | Détection | Migration |
|---|---|---|
| **P1** `from datetime import datetime` | classe `datetime` directement | ajout `, timezone` à l'import + `datetime.now(timezone.utc)` |
| **P2** `import datetime as _dt` | `_dt` = module | `_dt.datetime.now(_dt.timezone.utc)` (aucun import à modifier) |
| **P3** `import datetime` | module sans alias | `datetime.datetime.now(datetime.timezone.utc)` |
| **P4** (cas spécial) `from datetime import datetime as _dt[_utc]` | `_dt[_utc]` = classe | ajout `, timezone as _tz[_utc]` à l'import + `_dt[_utc].now(_tz[_utc].utc)` |

P4 rencontré : `station_web.py` L1682 (`_dt_utc` → `_dt_utc, _tz_utc`), `station_web.py` L2597 (lazy import inside fonction), `app/blueprints/api/__init__.py` L300/L314/L328 (3 imports lazy distincts complétés à la volée).

---

## Liste exhaustive des fichiers modifiés (29)

### LOT 1 — station_web + 11 blueprints (12 fichiers, 30 occurrences)

| Fichier | Occ | Patterns rencontrés |
|---|---:|---|
| `station_web.py` | 5 | P4 ×3 (alias `_dt_utc`/lazy `_dt`), P2 ×2 (`_dt.datetime.utcnow`) |
| `app/blueprints/feeds/__init__.py` | 6 | P1 (top-level `from datetime import datetime, timedelta` → +`, timezone`) |
| `app/blueprints/api/__init__.py` | 4 | P4 ×3 (lazy inside route handlers) + P1 ×1 (`api_version`) |
| `app/blueprints/weather/__init__.py` | 4 | P1 (timezone déjà importé) |
| `app/blueprints/astro/__init__.py` | 2 | P1 |
| `app/blueprints/export/__init__.py` | 2 | P1 |
| `app/blueprints/ai/__init__.py` | 1 | P1 (timezone déjà importé) |
| `app/blueprints/iss/routes.py` | 1 | P2 |
| `app/blueprints/lab/__init__.py` | 1 | P1 |
| `app/blueprints/main/__init__.py` | 1 | P2 |
| `app/blueprints/satellites/__init__.py` | 1 | P1 |
| `app/blueprints/seo/__init__.py` | 1 | P1 |
| `app/blueprints/seo/routes.py` | 1 | P1 |

### LOT 2 — app/services (5 fichiers, 9 occurrences)

| Fichier | Occ | Patterns |
|---|---:|---|
| `app/services/external_feeds.py` | 4 | P2 |
| `app/services/iss_compute.py` | 2 | P2 |
| `app/services/lab_helpers.py` | 1 | P1 (lazy inside fonction) |
| `app/services/weather_archive.py` | 1 | P1 (timezone déjà importé) |
| `app/services/weather_db.py` | 1 | P1 (timezone déjà importé) |

### LOT 3 — services + modules legacy (6 fichiers, 14 occurrences)

| Fichier | Occ | Patterns |
|---|---:|---|
| `services/nasa_service.py` | 4 | P1 |
| `services/ephemeris_service.py` | 4 | P2 |
| `modules/stellarium_fusion.py` | 2 | P3 |
| `modules/iss_passes.py` | 1 | P3 |
| `modules/observation_planner.py` | 1 | P1 (timezone déjà importé) |
| `modules/space_alerts.py` | 1 | P1 (lazy inside fonction) |

### LOT 4 — racine legacy (5 fichiers, 5 occurrences)

| Fichier | Occ | Patterns |
|---|---:|---|
| `skyview_module.py` | 2 | P1 |
| `noyau_orbital.py` | 1 | P1 |
| `news_module.py` | 1 | P1 |
| `ce_soir_module.py` | 1 | P1 (extra brief) |
| `apod_translator.py` | 1 | P1 (extra brief) |

---

## Tests réalisés

| # | Test | Attendu | Résultat |
|---|---|---|---|
| 1 | `py_compile` LOT 1 (13 fichiers) | OK | **OK** |
| 2 | `py_compile` LOT 2 (5 fichiers) | OK | **OK** |
| 3 | `py_compile` LOT 3 (6 fichiers) | OK | **OK** |
| 4 | `py_compile` LOT 4 (5 fichiers) | OK | **OK** |
| 5 | `grep -rn ".utcnow()" .` (hors exclus) | 0 | **0** |
| 6 | `grep -rn ".now(timezone.utc)..."` total | ≥ 58 | **165** |
| 7 | `import station_web` complet | OK | **OK** (29 BP + 8 hooks + 293 routes enregistrés) |
| 8 | `station_web._dt_utc` résout | `<class datetime.datetime>` | **`<class 'datetime.datetime'>`** |
| 9 | `station_web._tz_utc` résout | `<class datetime.timezone>` | **`<class 'datetime.timezone'>`** |
| 10 | `compute_stellarium_freshness(now_iso)` (PASS 27.3) | `live` | **`live`** |
| 11 | `compute_stellarium_freshness(None)` | `unknown` | **`unknown`** |

Pour le test 7-11, l'import a été réalisé en environnement isolé (perms `.env` 600 root non lisibles par `zakaria`). Patches appliqués pour la durée du test : `open("/.env")` → `StringIO('')`, `RotatingFileHandler` → redirigé vers `/tmp/`, `sqlite3.connect` → `:memory:`. Aucune modification fichier persistante.

---

## Note sur la validation systemd

Le service `astroscan.service` n'a **pas** été redémarré (RÈGLE 1 du brief : `zakaria` fera la validation). Les workers gunicorn actuels servent encore le code pré-PASS 27.4 jusqu'au prochain cycle (`--max-requests=1000 --max-requests-jitter=50`) ou jusqu'à un `systemctl restart astroscan` manuel.

---

## Procédure de rollback (texte prose, non exécutable)

En cas de régression détectée après déploiement, le retour à l'état pré-PASS 27.4 est faisable de deux manières équivalentes.

**Option A — via le tag git.** Le tag `pass27_4-pre` pointe sur le commit `5f359c7` (PASS 27.3 final). Un `git reset --hard` sur ce tag annule le commit `34a7808` et restitue l'intégralité des 29 fichiers à leur état pré-migration. Cette opération est destructrice côté working tree ; elle suppose qu'aucun commit additionnel n'a été créé après PASS 27.4. Ensuite, `systemctl restart astroscan` (par root) recharge les workers gunicorn sur le code restauré.

**Option B — via le snapshot tarball.** Un snapshot complet a été créé en PHASE 0 dans `/tmp/pass27_4_snapshot/` contenant `station_web.py` + l'arborescence `app/` + `services/` + `modules/` + les 5 fichiers racine (`skyview_module.py`, `noyau_orbital.py`, `news_module.py`, `ce_soir_module.py`, `apod_translator.py`). En cas d'urgence sans accès git, ces fichiers peuvent être recopiés tels quels dans `/root/astro_scan/` pour restituer l'état pré-PASS. Note : le snapshot vit dans `/tmp/` qui est volatile au reboot ; il est garanti présent uniquement durant la session courante.

**Option C — rollback partiel.** Si la régression touche un seul lot (par exemple LOT 3 `modules/`), le `git checkout pass27_4-pre -- modules/` restaure uniquement ce sous-arbre sans toucher au reste, suivi d'un commit dédié documentant la raison du rollback partiel.

Aucun rollback automatique n'est prévu : le diff étant purement substitutionnel (+79/−79 lignes, zéro nouvelle abstraction), tout retour en arrière doit être déclenché manuellement après diagnostic.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass27_4-pre` | `5f359c7` | Snapshot avant migration (HEAD = PASS 27.3) |
| `pass27_4-done` | `34a7808` | Migration appliquée |

---

## Diff résumé

```
git diff --staged --stat (avant commit) :
 29 files changed, 79 insertions(+), 79 deletions(-)
```

Aucun fichier supprimé. Aucun fichier créé (hors ce rapport). Aucun import retiré. Les seules additions d'import sont `, timezone` (ou `, timezone as _tz[_utc]`) dans 22 fichiers où le nom n'était pas encore disponible dans le scope.

---

## Conformité aux règles strictes

| Règle | Statut |
|---|---|
| 1. Pas de redémarrage `astroscan.service` | **Respecté** (zakaria fera la validation) |
| 2. Pas de modif `wsgi.py` | **Respecté** (`wsgi.py` non touché) |
| 3. Pas de modif `.archive/`, `backup/`, `recovery/`, `venv/` | **Respecté** (grep filtré) |
| 4. STOP en cas d'échec phase | **Non déclenché** (toutes phases OK) |
| 5. Rollback en prose, pas en bloc shell | **Respecté** (cf. section ci-dessus) |
| 6. Demander si pattern non listé | **N/A** (4 patterns standards uniquement, pas de classe custom) |
| 7. Pas d'abstraction `now_utc()` | **Respecté** (substitution directe) |
| 8. Pas de modif `tests/` | **Respecté** (aucun fichier `test*.py` modifié) |

---

## Prochaines étapes possibles

PASS 27.4 prépare le terrain pour Python 3.13 (où `datetime.utcnow()` deviendra une `DeprecationWarning` runtime) et Python 3.14 (suppression définitive). Aucune action de suivi requise sur ce périmètre.

Pistes connexes (hors scope PASS 27.4) :
- `datetime.fromisoformat(s.replace("Z","+00:00"))` reste idiomatique mais deviendra obsolète quand Python 3.11+ supportera nativement le suffixe `Z` (déjà le cas en 3.11). Migration potentielle dans un PASS futur.
- Audit des `time.time()` vs `time.monotonic()` pour les usages de comparaison de durée (déjà partiellement fait au PASS 20.2 / 27.2 pour le backoff TLE).
