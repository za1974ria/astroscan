# PASS 20.3 — Lab & Skyview helpers extraction

**Date** : 2026-05-08
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass20_3-pre` (avant) → `pass20_3-done` (après)
**Backup** : `station_web.py.bak_pass20_3`
**Commit** : `ff02348`

---

## Résumé

| Métrique | Avant | Après |
|---|---|---|
| `station_web.py` | 4723 lignes | **4703** lignes (**−20**) |
| `app/services/lab_helpers.py` | n/a | **nouveau, 95 lignes** |
| Symboles migrés | 8 | **8** (7 globals + 1 fonction) |
| HTTP /portail | 200 | **200** |
| HTTP /observatoire | 200 | **200** |
| HTTP /lab | 200 | **200** |
| HTTP /api/lab/images | 200 | **200** |
| HTTP /research-center | 200 | **200** |

---

## Cartographie des 8 symboles

### Lignes d'origine dans station_web.py

| Symbole | Ligne origine | Type |
|---|---|---|
| `LAB_UPLOADS` | 3797 | `str` (path disque) |
| `RAW_IMAGES` | 3799 | `str` (path disque) |
| `ANALYSED_IMAGES` | 3800 | `str` (path disque) |
| `MAX_LAB_IMAGE_BYTES` | 3801 | `int` (25 MB) |
| `METADATA_DB` | 3802 | `str` (path disque) |
| `SPACE_IMAGE_DB` | 3812 | `str` (alias = RAW_IMAGES) |
| `_lab_last_report` | 3813 | `dict` (état volatile) |
| `_sync_skyview_to_lab` | 4041–4071 | `function` (sync SkyView → RAW_IMAGES) |

### Consommateurs externes (lazy imports `from station_web import …`)

| Blueprint | Symboles importés |
|---|---|
| `app/blueprints/lab/__init__.py` | `_lab_last_report`, `LAB_UPLOADS`, `MAX_LAB_IMAGE_BYTES`, `RAW_IMAGES`, `ANALYSED_IMAGES`, `SPACE_IMAGE_DB`, `METADATA_DB`, `_sync_skyview_to_lab` |
| `app/blueprints/research/__init__.py` | `LAB_UPLOADS` |

→ Le shim `from station_web import …` doit absolument continuer à fournir ces 8 noms après PASS 20.3. **Validé** par les checks HTTP `/lab` 200 et `/api/lab/images` 200 et `/research-center` 200.

---

## Procédure appliquée

### Step 1 — Pre-tag + backup

```
$ git tag pass20_3-pre
$ cp station_web.py station_web.py.bak_pass20_3
-rw-rw-r-- 1 zakaria zakaria 199798 May  8 00:01 station_web.py.bak_pass20_3
```

### Step 2 — Création de `app/services/lab_helpers.py`

95 lignes dont :
- Module docstring complet expliquant la migration et le pattern lazy-import
- Imports module-level minimes : `os`, `STATION` depuis `app.services.station_state`
- 7 constantes/globals déplacées verbatim (avec annotations de type)
- 1 fonction `_sync_skyview_to_lab()` déplacée verbatim, **sauf** :
  - `import shutil` reste local à la fonction (comme dans l'original)
  - **Ajout** : `import json` + `from datetime import datetime` locaux (étaient au top-level dans station_web — ici on les met au point d'usage pour autonomie du module)
  - **Ajout** : `from station_web import HEALTH_STATE, SKYVIEW_DIR, _health_set_error, log` en lazy import à l'INTÉRIEUR du corps (évite cycle import au load)
- `__all__` explicite avec les 8 noms

#### Pourquoi lazy import dans `_sync_skyview_to_lab` ?

Si `lab_helpers.py` faisait `from station_web import HEALTH_STATE, …` au module-level :
- station_web démarre l'exécution top-down
- À la ligne du shim (3797), Python tente `from app.services.lab_helpers import …`
- `lab_helpers` démarre son load, fait `from station_web import HEALTH_STATE`
- Mais station_web n'a pas encore atteint la ligne 781 (`HEALTH_STATE = {…}`)
- **ImportError** au load

Solution : lazy import à l'intérieur de la fonction. La fonction n'est appelée qu'après le load complet de station_web (typiquement par un thread `_start_skyview_sync` après init), donc tous les noms sont disponibles. Pattern conforme au prompt : *« If unsure, KEEP IT in station_web AND re-import »*.

### Step 3 — Validation isolée du module

```
$ python3 -c "from app.services.lab_helpers import (
    _lab_last_report, LAB_UPLOADS, MAX_LAB_IMAGE_BYTES,
    RAW_IMAGES, ANALYSED_IMAGES, SPACE_IMAGE_DB, METADATA_DB,
    _sync_skyview_to_lab); print('IMPORT OK — 8 symbols available')"
