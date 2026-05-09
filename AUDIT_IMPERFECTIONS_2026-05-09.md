# AUDIT DES IMPERFECTIONS ANODINES — ASTRO-SCAN

**Date** : 2026-05-09
**Périmètre** : 10 pages templates + 12 fichiers CSS du dossier `static/`
**Posture** : audit lecture seule, aucun fichier modifié.
**Référentiel cible** : SpaceX / NASA-JPL / Linear / Stripe (sobriété + polish typo / espacement).

---

## TL;DR — Ce qui ressort

ASTRO-SCAN possède **un système de design propre dans `static/css/design_tokens.css`**
(spacing 4/8/16/24/40/64, typo Orbitron + Space/Share Tech Mono + Inter,
4 transitions normalisées, variables couleurs claires) — mais **aucun template
priorité ne l'utilise**. Chaque template embarque un `:root { ... }` parallèle
qui redéfinit `--cyan`, `--text`, `--border`, etc. avec des nuances légèrement
différentes. Ce parallélisme produit l'essentiel de la "fatigue visuelle"
détectée : ce ne sont pas de gros défauts, ce sont des micro-écarts répétés
qui empêchent le site de "respirer pareil" d'une page à l'autre.

Le top imperfections, par ordre de "repos visuel offert" si corrigé :

1. **Polices Google Fonts importées via `@import` dans `<style>`** (observatoire.html)
   — bloque le rendu, oublié sur landing.html → FOUC variable d'une page à l'autre.
2. **Tailles de texte sous les 12 px** : 56× `10px`, 35× `11px`, 19× `9px`, 10× `9.5 px`.
   Lisibilité limite et hiérarchie typographique floue.
3. **Cyan multiple** : `#00d4ff` × 216 cohabite avec `#00eaff` × 21,
   `#00d8ff` × 10, `#00bfff` × 7, `#00ffff` × 11, `#00e5ff` × 9 → l'œil voit
   un "bleu qui flotte" sans en saisir la cause.
4. **`!important` épidémique** : `orbital_map.html` 163, `portail.html` 128,
   `observatoire.html` 102 → cascade CSS enrayée, hover/focus parfois cassés.
5. **315 `style="…"` inline dans `observatoire.html`** seul. La maintenance
   visuelle devient impossible.
6. **Animations sans `prefers-reduced-motion`** sur les 10 pages priorité
   (le pattern est respecté uniquement dans 3 CSS de blueprints secondaires).
7. **Boutons sans `cursor:pointer` explicite** : `portail.html` 43 boutons / 9 ;
   `observatoire.html` 44 / 19. Couplage avec `<button>` natif compense, mais
   les `<div onclick>` (nombreux) ne le font pas.
8. **`:focus-visible` quasi inexistant** (1 seul fichier) ; navigation au
   clavier sans retour visuel cohérent.
9. **Images poids lourd à la racine `static/`** : `earth.jpg` 2.6 MB,
   `earth_texture.jpg` 2.5 MB, `preview.png` 1.1 MB — non lazy, non WebP.
10. **`ce_soir.html`, `dashboard.html`, `orbital_dashboard.html`,
    `orbital_map.html` sans `<meta name="description">`** — SEO + partage social
    dégradé. Inversement `landing.html` et `observatoire.html` en ont **deux**
    (FR/EN) côte-à-côte, donc dupliquées pour Google.

Aucun de ces défauts n'est bloquant en prod. Tous se corrigent en
< 2 h chacun, plusieurs en < 30 min.

---

## Section 1 — Inventaire des variables CSS

### Système central : `static/css/design_tokens.css` (79 lignes, 49 variables)

Excellent point de départ. Le fichier est l'unique source de vérité pensée :

