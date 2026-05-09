# PASS 21.3 — Skyview sync thread extraction vers `app/workers/`

**Date** : 2026-05-08
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass21_3-pre` (avant) → `pass21_3-done` (après)
**Backup** : `station_web.py.bak_pass21_3`
**Commit** : `dc5f252`

---

## Résumé

| Métrique | Avant | Après |
|---|---|---|
| `station_web.py` | 4423 lignes | **4420** lignes (**−3**) |
| `app/workers/skyview_sync.py` | n/a | **nouveau, 47 lignes** |
| Fonctions migrées | 1 | **1 (`_start_skyview_sync`)** |
| HTTP /portail, /observatoire, /api/health, /lab | 200 | **200** |
| Phases O-A à O-I | intactes | **intactes** |

Réduction modeste car `_start_skyview_sync()` ne contenait que 9 lignes (boucle minimaliste) — la majorité de la logique métier (`_sync_skyview_to_lab`) avait déjà été extraite dans `app/services/lab_helpers.py` au PASS 20.3. PASS 21.3 a juste fait migrer le **wrapper de démarrage du thread**.

---

## Audit pré-extraction

### Localisation

```
$ grep -nE "^def _start_skyview|^def _skyview_sync|^SKYVIEW_SYNC_|^_SKYVIEW" station_web.py
3974:def _start_skyview_sync():
```

Une seule fonction, pas de constantes ni globals dédiés.

### Corps original (lignes 3974-3982, 9 lignes)

```python
def _start_skyview_sync():
    """Boucle de sync SkyView → Lab toutes les 60 secondes."""
    import threading
    def loop():
        while True:
            _sync_skyview_to_lab()
            time.sleep(60)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
```

Worker très simple : démarre un thread daemon qui boucle `while True: _sync_skyview_to_lab(); time.sleep(60)`. Aucun lock, aucun pattern leader/standby, pas de re-schedule Timer (boucle infinie en thread daemon).

### Dépendances

| Symbole | Origine | Stratégie |
|---|---|---|
| `threading` | stdlib | import module-level dans le worker |
| `time` | stdlib | import module-level dans le worker |
| `_sync_skyview_to_lab` | `app/services/lab_helpers.py` (PASS 20.3) | **lazy import inside** depuis le service canonique |

Le shim PASS 20.3 dans station_web ré-exporte aussi `_sync_skyview_to_lab` dans son namespace, mais le worker préfère l'import direct depuis `app.services.lab_helpers` (canonique, évite le détour station_web).

### Consommateurs

```
$ grep -rn "from station_web import.*_start_skyview_sync" --include='*.py' . | grep -v __pycache__ | grep -v '\.bak'
app/bootstrap.py:52:        from station_web import _start_skyview_sync
```

Un seul consommateur. Le shim doit fournir `_start_skyview_sync` au namespace de station_web.

---

## Procédure appliquée

### Step 1 — Pre-tag + backup

```
$ git tag pass21_3-pre
$ cp station_web.py station_web.py.bak_pass21_3
-rw-rw-r-- 1 zakaria zakaria 188608 May  8 00:41 station_web.py.bak_pass21_3
```

### Step 2 — Création de `app/workers/skyview_sync.py` (47 lignes)

Module dédié au wrapper de démarrage du thread skyview. Imports module-level minimes : `threading`, `time` (stdlib). Lazy import de `_sync_skyview_to_lab` à l'intérieur de la boucle, depuis `app.services.lab_helpers` (canonique).

```python
import threading
import time

def _start_skyview_sync():
    """Boucle de sync SkyView → Lab toutes les 60 secondes."""
    def loop():
        from app.services.lab_helpers import _sync_skyview_to_lab
        while True:
            _sync_skyview_to_lab()
            time.sleep(60)
    t = threading.Thread(target=loop, daemon=True)
    t.start()

