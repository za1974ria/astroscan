# ASTROSCAN POLISH — ÉTAPE 1 (Quick Wins texte)

**Branche** : `migration/phase-2c`
**Date** : 2026-05-06
**Mode** : LECTURE/ÉCRITURE — texte uniquement, aucune logique Python touchée.

---

## Phase A — Diagnostic

### Système i18n détecté
- **Pas de fichier de traduction JSON, pas de Babel.**
- Approche **hybride inline** :
  - Côté Jinja : `{% if lang == 'en' %}…{% else %}…{% endif %}`
  - Côté JS : variable `currentLang` injectée par `SERVER_LANG` (cf. `templates/portail.html:1931`).
- Le BP `app/blueprints/i18n/` (PASS 30) injecte `lang` via `context_processor`. Cookie `lang` 1 an.
- **Impact** : tout texte est dans les templates (pas de catalogue central). Toute correction se fait par éditions ciblées des HTML/JS.

### Fichiers identifiés
| # | Fichier | Lignes ciblées | Type |
| - | --- | --- | --- |
| B1 / B2 | `templates/portail.html` | 2153, 2154, 2218, 2244, 2252 | textContent JS |
| B1bis | `static/sondes_aegis.js` | 1370, 1380, 1446 | innerHTML JS |
| B3 | `templates/research_dashboard.html` | 275, 284, 291, 517, 521 | mix HTML + JS textContent |
| B4 | `templates/observatoire.html` | 504 | texte HTML |
| (info) | `templates/space.html` | 1 occurrence INTELLIGENCE SPATIALE — non touché Étape 1 |

### Cause racine bug B1
Dans `portail.html` L2153–2154, le code écrivait le texte FR dans `iss-status` mais le texte EN dans `iss-meta-note`, sans tester `currentLang`. Aux L2218/2244/2252, l'EN était hardcodé seul. **Solution** : ternaire `currentLang === 'fr' ? FR : EN`, pattern déjà utilisé dans le même fichier à la L2195.

---

## Phase B — Corrections appliquées

### B1 + B2 — `templates/portail.html` (5 hunks)

Avant chaque modification, contexte JS validé : toutes les occurrences sont des `.textContent` injectées dans le DOM (jamais des clés d'API ni des attributs HTML). `currentLang` est défini globalement L1931 et donc en scope.

| L | Before | After |
| -: | --- | --- |
| 2153 | `if (st) st.textContent = 'Données temporairement indisponibles';` | `if (st) st.textContent = currentLang === 'fr' ? 'Synchronisation en cours · NASA API' : 'Synchronizing · NASA API';` |
| 2154 | `if (metaEl) metaEl.textContent = 'Data temporarily unavailable';` | `if (metaEl) metaEl.textContent = currentLang === 'fr' ? 'Synchronisation en cours · NASA API' : 'Synchronizing · NASA API';` |
| 2218 | `metaEl.textContent = d ? '' : 'Data temporarily unavailable';` | `metaEl.textContent = d ? '' : (currentLang === 'fr' ? 'Synchronisation en cours · NASA API' : 'Synchronizing · NASA API');` |
| 2244 | `if (!d) { metaEl.textContent = 'Data temporarily unavailable'; return; }` | `if (!d) { metaEl.textContent = currentLang === 'fr' ? 'Synchronisation en cours · NASA API' : 'Synchronizing · NASA API'; return; }` |
| 2252 | `metaEl.textContent = 'Data temporarily unavailable';` | `metaEl.textContent = currentLang === 'fr' ? 'Synchronisation en cours · NASA API' : 'Synchronizing · NASA API';` |

### B1bis — `static/sondes_aegis.js` (3 hunks)

`currentLang` n'existe **pas** dans ce fichier → fallback sur `document.documentElement.lang === 'fr'` (l'attribut `<html lang>` est dynamiquement injecté par Jinja, vérifié dans `portail.html`, `landing.html`, `observatoire.html`).