- **6 niveaux de spacing** sur grille 8 (`--space-xs:4px` → `--space-2xl:64px`)
- **6 tailles de texte** (`--text-xs:0.65rem` → `--text-2xl:1.5rem`)
- **3 polices** : Orbitron (display), Space Mono (mono), Inter (body)
- **3 transitions** standardisées (`fast/normal/slow` = 150/300/500 ms)
- **4 niveaux de radius** (4/8/16/24)
- **6 niveaux de z-index** nommés
- **Glows** déclinés par couleur sémantique (`--glow-accent`, `--glow-green`, etc.)

### Adoption par fichier

| Fichier | hex | rgb/rgba | vars `--` | Verdict |
|---------|----:|---------:|----------:|---------|
| `static/css/design_tokens.css` | 7 | 11 | 49 | ✅ source |
| `static/css/orbital_command.css` | 21 | 105 | 13 | ad-hoc partiel |
| `static/css/components.css` | 0 | 13 | 0 | utilise vars (bien) |
| `static/css/fixes.css` | 0 | 0 | 0 | OK |
| `static/scan_signal/css/scan_signal.css` | 15 | 38 | 23 | tokens locaux |
| `static/scan_signal/css/live_effects.css` | 7 | 14 | 0 | hardcodé |
| `static/scan_signal/css/panels.css` | 1 | 17 | 0 | hardcodé |
| `static/flight_radar/css/atc_premium.css` | 54 | 136 | 17 | **190 couleurs hardcodées** |
| `static/ground_assets/css/ground_assets.css` | 17 | 100 | 23 | ad-hoc |
| `static/ground_assets/css/panels.css` | 2 | 6 | 0 | hardcodé |
| `static/ground_assets/css/responsive.css` | 0 | 0 | 0 | OK |

### Top 10 couleurs hex répétées (toutes CSS confondues)

```
17  #00ff66    — vert "matrix" (n'existe pas dans tokens — devrait être #00ff88)
10  #ffffff    — blanc pur (devrait passer par var)
10  #ffb400    — orange/ambre (proche de --color-orange #ff8c00)
 8  #00c8e8    — cyan (variante de --color-accent #00d4ff)
 6  #00ffcc    — cyan-turquoise hors tokens
 6  #00e5ff    — variante de --color-accent
 3  #ffd166    — gold variante de --color-gold #f5c518
 3  #ff4444    — rouge (matche --color-red ✓)
 3  #05070a    — fond (proche --color-bg #050a14)
 3  #00ff88    — vert (matche --color-green ✓)
```

### Variables locales dans templates — collisions

Top names redéfinis localement dans plusieurs templates :

| Variable | Templates |
|----------|----------:|
| `--text` | 5 |
| `--cyan` | 5 |
| `--border` | 5 |
| `--void` | 4 |
| `--text-dim` | 4 |
| `--text-bright` | 4 |
| `--red` | 4 |
| `--panel` | 4 |
| `--mono` | 4 |
| `--green` | 4 |
| `--font` | 4 |
| `--border-bright` | 4 |
| `--amber` | 4 |
| `--sidebar-w` | 3 |

Chaque template a son propre mini-design-system. Les valeurs sont
**proches mais pas identiques** (ex. `portail.html` : `--cyan:#00d4ff`,
`landing.html` : `--cyan:#00e8ff`).

**Verdict Section 1** : design system **présent mais non adopté**.
Cohérent à l'intérieur d'un template, incohérent entre templates.

---

## Section 2 — Espacement : grille 4/8 partiellement respectée

### Top 15 valeurs `padding`/`margin` (toutes confondues, en `px`)

```
28  4px       ✅ tokens (--space-xs)
23  10px      ❌ hors grille
21  8px       ✅ tokens (--space-sm)
21  14px      ❌ hors grille (proche de 16)
19  6px       ❌ hors grille
15  12px      ❌ hors grille (entre 8 et 16)
10  5px       ❌ hors grille
10  2px       ❌ hors grille
 7  3px       ❌ hors grille
 6  18px      ❌ hors grille (entre 16 et 24)
 5  22px      ❌ hors grille (proche de 24)
 3  9px       ❌ hors grille
 3  7px       ❌ hors grille
 1  60px      ❌ hors grille (proche --space-2xl 64)
```

