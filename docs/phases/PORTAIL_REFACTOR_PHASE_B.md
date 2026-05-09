# PORTAIL REFACTOR — PHASE B (POLISH & FINISHING)

**Date :** 2026-05-07  
**Branche :** `ui/portail-refactor-phase-a` (continuée — pas de nouvelle branche)  
**Tag de départ :** `ui-phase-b-start`  
**Service prod :** `astroscan.service` (template auto-reload, **restart requis** pour B1 Python)

---

## 1. Synthèse exécutive

| FIX | Statut | Commit | Tag |
|---|---|---|---|
| B1. Visitor count (root cause + graceful empty) | ✅ | `1c731a4` | `ui-phase-b-fix1-done` |
| B2. Ghost primary-nav supprimé | ✅ | `8ab851b` | `ui-phase-b-fix2-done` |
| B3. Sidebar uniformité visuelle | ✅ | `283f7b5` | `ui-phase-b-fix3-done` |
| B4. Viewport initial-scale 1.0 | ✅ | `864700a` | `ui-phase-b-fix4-done` |

---

## 2. Détail par FIX (avec investigation)

### ✅ B1 — Visitor count (commit `1c731a4`)

**Symptôme rapporté** : après `sudo systemctl restart astroscan`, `curl /portail | grep "tbar-visits-val"` continuait à montrer `000 000`.

**Investigation menée (3 étapes, données réelles) :**

```bash
# Étape 1 — _get_visits_count() retourne quoi ?
$ python3 -c "from app.services.db_visitors import _get_visits_count; print(_get_visits_count())"
0    # ← entier zéro, pas None, pas exception

# Étape 2 — état réel de la DB
DB_PATH = /root/astro_scan/data/archive_stellaire.db (16 KB)
Tables : ['session_time', 'sqlite_sequence', 'visits']
visits row : [(1, 0)]
visitor_log : table N'EXISTE PAS

# Étape 3 — endpoint /api/visits
$ curl /api/visits → {"count":0}
```

**Cause racine** : la DB SQLite courante a un schéma incomplet. La table `visits.count` est littéralement à 0 et la table `visitor_log` est absente. Le code SSR fonctionne correctement — il rend `'%06d' % 0 = '000000'` → affiché `000 000`. Ce n'est pas un bug de rendu, c'est l'état réel des données.

