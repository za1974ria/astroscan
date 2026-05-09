# OBSERVATOIRE REFACTOR — PHASE O-B — VIVACITÉ + NAVIGATION

**Date** : 2026-05-07
**Branche** : `ui/portail-refactor-phase-a`
**Fichier modifié** : `templates/observatoire.html`
**Backup** : `templates/observatoire.html.bak_phase_ob`

---

## Objectif

Trois irritants visuels remontés après revue post Phase O-A :

1. Bloc « Mode: -, Status: -, Object: -, Score: -, Response: - » avec tirets
   hardcodés → message « non professionnel et inquiétant ».
2. Widget « VOIR MASTER · orbital-chohra-main · OFFLINE » en rouge → station
   solo, le rouge transmet un faux signal d'incident.
3. Aucun lien retour vers `/portail` → navigation cassée.

---

## Commits

| SHA       | Message                                                              |
| --------- | -------------------------------------------------------------------- |
| `62047cd` | ui(observatoire): OB1 — remove ghost Mode/Status block              |
| `94192d0` | ui(observatoire): OB2 — apaise OFFLINE → STATION SOLO (CSS)         |
| `1ff703c` | ui(observatoire): OB3 — breadcrumb retour portail                   |

## Tags Git

| Tag                         | Cible                                       |
| --------------------------- | ------------------------------------------- |
| `obs-phase-ob-pre-fix1`     | Avant OB1 (ghost block visible)             |
| `obs-phase-ob-fix1-done`    | Après OB1 (stub caché)                      |
| `obs-phase-ob-pre-fix2`     | Avant OB2 (OFFLINE rouge)                   |
| `obs-phase-ob-fix2-done`    | Après OB2 (STATION SOLO cyan)               |
| `obs-phase-ob-pre-fix3`     | Avant OB3 (pas de breadcrumb)               |
| `obs-phase-ob-fix3-done`    | Après OB3 (breadcrumb en place)             |

---

## OB1 — Suppression du bloc ghost Mode/Status

### Diagnostic

Le bloc HTML statique aux lignes 433-439 :

```html
<div class="status-panel asc-obs-status-panel">
  <div>Mode: <span id="mode-status">-</span></div>
  <div>Status: <span id="global-status">-</span></div>
  <div>Object: <span id="priority-object">-</span></div>
  <div>Score: <span id="priority-score">-</span></div>
  <div>Response: <span id="response-time">-</span></div>
</div>
```

### Vérification dépendances JS

```
$ grep -rn "mode-status|global-status|priority-object|priority-score|response-time" static/js/
static/js/astroscan_status_ui.js:30:  setText("mode-status", obs ?? "—");
static/js/astroscan_status_ui.js:37:  setText("global-status", gs);
static/js/astroscan_status_ui.js:44:  setText("priority-object", name);
static/js/astroscan_status_ui.js:48:  setText("priority-score", po.score);
static/js/astroscan_status_ui.js:57:  setText("response-time", ...);
static/js/astroscan_status_ui.js:68-72: ["mode-status", "global-status", "priority-object", "priority-score", "response-time"]
```

→ `astroscan_status_ui.js` utilise `setText()` sur les 5 IDs. On NE PEUT PAS
les supprimer du DOM sans casser le script. Stratégie : **stub caché**.

### Action

1. Bloc visible remplacé par stub `display:none`, `aria-hidden="true"`,
   classe `asc-obs-status-stub` (5 `<span>` vides conservant les IDs).
2. CSS orpheline `.status-panel.asc-obs-status-panel` (lignes 208-209)
   supprimée — plus aucune règle ne la cible.
3. `setText()` continue de fonctionner sans erreur, mais aucun rendu visuel.

### Comptes

| Élément                                      | Avant | Après |
| -------------------------------------------- | ----: | ----: |
| Texte « Mode: \<span »                       |     1 |     0 |
| Texte « Object: \<span »                     |     1 |     0 |
| Texte « Response: \<span »                   |     1 |     0 |
| 5 IDs ghost (mode/global/object/score/response) | 5  |     5 |
| Règles CSS `.status-panel.asc-obs-status-panel` | 2 |     0 |

---

## OB2 — OFFLINE → STATION SOLO (CSS)

### Diagnostic

Le span inline (ligne 442) :

```html
<span id="asc-view-sync-ws" data-state="open">
  <span style="color:#00ff9c;font-weight:bold;">ONLINE</span>
</span>
```