### Constat

- **Valeurs sur grille** (4 / 8) : 49 occurrences sur ~177 → **27 %**
- **Valeurs proches mais hors grille** : 22 px (devrait être 24), 14 px (16),
  18 px (16 ou 20), 60 px (64), 10 px (8 ou 12)…
- **Valeurs symptomatiques de "ajustement à l'œil"** : 3, 5, 7, 9, 22, 60.

**Verdict Section 2** : grille **non respectée** dans les templates inline.
Le fichier `design_tokens.css` la définit mais aucun `var(--space-*)` n'est
visible dans `portail.html`, `observatoire.html`, `ce_soir.html`,
`orbital_map.html`. Les valeurs hors grille (10/14/22) sont les plus
visuellement perturbantes : l'œil ne sait pas si c'est intentionnel.

**Exemples concrets**
- `landing.html:64-67` : `padding-top:72px; padding-bottom:48px; margin-top:56px; margin-bottom:56px;`
  → 72/56 = ratio 9/7, pas un rythme. Devrait être 64+48 ou 72+48.
- `portail.html:175` : `font-size: 8px !important; padding: 2px 8px !important;`
  → 8 px de typo + 2 px de padding = densité illisible.
- `ce_soir.html:198` : `transform:translateY(-2px)` au hover → micro-saut
  asymétrique vs autres pages qui font `-1px`.

---

## Section 3 — Typographie : système central existant, utilisation marginale

### Polices déclarées (uniques)

```
'Orbitron'         (display)         ← tokens + utilisé
'Share Tech Mono'  (mono)            ← utilisé partout (ne matche pas tokens)
'Space Mono'       (--font-mono)     ← déclaré dans tokens, jamais utilisé
'Inter'            (body)            ← déclaré dans tokens, jamais utilisé
system-ui          (fallback générique) ← utilisé directement landing.html
```

### Tailles de texte (top 30, toutes confondues)

```
56  10px        — taille "ambiante"
35  11px
19  9px         — limite lisibilité
17  12px
10  9.5px       — quart de pixel (n'existe pas)
10  13px
 6  18px / 14px
 5  var(--text-xs)
 4  22px        — "presque 24"
 3  8.5px / 16px / 10.5px
 1  var(--text-sm) / 8px / 48px / 32px / 26px / 24px / 20px / 11.5px
 1  1.15em / 0.9em / 0.6rem
```

### Constats

- **3 unités mélangées** : `px`, `rem`, `em` (ce dernier rare mais présent).
- **Tailles fractionnaires** : 8.5, 9.5, 10.5, 11.5 — l'œil ne les distingue pas
  des entiers ; elles brouillent juste la lecture du code.
- **Échelle non géométrique** : pas de ratio constant entre niveaux. Stripe et
  Linear utilisent un ratio ~1.125 ou 1.2. ASTRO-SCAN saute de 9 → 10 → 11
  → 12 → 13 (cinq niveaux dans 4 px) puis bond direct à 18, 22, 26.
- **`var(--text-*)` utilisé seulement 6 fois** sur ~150 occurrences typo.

### Poids

```
24  600        ← dominant
12  700
12  500
 1  bold       ← incohérence
```

✅ Système simple et homogène.

### Line-height

Très peu déclaré explicitement (héritage souvent par défaut). Pour des polices
mono à 9 px, line-height 1.0 produit du texte serré ; 1.5 du texte aéré.
Le mélange est invisible mais perceptible.

**Verdict Section 3** : typo **trop dense** (10 px standard est sous le minimum
recommandé pour confort moderne — Stripe utilise 14 px de base, Linear 13 px).
Système central ignoré.

---

## Section 4 — Transitions & animations

### Durations (top 15)