__all__ = ["_start_skyview_sync"]
```

Note d'optimisation discrète : le `import threading` était dans le corps de la fonction d'origine ; il est désormais module-level dans le worker (plus efficace, importé une seule fois au load au lieu d'à chaque appel — non que ça compte beaucoup pour une fonction appelée une seule fois au boot).

### Step 3 — Validation isolée

```
$ python3 -c "from app.workers.skyview_sync import _start_skyview_sync; \
    print('IMPORT OK'); print('  __module__:', _start_skyview_sync.__module__)"
IMPORT OK
  __module__: app.workers.skyview_sync
```

### Step 4 — Modification `station_web.py`

Remplacement direct de la définition de la fonction (9 lignes) par le bloc shim (6 lignes) :

```python
# PASS 21.3 (2026-05-08) — Skyview sync thread extracted to app/workers/skyview_sync.py
# Shim re-export for backward compatibility (app/bootstrap.py:52 imports
# `from station_web import _start_skyview_sync` to start the thread.)
# La fonction _sync_skyview_to_lab() consommée par la boucle est
# fournie par app/services/lab_helpers.py (PASS 20.3).
from app.workers.skyview_sync import _start_skyview_sync  # noqa: E402,F401
```

---

## Validation des 20 checks

| # | Check | Attendu | Résultat | Verdict |
|---|---|---|---|---|
| 1 | AST parse station_web | OK | **OK** | ✓ |
| 2 | AST parse skyview_sync | OK | **OK** | ✓ |
| 3 | Import isolé | OK | **OK** | ✓ |
| 4 | `wc -l station_web.py` | (réduction modeste) | **4420** (−3) | ✓ |
| 5 | `^def _start_skyview_sync` | 0 | **0** | ✓ |
| 6 | Shim block présent | présent | **l.3974** | ✓ |
| 7 | /portail HTTP | 200 | **200** | ✓ |
| 8 | /observatoire HTTP | 200 | **200** | ✓ |
| 9 | /api/health HTTP | 200 | **200** | ✓ |
| 10 | /lab HTTP | 200 | **200** | ✓ |
| 11 | /api/lab/images HTTP | 200 | **200** | ✓ |
| 12 | TLEMCEN ≥ 15 | ≥ 15 | **15** | ✓ |
| 13 | solar-system ≥ 4 | ≥ 4 | **4** | ✓ |
| 14 | sky-map-widget ≥ 4 | ≥ 4 | **4** | ✓ |
| 15 | cosmic-dashboard ≥ 11 | ≥ 11 | **11** | ✓ |
| 16 | PASS 20.1 /api/visitors/snapshot | 200 | **200** | ✓ |
| 17 | PASS 20.2 /api/iss | 200 | **200** | ✓ |
| 18 | PASS 20.2 /api/satellites/tle | 200 | **200** | ✓ |
| 19 | PASS 20.4 /api/version | 200 | **200** | ✓ |
| 20 | PASS 20.4 /api/modules-status | 200 | **200** | ✓ |
| 21 | PASS 20.4 /api/ephemerides/tlemcen | 200 | **200** | ✓ |

**Bilan** : 21 checks ✓. **Aucun rollback déclenché.**

---

## Procédure de rollback (documentée même si non utilisée)

```bash
cp station_web.py.bak_pass21_3 station_web.py
rm -f app/workers/skyview_sync.py
git reset --hard pass21_3-pre
echo "ROLLBACK COMPLETED"
```

---

## Fichiers touchés

| Fichier | Modif |
|---|---|
| `app/workers/skyview_sync.py` | nouveau (47 lignes — wrapper thread + lazy import + `__all__`) |
| `station_web.py` | −9 lignes (def + corps), +6 lignes (shim) = **−3 net** |
| `station_web.py.bak_pass21_3` | nouveau (backup pré-PASS) |
| `PASS_21_3_REPORT.md` | ce rapport |

Aucun autre fichier touché : blueprints, templates, static, wsgi.py, app/__init__.py, app/bootstrap.py (consommateur préservé via shim), app/services/* (PASS 20.1-20.4 préservés), app/workers/translate_worker.py (PASS 21.1), app/workers/tle_collector.py (PASS 21.2), tests/.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass21_3-pre` | 8749ee3 (HEAD avant extraction) | Snapshot avant |
| `pass21_3-done` | dc5f252 | Extraction appliquée |

