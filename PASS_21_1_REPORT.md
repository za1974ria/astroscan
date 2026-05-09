# PASS 21.1 — `translate_worker` extraction vers `app/workers/`

**Date** : 2026-05-08
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass21_1-pre` (avant) → `pass21_1-done` (après)
**Backup** : `station_web.py.bak_pass21_1`
**Commit** : `4c9299a`

---

## Résumé

| Métrique | Avant | Après |
|---|---|---|
| `station_web.py` | 4624 lignes | **4584** lignes (**−40**) |
| `app/workers/` | n'existait pas | **nouveau package** |
| `app/workers/__init__.py` | n/a | **nouveau, 12 lignes** |
| `app/workers/translate_worker.py` | n/a | **nouveau, 78 lignes** |
| Symboles migrés | 1 | **1 (translate_worker function, 49 lignes corps)** |
| HTTP /portail, /observatoire, /api/health | 200 | **200** |
| Phases O-A à O-I | intactes | **intactes** |

---

## Contexte

Premier worker extrait du monolithe vers le nouveau package `app/workers/`. Le prompt cible explicitement **le plus simple** (pas de locks partagés, pas de sync inter-worker) pour valider le pattern d'extraction worker avant de passer aux threads plus complexes (TLE collector, AIS subscriber, flight radar).

Cible : `translate_worker()` — boucle daemon qui toutes les 10 minutes parcourt les observations dont `rapport_fr` est vide et `analyse_gemini` est rempli, demande à Gemini un résumé en 2 phrases, et met à jour la base.

Consommateur unique : `app/bootstrap.py:60` qui fait `from station_web import translate_worker` puis `Thread(target=translate_worker, …).start()`.

---

## Audit pré-extraction

### Localisation

```
$ grep -nE "^def translate_worker|^def _start_translate|TRANSLATE_CACHE|TRANSLATE_TTL_SECONDS|TRANSLATE_LAST_REQUEST_TS" station_web.py
170:TRANSLATE_CACHE = {}
171:TRANSLATE_TTL_SECONDS = 3600
172:TRANSLATE_LAST_REQUEST_TS = 0.0
4095:def translate_worker():
```

- Pas de wrapper `_start_translate_worker()` — le démarrage est fait directement par `app/bootstrap.py`.
- 3 globals (`TRANSLATE_CACHE`, `TRANSLATE_TTL_SECONDS`, `TRANSLATE_LAST_REQUEST_TS`) en début de fichier.

### Audit dépendances

```
$ grep -rnE "\bTRANSLATE_CACHE\b|\bTRANSLATE_TTL_SECONDS\b|\bTRANSLATE_LAST_REQUEST_TS\b" --include='*.py' . | grep -v __pycache__ | grep -v '\.bak'
station_web.py:170:TRANSLATE_CACHE = {}
station_web.py:171:TRANSLATE_TTL_SECONDS = 3600
station_web.py:172:TRANSLATE_LAST_REQUEST_TS = 0.0
app/config.py:79:TRANSLATE_TTL_SECONDS: int   = 3600    # 1 h
app/services/ai_translate.py:45:TRANSLATE_TTL_SECONDS = 3600
```

→ Les 3 globals sont **dead code** dans station_web (zéro usage actif). `TRANSLATE_TTL_SECONDS` a deux autres définitions vivantes dans `app/config.py` et `app/services/ai_translate.py` — celles-là sont actives.

**Décision** : laisser les 3 globals dead-code en place dans station_web (hors scope PASS 21.1). Leur retrait ne ferait gagner que 3 lignes et n'apporte aucune simplification fonctionnelle.

### Dépendances de `translate_worker()`

| Symbole | Origine | Stratégie |
|---|---|---|
| `sqlite3` | stdlib | import module-level dans le worker |
| `time` | stdlib | import module-level dans le worker |
| `DB_PATH` | station_web.py:191 | lazy import inside la fonction |
| `log` | station_web.py:511 | lazy import inside la fonction |
| `_call_gemini` | `app.services.ai_translate` | lazy import déjà présent dans le corps original |

Aucune dépendance vers les 3 globals dead-code → ils ne suivent pas le worker.

### Consommateur

```
$ grep -rn "from station_web import.*translate_worker" --include='*.py' . | grep -v __pycache__ | grep -v '\.bak'
app/bootstrap.py:60:        from station_web import translate_worker
```

Un seul consommateur. Le shim doit fournir `translate_worker` au namespace de station_web.

---

## Procédure appliquée

### Step 1 — Pre-tag + backup

```
$ git tag pass21_1-pre
$ cp station_web.py station_web.py.bak_pass21_1
-rw-rw-r-- 1 zakaria zakaria 196078 May  8 00:20 station_web.py.bak_pass21_1
```

### Step 2 — Création du package `app/workers/`

```
$ mkdir -p app/workers
```

### Step 3 — Création de `app/workers/__init__.py` (12 lignes)

Module init avec docstring explicitant la convention :
- chaque worker expose une fonction de boucle (e.g. `translate_worker`)
- éventuellement un wrapper `_start_X()` qui crée le `Thread`
- démarrés depuis `app/bootstrap.py` via les shims de rétro-compat

### Step 4 — Création de `app/workers/translate_worker.py` (78 lignes)

Module dédié contenant la fonction `translate_worker()` déplacée verbatim depuis station_web.py:4095-4143, avec deux différences :

1. **Lazy imports inside la boucle** : `DB_PATH` et `log` sont importés à l'intérieur de la fonction au lieu du module-level. Pourquoi ? Au moment où `app/workers/translate_worker` est chargé via le shim de station_web (durant le boot), `DB_PATH` et `log` ne sont peut-être pas encore liés dans le namespace de station_web (le shim peut être placé avant les définitions correspondantes). Lazy import → évalué au premier appel du worker, qui se produit après le boot complet (lancé par `app/bootstrap.py` post-init).

2. **`_call_gemini` lazy import déplacé** : était dans la boucle originale, conservé tel quel.

Les deux imports module-level — `sqlite3` et `time` — sont sûrs car standards de la stdlib et n'ont pas de dépendance circulaire.

`__all__ = ["translate_worker"]` explicite.

### Step 5 — Validation isolée

```
$ python3 -c "from app.workers.translate_worker import translate_worker; \
    print('IMPORT OK'); print('  fn:', translate_worker); print('  __module__:', translate_worker.__module__)"