```
21  .2s     ←  dominante (200 ms en notation seconde)
10  .25s    
10  .15s    
 5  .35s    
 3  200ms   ←  même valeur que .2s, notation différente
 3  .1s     
 3  0.6s    
 2  .6s     
 2  .18s    
 2  .12s    
 2  0.18s   
 2  0.15s   
 1  500ms / .3s / 300ms
```

### Easing functions

```
34  ease            ← dominant générique
 2  cubic-bezier(0.2, 0.8, 0.2, 1)
 1  cubic-bezier(.2,.8,.3,1)   ← variante avec espace différent
 1  ease-out
```

### Constats

- **3 notations pour la même durée** : `.2s`, `0.2s`, `200ms`. Cosmétique mais
  signal de désordre.
- **Durations hors palette** : `.18s`, `.12s`, `.35s` — proches de `.2s` /
  `.1s` / `.3s` mais distinctes. Aucune raison technique.
- **`ease` partout** : c'est le `linear` du débutant. Linear, Stripe et NASA-JPL
  utilisent presque exclusivement des cubic-bezier custom (`.4, 0, .2, 1`
  Material, ou `.16, 1, .3, 1` "Quint").
- **Tokens définis mais non utilisés** : `--transition-fast/normal/slow` n'est
  référencé nulle part dans les templates priorité.

### Hover sans transition

| Template | `:hover` | `transition` | Déficit |
|----------|---------:|-------------:|---------|
| `landing.html` | 5 | 4 | ⚠️ +1 hover sans transition |
| `portail.html` | 14 | 19 | ✅ |
| `observatoire.html` | 12 | 16 | ✅ |
| `ce_soir.html` | 8 | 13 | ✅ |
| `dashboard.html` | 1 | 1 | ✅ |

Un seul léger déficit (`landing.html`). Globalement OK.

### `prefers-reduced-motion`

Présent uniquement dans :
- `static/scan_signal/css/live_effects.css`
- `static/ground_assets/css/ground_assets.css`
- `static/ground_assets/css/responsive.css`

**Absent dans tous les templates priorité** (landing/portail/observatoire/
ce_soir/orbital_*). Les animations starfield, glow et keyframes s'exécutent
inconditionnellement. Détail anodin → important pour les utilisateurs
sensibles au mal des transports / vestibulaires.

**Verdict Section 4** : animations **fonctionnelles mais génériques**.
Le polish "Linear/Stripe" demande un cubic-bezier signature unique et le
respect de `prefers-reduced-motion`.

---

## Section 5 — Images & médias

### Comptage par template (top 10 priorité)

| Template | `<img>` | sans `alt` | sans `loading="lazy"` |
|----------|--------:|-----------:|----------------------:|
| `observatoire.html` | 9 | 2 | 6 |
| `a_propos.html` | 3 | 0 | 0 ✅ |
| `portail.html` | 2 | 1 | 2 |
| `landing.html` | 1 | 1 | 1 |
| `orbital_dashboard.html` | 1 | 0 | 1 |
| autres | 0 | — | — |

### Top 10 images les plus lourdes dans `static/`

```
2.6 MB   static/earth.jpg
2.5 MB   static/earth_texture.jpg
1.1 MB   static/preview.png        (open-graph, partagée social)
261 KB   static/img/skyview/skyview_M27_DSS2_Red_*.gif
234 KB   static/img/skyview/skyview_M27_WISE_3.4_*.gif
218 KB   static/img/skyview/skyview_M104_DSS2_Red_*.gif (×2)
213 KB   static/img/skyview/skyview_NGC7293_GALEX_Near_UV_*.gif
211 KB   static/img/skyview/skyview_M13_DSS2_Red_*.gif
206 KB   static/img/skyview/skyview_NGC7293_DSS_*.gif
```

3 images **>500 KB**. Les 3 lourdes (`earth.jpg`, `earth_texture.jpg`,
`preview.png`) totalisent **6.3 MB** non optimisés.

### Constats