IMPORT OK — 8 symbols available
  LAB_UPLOADS = /root/astro_scan/data/lab_uploads
  MAX_LAB_IMAGE_BYTES = 26214400
  _lab_last_report id = 124320291241408
```

### Step 4 — Modifications de station_web.py

**Bloc 1** (l. 3797–3813 d'origine) — section DIGITAL LAB :

Avant : 7 lignes de globals + 4 makedirs + 4 lignes blank/comments + LAB_LOGS_DIR + SKYVIEW_DIR (17 lignes au total).

Après : shim block ré-important les 7 globals + `_sync_skyview_to_lab` depuis `app.services.lab_helpers`, et conservation in-place de `LAB_LOGS_DIR`, `SKYVIEW_DIR`, `os.makedirs(...)` (init disque non extrait, hors périmètre prompt).

```python
# PASS 20.3 (2026-05-08) — Lab/Skyview helpers extracted to app/services/lab_helpers.py
from app.services.lab_helpers import (  # noqa: E402,F401
    _lab_last_report,
    LAB_UPLOADS,
    MAX_LAB_IMAGE_BYTES,
    RAW_IMAGES,
    ANALYSED_IMAGES,
    SPACE_IMAGE_DB,
    METADATA_DB,
    _sync_skyview_to_lab,
)
LAB_LOGS_DIR = os.path.join(STATION, "data", "images_espace", "logs")
os.makedirs(RAW_IMAGES, exist_ok=True)
…
SKYVIEW_DIR = os.path.join(STATION, "data", "skyview")
os.makedirs(SKYVIEW_DIR, exist_ok=True)
```

**Bloc 2** (l. 4041–4071 d'origine) — fonction `_sync_skyview_to_lab` :

Avant : 31 lignes (def + corps).

Après : 4 lignes de commentaire pointant vers `lab_helpers.py`. Le nom reste lié au namespace de station_web par le shim du Bloc 1 — donc les 4 usages internes (`_start_skyview_sync` etc.) continuent de fonctionner.

---

## Validation des 18 checks

| # | Check | Attendu | Résultat | Verdict |
|---|---|---|---|---|
| 1 | AST parse station_web | OK | **OK** | ✓ |
| 2 | AST parse lab_helpers | OK | **OK** | ✓ |
| 3 | `wc -l station_web.py` | minor change | 4703 (−20) | ✓ |
| 4a | `^_lab_last_report=` | 0 | **0** | ✓ |
| 4b | `^LAB_UPLOADS=` | 0 | **0** | ✓ |
| 4c | `^MAX_LAB_IMAGE_BYTES=` | 0 | **0** | ✓ |
| 4d | `^RAW_IMAGES=` | 0 | **0** | ✓ |
| 4e | `^ANALYSED_IMAGES=` | 0 | **0** | ✓ |
| 4f | `^SPACE_IMAGE_DB=` | 0 | **0** | ✓ |
| 4g | `^METADATA_DB=` | 0 | **0** | ✓ |
| 4h | `^def _sync_skyview_to_lab` | 0 | **0** | ✓ |
| 5 | Shim block présent | présent | **l.3797 + l.4047** | ✓ |
| 6 | /portail HTTP | 200 | **200** | ✓ |
| 7 | /observatoire HTTP | 200 | **200** | ✓ |
| 8 | /api/health HTTP | 200 | **200** | ✓ |
| 9 | /lab HTTP | 200 | **200** | ✓ |
| 10 | /api/lab/images HTTP | 200 | **200** | ✓ |
| 11 | /research-center HTTP | 200 | **200** | ✓ |
| 12 | TLEMCEN ≥ 15 | ≥ 15 | **15** | ✓ |
| 13 | solar-system ≥ 4 | ≥ 4 | **4** | ✓ |
| 14 | sky-map-widget ≥ 4 | ≥ 4 | **4** | ✓ |
| 15 | cosmic-dashboard ≥ 11 | ≥ 11 | **11** | ✓ |
| 16 | PASS 20.1 /api/visitors/snapshot | 200 | **200** | ✓ |
| 17 | PASS 20.2 /api/iss | 200 | **200** | ✓ |
| 18 | PASS 20.2 /api/satellites/tle | 200 | **200** | ✓ |

**Bilan** : 18 checks ✓. **Aucun rollback déclenché.**

Les checks 9-11 et 16-18 sont les plus probants :
- **`/lab`, `/api/lab/images`, `/research-center`** exercent directement les blueprints qui utilisent les 8 symboles via `from station_web import …`. Les 200 prouvent que le shim fonctionne.
- **`/api/visitors/snapshot`, `/api/iss`, `/api/satellites/tle`** confirment que PASS 20.1 (visitors_helpers) et PASS 20.2 (tle_cache) ne sont pas régressés.

---

## Procédure de rollback (documentée même si non utilisée)

```bash
cp station_web.py.bak_pass20_3 station_web.py
rm -f app/services/lab_helpers.py
git reset --hard pass20_3-pre
echo "ROLLBACK COMPLETED"
```

`app/services/lab_helpers.py` étant entièrement nouveau (PASS 20.3), un simple `rm` suffit (pas de `git checkout pass20_3-pre -- …` nécessaire car le fichier n'existait pas avant).

---

## Fichiers touchés

| Fichier | Modif |
|---|---|
| `app/services/lab_helpers.py` | nouveau (95 lignes — 7 globals + 1 fonction + lazy imports + `__all__`) |
| `station_web.py` | −38 lignes (7 globals + 31 lignes def), +18 lignes (shim + commentaires) = **−20 net** |
| `station_web.py.bak_pass20_3` | nouveau (backup pré-PASS) |
| `PASS_20_3_REPORT.md` | ce rapport |

Aucun autre fichier touché : blueprints (lab_bp, research_bp préservés intacts), templates, static, wsgi.py, app/__init__.py, app/bootstrap.py, app/services/visitors_helpers.py (PASS 20.1), app/services/tle_cache.py (PASS 20.2), tests/.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass20_3-pre` | b86900e (HEAD avant extraction) | Snapshot avant |
| `pass20_3-done` | ff02348 | Extraction appliquée |

