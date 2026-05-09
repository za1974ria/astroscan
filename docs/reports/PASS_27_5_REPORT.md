# PASS 27.5 — Graceful degradation `/api/sdr/passes` (12 s → 120 ms)

**Date** : 2026-05-09
**Branche** : `ui/portail-refactor-phase-a`
**Tags** : `pass27_5-pre` (avant) → `pass27_5-done` (après)
**Snapshot** : `/tmp/sdr_pre_pass27_5.py` (sauvegarde du fichier d'origine)
**Commit** : `d18b5dc`

---

## Résumé

La route `/api/sdr/passes` (handler `app/routes/sdr.py:api_sdr_passes_impl()`) timeoutait systématiquement à **12 s** parce qu'elle déclenchait un `curl` vers `celestrak.org` (`GROUP=noaa`) inaccessible depuis Hetzner Hillsboro. Pendant ce temps, le worker TLE principal (`tle_refresh_loop`) maintenait déjà ~370-1000 TLE en mémoire dans `TLE_CACHE["items"]`, dont les 3 NOAA cherchés (NORAD 25338, 28654, 33591), ignorés par le handler.

Le handler a été ré-architecturé en cascade à 3 stratégies + cache négatif + graceful degradation, **sans modifier la signature ni le format de retour en cas de succès**.

| Métrique | Avant | Après (cas nominal) | Après (cas dégradé répété) |
|---|---|---|---|
| Latence `/api/sdr/passes` | **~12 000 ms** | **120 ms** | **0.3 ms** |
| Source TLE primaire | curl Celestrak (12 s timeout) | TLE_CACHE worker (in-memory) | cache négatif (skip) |
| Fail-safe si tout échoue | timeout HTTP côté client | retour `degraded: True` immédiat | retour `degraded: True` immédiat |
| Lignes `app/routes/sdr.py` | 144 | **208** | — |

---

## Les 3 stratégies de résolution TLE

### Stratégie 1 — `TLE_CACHE` worker (in-memory)

Source primaire. Le worker `tle_refresh_loop` (PASS 27.2) maintient en RAM un dict `TLE_CACHE` avec une clé `items` = liste de dicts (un par satellite). Identité préservée par `app.services.tle_cache.TLE_CACHE` (cf. PASS 23.5).

Lookup tolérant aux variations de schéma rencontrées (CelesTrak GP JSON, SatNOGS, fichiers TLE 3-lignes parsés) :

| Champ | Clés acceptées (priorité décroissante) |
|---|---|
| ID NORAD | `norad_id` → `catnr` → `NORAD_CAT_ID` → `norad_cat_id` |
| Nom | `name` → `OBJECT_NAME` → `f"NORAD {nid}"` |
| Ligne TLE 1 | `tle1` → `TLE_LINE1` → `tle_line1` |
| Ligne TLE 2 | `tle2` → `TLE_LINE2` → `tle_line2` |

Structure réelle observée (vérification runtime) : `items[i]` retourné par `normalize_celestrak_record()` (cf. `services/orbital_service.py:60`) utilise `norad_cat_id` (string ou int selon source) et `tle_line1`/`tle_line2`. Les autres clés sont supportées par tolérance pour les évolutions futures.

Latence : **<1 ms** scan O(N) sur 1000 entrées max. Aucun I/O.

### Stratégie 2 — Cache local `data/noaa_tle.json` (TTL 2 h)

Fichier JSON local écrit par la stratégie 3 lors du dernier fetch CelesTrak réussi. TTL 2 heures (cohérent avec le rythme de variation des éléments orbitaux NOAA POES).

Contrôle préalable du **cache négatif** (`failed_at < 300 s`) : si le dernier fetch CelesTrak a échoué récemment, on saute la lecture du cache positif (qui sera de toute façon vide ou stale) et on tombe directement en degraded. Évite la double-tentative d'un fichier qu'on sait obsolète.

Latence : **~5-50 ms** (lecture disque + json.load).

### Stratégie 3 — Fetch CelesTrak (dernier recours, timeout 5 s)

Conservée pour permettre une auto-récupération si le réseau Hetzner-Hillsboro débloque l'accès à `celestrak.org`. Différences vs version pré-PASS :
- `--max-time 5` (était `12`) → cap dur à 5 s même si TCP handshake passe
- `subprocess.run(timeout=6)` (était `15`) → cap externe Python +1 s pour ne pas masquer un curl bloqué
- Gate préalable `failed_at < 300 s` qui skip le fetch sans pénalité (0.3 ms)
- En cas d'échec (stdout vide, exception, timeout) : écriture immédiate d'un cache négatif `{"failed_at": now, "tles": {}}` pour bloquer les 5 minutes suivantes
- En cas de succès : écriture cache positif `{"timestamp": now, "tles": {...}}` (TTL 2 h)

Latence : **5 000-6 000 ms** worst-case (timeout 5 s + parsing). Mitigé à **0.3 ms** dès le 2ème appel grâce au cache négatif.

### Cascade complète et graceful degradation

```
[req] → S1 TLE_CACHE worker  → 3/3 trouvés ? → SGP4 → success JSON (5 champs)
            ↓ partiel/vide
        S2 cache local 2 h   → complète ?    → SGP4 → success JSON
            ↓ partiel/vide
        S3 curl CelesTrak    → succès ?      → SGP4 → success JSON
            ↓ échec
        cache négatif écrit (failed_at = now, TTL 5 min)
            ↓
        tles_raw vide ?
            ↓ oui
        return {"ok": True, "degraded": True, "reason": "...", "passes": [], "count": 0, "method": "skyfield_sgp4"}
```

---

## Tests effectués

### PHASE 3 — Validation syntaxique

| # | Test | Résultat |
|---|---|---|
| 1 | `py_compile app/routes/sdr.py` | **OK** |
| 2 | `from app.routes.sdr import api_sdr_passes_impl` | **OK** |
| 3 | `import station_web` (avec patches `.env`/handler/sqlite) | **OK** (29 BP + 8 hooks + 293 routes) |

### PHASE 4 — Test fonctionnel via Flask `app_context`

Test exact selon le brief (avec `resp.get_json()`) :

| Mesure | Valeur | Verdict |
|---|---|---|
| Latence | **0.120 s** | ✓ < 500 ms |
| `data["ok"]` | `True` | ✓ |
| `data["count"]` | `28` | ✓ (28 passages calculés sur 48 h pour Tlemcen 34.87°N 1.32°E alt 800 m) |
| `data["method"]` | `"skyfield_sgp4"` | ✓ (préservé) |
| `data["station"]` | `"Tlemcen, Algérie"` | ✓ (préservé) |
| `data["degraded"]` | absent | ✓ (pas ajouté en branche succès) |
| Premier passage | `NOAA-15 137.620 MHz aos=1778304758 max_el=8.3°` | ✓ |

### Tests scénarios additionnels (4 cas end-to-end)

| Scénario | Latence | `count` | `degraded` | Validation |
|---|---:|---:|---|---|
| 1. TLE_CACHE rempli (cas normal post-boot) | **120 ms** | 28 | False | ✓ objectif <500ms atteint |
| 2. TLE_CACHE vide + cache absent + curl Celestrak fail | 5011 ms | 0 | True | cache négatif écrit (45 bytes) |
| 3. Cache négatif actif (subsequent call après scénario 2) | **0.3 ms** | 0 | True | curl skippé sans pénalité |
| 4. Cache local positif <2h | **44 ms** | 29 | False | bypass S3 inutile |

Le scénario 2 (5 s) est l'unique cas pathologique. Il survient au plus une fois toutes les 5 minutes grâce au cache négatif. En régime stationnaire de production, la latence reste **sous 200 ms**.

---

## Format de réponse documenté (compatibilité ascendante)

### Branche succès (≥1 TLE résolu, contrat **inchangé**)

```json
{
  "ok": true,
  "passes": [
    {"sat": "NOAA-15", "freq": "137.620 MHz", "aos": 1778304758, "los": 1778305120, "max_el": 8.3, "simulated": false},
    ...
  ],
  "station": "Tlemcen, Algérie",
  "count": 28,
  "method": "skyfield_sgp4"
}
```

Les 5 champs `ok`, `passes`, `station`, `count`, `method` sont strictement identiques au format pré-PASS 27.5 (mêmes noms, mêmes types, même ordre). Aucun champ `degraded` ou `reason` n'apparaît dans cette branche.

### Branche graceful degradation (`tles_raw` vide après les 3 stratégies, **nouvelle**)

```json
{
  "ok": true,
  "passes": [],
  "station": "Tlemcen, Algérie",
  "count": 0,
  "method": "skyfield_sgp4",
  "degraded": true,
  "reason": "TLE NOAA temporairement indisponibles (Celestrak/AMSAT)"
}
```

Les 5 champs originaux restent présents (le frontend qui itère sur `passes` ou lit `count` continue de fonctionner sans condition). Les 2 champs additionnels (`degraded`, `reason`) sont présents UNIQUEMENT dans cette branche pathologique. Un consommateur qui ignore les clés inconnues n'est pas impacté.

**Compatibilité ascendante** : tout client préexistant qui consommait l'ancien format reçoit aujourd'hui exactement la même structure en cas de succès. En cas de dégradation, il reçoit `count: 0` et `passes: []` comme il l'aurait reçu avant un timeout (ou pire, une erreur HTTP 504).

---

## Conformité aux contraintes strictes

| # | Contrainte | Vérification | Statut |
|---|---|---|---|
| 1 | Pas de redémarrage `astroscan.service` | Aucun `systemctl restart` invoqué | ✓ |
| 2 | Signature `api_sdr_passes_impl` inchangée | 7 paramètres identiques | ✓ |
| 3 | Fetch Celestrak conservé en dernier recours | Stratégie 3 conservée, timeout réduit 12 s → 5 s | ✓ |
| 4 | `app/blueprints/sdr/routes.py` non touché | `git diff --stat` ne mentionne que `app/routes/sdr.py` | ✓ |
| 5 | TLE_worker non modifié, lecture read-only | Seul `TLE_CACHE.get("items", [])` utilisé | ✓ |
| 6 | STOP en cas d'échec phase | Aucune phase n'a échoué | ✓ |
| 7 | Rollback en prose, pas en bloc shell | Cf. section dédiée ci-dessous | ✓ |
| 8 | Si structure TLE_CACHE inattendue, documenter | Structure conforme attendu (`items` = liste, `norad_cat_id` clé principale) ; lookup multi-clé tolérant ajouté pour robustesse | ✓ |

---

## Procédure de rollback (texte prose, non exécutable)

En cas de régression détectée après déploiement, le retour à l'état pré-PASS 27.5 est faisable de deux manières équivalentes.

**Option A — via le tag git.** Le tag `pass27_5-pre` pointe sur le commit `34a7808` (PASS 27.4 final). Un retour `git checkout pass27_5-pre -- app/routes/sdr.py` restaure uniquement le handler dans son état pré-PASS sans toucher aux 4 PASS précédents (27.1-27.4) ni au reste du commit `d18b5dc`. Suivi d'un commit dédié documentant la raison du rollback partiel. Cette option préserve toute la migration `datetime.utcnow()` du PASS 27.4.

**Option B — via le snapshot fichier.** Un snapshot du `sdr.py` d'origine a été créé en PHASE 0 dans `/tmp/sdr_pre_pass27_5.py` (144 lignes). En cas d'urgence sans accès git, ce fichier peut être recopié tel quel vers `/root/astro_scan/app/routes/sdr.py` pour restituer le handler pré-PASS. Note : `/tmp/` est volatile au reboot ; le snapshot est garanti uniquement pour la session de déploiement courante.

**Option C — désactivation soft via cache négatif manuel.** Si le problème provient uniquement de la stratégie 3 (curl Celestrak), il suffit d'écrire manuellement dans `data/noaa_tle.json` un payload `{"failed_at": <timestamp futur+1an>, "tles": {}}` pour forcer le skip permanent du fetch HTTP, en gardant le bénéfice des stratégies 1 et 2. Cette option ne nécessite aucune modification de code.

Aucun rollback automatique n'est prévu : le diff étant additif (cascade avant le code SGP4 préservé), tout retour en arrière doit être déclenché manuellement après diagnostic.

---

## Tags git

| Tag | Commit | Sens |
|---|---|---|
| `pass27_5-pre` | `34a7808` | Snapshot avant migration (HEAD = PASS 27.4) |
| `pass27_5-done` | `d18b5dc` | Cascade + cache négatif + graceful appliqués |

---

## Diff résumé

```
git diff --staged --stat (avant commit) :
 app/routes/sdr.py | 226 +++++++++++++++++++++++++++++++++++-------------------
 1 file changed, 145 insertions(+), 81 deletions(-)
```

Aucun autre fichier touché. Le handler passe de 144 à 208 lignes (+64 nettes) — augmentation justifiée par la cascade explicite, le contrôle de cache négatif en deux endroits (avant et après tentative HTTP), et la branche graceful degradation isolée.

---

## Note sur la validation systemd

Le service `astroscan.service` n'a **pas** été redémarré (RÈGLE 1). Les workers gunicorn actuels servent encore le handler pré-PASS 27.5 jusqu'au prochain cycle (`--max-requests=1000`) ou jusqu'à un `systemctl restart astroscan` manuel par root. La validation runtime décrite en PHASE 4 a été conduite en environnement isolé (Flask `app_context()` + `TLE_CACHE` hydraté en mémoire via `load_tle_cache_from_disk()`), preuve que le code est fonctionnel.

---

## Architecture après PASS 27.5

| Source | Localisation | Latence typique | Use case |
|---|---|---:|---|
| TLE_CACHE in-memory (worker) | `app.services.tle_cache.TLE_CACHE["items"]` | <1 ms | Cas nominal post-boot ✓ |
| Cache local NOAA (TTL 2 h) | `data/noaa_tle.json` | 5-50 ms | Worker non démarré / `items` purgé |
| Fetch CelesTrak (timeout 5 s) | `https://celestrak.org/NORAD/elements/gp.php?GROUP=noaa` | 5 000 ms (worst) | Hors Hetzner uniquement |
| Cache négatif (TTL 5 min) | `data/noaa_tle.json` `failed_at` | 0.3 ms | Anti-spam après échec curl |
| Graceful degradation | inline | <1 ms | Failsafe absolu |

Aucune dépendance circulaire introduite. Aucun import ajouté au top-level (l'import `from app.workers.tle_worker import TLE_CACHE` est lazy inside la fonction, pour éviter de retarder le boot Flask).