- `preview.png` est le `og:image` partagé sur tous les social media
  (twitter:image, og:image, …) — un PNG 1.1 MB mais
  **400×210 attendus pour OG** : suspecte conversion JPG/WebP à <100 KB.
- `earth.jpg` / `earth_texture.jpg` 2.5 MB chacun : utilisés en texture
  WebGL/Three.js ? Si oui, ils peuvent rester. Sinon, KTX2 ou WebP cible
  ~600 KB.
- Aucune image WebP/AVIF servie. Tous JPG/PNG/GIF.
- `observatoire.html` : 9 images dont 6 sans `loading="lazy"` — 2-3 secondes
  de bande passante gaspillées pour le hero seul.

**Verdict Section 5** : images **fonctionnelles** mais **non optimisées**.
Le profil bandwidth est typique d'un site amateur ; un script `cwebp -q 82`
sur les 3 lourdes économise ~5 MB par visite.

---

## Section 6 — Incohérences visuelles par page

### 6.1 — `landing.html` (573 lignes) — note polish 6.5/10

Top 5 imperfections :

1. `:64-67` — Padding/margin du hero non rythmé : 72/48/56/56 px.
   *Suggestion* : `padding-top:64px; padding-bottom:48px; margin-block:56px`
   (8-grid) ou tout en `var(--space-*)`. **Effort 5 min.**
2. `:71` — `font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`
   alors que les autres pages chargent Orbitron + Share Tech Mono. La page
   d'accueil **n'a pas la typo signature du site**. **Effort 30 min** (vérifier
   non-régression FOUC).
3. `:78` — `font-size: clamp(34px, 5vw, 40px)` pour le titre principal :
   le clamp est correct, mais 34→40 est un range étroit. À 1280 px de viewport
   on est à clamp = 5vw = 64 px **donc plafonné à 40 px** : le clamp ne sert à
   rien sur desktop. *Suggestion* : `clamp(36px, 6vw, 64px)`.
4. **5 `:hover` pour 4 `transition`** → un hover saute brutalement.
   Diff entre `.hero a:hover` et `.bullet-item:hover` (à vérifier ligne par ligne).
5. Aucun `prefers-reduced-motion` malgré le canvas starfield et l'animation
   d'apparition. **Effort 15 min** (un `@media` global qui désactive `transform`
   et `transition`).

### 6.2 — `portail.html` (2 617 lignes) — note polish 5/10

Top 5 imperfections :

1. **128 `!important`** dans le bloc `<style>` — symptôme de bataille avec
   un CSS hérité. Chaque ajout futur deviendra un nouveau `!important`.
   *Suggestion* : audit en 2 h pour ramener à <20 (cas vraiment inévitables).
2. **39 `style="…"` inline** — perturbe la maintenance ; si on change le
   token cyan, il faut visiter chaque inline.
3. `:175` — `font-size: 8px !important` : trop petit, illisible sur écran HD.
4. **Bloc `<style>` de 1 193 lignes** dans le template. À extraire vers
   `static/css/portail.css`. **Effort ~1 h**.
5. 43 `<button>` ou `onclick=` mais seulement 9 `cursor:pointer` explicites.
   Sur les boutons natifs, le navigateur applique un curseur par défaut, mais
   les `<div onclick>` (à compter cas par cas) ne le reçoivent pas.

### 6.3 — `observatoire.html` (3 530 lignes) — note polish 4/10

Top 5 imperfections :

1. **315 `style="…"` inline** — record du repo. Chaque modal, chaque carte,
   chaque badge a son style local. Refactor majeur (probablement 4-6 h).
2. **102 `!important`** + bloc `<style>` 644 lignes + un second bloc de
   217 lignes. La cascade est imprévisible.
3. `:50` — `@import url('https://fonts.googleapis.com/...')` dans le `<style>`.
   `@import` **bloque le rendu** parallèle des autres ressources. Doit
   être un `<link>` dans `<head>`, comme dans `portail.html` et `ephemerides.html`.