```
$ git log --oneline -5
ff02348 refactor(monolith): PASS 20.3 — extract lab/skyview helpers to app/services/lab_helpers.py
b86900e doc: rapport PASS 20.2 — TLE/Satellites helpers extraction
59f5ef6 refactor(monolith): PASS 20.2 — extract TLE/Satellites helpers to app/services/tle_cache.py
eb636e9 doc: rapport PASS 20.1 — visitors helpers extraction
37d55c4 refactor(monolith): PASS 20.1 — extract visitors helpers (8 funcs) to app/services/visitors_helpers.py
```

---

## Phases O-A à O-I — préservation confirmée

| Phase | Marqueur | Avant PASS 20.3 | Après PASS 20.3 |
|---|---|---|---|
| O-F (Cosmic Live Dashboard) | `cosmic-dashboard` | 11 | **11** ✓ |
| O-G (Sky Map) | `sky-map-widget` | 4 | **4** ✓ |
| O-H (Solar System + Twinkle) | `solar-system` | 4 | **4** ✓ |
| Tlemcen markers | `TLEMCEN` | 15 | **15** ✓ |

Aucune régression UI.

---

## Architecture après PASS 20.1 + 20.2 + 20.3

`app/services/` contient désormais trois façades unifiées :

| Façade | Rôle | Symboles exposés |
|---|---|---|
| `visitors_helpers.py` | Visiteurs / GeoIP / Stats | 8 (PASS 20.1) |
| `tle_cache.py` | TLE / Satellites | 6 (PASS 20.2) |
| `lab_helpers.py` | Lab / Skyview | 8 (PASS 20.3) |

Le pattern « façade + shim + lazy imports si dépendances inverses » est désormais éprouvé dans trois variantes :
- PASS 20.1 : extraction simple (pas de dépendance vers station_web)
- PASS 20.2 : enrichissement d'une façade existante (re-exports cross-modules)
- PASS 20.3 : extraction avec dépendances inverses (HEALTH_STATE, log → lazy imports)

---

## Roadmap PASS 20.4+ (groupes restants)

| Pass | Cible | Estimation lignes monolith |
|---|---|---|
| 20.4 | Helpers analytics (`_analytics_*`) | ~250 lignes |
| 20.5 | Helpers APOD / Hubble fetchers | ~300 lignes |
| 20.6 | Helpers sondes / spacecraft | ~200 lignes |
| 20.7 | Helpers cache + state internes | ~200 lignes |
| 20.8 | Threads collectors → app/workers/ | ~250 lignes |
| 20.9 | Init DB (WAL, schemas) → app/db/ | ~150 lignes |

État courant : station_web.py = 4703 lignes. Cible long-terme : 1500 lignes (= ~3200 lignes encore à extraire). Les 6 prochaines passes peuvent extraire ~1350 lignes ; le reste exigerait extraction des helpers SGP4 et orbital + helpers misc (~1850 lignes).