Au reload, `astroscan_view_sync.js` fait `dot.textContent = "OFFLINE"` +
`data-state="offline"` (la sync WS n'est pas active en mode solo).

CSS legacy (ligne 214) :
```css
#asc-view-sync-ws[data-state="offline"]{color:#ff6688!important;}
```
→ texte rouge, vide signifiant.

### Action (CSS-only — aucun .js touché)

Ajout en fin de `<style>` :

```css
#asc-view-sync-ws[data-state="offline"],
#asc-view-sync-ws[data-state="connecting"],
#asc-view-sync-ws[data-state="reconnecting"] {
  color: transparent !important;     /* masque le textContent OFFLINE */
  font-size: 0 !important;
  letter-spacing: 0 !important;
}
#asc-view-sync-ws[data-state="offline"]::before,
#asc-view-sync-ws[data-state="connecting"]::before,
#asc-view-sync-ws[data-state="reconnecting"]::before {
  content: "STATION SOLO";
  font-size: 9px;
  letter-spacing: 1.5px;
  color: var(--cyan);
  opacity: 0.6;
  font-weight: 700;
}
```

+ override de classes legacy `.asc-view-sync-master[data-state="offline"]`,
`.asc-view-sync-master.bad-offline`, `.asc-status-master.offline` →
fond cyan dim transparent, plus aucune connotation rouge.

### Comportement

- **Mode solo (ws=offline)** : visible « STATION SOLO » cyan dim opacity 0.6
- **Reconnecting/connecting** : « STATION SOLO » à opacity 0.4 (transitoire)
- **Sync active (ws=open)** : « ONLINE » cyan (rule legacy ligne 213 inchangée)

### Comptes

| Élément                          | Avant | Après |
| -------------------------------- | ----: | ----: |
| Texte « OFFLINE » coloré rouge   |     1 |     0 (visuellement masqué) |
| Texte « STATION SOLO » dans HTML |     0 |     2 (deux règles `::before`) |

---

## OB3 — Breadcrumb retour portail

### Action

#### HTML (juste après `<canvas id="starfield-bg">`)

```html
<nav class="breadcrumb-nav" aria-label="Navigation">
  <a href="/portail" class="breadcrumb-link">◄ PORTAIL</a>
  <span class="breadcrumb-sep">·</span>
  <span class="breadcrumb-current">OBSERVATOIRE</span>
</nav>
```

Bilingue : `PORTAIL/HOME`, `OBSERVATOIRE/OBSERVATORY` via `{% if lang %}`.

#### CSS (fin du `<style>`)

- `position: fixed; top: 12px; left: 16px; z-index: 1010` — flotte au-dessus
  du header (`z-index:10`) sans impacter le layout.
- `backdrop-filter: blur(4px)` + fond `rgba(0,12,24,0.55)` → reste lisible
  même quand survole une zone claire du header.
- Hover : `box-shadow: 0 0 12px rgba(0,212,255,0.4)` + texte `#cce4ff`
  → glow cyan signature.
- Mobile (`<= 768px`) : font 0.5rem, `OBSERVATOIRE` masqué pour gagner la
  place, seul `◄ PORTAIL` reste cliquable.

### Comptes

| Élément                  | Avant | Après |
| ------------------------ | ----: | ----: |
| `breadcrumb-nav`         |     0 |     1 |
| `breadcrumb-link`        |     0 |     1 (HTML) + 4 (règles CSS) |
| `◄ PORTAIL` (FR rendu)   |     0 |     1 |

---

## Validation finale

```
=== service ===                       active
=== HTTP ===                          HTTP/1.1 200 OK
=== OB1 ghost (=0) ===                0   ✓
=== OB1 stub IDs préservés (=5) ===   5   ✓
=== OB2 STATION SOLO (>=1) ===        2   ✓
=== OB3 breadcrumb (>=2) ===          4   ✓
```

Le service `astroscan` est resté `active` tout au long (Flask/gunicorn
recharge les templates à chaque requête, pas de restart nécessaire).

---

## Notes visuelles

- **OB1** : la zone du `#asc-sync-strip` est désormais ramassée — ne reste
  que le badge « SYNCHRO SERVEUR » + la mini-vue à droite (VUE master /
  session / STATION SOLO). Plus aucun « - » orphelin.
- **OB2** : la transition OFFLINE rouge → STATION SOLO cyan supprime
  l'effet « incident en cours » sur une station qui fonctionne nominalement
  en solo. Si la sync multi-observateur est réactivée plus tard
  (`data-state="open"`), aucun ajustement nécessaire — le `::before` ne se
  déclenche que sur les states `offline/connecting/reconnecting`.
- **OB3** : le breadcrumb à top-left est très petit (0.6rem) et reste cyan
  dim au repos. Au hover, le glow cyan signature se déclenche — le détail
  qui crée la différence. Sur mobile, l'élément se réduit à `◄ PORTAIL`
  seul, gain d'espace sur la barre.

---

## Hors-scope (Phase O-C éventuelle)

- Compactage cards observatoire (équivalent Phases D2/D3 du portail)
- Audit homogénéité couleurs résiduelles `#0CC` / `#7ddcff` / `#aabbcc`
- Restructuration sidebar AEGIS chat
- Cohérence visuelle inter-onglets (DSO/Targets/Hubble/JWST)

---

**Phase O-B : DONE — vivacité restaurée, navigation reconnectée.**