4. **2 images sans `alt`**, **6 images sans `loading="lazy"`** sur 9 totales.
   La hero APOD à plein écran est rechargée à chaque visite.
5. `viewport: maximum-scale=1.0, user-scalable=no` — empêche le zoom mobile,
   accessibilité dégradée.

### 6.4 — `ce_soir.html` (1 093 lignes) — note polish 6/10

Top 5 imperfections :

1. Aucune `<meta name="description">` — SEO + previews social vides.
2. Hovers utilisant `transform:translateY(-2px)` (`.oc:hover`, `.city-pill:hover`)
   alors que d'autres pages font `-1px`. Micro-saut perçu différent.
3. `:198` — combo `border-color`, `background`, `transform` au hover sans
   `transition` explicite sur la propriété `transform` (la rule globale couvre
   `all` mais peut être surchargée).
4. `:507` — un `:focus` manuel sur `.city-search-input` (✅ bien) mais aucun
   autre `:focus` sur les boutons de la page.
5. 21 `style="…"` inline + 10 `!important`.

### 6.5 — `dashboard.html` (36 lignes) — note polish N/A

Page minimale (probablement un wrapper / redirection). **Pas auditable
en l'état**. Vérifier sa raison d'être : si page vide, supprimer ; si
chargement async, ajouter un loading skeleton.

### 6.6 — `orbital_dashboard.html` (980 lignes) — note polish 6/10

Top 5 imperfections :

1. Aucune `<meta name="description">`.
2. 61 `style="…"` inline.
3. 5 `!important` (acceptable).
4. 1 image sans `loading="lazy"`.
5. Pas de `prefers-reduced-motion`.

### 6.7 — `orbital_map.html` (3 244 lignes) — note polish 3.5/10

Top 5 imperfections :

1. **163 `!important`** — record absolu. CSS quasiment ingouvernable.
2. **Bloc `<style>` de 973 lignes**.
3. `<html lang="">` **vide** — accessibilité critique cassée.
4. Aucune `<meta name="description">`.
5. **107 `style="…"` inline**, dont la plupart sur les contrôles de carte.

### 6.8 — `a_propos.html` (1 023 lignes) — note polish 7/10

Top 5 imperfections :

1. 71 `style="…"` inline.
2. 9 `!important`.
3. Pas de `prefers-reduced-motion`.
4. ✅ 3 images, toutes avec `alt` et `loading="lazy"` — la meilleure page
   du repo sur les images.
5. Bloc `<style>` 287 lignes — extractible.

### 6.9 — `about.html` (385 lignes) — note polish 7.5/10

Top 5 imperfections :

1. 2 `style="…"` inline (très peu — bonne hygiène).
2. 1 seul `!important`.
3. Pas de `prefers-reduced-motion`.
4. Aucune image.
5. Bloc `<style>` 125 lignes — concentré et lisible. La page la plus propre.

### 6.10 — `ephemerides.html` (669 lignes) — note polish 7/10

Top 5 imperfections :

1. 19 `style="…"` inline.
2. 10 `!important`.
3. `<link href="https://fonts.googleapis.com/..."` correctement dans `<head>`
   (✅ contrairement à `observatoire.html`).
4. Pas de `prefers-reduced-motion`.
5. Bloc `<style>` 264 lignes. Tokens locaux non synchronisés avec
   `design_tokens.css`.

---

## Section 7 — Accessibilité anodine

### Synthèse

| Item | État |
|------|------|
| Fichiers avec `:focus-visible` | **1** (sur 22 fichiers CSS+HTML examinés) |
| Total règles `:focus { … }` | **1** |
| Fichiers avec `::selection` custom | **0** |
| Fichiers avec `::-webkit-scrollbar` custom | 3 (orbital_command, panels.css scan_signal, atc_premium) |
| Fichiers avec `prefers-reduced-motion` | 3 (uniquement blueprints scan_signal & ground_assets) |
| Fichiers avec `prefers-color-scheme` | **0** |
| Fichiers avec `scroll-behavior:smooth` | 1 (`ground_assets/css/panels.css`) |
| Templates avec meta description | 5 / 10 |
| `<html lang="">` vide | 1 (`orbital_map.html`) |
| Inputs vs `<label>` (top pages) | 0 `<label>` quasi partout — repose sur `aria-label` |

