# PASS 23.1 — Dead code removal (investigation négative)

**Date** : 2026-05-08
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass23_1-pre` → `pass23_1-done`
**Backup** : `station_web.py.bak_pass23_1` (créé mais identique au fichier — aucune modif)
**Modifications de code** : **AUCUNE**

---

## Verdict

> 🛑 **AUCUNE des 4 fonctions candidates n'est dead.** Toutes sont utilisées en interne par d'autres helpers de station_web, qui eux-mêmes sont consommés par des modules actifs (`app/services/analytics_dashboard.py`, `app/blueprints/health/__init__.py`).
>
> **PASS 23.1 conclut sur une suppression nulle**, mais l'investigation a révélé un **pattern d'import important non détecté précédemment** : `app/blueprints/health` utilise `import station_web as _sw` puis `_sw.X(...)`, pattern qui passe sous le radar du grep `from station_web import X`.

---

## Investigation candidat par candidat

### Candidat 1 : `_analytics_tz_for_country_code`

**Définition** : `station_web.py:1776`

**Audit interne** :
```
$ grep -nE "\b_analytics_tz_for_country_code\b" station_web.py
1776:def _analytics_tz_for_country_code(code):
1821:        tzname = _analytics_tz_for_country_code(country_code)
1839:        tzname = _analytics_tz_for_country_code(country_code)
```

→ **2 references internes** (lignes 1821, 1839).

**Audit externe** (`app/`, `services/`) : 0 référence directe via `from station_web import`.

**Callers internes** :
- `_analytics_start_local_display` (ligne 1813)
- `_analytics_time_hms_local` (ligne 1831)

**Audit transitif** :
```
$ grep -rnE "\b_analytics_start_local_display\b|\b_analytics_time_hms_local\b" --include='*.py' app/
app/services/analytics_dashboard.py:189: "start_local": _analytics_start_local_display(st_iso, cc),
app/services/analytics_dashboard.py:272: "start_local": _analytics_start_local_display(...),
app/services/analytics_dashboard.py:277:     "time_local": _analytics_time_hms_local(
```

→ **CHEMIN ACTIF** : `_analytics_tz_for_country_code` ← `_analytics_start_local_display`/`_analytics_time_hms_local` ← `app/services/analytics_dashboard.py` (analytics dashboard production).

**Verdict** : ✅ **VIVANT — KEEP**.

---

### Candidat 2 : `build_priority_object`

**Définition** : `station_web.py:718`

**Audit interne** :
```
$ grep -nE "\bbuild_priority_object\b" station_web.py
718:def build_priority_object(stellarium_data, freshness):
2988:    priority_object = build_priority_object(stellarium_data, freshness)
```

→ **1 reference interne** (ligne 2988).

**Audit externe** : 0 référence directe.

**Caller interne** : `_build_status_payload_dict` (ligne 2892).

**Audit transitif** :
```
$ grep -rnE "_build_status_payload_dict" --include='*.py' app/
app/blueprints/health/__init__.py:189: d = _sw._build_status_payload_dict(now_iso, include_external=False)
```

→ **CHEMIN ACTIF** : `build_priority_object` ← `_build_status_payload_dict` ← `app/blueprints/health/__init__.py` (route `/api/health` ou similaire).

**Verdict** : ✅ **VIVANT — KEEP**.

---

### Candidat 3 : `build_system_intelligence`

**Définition** : `station_web.py:782`

**Audit interne** :
```
$ grep -nE "\bbuild_system_intelligence\b" station_web.py
782:def build_system_intelligence(
2870:        "system_intelligence": build_system_intelligence(
2989:    system_intelligence = build_system_intelligence(
```

→ **2 references internes** (lignes 2870, 2989).

**Callers internes** :
- `_fallback_status_payload_dict` (ligne 2828)
- `_build_status_payload_dict` (ligne 2892)

Les deux sont consommés par `app/blueprints/health/__init__.py` via `import station_web as _sw`.

**Verdict** : ✅ **VIVANT — KEEP**.

---

### Candidat 4 : `compute_stellarium_freshness`

**Définition** : `station_web.py:696`

**Audit interne** :
```
$ grep -nE "\bcompute_stellarium_freshness\b" station_web.py
696:def compute_stellarium_freshness(last_timestamp):
2987:    freshness = compute_stellarium_freshness(last_timestamp)
```

→ **1 reference interne** (ligne 2987).

**Caller interne** : `_build_status_payload_dict` (ligne 2892), même chemin transitif que les 2 candidats précédents.

**Verdict** : ✅ **VIVANT — KEEP**.

---

### Vérification dépendance `load_stellarium_data`

```
$ grep -nE "load_stellarium_data" station_web.py
664:def load_stellarium_data():
2971:        stellarium_data = load_stellarium_data()
```

→ utilisée par `_build_status_payload_dict` ligne 2971. **VIVANTE — KEEP**.

---

## Pattern d'import important découvert

L'investigation a révélé un pattern d'import qui **passait sous le radar** des audits PASS antérieurs :

```python
# app/blueprints/health/__init__.py
import station_web as _sw
...
def some_route():
    d = _sw._build_status_payload_dict(now_iso, include_external=False)
```

Ce pattern **N'EST PAS** détecté par `grep "from station_web import X"` qui était le check standard utilisé jusqu'ici. Pour future-proofer les audits d'extraction (PASS 22.x, 23.x), il faut **également** chercher :

```bash
grep -rn "import station_web" --include='*.py' app/
grep -rn "_sw\." --include='*.py' app/
grep -rn "station_web\." --include='*.py' app/
```

Ces patterns peuvent référencer **n'importe quel symbole** du namespace de station_web sans transiter par un `from … import`, ce qui rend la rétro-compat du shim **encore plus critique** : tout ré-export du shim doit être correct, sinon ces accès `_sw.X` casseront silencieusement.

PASS 23.1 a **par chance** confirmé que les 4 fonctions ciblées sont actives, donc aucun risque immédiat. Mais un PASS futur qui retirerait une fonction détectée comme « dead » par grep `from station_web import` pourrait casser un caller `_sw.X`.

**Recommandation** : intégrer ce check dans tous les futurs audits d'extraction.

---

## Tableau de synthèse

| Candidat | Définition | Refs internes | Caller interne | Caller transitif | Verdict |
|---|---|---|---|---|---|
| `_analytics_tz_for_country_code` | l.1776 | 2 | `_analytics_start_local_display` + `_analytics_time_hms_local` | `app/services/analytics_dashboard.py` | ✅ KEEP |
| `build_priority_object` | l.718 | 1 | `_build_status_payload_dict` | `app/blueprints/health/__init__.py` (via `_sw.`) | ✅ KEEP |
| `build_system_intelligence` | l.782 | 2 | `_fallback_status_payload_dict` + `_build_status_payload_dict` | idem | ✅ KEEP |
| `compute_stellarium_freshness` | l.696 | 1 | `_build_status_payload_dict` | idem | ✅ KEEP |

**Suppressions effectives** : 0.
**Lignes économisées** : 0.
**Risques évités** : 4 fonctions cassées en production si suppression aveugle.

---

## Validation finale (intégrité système)

| # | Check | Résultat |
|---|---|---|
| 1 | AST parse station_web | **OK** ✓ |
| 2 | `wc -l station_web.py` | **4057** (inchangé) |
| 3-16 | 14 endpoints HTTP : `/`, `/portail`, `/observatoire`, `/api/health`, `/api/version`, `/api/modules-status`, `/api/visitors/snapshot`, `/api/iss`, `/api/satellites/tle`, `/lab`, `/api/lab/images`, `/api/weather`, `/api/weather/history`, `/api/weather/archive` | **200 ✓** |
| 17 | `/api/weather/archive/2099-01-01` (404 by design) | **404 ✓** |
| 18-21 | Phases UI O-A à O-I : TLEMCEN, solar-system, sky-map-widget, cosmic-dashboard | **15, 4, 4, 11 ✓** |

**Bilan** : 21 checks ✓. Aucune régression. Aucun changement de code à valider.

---

## Procédure de rollback (théorique — non applicable car aucune modif)

```bash
# Pas de rollback nécessaire — aucune modification de code.
# Si un autre opérateur veut supprimer le backup et revenir à l'état pre-PASS :
rm -f station_web.py.bak_pass23_1
git reset --hard pass23_1-pre  # équivalent au HEAD actuel (no-op)
```

---

## Fichiers touchés

| Fichier | Modif |
|---|---|
| `station_web.py` | **aucune** (investigation pure) |
| `station_web.py.bak_pass23_1` | nouveau (backup pré-PASS — identique au fichier actuel) |
| `PASS_23_1_REPORT.md` | ce rapport |

Aucun autre fichier touché.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass23_1-pre` | 4d1ddb5 (HEAD avant) | Snapshot avant investigation |
| `pass23_1-done` | (commit du rapport) | Investigation conclue, suppression nulle |

---

## Phases O-A à O-I — préservation confirmée

| Phase | Marqueur | Avant PASS 23.1 | Après PASS 23.1 |
|---|---|---|---|
| O-F (Cosmic Live Dashboard) | `cosmic-dashboard` | 11 | **11** ✓ |
| O-G (Sky Map) | `sky-map-widget` | 4 | **4** ✓ |
| O-H (Solar System + Twinkle) | `solar-system` | 4 | **4** ✓ |
| Tlemcen markers | `TLEMCEN` | 15 | **15** ✓ |

---

## Architecture inchangée

`app/services/` (7 façades) + `app/workers/` (4 workers) = **65 symboles** (inchangé).

`station_web.py` : **4057 lignes** (inchangé).

Réduction cumulée depuis PASS 18 : **−1037 lignes** (inchangé).

---

## Leçon de PASS 23.1

> **« Dead code is not always dead — verify, then prune. »**

Le prompt a été tenu jusqu'à la lettre : **vérifier exhaustivement avant suppression**. Le résultat (suppression nulle) est une **non-action positive** : on a évité 4 régressions potentielles silencieuses.

Pour PASS futurs candidats à la suppression, la check-list complète est :
1. Internal refs in `station_web.py` (excluant la def)
2. External refs via `from station_web import X` dans `app/`, `services/`
3. **External refs via `import station_web as _sw; _sw.X(...)`** ← découvert au PASS 23.1
4. Refs transitives : si caller A appelle X et A est utilisé par module externe, alors X est vivant

---

## Roadmap restante (PASS 23.2+ et au-delà)

PASS 23.1 ne réduit pas station_web.py. Pour continuer la trajectoire vers la cible 1500 lignes, les PASS 22.3-22.8 (helpers analytics, APOD/Hubble fetchers, sondes, cache/state, MicroObs FITS, requests monkey-patch) restent disponibles comme prévu dans le rapport PASS 22.2.

Tous les futurs PASS d'extraction devront intégrer le **check `_sw.X` pattern** dans leur audit pour éviter de casser silencieusement des callers indirects.