IMPORT OK
  fn: <function translate_worker at 0x7145169a4fe0>
  __module__: app.workers.translate_worker
```

`__module__` confirme que la fonction réside désormais physiquement dans `app.workers.translate_worker`. Le shim dans station_web la ré-expose mais ne la redéfinit pas.

### Step 6 — Modification station_web.py

Avant (lignes 4095-4143, 49 lignes) :
```python
def translate_worker():
    """
    Daemon worker:
    ...
    """
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            ...
        except Exception as e:
            log.warning("translate_worker: %s", e)
        try:
            time.sleep(600)
        except Exception:
            time.sleep(60)
```

Après (6 lignes) :
```python
# PASS 21.1 (2026-05-08) — translate_worker extracted to app/workers/translate_worker.py
# Shim re-export for backward compatibility (app/bootstrap.py:60 imports
# `from station_web import translate_worker` to start the thread.)
# Le corps original (49 lignes) a été déplacé verbatim vers le worker
# avec lazy imports inside pour DB_PATH/log (cycle-safe au load).
from app.workers.translate_worker import translate_worker  # noqa: E402,F401
```

---

## Validation des 20 checks

| # | Check | Attendu | Résultat | Verdict |
|---|---|---|---|---|
| 1 | AST parse station_web | OK | **OK** | ✓ |
| 2 | AST parse `__init__.py` | OK | **OK** | ✓ |
| 3 | AST parse translate_worker.py | OK | **OK** | ✓ |
| 4 | Import isolé | OK | **OK** | ✓ |
| 5 | `wc -l station_web.py` | ~4570-4610 | **4584** | ✓ |
| 6 | `^def translate_worker` | 0 | **0** | ✓ |
| 7 | Shim block présent | présent | **l.4095** | ✓ |
| 8 | /portail HTTP | 200 | **200** | ✓ |
| 9 | /observatoire HTTP | 200 | **200** | ✓ |
| 10 | /api/health HTTP | 200 | **200** | ✓ |
| 11 | /api/translate/health HTTP | 200 ou 404 | **404** | ✓ (route inexistante, pas 500) |
| 12 | TLEMCEN ≥ 15 | ≥ 15 | **15** | ✓ |
| 13 | solar-system ≥ 4 | ≥ 4 | **4** | ✓ |
| 14 | sky-map-widget ≥ 4 | ≥ 4 | **4** | ✓ |
| 15 | cosmic-dashboard ≥ 11 | ≥ 11 | **11** | ✓ |
| 16 | PASS 20.1 /api/visitors/snapshot | 200 | **200** | ✓ |
| 17 | PASS 20.2 /api/iss | 200 | **200** | ✓ |
| 18 | PASS 20.2 /api/satellites/tle | 200 | **200** | ✓ |
| 19 | PASS 20.3 /lab | 200 | **200** | ✓ |
| 20 | PASS 20.3 /api/lab/images | 200 | **200** | ✓ |
| 21 | PASS 20.4 /api/version | 200 | **200** | ✓ |
| 22 | PASS 20.4 /api/modules-status | 200 | **200** | ✓ |

**Bilan** : 22 checks ✓. **Aucun rollback déclenché.**

### Note sur le thread effectivement en cours d'exécution

Le service systemd `astroscan` tourne en gunicorn avec workers configurés `--max-requests 1000 --max-requests-jitter 50`. Les workers actuels ont chargé station_web.py *avant* PASS 21.1 (ancienne définition de translate_worker). Quand un worker se recyclera (après ~1000 requêtes), il rechargera station_web qui passera désormais par le shim et instanciera la fonction depuis `app.workers.translate_worker`.

Vérification de cette transition impossible côté shell utilisateur (pas de `sudo journalctl`). Le rollback est tout de même non-déclenché car :
1. Tous les checks fonctionnels HTTP passent → l'ancien thread continue d'opérer correctement avec la fonction qu'il a en mémoire.
2. Le nouveau code est validé par AST + import isolé → aucun bug syntaxique ou d'import.
3. Le worker n'a pas de state shared mutable côté monolith (les 3 globals dead-code n'étaient même pas utilisés).

À chaque rotation worker, le nouveau worker prendra le code extracté sans interruption observable.

---

## Procédure de rollback (documentée même si non utilisée)

```bash
cp station_web.py.bak_pass21_1 station_web.py
rm -f app/workers/translate_worker.py
# Garder app/workers/__init__.py — ne sert à rien d'enlever un dossier vide
git reset --hard pass21_1-pre
echo "ROLLBACK COMPLETED"
```

---

## Fichiers touchés

| Fichier | Modif |
|---|---|
| `app/workers/__init__.py` | nouveau (12 lignes — module init + docstring) |
| `app/workers/translate_worker.py` | nouveau (78 lignes — fonction worker + lazy imports) |
| `station_web.py` | −49 lignes (def + corps), +6 lignes (shim + commentaires) = **−43 net** dans le diff git, **−40 net** sur `wc -l` (la suppression a englobé 3 lignes blanches du contexte) |
| `station_web.py.bak_pass21_1` | nouveau (backup pré-PASS) |
| `PASS_21_1_REPORT.md` | ce rapport |

Aucun autre fichier touché : blueprints, templates, static, wsgi.py, app/__init__.py, app/bootstrap.py (consommateur préservé intact via shim), app/services/* (PASS 20.1-20.4 préservés), tests/.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass21_1-pre` | bda0320 (HEAD avant extraction) | Snapshot avant |
| `pass21_1-done` | 4c9299a | Extraction appliquée |