Contextes validés : injection dans `box.innerHTML` via concaténation de chaînes (cas (a) — texte affiché à l'utilisateur, jamais une clé technique).

| L | Before | After |
| -: | --- | --- |
| 1370 | `'<p class="sub-h">Data temporarily unavailable</p></div>';` | `'<p class="sub-h">' + (document.documentElement.lang === 'fr' ? 'Synchronisation en cours · NASA API' : 'Synchronizing · NASA API') + '</p></div>';` |
| 1380 | idem | idem |
| 1446 | idem | idem |

### B3 — `templates/research_dashboard.html` (5 hunks)

| L | Before | After | Note |
| -: | --- | --- | --- |
| 275 | `<span class="small">Etat:</span>` | `<span class="small">État&nbsp;:</span>` | NBSP avant `:` (typographie FR) |
| 284 | `<div class="small">Images archivees dans la base</div>` | `<div class="small">Images archivées dans la base</div>` | accent é |
| 291 | `<div class="small" id="aegisModel">Modele: -</div>` | `<div class="small" id="aegisModel">Modèle&nbsp;: -</div>` | accent + NBSP |
| 517 | `$("aegisModel").textContent = "Modele: " + (isOk ? "Gemini/Groq" : "inconnu");` | `$("aegisModel").textContent = "Modèle : " + (isOk ? "Gemini/Groq" : "inconnu");` | cas (a) — textContent → corrigé |
| 521 | `$("aegisModel").textContent = "Modele: -";` | `$("aegisModel").textContent = "Modèle : -";` | cas (a) — textContent → corrigé |

**Décision JS** :
- L517 et L521 → cas (a) : `.textContent = "Modele: …"` injecté dans le DOM. **CORRIGÉ**.
- En JS, espace régulier (pas NBSP) — encoding plus simple ; le rendu visuel est équivalent dans la pratique.

`Uptime:` (L276) et `TLE:` (L277) **non touchés** comme demandé (termes techniques standards).

### B4 — `templates/observatoire.html` (1 hunk)

Vérification CSS préalable : la classe `.logo` (L56) **n'a pas** `text-transform: uppercase`. La modification ne sera pas écrasée par le CSS.

| L | Before | After |
| -: | --- | --- |
| 504 | `<div class="logo">AstroScan-Chohra OBSERVATORY</div>` | `<div class="logo">AstroScan-Chohra · Observatory</div>` |

> **Note résiduelle** : le mot `OBSERVATORY` apparaît encore L2257 mais c'est un **commentaire JS interne** (`// ── OBSERVATORY STATUS — …`), non rendu — ignoré.

### B5 — Scan complémentaire (informationnel, non-corrigé)

Mots français dans des positions visibles à l'utilisateur, sans accent :

| Fichier | L | Texte | Verdict |
| --- | -: | --- | --- |
| `templates/research_dashboard.html` | 273 | `<h2>Statut systeme</h2>` | **À corriger Étape 1.2** : `Statut système` |

Faux positifs ignorés (identifiants techniques, pas du texte affiché) :
- `templates/observatoire.html:552, 859, 2284` — `data-tab="systeme"`, panel `id="panel-systeme"`, comparaison JS `t === 'systeme'`. Ce sont des **identifiants ASCII** internes ; ne pas accentuer.

---

## Phase C — Validation

| Vérification | Résultat |
| --- | --- |
| `python -m py_compile station_web.py` | **OK** |
| `create_app('production')` (avec SECRET_KEY/NASA_API_KEY temporaires) | **OK — 291 routes chargées** (≥ 262 cible) |
| `git diff --stat` (Polish files uniquement) | voir tableau ci-dessous |

### Diff par fichier (lignes Polish uniquement)

| Fichier | + Lignes | − Lignes |
| --- | -: | -: |
| `templates/portail.html` | 5 | 5 |
| `templates/research_dashboard.html` | 5 | 5 |
| `templates/observatoire.html` | 1 | 1 |
| `static/sondes_aegis.js` | 3 | 3 |
| **TOTAL Polish** | **14** | **14** |

### Confirmations
- `grep "Data temporarily unavailable"` sur les 4 fichiers ciblés → **0 résultat** ✓
- `grep "Données temporairement indisponibles"` → **0 résultat** ✓
- `grep "Etat:"` dans `research_dashboard.html` → **0 résultat** ✓
- `grep "Images archivees"` dans `research_dashboard.html` → **0 résultat** ✓
- `grep "Modele:"` dans `research_dashboard.html` → **0 résultat** ✓
- `grep "AstroScan-Chohra OBSERVATORY"` dans `observatoire.html` (texte rendu) → **0 résultat** ✓

> Le `git diff --stat` global montre des centaines de lignes modifiées sur d'autres templates (`flight_radar.html`, `orbital_map.html`, `ce_soir.html`, etc.) — ces changements **étaient déjà en working tree avant la session** (voir `git status` initial). **Aucun de ces fichiers n'a été touché en Étape 1.**

---

## Templates de secours non touchés (à auditer plus tard)

| Fichier | L | Statut |
| --- | -: | --- |
| `templates/observatoire_live.html` | 23 | ancienne casse `AstroScan-Chohra OBSERVATORY` |
| `templates/observatoire_50ko.html` | 23 | idem |
| `templates/observatoire_mediocre.html` | 23 | idem |
| `templates/observatoire_backup.html` | 186 | idem |

À auditer en Étape 1.2 ou Étape 2 :
- vérifier qu'ils ne sont **plus servis** par aucune route avant suppression
- sinon, leur appliquer la même correction B4

---

## Instructions de rollback

```bash
# Rollback intégral des 4 fichiers Polish (les autres changements en working tree restent intacts)
git checkout -- templates/portail.html templates/research_dashboard.html templates/observatoire.html static/sondes_aegis.js

# Si déjà restart effectué (ce qui n'a PAS été fait dans cette session) :
sudo systemctl restart astroscan
# Smoke test :
curl -s http://127.0.0.1:5003/health | head -3
curl -sI http://127.0.0.1:5003/portail | head -1
curl -sI http://127.0.0.1:5003/research-dashboard | head -1
curl -sI http://127.0.0.1:5003/observatoire | head -1
```

---

## Recommandation pour la suite

### Vérifications visuelles (à faire par l'utilisateur AVANT restart)

1. **Page `/portail` en mode FR** → plus aucune chaîne `Data temporarily unavailable` visible.
   - Test : déconnecter le réseau, attendre ~5 s, observer les widgets ISS / SDR / APOD.
   - Attendu : `Synchronisation en cours · NASA API` (couleur rouge inchangée — voir Étape 3).
2. **Page `/portail` en mode EN** (`?lang=en`) → idem mais texte `Synchronizing · NASA API` cohérent.
3. **Page `/research-dashboard`** → labels affichent `État`, `Images archivées dans la base`, `Modèle : Gemini/Groq` (ou `Modèle : -`).
4. **Page `/observatoire`** → header lit `AstroScan-Chohra · Observatory` (gradient préservé, pas en majuscules).
5. **Sondes AEGIS / passages ISS** (composant injecté) en mode FR offline → `Synchronisation en cours · NASA API`.

### Quand restarter ?

- **Pas avant validation visuelle**.
- Le restart **n'est pas nécessaire** pour les changements `templates/*.html` et `static/*.js` :
  - Templates HTML : `TEMPLATES_AUTO_RELOAD=True` + `auto_reload=True` côté Jinja → rendu rafraîchi à chaque requête ; un simple **F5 navigateur** suffit.
  - JS statique (`static/sondes_aegis.js`) : `SEND_FILE_MAX_AGE_DEFAULT=0` → pas de cache navigateur côté Flask. **Ctrl+F5 / hard reload** côté navigateur recommandé pour purger le cache utilisateur.
- Si un restart est jugé nécessaire (par prudence) :
  ```bash
  sudo systemctl restart astroscan
  ```
  Puis smoke-test : `/health`, `/portail`, `/research-dashboard`, `/observatoire`.

### Travaux différés (Étape 1.2 ou Étape 3)

- **Étape 1.2 (texte restant)** :
  - `templates/research_dashboard.html:273` : `Statut systeme` → `Statut système`
  - Audit des 4 templates de secours (`observatoire_*` non servis) pour suppression ou alignement de casse.
- **Étape 3 (CSS / wording rouge)** : le ton rouge alarme du bandeau `Synchronisation en cours · NASA API` reste à adoucir (vert/ambre) mais hors scope Étape 1.

---

**Fin du rapport.** Aucun commit, aucun restart effectué.
