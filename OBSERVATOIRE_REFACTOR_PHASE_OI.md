# Phase O-I — Repositionnement chirurgical du widget Solar System

**Branche** : `ui/portail-refactor-phase-a`
**Date** : 2026-05-07
**Tags** : `oi-pre` (avant) → `oi-done` (après)
**Backup** : `templates/observatoire.html.bak_phase_oi`
**Commit** : `6440b70`

---

## Mission

Le widget Solar System livré en Phase O-H était fonctionnel et visuellement réussi (Kepler J2000 + ambiance cinématographique fusionnés). Mais inséré au mauvais endroit : entre la fin de `.tele-layout` et le début de la sky-map, en pleine largeur. L'utilisateur a précisé : « se n'est pas sa place mets la dans le vide noire » — le vide noir qui apparaissait **sous l'image APOD**, à gauche, **en face du panneau d'analyses** à droite.

Mission : déplacement chirurgical du widget vers ce vide. Aucune modification du code interne du widget.

---

## Diagnostic structurel (pourquoi il y avait un vide noir)

`.tele-layout` est un grid CSS :

```css
.tele-layout { display: grid; grid-template-columns: 1fr 370px; gap: 16px; margin-bottom: 20px; }
```

Avant Phase O-I, deux enfants seulement :

| Enfant | Position grid | Hauteur intrinsèque |
|---|---|---|
| `.tele-screen` (image APOD + overlays) | r1c1 | ~280–380 px |
| `.tele-panel` (5 analyse-box empilés) | r1c2 | beaucoup plus haut (≥ 600 px) |

Comportement par défaut du grid : `align-items: stretch`. La row 1 prend la hauteur du plus grand enfant (le panel), donc `.tele-screen` se retrouve étirée verticalement avec l'image plaquée en haut → un grand vide noir cosmétique sous l'image dans la cellule r1c1.

C'est **ce vide** que l'utilisateur a identifié comme la cible du widget.

---

## Avant / Après

### Position avant (Phase O-H) — ligne 1043

```html
<div class="tele-layout">
  <div class="tele-screen">…</div>
  <div class="tele-panel">…</div>
</div>            ← fermeture de tele-layout

<!-- PASS UI O-H — SOLAR SYSTEM LIVE. -->
<div class="solar-system-widget" id="solar-system-widget">…</div>

<!-- PASS UI O-G — sky-map. -->
<div class="sky-map-widget">…</div>
```

Visuellement :

```
┌─────────────────────┬──────────────┐
│  IMAGE APOD (r1c1)  │  PANEL       │
│  ┃ vide noir ┃      │  ANALYSES    │
│  ┃ étiré ┃          │  (r1c2)      │
└─────────────────────┴──────────────┘
┌────────────────────────────────────┐
│   SOLAR SYSTEM WIDGET (mauvais)    │
└────────────────────────────────────┘
┌────────────────────────────────────┐
│   SKY MAP                          │
└────────────────────────────────────┘
```

### Position après (Phase O-I) — ligne 1041

```html
<div class="tele-layout">
  <div class="tele-screen">…</div>
  <div class="tele-panel" style="grid-column:2;grid-row:1 / span 2">…</div>
  <!-- PASS UI O-I — déplacement Solar System -->
  <!-- PASS UI O-H — SOLAR SYSTEM LIVE. -->
  <div class="solar-system-widget" id="solar-system-widget"
       style="grid-column:1;grid-row:2;margin:0">…</div>
</div>            ← fermeture de tele-layout

<!-- PASS UI O-G — sky-map. -->
<div class="sky-map-widget">…</div>
```

Visuellement :

```
┌─────────────────────┬──────────────┐
│  IMAGE APOD (r1c1)  │              │
├─────────────────────┤  PANEL       │
│  SOLAR SYSTEM       │  ANALYSES    │
│  (r2c1, ex-vide ↑)  │  (r1-r2 c2)  │
└─────────────────────┴──────────────┘
┌────────────────────────────────────┐
│   SKY MAP                          │
└────────────────────────────────────┘
```

Le vide noir qui dérangeait l'utilisateur en r1c1 (sous l'image) est désormais habité par la vue orbitale Kepler avec sa comète et ses étoiles filantes.

---

## Modifications HTML (3 attributs, 1 déplacement)

1. **`.tele-panel`** : ajout `style="grid-column:2;grid-row:1 / span 2"` pour que le panneau d'analyses s'étende verticalement sur les 2 rows du grid. Sans ça, ajouter un widget en r2c1 créerait une r2c2 vide à droite. Avec ça, le panel garde toute sa hauteur sur les 2 rows et le widget arrive proprement à côté.