```
$ git log --oneline -4
4c9299a refactor(monolith): PASS 21.1 — extract translate_worker to app/workers/
bda0320 doc: rapport PASS 20.4 — Telescope/System/Accuracy helpers extraction
b798d96 refactor(monolith): PASS 20.4 — extract telescope/system/accuracy helpers
54e4224 doc: rapport PASS 20.3 — Lab/Skyview helpers extraction
```

---

## Phases O-A à O-I — préservation confirmée

| Phase | Marqueur | Avant PASS 21.1 | Après PASS 21.1 |
|---|---|---|---|
| O-F (Cosmic Live Dashboard) | `cosmic-dashboard` | 11 | **11** ✓ |
| O-G (Sky Map) | `sky-map-widget` | 4 | **4** ✓ |
| O-H (Solar System + Twinkle) | `solar-system` | 4 | **4** ✓ |
| Tlemcen markers | `TLEMCEN` | 15 | **15** ✓ |

Aucune régression UI.

---

## Architecture après PASS 20.1-20.4 + 21.1

`app/services/` (5 façades de helpers) + `app/workers/` (1 worker) :

| Module | Type | PASS | Symboles |
|---|---|---|---|
| `app/services/visitors_helpers.py` | service | 20.1 | 8 |
| `app/services/tle_cache.py` | service | 20.2 | 6 |
| `app/services/lab_helpers.py` | service | 20.3 | 8 |
| `app/services/telescope_helpers.py` | service | 20.4 | 1 |
| `app/services/system_helpers.py` | service | 20.4 | 4 |
| `app/workers/__init__.py` | package init | 21.1 | — |
| `app/workers/translate_worker.py` | worker | 21.1 | 1 |
| **Total extrait** | — | — | **28 symboles** |

Pattern « shim + lazy imports » désormais appliqué aux **deux** archétypes : services helpers (PASS 20.x) et workers de fond (PASS 21.x). Le pattern est éprouvé pour le worker le plus simple ; les workers à venir (TLE collector, AIS subscriber, flight radar) hériteront du même squelette.

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
| **PASS 21.1 (translate_worker)** | **4584** | **−40** | **−510** |

Cible long-terme : ~1500 lignes. Reste ~3084 lignes à extraire.

---

## Roadmap PASS 21.x (workers restants) + PASS 20.5+ (helpers)

| Pass | Cible | Complexité | Estimation lignes |
|---|---|---|---|
| 21.2 | `_start_skyview_sync()` thread | simple | ~25 |
| 21.3 | TLE collector loop (download + parse + cache update) | moyenne (locks) | ~150 |
| 21.4 | AISStream subscriber thread | moyenne (websocket) | ~100 |
| 21.5 | Flight radar poll loop | simple | ~80 |
| 21.6 | Lab image collector | simple | ~50 |
| 20.5 | Helpers analytics (`_analytics_*`) | simple | ~250 |
| 20.6 | Helpers APOD / Hubble fetchers | simple | ~300 |
| 20.7 | Helpers sondes / spacecraft | moyenne | ~200 |
| 20.8 | Helpers cache + state internes | moyenne | ~200 |
| 20.9 | Init DB (WAL, schemas) → app/db/ | sensible | ~150 |

Après ces 10 passes : station_web.py estimé ~3079 lignes. Pour atteindre 1500, prévoir extraction des helpers SGP4/orbital + helpers misc dans des PASS ultérieurs.