### Top 10 issues a11y, priorité décroissante

1. **`orbital_map.html` `<html lang="">`** — screen-readers sans hint de langue.
2. **5 pages sans meta description** : `ce_soir.html`, `dashboard.html`,
   `orbital_dashboard.html`, `orbital_map.html`. SEO + Twitter card vides.
3. **`viewport=maximum-scale=1.0, user-scalable=no`** dans `observatoire.html`
   — empêche le zoom (a11y critique).
4. **Aucun `:focus-visible`** sur les boutons interactifs des 10 pages
   priorité — navigation clavier sans feedback.
5. **`prefers-reduced-motion` ignoré sur les 10 pages priorité.**
6. **`<input>` sans `<label>` associé** dans `observatoire.html` (3 inputs),
   `ce_soir.html` (1), `orbital_dashboard.html` (1), `orbital_map.html` (10).
   `aria-label` partiellement compensatoire.
7. **Boutons `<div onclick>`** non systématiquement assortis de
   `cursor:pointer` — `portail.html` et `observatoire.html` particulièrement.
8. **Couleurs texte sur fond cyan ténu (`rgba(0,212,255,.04)`)** — contraste
   < 3:1 sur les états hover de panneaux. WCAG AA exige 4.5:1.
9. **Pas d'`aria-current`** sur la nav active (vérification visuelle :
   sidebar des templates portail/observatoire indique l'état actif via
   couleur seule, pas via attribut ARIA).
10. **Liens sans `text-decoration` ni soulignement substitut** dans plusieurs
    blocs `.footer-links`, `.tbar-links` — un utilisateur daltonien voit le
    lien comme du texte.

---

## Section 8 — Détails de pro qui manquent (vs Linear / Stripe / SpaceX)