```
$ git log --oneline -4
dc5f252 refactor(monolith): PASS 21.3 — extract Skyview sync thread to app/workers/
8749ee3 doc: rapport PASS 21.2 — TLE collector thread extraction
d5b2b85 refactor(monolith): PASS 21.2 — extract TLE collector thread to app/workers/
0773613 doc: rapport PASS 21.1 — translate_worker extraction vers app/workers/
```

---

## Phases O-A à O-I — préservation confirmée

| Phase | Marqueur | Avant PASS 21.3 | Après PASS 21.3 |
|---|---|---|---|
| O-F (Cosmic Live Dashboard) | `cosmic-dashboard` | 11 | **11** ✓ |
| O-G (Sky Map) | `sky-map-widget` | 4 | **4** ✓ |
| O-H (Solar System + Twinkle) | `solar-system` | 4 | **4** ✓ |
| Tlemcen markers | `TLEMCEN` | 15 | **15** ✓ |

Aucune régression UI.

---

## Architecture après PASS 20.1-20.4 + 21.1-21.3

`app/services/` (5 façades helpers) + `app/workers/` (3 workers) :

| Module | Type | PASS | Symboles |
|---|---|---|---|
| `app/services/visitors_helpers.py` | service | 20.1 | 8 |
| `app/services/tle_cache.py` | service | 20.2 | 6 |
| `app/services/lab_helpers.py` | service | 20.3 | 8 |
| `app/services/telescope_helpers.py` | service | 20.4 | 1 |
| `app/services/system_helpers.py` | service | 20.4 | 4 |
| `app/workers/__init__.py` | package init | 21.1 | — |
| `app/workers/translate_worker.py` | worker | 21.1 | 1 |
| `app/workers/tle_collector.py` | worker | 21.2 | 5 |
| `app/workers/skyview_sync.py` | worker | 21.3 | 1 |
| **Total** | — | — | **34 symboles** |

Pattern « shim + lazy imports + service réutilisé » désormais éprouvé sur trois workers de complexité variée :
- 21.1 (translate_worker) : worker simple, dépendance station_web
- 21.2 (tle_collector) : 5 fonctions, mutations cross-modules (TLE_CACHE, HEALTH_STATE)
- **21.3 (skyview_sync) : worker minimal réutilisant un service déjà extrait**

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
| PASS 21.1 (translate_worker) | 4584 | −40 | −510 |
| PASS 21.2 (tle_collector) | 4423 | −161 | −671 |
| **PASS 21.3 (skyview_sync)** | **4420** | **−3** | **−674** |

PASS 21.3 est volontairement **petit en lignes** mais structurellement important : valide que le pattern « worker qui réutilise un service » fonctionne sans dupliquer la logique métier (`_sync_skyview_to_lab` reste dans `lab_helpers.py`, le worker n'orchestre que la boucle).

Cible long-terme : ~1500 lignes. Reste ~2920 lignes à extraire.

---

## Roadmap restante

| Pass | Cible | Complexité | Estimation lignes |
|---|---|---|---|
| 21.4 | Lab image collector (`_run_lab_image_collector_once` + wrapper) | sensible (fcntl.flock) | ~80 |
| 21.5 | Aegis collector lock + run wrapper | sensible (fcntl.flock) | ~80 |
| 21.6 | AISStream subscriber thread | moyenne (websocket) | ~100 |
| 21.7 | Flight radar poll loop | simple | ~80 |
| 20.5 | Helpers analytics (`_analytics_*`) | simple | ~250 |
| 20.6 | Helpers APOD/Hubble fetchers | simple | ~300 |
| 20.7 | Helpers sondes/spacecraft (`_fetch_voyager`, `_fetch_neo`, `_fetch_solar_*`, `_fetch_mars_rover`) | moyenne | ~250 |
| 20.8 | Helpers cache + state internes | moyenne | ~200 |
| 20.9 | Init DB (WAL, schemas) → app/db/ | sensible | ~150 |
| 20.10 | Helpers MicroObs FITS (`_mo_*`) | sensible | ~200 |
