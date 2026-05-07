# OBSERVATOIRE REFACTOR — PHASE O-A — IDENTITÉ VISUELLE COSMOS

**Date** : 2026-05-07
**Branche** : `ui/portail-refactor-phase-a`
**Fichier modifié** : `templates/observatoire.html` (2125 → 2128 lignes)
**Backup** : `templates/observatoire.html.bak_phase_oa`

---

## Objectif

Migrer `/observatoire` vers la même identité visuelle que `/portail` (déjà validée Phases A→D5) :
fond starfield Canvas + transparence body, marque `ORBITAL-CHOHRA`, palette cyan cosmos `#00d4ff`.

Aucune modification du layout, des widgets, ou de la logique JS.

---

## Commits

| SHA       | Message                                                              |
| --------- | -------------------------------------------------------------------- |
| `8006b2a` | ui(observatoire): OA1 — Canvas starfield + transparent body         |
| `3290219` | ui(observatoire): OA2 — brand AstroScan-Chohra → ORBITAL-CHOHRA     |
| `4f5cac8` | ui(observatoire): OA3 — palette green matrix → cyan cosmos          |

## Tags Git

| Tag                         | Cible                                       |
| --------------------------- | ------------------------------------------- |
| `obs-phase-oa-pre-fix1`     | Avant OA1 (état initial — green matrix)     |
| `obs-phase-oa-fix1-done`    | Après OA1 (canvas en place)                 |
| `obs-phase-oa-pre-fix2`     | Avant OA2                                   |
| `obs-phase-oa-fix2-done`    | Après OA2 (marque migrée)                   |
| `obs-phase-oa-pre-fix3`     | Avant OA3                                   |
| `obs-phase-oa-fix3-done`    | Après OA3 (palette cyan)                    |

---

## OA1 — Canvas starfield + body transparent

### Modifications

1. **CSS `html, body`** (ligne 43) : `background: var(--bg)` → `background: transparent`
   (rendu du canvas derrière les widgets).
2. **CSS `#starfield-bg`** (nouvelle règle ligne 44) :
   `position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:-1;
    pointer-events:none; background:radial-gradient(ellipse at center, #020615, #000409, #000000);`
3. **`<canvas id="starfield-bg" aria-hidden="true">`** inséré juste après `<body>` (ligne 404).
4. **`<script defer src="/static/js/starfield.js">`** inséré avant `</body>` (ligne 2126).

`starfield.js` est exactement le même fichier déjà validé sur `/portail` (Phase C).
Le `<div id="stars">` historique reste en place : seconde couche scintillement par-dessus le canvas.

---

## OA2 — Marque AstroScan-Chohra → ORBITAL-CHOHRA

### Comptes

| Token              | Avant | Après |
| ------------------ | ----: | ----: |
| `AstroScan-Chohra` |     9 |     0 |
| `Zakaria Chohra — AstroScan` (author meta) | 1 | 0 |
| `ORBITAL-CHOHRA`   |     1 |    11 |

### Lignes touchées

- L7, L17 : `<title>` (EN + FR)
- L10, L20 : `<meta property="og:title">`
- L14, L24 : `<meta name="twitter:title">`
- L27 : `<meta name="author">` (suffixe migré)
- L36 : `<meta property="og:site_name">`
- L411 : `<div class="logo">ORBITAL-CHOHRA · Observatory</div>`

L540 (sous-titre directeur) et L1364 (commentaire endpoint) étaient déjà en `ORBITAL-CHOHRA`.

---

## OA3 — Palette green matrix → cyan cosmos

### Mapping appliqué (par str.replace, dans l'ordre)

| Avant                       | Après                       |
| --------------------------- | --------------------------- |
| `--acid:#00ff88` (def `:root`) | `--cyan:#00d4ff`         |
| `#00ff88`                   | `#00d4ff`                   |
| `#00FF88`                   | `#00d4ff`                   |
| `0,255,136` (substring rgba — couvre TOUS les alphas : .03 .04 .05 .06 .07 .08 .1 .12 .15 .16 .18 .2 .25 .26 .3 .35 .4 .5 .6 .7 + variantes 0.04, 0.06, 0.08, 0.1, 0.15, 0.2, 0.4, 0.6) | `0,212,255` |
| `var(--acid)`               | `var(--cyan)`               |

### Comptes (occurrences via `str.count`, pas `grep -c`)

| Token                | Avant | Après |
| -------------------- | ----: | ----: |
| `#00ff88`            |    45 |     0 |
| `#00FF88`            |     0 |     0 |
| `0,255,136` (rgba)   |    73 |     0 |
| `var(--acid)`        |    54 |     0 |
| `--acid:#00ff88` def |     1 |     0 |
| `#00d4ff`            |     2 |    47 |
| `0,212,255`          |     4 |    77 |
| `var(--cyan)`        |     0 |    54 |

### Variable `:root`

```diff
- :root{--acid:#00ff88;--blue:#00aaff;--purple:#aa44ff;--amber:#ffaa00;--red:#ff4466;--bg:#020810;}
+ :root{--cyan:#00d4ff;--blue:#00aaff;--purple:#aa44ff;--amber:#ffaa00;--red:#ff4466;--bg:#020810;}
```

`--bg` reste à `#020810` (utilisé seulement comme fallback ; le body est transparent).

---

## Validation finale (curl + service)

```
=== service ===           active
=== HTTP ===              HTTP/1.1 200 OK
=== starfield-bg (>=2) ===   2  ✓  (CSS rule + canvas tag)
=== starfield.js (>=1) ===   1  ✓
=== AstroScan-Chohra (=0) === 0  ✓
=== ORBITAL-CHOHRA (>=5) ===  8  ✓  (rendu pour une seule langue active à la fois)
=== green tokens (=0) ===    0  ✓  (00ff88|0,255,136|var(--acid))
```

Service `astroscan.service` : `active` — Flask/gunicorn a rechargé le template
automatiquement (pas de restart manuel nécessaire, le fichier est lu à chaque requête).

---

## Notes visuelles

- Le canvas `#starfield-bg` est en `z-index:-1` : tout le contenu existant
  (header, nav, main, sidebar AEGIS, modals) reste devant sans intervention layout.
- Le `<div id="stars">` JS-généré (z-index:0, pointer-events:none) ajoute une
  deuxième couche scintillement par-dessus le canvas : double profondeur cosmique.
- Le `radial-gradient` du body (`.nebula`) utilisait `rgba(0,255,136,.05)` — désormais
  `rgba(0,212,255,.05)` : la lueur diffuse en bas-droite est maintenant cyan.
- Le `linear-gradient` du logo header (`linear-gradient(135deg,#00ff88,#00aaff,#aa44ff)`)
  est devenu `linear-gradient(135deg,#00d4ff,#00aaff,#aa44ff)` : le dégradé du logo
  passe désormais cyan→blue→purple en continu (avant : green→blue→purple, rupture chromatique).
- L'animation `@keyframes glow` (`text-shadow:0 0 8px #00ff88`) glow désormais cyan :
  cohérence avec l'identité portail.

---

## Hors-scope (pour Phase O-B)

- Restructuration HTML de la sidebar (ordre/regroupement widgets)
- Compactage vertical des cards (équivalent Phases D2/D3 du portail)
- Audit homogénéité couleurs résiduelles `#0CC` / `#7ddcff` / `#aabbcc` / `#556677`
- Migration sources de données live et cohérence visuelle inter-onglets

---

**Phase O-A : DONE — identité cosmos cyan en place sur `/observatoire`.**