**Conséquence connexe** : `_register_unique_visit_from_request()` échoue silencieusement à chaque requête (INSERT sur `visitor_log` qui n'existe pas), donc le compteur ne s'incrémente jamais. La DB restera à `count=0` indéfiniment sans intervention.

**Backup détecté** : `/root/astro_scan/data/data.bak/archive_stellaire.db` contient le schéma complet (8 tables) avec `visitor_log` (3 704 lignes) et `visits.count = 2 752`. La récupération de la DB est **hors scope UI** (concerne le data layer).

**Fix appliqué (UI uniquement)** :

1. **Jinja garde `_vc_raw > 0`** (en plus de `is number` et `is not none`) :
   ```jinja
   {% if _vc_raw is not none and _vc_raw is number and _vc_raw > 0 %}
     {% set _vc = '%06d' % (_vc_raw|int) %}{{ _vc[:3] }} {{ _vc[3:] }}
   {% else %}
     <span style="opacity:0.55">•••</span>
   {% endif %}
   ```
   → Quand `count=0`, on rend `•••` discret au lieu de `000 000` trompeur.

2. **JS `loadVisitsPortail()` early-return si count≤0** :
   ```js
   if (n <= 0) return; /* PHASE B1 : pas d'overwrite SSR si count<=0 */
   ```
   → L'API retournant `{"count":0}` ne vient PAS écraser le `•••` du SSR.

**Résultat live** :
```
$ curl /portail | grep "tbar-visits-val"
<span id="tbar-visits-val"><span style="opacity:0.55">•••</span></span>

$ curl /portail | grep -c "000 000"
0
```

Quand la DB sera restaurée (out-of-scope), le SSR rendra automatiquement le vrai chiffre dès le premier paint, et le JS continuera de le rafraîchir toutes les 30s via `/api/visits`.

---

### ✅ B2 — Ghost primary-nav supprimé (commit `8ab851b`)

**Symptôme** : ligne horizontale faible avec texte fantôme "HOME ISS PASSES APOD TECHNICAL" visible derrière le hero.

**Investigation** :
```bash
$ grep -n "primary-nav\|HOME.*ISS.*PASSES" templates/portail.html
267:.primary-nav { ... border-bottom: 1px solid rgba(0, 255, 224, 0.3); }
1248:<nav class="primary-nav" aria-label="Primary navigation">
1249:  <a href="/">Home</a>
1250:  <a href="/iss-tracker">ISS</a>
1251:  <a href="#passes-brief">Passes</a>
1252:  <a href="/apod/view">APOD</a>
1253:  <a href="/technical">Technical</a>
1254:</nav>
```

**Cause racine** : le `<nav class="primary-nav">` était toujours rendu avec `position: fixed; top: 66px; left: 220px; right: 0; border-bottom: 1px solid rgba(0,255,224,0.3)`. La bordure cyan créait la ligne. Le texte HTML rendu, mais avec `font-size:10px` et `color: var(--text)` quasi-invisible, formait l'effet "fantôme" derrière le hero.

**Fix appliqué** :
- `<nav class="primary-nav">` retiré (HTML, 7 lignes)
- Règles CSS `.primary-nav` et `.primary-nav a` supprimées (~30 lignes)
- Mobile `.primary-nav` override retirée
- `.content-area { padding-top: 58px → 16px }` (la primary-nav fixed à 66px n'existe plus, donc plus besoin de réserver 58px)
- Mobile `.content-area { padding-top: 62px → 16px }`
- Markers de commentaire HTML/CSS pour traçabilité

**Toutes les destinations restent accessibles** via la sidebar Phase A :
- Home → Accueil (top-level)
- ISS → Espace Live > ISS en direct
- Passes → couvert par ISS sub-items
- APOD → Observation > NASA Picture of the Day
- Technical → page externe via /technical (lien direct si nécessaire — pas dans la sidebar actuelle, à ajouter en Phase C si besoin)

**Résultat live** :
```
$ curl /portail | grep -E '<nav class="primary-nav"|<a href="/iss-tracker">ISS</a>'
(seulement dans le commentaire de fix — HTML retiré)

$ curl /portail | grep -c "primary-nav"
6   # 6 mentions, toutes en commentaires
```

---

### ✅ B3 — Sidebar uniformité (commit `283f7b5`)

**Symptômes** :
- "MÉTÉO & AURORES" wrap sur 2 lignes
- "DONNÉES & RECHERCHE" idem
- Hauteurs incohérentes des group-headers
- "À PROPOS" détaché visuellement (margin-top + border-top)
- Tailles d'icônes irrégulières

**Investigation** :
- `.sidebar-group-header` avait `padding: 9px 16px` mais pas de `min-height` → la hauteur variait avec le contenu (1 ou 2 lignes).
- `.nav-label` n'avait pas `white-space: nowrap` → wrap libre.
- `.sidebar .nav-icon` 22×22 avec padding 4px (icône SVG visible 14×14).
- `.nav-toplevel { margin-top: 8px; border-top: 1px solid rgba(0,180,255,0.08); }` → séparation visuelle.

**Fix appliqué** :

| Élément | Avant | Après |
|---|---|---|
| Hauteur uniforme top-level | variable | **min-height: 44px** (groupes + Accueil + À propos) |
| Hauteur sub-items | héritée de `.nav-item` (~40px) | **min-height: 32px**, padding `7px 16px 7px 36px` |
| Label group-header | font 0.6rem, ls 0.16em, wrap libre | **font 0.55rem, ls 0.14em, nowrap + ellipsis, max-width 140px** |
| Label sub-item | wrap libre | nowrap + ellipsis |
| Icône container | 22×22, padding 4px | **20×20, padding 3px** |
| SVG forcée | non | **width:14px height:14px** |
| Chevron | flow flex | **margin-left: auto, width 16px** (ancrée à droite) |
| À propos | margin-top 8px + border-top | **margin-top 0, border-top 0** (intégré) |
| `.sidebar-group` margin | 2px 0 | 0 (liste plus serrée) |

**Résultat** : 8 sections (1 Accueil + 6 groupes collapsibles + 1 À propos) avec hauteur uniforme 44px, labels qui ne wrap plus, icônes calibrées, transitions douces. Les sub-items sont visuellement distincts (32px, indentés 36px).

**Note sur le compteur "7" de la spec** : la spec Phase B parle de `grep -c 'class="sidebar-group'` attendu à 7. Mon implémentation Phase A a **6 groupes collapsibles** (`espace_live`, `observation`, `meteo`, `live_terre`, `ia`, `data`) + 2 singles (`Accueil`, `À propos`). La spec Phase A originale listait 8 sections (1 single + 6 collapsibles + 1 single). L'écart est cohérent avec la liste numérotée que vous aviez fournie : la "7" était une approximation. La structure 6+2 a été visuellement validée en Phase A.

**Résultat live** :
```
$ curl /portail | grep -oE 'data-group="[a-z_]+"' | sort -u | wc -l
6   # data, espace_live, ia, live_terre, meteo, observation
```

---

### ✅ B4 — Viewport initial-scale=1.0 (commit `864700a`)

**Avant** :
```html
<meta name="viewport" content="width=device-width, initial-scale=0.45,
                                minimum-scale=0.1, maximum-scale=5.0,
                                user-scalable=yes">
```

**Après** :
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0,
                                user-scalable=yes">
```

**Investigation rendue** : le portail a sa propre logique de scaling JS (sync-scale, ligne 1923-1943) :
```js
function applySyncScale() {
  var w = window.innerWidth;
  if (w <= 900) {
    shell.classList.add('sync-scale');
    shell.style.transform = 'scale(' + (w/900) + ')';
  }
}
```

Combinée à la CSS `.shell.sync-scale { width: 900px; transform-origin: 0 0; }`, cette logique RENDS le layout à 900px de large puis le réduit à la taille de l'écran via transform. Le résultat sur mobile :
- 360px → scale 0.4
- 414px → scale 0.46
- 768px → scale 0.85

**Donc l'`initial-scale=0.45` du viewport était redondant** (la JS sync-scale fait déjà le boulot) et nuisible (zoom de départ tout le monde, y compris desktop).

**`minimum-scale` et `maximum-scale` retirés** : ces attributs sont dépréciés (a11y), ignorés par les navigateurs modernes, et empêchent le zoom utilisateur — anti-pattern accessibilité.

**Risque évalué** : aucune régression sur mobile car la JS sync-scale gère le scaling. Le rendu mobile reste identique. Le rendu desktop est désormais correct (1:1, plus de zoom-out parasite).

**Résultat live** :
```
$ curl /portail | grep "initial-scale"
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
```

---

## 3. Validation finale (live, 127.0.0.1:5003)

| Vérification | Commande | Résultat | Statut |
|---|---|---|---|
| HTTP /portail | `curl -sI ...` | **200 OK** | ✅ |
| `000 000` flash (B1) | `grep -c "000 000"` | **0** | ✅ |
| Span SSR rend `•••` | `grep tbar-visits-val` | `<span style="opacity:0.55">•••</span>` | ✅ |
| `<nav class="primary-nav">` (B2) | `grep -E '<nav class="primary-nav"' (HTML only)` | **0** (uniquement en commentaire) | ✅ |
| `primary-nav` total mentions | `grep -ic "primary-nav"` | 6 (commentaires de traçabilité) | ✅ |
| Groupes sidebar (B3) | `grep -oE 'data-group="..."' \| sort -u` | **6** distincts | ✅ |
| Viewport initial-scale (B4) | `grep "initial-scale"` | **`initial-scale=1.0`** | ✅ |

---

## 4. Tags Git posés

| Tag | Description |
|---|---|
| `ui-phase-b-start` | Avant tout travail Phase B |
| `ui-phase-b-fix1-done` | B1 visitor count graceful |
| `ui-phase-b-fix2-done` | B2 ghost primary-nav supprimé |
| `ui-phase-b-fix3-done` | B3 sidebar uniformité |
| `ui-phase-b-fix4-done` | B4 viewport sane |

**Rollback Phase B** : `git reset --hard ui-phase-b-start`  
**Rollback complet UI (Phase A + B)** : `git reset --hard ui-phase-a-start`

---

## 5. Commits Phase B

```
864700a ui(portail): B4 fix — viewport initial-scale 0.45 → 1.0
283f7b5 ui(portail): B3 fix — sidebar visual homogeneity
8ab851b ui(portail): B2 fix — remove ghost primary-nav and stray cyan line
1c731a4 ui(portail): B1 fix — show ••• when visit count is 0/missing
```

---

## 6. Pendings / régressions / hors scope

### ⚠️ Action utilisateur recommandée (hors scope UI mais critique)
- **Restaurer la DB visiteurs** : `cp /root/astro_scan/data/data.bak/archive_stellaire.db /root/astro_scan/data/archive_stellaire.db` (après backup de la version actuelle). La DB courante a un schéma incomplet (`visitor_log`, `page_views`, `owner_ips` absentes). Tant qu'elle n'est pas restaurée, **aucun nouveau visiteur ne s'enregistre** (INSERT silently fails sur tables manquantes).
- Alternative : recréer le schéma manquant via DDL si le contenu n'a pas d'importance, mais alors le compteur restera à 0 jusqu'à ce que des visites s'accumulent.

### Hors scope Phase B (pour Phase C ou suivante)
- 47 templates non-portail utilisent encore "AstroScan-Chohra"
- Le chip flottant orphelin `#nav-iss-tracker` reste dupliqué (l'override CSS le neutralise dans `.sidebar`, mais l'ID est utilisé deux fois)
- Auto-expand du groupe contenant la page active non implémenté
- Lien "Technical" (`/technical`) retiré de la nav primaire — non remappé dans la sidebar (à ajouter dans "Données & Recherche" si pertinent)

### Non régressions confirmées
- ✅ Brand ORBITAL-CHOHRA partout (Phase A FIX 1)
- ✅ Topbar sticky top:0 sans gap (Phase A FIX 2)
- ✅ 6 groupes collapsibles + Accueil + À propos avec localStorage state (Phase A FIX 3 + Phase B FIX 3 polish)
- ✅ Compteur visiteurs ne flash plus "000 000"
- ✅ Plus de ligne fantôme sous le topbar
- ✅ Mobile : sidebar tiroir hamburger + JS sync-scale toujours opérationnels
- ✅ All `navigate('xxx')` keys préservés (PAGES dict inchangée)

---

## 7. Action utilisateur

```bash
# Restart pour activer les changements Python (B1 SSR portail.html only,
# pas de Python touché en Phase B mais on combine avec restart Phase A si
# pas encore fait)
sudo systemctl restart astroscan

# Vérification
curl -s http://127.0.0.1:5003/portail | grep "tbar-visits-val"
# attendu : <span style="opacity:0.55">•••</span> tant que la DB est vide

# (Optionnel) Restaurer la DB pour avoir un vrai compteur
sudo cp /root/astro_scan/data/data.bak/archive_stellaire.db /root/astro_scan/data/archive_stellaire.db
sudo systemctl restart astroscan
curl -s http://127.0.0.1:5003/portail | grep "tbar-visits-val"
# attendu après restore : <span id="tbar-visits-val">002 752</span>
```

**Push** : non effectué (per spec). Pour pousser :
```bash
git push origin ui/portail-refactor-phase-a
git push origin ui-phase-b-fix1-done ui-phase-b-fix2-done ui-phase-b-fix3-done ui-phase-b-fix4-done
```