| Détail | Présent ? | Impact perçu |
|--------|:---------:|--------------|
| `:focus-visible` (vs `:focus` simple) | ❌ 1/22 | navigation clavier brute |
| `scroll-behavior: smooth` | ⚠️ 1 fichier | scroll instantané (vs glissé) |
| `::selection` custom (couleur sélection) | ❌ 0 | sélection bleue système |
| `::-webkit-scrollbar` custom | ⚠️ 3 fichiers | scrollbars OS par défaut sur 7 pages |
| `prefers-color-scheme` (light/dark auto) | ❌ 0 | site forcé dark, blanc agressif si user clair |
| `prefers-reduced-motion` global | ❌ | starfield/glow ininterruptibles |
| Loading **skeletons** (vs spinner) | ❌ aucun spinner détecté ; un `skeleton` mentionné dans `components.css` mais non utilisé | flashs de "rien" pendant le fetch |
| Police `font-display: swap` | ⚠️ partiel (Google Fonts l'inclut souvent par défaut, mais `@import` dans observatoire.html ne le force pas) | FOUC perceptible |
| `image-rendering: pixelated/optimizeQuality` sur images astro | ❌ | textures Earth peuvent paraître floues au zoom |
| `aspect-ratio` CSS sur conteneurs image | ❌ détecté | layout shift au chargement (CLS dégradé) |
| `content-visibility: auto` sur sections below-fold | ❌ | render bloqué tant que tout n'est pas parsé |
| Print stylesheet (`@media print`) | ❌ | impression illisible (pages noires) |

Aucun de ces points n'est critique. Pris ensemble, ils forment **la
différence "fait pro" vs "fait amateur"**.

---

## Section 9 — VERDICT SYNTHÉTIQUE — TOP 10 KAIZEN DU JOUR

| # | Imperfection | Page | Repos visuel | Effort | Aujourd'hui ? |
|---|--------------|------|:------------:|:------:|:-------------:|
| 1 | Remplacer `@import` Google Fonts par `<link>` dans `<head>` | `observatoire.html:50` | 🟢 | ⚡ <30 min | ✅ oui |
| 2 | Ajouter `<meta name="description">` aux 5 pages qui en manquent | ce_soir, dashboard, orbital_dashboard, orbital_map | 🟢 | ⚡ <30 min | ✅ oui |
| 3 | Réparer `<html lang="">` vide | `orbital_map.html` | 🟢 | ⚡ <5 min | ✅ oui |
| 4 | Ajouter `@media (prefers-reduced-motion: reduce)` global dans `design_tokens.css` | tous | 🟢 | ⚡ 30 min | ✅ oui |
| 5 | Ajouter `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }` global | tous | 🟡 | ⚡ <30 min | ✅ oui |
| 6 | Convertir `earth.jpg`/`earth_texture.jpg`/`preview.png` en WebP qualité 82 (gain ≈ 5 MB) | static/ | 🟢 | ⏱ 30 min-1 h | ✅ oui |
| 7 | Unifier les durations de transitions sur `var(--transition-fast/normal/slow)` | tous | 🟡 | ⏱ 1 h | 🤔 demain |
| 8 | Standardiser le cyan : remplacer `#00eaff`, `#00d8ff`, `#00bfff`, `#00e5ff` par `var(--color-accent)` | tous CSS | 🟢 | ⏱ 1-2 h | 🤔 demain |
| 9 | Extraire les blocs `<style>` >500 lignes vers `static/css/<page>.css` (portail, observatoire, orbital_map) | 3 templates | 🟢 | 🕐 4-6 h | ❌ non (dédier 1 j) |
| 10 | Reconquérir les `!important` dans `orbital_map.html` (163 → <20) | `orbital_map.html` | ⚪ | 🕐 >2 h | ❌ non |

### Ordre d'attaque recommandé pour AUJOURD'HUI

**Bloc 1 (≈ 1 h, gain SEO + a11y immédiat)** : items #1 + #2 + #3 + #5
— corrections quasi-mécaniques, pas de risque visuel.

**Bloc 2 (≈ 30 min, gain perf bandwidth)** : item #6 (conversion WebP des 3
images lourdes via `cwebp -q 82` + remplacement `<img src=…>` dans les
templates concernés).

**Bloc 3 (≈ 30 min, gain perçu sur tout le site)** : item #4 — bouge
un seul fichier `design_tokens.css` mais protège l'utilisateur sensible
sur les 10 pages.

**Total bloc Kaizen 2026-05-09** : **~2 h, 4 commits, 0 risque prod**.
Le site change de niveau visuel/UX sans qu'on touche à un seul algorithme.

---

## Annexe — Méthodologie

- Lecture seule (`grep`, `find`, `awk`, `cat`, `wc`). Aucun fichier modifié.
- Heuristiques :
  - `<button>` natif : compté comme bouton mais peut hériter de `cursor:pointer`
    par UA → la colonne "sans cursor" sous-estime probablement la couverture.
  - "Hover sans transition" : compté au niveau template (pas global) — ne
    capture pas les `transition` héritées par cascade.
  - "Style inline" : compte les `style="…"` HTML, pas les `<style>` blocks.
- Top 10 priorité dans l'ordre demandé : `landing → portail → observatoire
  → ce_soir → dashboard → orbital_dashboard → orbital_map → a_propos
  → about → ephemerides`.
- Tagueur de pages CSS hors-priorité (`flight_radar`, `scan_signal`,
  `ground_assets`, `lab`, `nasa_proxy`, etc.) examiné via leurs CSS dédiés
  uniquement, pas leurs templates.
- Données chiffrées prises sur l'arborescence à la date 2026-05-09,
  branche `main` après cleanup (3530 lignes pour observatoire.html, etc.).