2. **`.solar-system-widget`** : ajout `style="grid-column:1;grid-row:2;margin:0"` pour :
   - Le forcer en col 1 row 2 (sous l'image, position cible) plutôt que la position auto qui aurait dépendu de l'ordre HTML
   - Annuler le `margin: 24px 16px` du widget en standalone (la grille gère elle-même le `gap: 16px` entre cellules — sans `margin:0`, le widget aurait été doublement décalé)

3. **Déplacement HTML** : extraction du bloc `<!-- PASS UI O-H -->` + `<div class="solar-system-widget">…</div>` depuis sa position post-`.tele-layout` vers l'**intérieur** de `.tele-layout` (avant le `</div>` fermant). Aucun changement à la structure interne du widget (header, canvas-wrap, footer, légende intacts).

4. **Marker O-I** ajouté juste avant le marker O-H pour traçabilité :
   ```html
   <!-- PASS UI O-I (2026-05-07) : déplacement Solar System widget vers le vide
        central de la zone APOD, position cible utilisateur. … -->
   ```

Aucune autre modification : le bloc CSS `.solar-system-widget` (Phase O-H) est intact, le bloc JS du widget est intact, les fichiers de la Phase O-G (sky-map) et O-F (cosmic-dashboard) ne sont pas touchés.

---

## Validation curl

```
$ systemctl is-active astroscan
active

$ curl -sI http://127.0.0.1:5003/observatoire | head -1
HTTP/1.1 200 OK

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "solar-system-widget"
4   # inchangé vs Phase O-H ✓ (HTML id+class + 2× CSS selectors)

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "PASS UI O-I"
1   # nouveau marker ✓

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "PASS UI O-H"
5   # inchangé (1 commentaire HTML + 1 commentaire CSS + 3× rules CSS) ✓

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "sky-star-bright"
2   # OH1 intact ✓

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "sky-map-widget"
4   # Phase O-G intact ✓

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "cosmic-dashboard"
11  # Phase O-F intact ✓
```

### Vérification de l'ordre DOM

```python
tele-screen     position: 48396
tele-panel      position: 49152      ← AVANT le widget Solar System (parent grid)
solar-system    position: 52855      ← DANS .tele-layout maintenant
tele-layout end position: 54548      ← le </div> de fermeture vient APRÈS le widget
sky-map-widget  position: 54779      ← APRÈS .tele-layout (Phase O-G)

Widget DANS .tele-layout : True ✓
Widget AVANT sky-map      : True ✓
```

---

## Pourquoi ce placement « comble » le vide

Le grid `.tele-layout` avait deux cellules occupées (r1c1 = image APOD, r1c2 = panel) et la hauteur de la row 1 était déterminée par le panel (haut). Cela créait un excédent de hauteur en r1c1 sous l'image — le vide noir.

Le fix transforme le grid de `2 cellules sur 1 row` en `3 cellules sur 2 rows` :

| Cellule | Contenu | Largeur | Comment |
|---|---|---|---|
| r1c1 | image APOD inchangée | 1fr | reste au format normal |
| r1-r2c2 | panel analyses | 370 px | étendu sur 2 rows via `grid-row:1 / span 2` |
| r2c1 | widget Solar System | 1fr | NOUVEAU : remplit l'ex-vide noir |

Comme `.tele-panel` s'étend désormais sur les 2 rows, sa hauteur naturelle (≥ 600 px) sert de référence pour les 2 rows combinées. La row 1 reprend une taille proche de la hauteur de l'image (~280–380 px) et la row 2 hérite du reste pour le widget. Plus de vide béant sous l'image.

Le widget Solar System a `aspect-ratio: 8 / 5` sur son `.ssw-canvas-wrap` ; en col 1 (1fr, largeur variable selon viewport), le canvas s'adapte fluidement et conserve les proportions.

---

## Tags git

| Tag | Pointe sur | Sens |
|---|---|---|
| `oi-pre` | ccff755 (HEAD avant Phase O-I) | Snapshot avant déplacement |
| `oi-done` | 6440b70 | Widget repositionné |

```
$ git log --oneline -4
6440b70 fix(observatoire): OI — repositionnement Solar System widget vers vide central APOD
ccff755 doc(observatoire): rapport Phase O-H — vivacité cosmique
ac1242d feat(observatoire): OH2 — widget Système Solaire Live (orbital + cinématique)
7361fd8 feat(observatoire): OH1 — twinkle des étoiles brillantes (mag<1.5)
```

---

## Contraintes respectées

- ✅ Aucune modification du code HTML/CSS/JS interne du widget Solar System (seul un `style="..."` placement a été ajouté à la balise wrapper, et le `margin:0` neutralise la marge externe par défaut sans toucher la règle CSS `.solar-system-widget` du bloc Phase O-H).
- ✅ Phases O-A à O-G **intactes** (vérifié par curl : sky-star-bright = 2, sky-map-widget = 4, cosmic-dashboard = 11, PASS UI O-H = 5).
- ✅ Aucun push remote.
- ✅ Backup `templates/observatoire.html.bak_phase_oi` créé avant patch.
- ✅ Tags `oi-pre` et `oi-done` posés.
- ✅ Single commit `6440b70`.
- ✅ Édition réalisée via outil Edit (pas de sed multi-ligne).

---

## Fichiers modifiés

| Fichier | Diff |
|---|---|
| `templates/observatoire.html` | +28 / −25 (déplacement bloc + 2 inline styles + marker O-I) |
| `OBSERVATOIRE_REFACTOR_PHASE_OI.md` | Ce rapport |

---

## Notes pour l'utilisateur

Aller sur `/observatoire`. La zone APOD en haut de la page affiche désormais :

- **À gauche en haut** : l'image APOD du jour (NASA / ESA), avec son overlay scanline et corners.
- **À gauche en bas** (ex-vide noir) : le widget Solar System Live — orbites Kepler avec planètes, comète elliptique, étoiles filantes, halo cyan sur la Terre avec label `◉ TLEMCEN`.
- **À droite, sur toute la hauteur** : le panneau d'analyses (Gemini, APOD du jour, Claude AI, MicroObservatory, bouton refresh) qui s'étend désormais sur les deux rangées du grid.

Sur mobile (< 768 px), le grid se comporte selon les media queries existantes du widget (aspect-ratio passe à 4:3, légende inline). Si nécessaire, le grid `.tele-layout` peut être passé en stack vertical via une media query future, mais ce n'est pas requis par cette phase.
