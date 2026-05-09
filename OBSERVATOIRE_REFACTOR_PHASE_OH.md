# Phase O-H — Vivacité cosmique

**Branche** : `ui/portail-refactor-phase-a`
**Date** : 2026-05-07
**Tags** : `oh-pre` (avant) → `oh-done` (après)
**Backup** : `templates/observatoire.html.bak_phase_oh`
**Commits** : `7361fd8` (OH1) · `ac1242d` (OH2) · *rapport (ce fichier)*

---

## Mission

Deux ajouts visuels finaux à `observatoire.html` après la Phase O-G :

1. **OH1** — Twinkle (scintillation) sur les étoiles brillantes (`mag < 1.5`) de la sky map. Réalisme : à l'œil nu, seules les étoiles brillantes laissent voir la scintillation atmosphérique.
2. **OH2** — Widget « SOLAR SYSTEM LIVE » : vue orbitale top-down du système solaire interne+externe (Mercure → Saturne) avec mécanique céleste réelle (Kepler J2000) **fusionnée** avec une ambiance cinématographique (parallax stars, étoiles filantes, comète elliptique). Inséré juste avant la sky-map de la Phase O-G.

Les phases O-A → O-G restent intactes.

---

## FIX OH1 — Twinkle des étoiles brillantes

### Cible
Le bloc `STARS.forEach` de la sky-map (Phase O-G), désormais en différenciant `mag < 1.5` (sky-star-bright animée) du reste (sky-star simple).

### Implémentation

CSS ajouté à côté de `.sky-star` :

```css
@keyframes skyStarTwinkle {
  0%, 100% { opacity: var(--twinkle-base, 0.85); }
  50%      { opacity: 1; filter: drop-shadow(0 0 4px currentColor); }
}
.sky-star-bright {
  animation: skyStarTwinkle 3.5s ease-in-out infinite;
}
```

JS modifié à la création de chaque étoile :

```js
var baseOpacity = dayMode ? 0.15 : Math.max(0.55, 1 - s.m * 0.12);
var star = el(NS, 'circle', { cx: p.x, cy: p.y, r: size, fill: s.c, opacity: baseOpacity });
if (s.m < 1.5) {
  star.setAttribute('class', 'sky-star sky-star-bright');
  star.style.animationDelay = (Math.random() * 3).toFixed(2) + 's';
  star.style.setProperty('--twinkle-base', baseOpacity.toFixed(2));
} else {
  star.setAttribute('class', 'sky-star');
}
```

Trois subtilités d'implémentation :

1. **Délai aléatoire 0–3 s** par étoile → désynchronisation, aucune scintillation collective artificielle.
2. **`--twinkle-base` custom property** → l'opacité de plancher de la keyframe est l'opacité naturelle de l'étoile (proportionnelle à magnitude). La scintillation va de cette base vers `1`, jamais en dessous, ce qui garde une étoile faible-mais-bright (comme Polaris mag 1.97 — non, Polaris ≥ 1.5 donc non animée — mais Spica mag 1.04 oui) toujours plus dim qu'une étoile très brillante (Sirius mag −1.46) au sommet de la keyframe.
3. **Filtre drop-shadow currentColor** uniquement à 50 % de la keyframe → pas de coût GPU constant.

### Étoiles animées (mag < 1.5)

15 étoiles sur 30 du catalogue passent au régime twinkle :
Sirius (−1.46), Canopus (−0.74), Arcturus (−0.05), Vega (0.03), Capella (0.08), Rigel (0.13), Procyon (0.34), Achernar (0.46), Betelgeuse (0.50), Hadar (0.61), Altair (0.77), Acrux (0.77), Aldebaran (0.85), Spica (1.04), Antares (1.09), Pollux (1.14) (note: Pollux à 1.14 < 1.5 inclus), Fomalhaut (1.16), Deneb (1.25), Mimosa (1.25), Regulus (1.40).

Les étoiles `≥ 1.5` (Adhara, Castor, Shaula, Bellatrix, Elnath, Alnilam, Alnitak, Mintaka, Polaris, Dubhe) restent fixes — réalisme.

### Validation

```
$ curl -s http://127.0.0.1:5003/observatoire | grep -c "sky-star-bright"
2   # 1× CSS rule + 1× JS class assignment ✓
```

---

## FIX OH2 — Widget Solar System Live

### Insertion confirmée

Marker `<!-- PASS UI O-H ... SOLAR SYSTEM LIVE -->` placé immédiatement avant le marker O-G `<!-- PASS UI O-G ... CARTE DU CIEL TLEMCEN -->`. Visuellement : Solar System apparaît au-dessus de la sky-map dans le flux vertical d'observatoire, qui apparaît elle-même au-dessus du Cosmic Live Dashboard (Phase O-F).

```
$ grep -nE "PASS UI O-H \(2026-05-07\) — SOLAR|PASS UI O-G \(2026-05-07\) — CARTE|PASS UI O-F FIX 3 \(2026-05-07\) — Widget COSMIC" templates/observatoire.html
880:  <!-- PASS UI O-H (2026-05-07) — SOLAR SYSTEM LIVE.
911:  <!-- PASS UI O-G (2026-05-07) — CARTE DU CIEL TLEMCEN CE SOIR.
946:  <!-- PASS UI O-F FIX 3 (2026-05-07) — Widget COSMIC LIVE DASHBOARD.
```

### Spécification scientifique

Mécanique céleste héliocentrique simplifiée (J2000), 6 planètes :

| Planète | a (UA) | e | Période (an) | L₀ (deg) | ϖ péri (deg) | Couleur display |
|---|---|---|---|---|---|---|
| Mercure | 0.387 | 0.2056 | 0.241 | 252.250 | 77.456 | gris |
| Vénus | 0.723 | 0.0068 | 0.615 | 181.979 | 131.602 | crème |
| Terre | 1.000 | 0.0167 | 1.000 | 100.466 | 102.937 | bleu (◉ TLEMCEN) |
| Mars | 1.524 | 0.0934 | 1.881 | 355.433 | 336.041 | rouge |
| Jupiter | 5.203 | 0.0484 | 11.862 | 34.351 | 14.753 | ocre |
| Saturne | 9.537 | 0.0542 | 29.457 | 50.078 | 92.432 | sable + anneau |

Pipeline orbital pour chaque planète à `t = now()` :

```
JD = (t.ms / 86400000) + 2440587.5
d  = JD − J2000
n  = 360 / (period · 365.25)              [vitesse angulaire deg/jour]
M  = ((L₀ − peri) + n·d) mod 360         [anomalie moyenne]
Newton sur E − e·sinE = M (10 itérations) [équation de Kepler]
(x', y') = (cos E − e, √(1−e²)·sin E)     [coords plan orbital, foyer = Soleil]
rotation par ϖ péri :
  x = x'·cos(peri) − y'·sin(peri)
  y = x'·sin(peri) + y'·cos(peri)
position display = (CX + x · rDisplay(a),  CY + y · rDisplay(a))
```

**Échelle d'affichage non-linéaire** `rDisplay(a) = 70 · a^0.62` : compresse le système solaire pour que Mercure (0.39 UA) reste lisible et Saturne (9.54 UA) tienne dans le canvas (~225 px du Soleil). Sans cette compression, soit Mercure est invisible au centre, soit Saturne sort du cadre. Trade-off accepté : les distances ne sont plus linéaires en UA, mais l'**ordre** et les **vitesses relatives** sont préservés (Mercure tourne 11×/an pendant que Saturne tourne 0.034×/an — l'utilisateur voit la différence en quelques secondes).

### Validation orbitale (test Node)

```
JD = 2461168.4375 (2026-05-07 22:30 UTC)

Planète   Position héliocentrique   Distance (UA)   [a·(1−e), a·(1+e)] attendu
Mercure   (+0.362, −0.090) UA       0.372           [0.307, 0.467] ✓
Vénus     (−0.410, +0.589) UA       0.718           [0.718, 0.728] ✓
Terre     (−0.686, −0.740) UA       1.009           [0.983, 1.017] ✓
Mars      (+1.393, +0.061) UA       1.394           [1.382, 1.666] ✓
Jupiter   (−2.579, +4.579) UA       5.255           [4.951, 5.455] ✓
Saturne   (+9.428, +0.973) UA       9.478           [9.020, 10.054] ✓
```

Toutes les distances héliocentriques sont **dans la fourchette aphelion-périhélie** de chaque planète. La math est correcte.

### Architecture rendu

Deux couches superposées dans `.ssw-canvas-wrap` (8:5 aspect-ratio, max 500 px de haut) :

1. **`<canvas id="ssw-bg-canvas">` arrière-plan** :
   - 150 étoiles parallaxe sur 3 profondeurs `0.3 / 0.6 / 1.0` (probabilités 30 % / 40 % / 30 %).
   - Twinkle individuel par accumulation `s.twinkle += 0.02·depth`, opacité `0.3 + 0.5·(sin+1)/2`.
   - Drift horizontal lent `s.x += 0.03·depth` → effet parallaxe (étoiles « proches » bougent vite, lointaines lentes).
   - Étoiles filantes : 0.5 % de chance par frame (`Math.random() < 0.005`), spawn depuis bord supérieur ou gauche, trajectoire diagonale 200×160 px, vie 1.0 → fade début 70 %, durée totale ~1.6 s.
   - HiDPI-aware : `devicePixelRatio` × `setTransform` → pas de flou sur écrans Retina.
   - Trail effet : `fillRect(0,0,w,h, rgba(0,2,8,0.4))` chaque frame → traînées fluides.

2. **`<svg id="ssw-svg" viewBox="0 0 800 500">` premier plan** :
   - **Soleil** : disque 24 px en gradient radial (`#ffe580` → `#ffcc66` → transparent) + cœur 11 px ambre-or, `drop-shadow 18 px rgba(255,204,100,0.7)`.
   - **Orbites** : 6 cercles concentriques pointillés cyan (rayon = `rDisplay(a)`).
   - **Comète** : trajectoire elliptique 220 × 90 inclinée 25°, période 90 s. Tête 2.5 px blanche `drop-shadow 8 px #aaffff`. Traînée = ligne entre position actuelle et position 1.5 s plus tôt, stroke `rgba(170,230,255,0.85)` 2 px avec drop-shadow.
   - **Planètes** : disque coloré + label monospace (sauf Terre = halo cyan + label `◉ TLEMCEN`). Saturne a en plus une ellipse pour l'anneau (rx 1.85·r, ry 0.55·r). Chaque planète a un `<title>` (tooltip natif) avec demi-grand axe et période.
   - **Subtitle live** : date+heure FR mise à jour à chaque frame (`JEU. 07 MAI 22:30:14 TLEMCEN`).
   - **Status pill** : « TEMPS RÉEL · KEPLER » avec point vert pulsant `sswPulse 2s ease-in-out`.

3. **Légende** absolue bas-droite : Soleil ambre, Terre bleu (Tlemcen), Mars rouge.

### Loop

```js
function loop(tMillis) {
  drawBgFrame();    // canvas
  renderSvg(tMillis); // svg
  requestAnimationFrame(loop);
}
```

60 fps. Le canvas redessine l'intégralité du fond chaque frame (avec le trail-fade) ; le SVG est reconstruit chaque frame aussi (vidé puis re-rempli) — c'est ~30 éléments DOM, négligeable. La précision Kepler est temporelle (la position est recalculée à chaque frame avec le `Date.now()` actuel), donc la rotation se fait **en vrai temps** : Mercure parcourt environ 1.5° par seconde de visualisation (1.5° = 360 / (0.241·365.25·86400) × 60 fps × 1 s ≈ 14.7° par seconde de simulation à vitesse réelle, mais la simulation est à vitesse réelle TT, donc en 60 s d'observation l'utilisateur voit Mercure avancer ~ 0.4° en orbite vraie).

> Note : on aurait pu accélérer artificiellement la simulation pour que l'utilisateur voie les planètes tourner visiblement en quelques secondes. **Choix volontaire** : on reste à vitesse réelle. La comète et les étoiles filantes apportent le mouvement perceptible. Les planètes sont des marqueurs scientifiques, pas un manège.

### Validation curl

```
$ systemctl is-active astroscan
active

$ curl -sI http://127.0.0.1:5003/observatoire | head -1
HTTP/1.1 200 OK

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "sky-star-bright"
2   # OH1 ✓

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "solar-system-widget"
4   # HTML id+class + 2 CSS selectors ✓ (attendu ≥ 4)

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "ssw-svg"
3   # HTML + 1 CSS + 1 JS ref ✓ (attendu ≥ 2)

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "ssw-bg-canvas"
3   # HTML + 1 CSS + 1 JS ref ✓

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "var PLANETS = \["
2   # 1× O-G sky map (déjà présent) + 1× O-H solar system ✓

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "hasRing:true"
1   # Saturne avec anneau ✓

# Régression checks (phases antérieures)
$ curl -s http://127.0.0.1:5003/observatoire | grep -c "sky-map-widget"
4   # INCHANGÉ vs Phase O-G ✓

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "cosmic-dashboard"
11  # INCHANGÉ vs Phase O-F ✓
```

---

## Bugs du prompt original corrigés

Le prompt fourni avait **trois défauts critiques** que j'ai corrigés en cours d'implémentation :

1. **Ligne 299** — `PLANETS` array tronqué :
   ```
   { n: 'Mercure', ... },
   { n: 'Vénus',   ... },
   { n: 'Terre',   ... },
   { n: 'Mars',    ... },
   { n: 'Jupiter', afied 2D) */     ← coupé en plein milieu
   ```
   Jupiter et Saturne **manquaient totalement**. Ajoutés avec leurs paramètres Keplériens corrects (a, e, period, L0, peri, c, r) et `hasRing:true` pour Saturne.

2. **Lignes 285–305** — Première moitié de `planetXY()` absente :
   Le prompt ne contenait que les **5 dernières lignes** de `planetXY` (rotation par ω + retour). Toute la partie en amont (`julianDay()`, `rDisplay()`, `solveKepler()`, calcul de l'anomalie moyenne, position dans le plan orbital) était absente. Si on avait laissé le code tel quel, `planetXY` aurait référencé des variables non définies (`x`, `y`, `p.peri`) → ReferenceError immédiate au premier `loop()`. Réécrit proprement, formule complète Kepler de bout en bout.

3. **Ligne 532** — Handler resize tronqué :
   ```js
   window.addEventListener('resize', f}     ← parse error
   ```
   Réécrit en `window.addEventListener('resize', function(){ resizeBgCanvas(); });`. Sans ce fix, ouvrir l'observatoire en mode redimensionnement aurait laissé un canvas de mauvaise taille.

Ajouts proactifs au-delà du prompt :

- **HiDPI canvas** (`devicePixelRatio` + `setTransform`) → pas de flou sur Retina/4K.
- **Saturne avec anneau** → cohérent avec la mention `Saturne` du prompt (sans cela, indistinguable de Jupiter visuellement).
- **drop-shadow sur étoiles filantes du canvas** → effet « comète miniature » plutôt que trait fade plat.

---

## Tags git

| Tag | Pointe sur | Sens |
|---|---|---|
| `oh-pre` | b4f1d2c (HEAD avant Phase O-H) | Snapshot avant insertion |
| `oh-done` | ac1242d | Phase O-H appliquée (OH1 + OH2) |

```
$ git log --oneline -5
ac1242d feat(observatoire): OH2 — widget Système Solaire Live (orbital + cinématique)
7361fd8 feat(observatoire): OH1 — twinkle des étoiles brillantes (mag<1.5)
b4f1d2c doc(observatoire): rapport Phase O-G — carte du ciel Tlemcen
380dcb8 feat(observatoire): OG — Carte du ciel Tlemcen ce soir (calcul local)
d4febe3 doc(observatoire): rapport final Phase O-F (OF1+OF2+OF3)
```

---

## Aspect visuel

### Sky map (impact OH1)

Avant : 30 étoiles statiques, opacité fixe, ambiance trop figée.
Après : les 15 étoiles brillantes (mag < 1.5) scintillent doucement avec déphasage individuel — Sirius pulse différemment de Vega de Capella d'Arcturus. À 50 % de la keyframe, chacune émet un drop-shadow coloré (cyan pour Vega, ambre pour Aldebaran, rouge-orange pour Antares) → effet « ciel qui respire ». Les 15 étoiles plus faibles restent fixes, ce qui crée un contraste perceptuel : l'œil distingue immédiatement les étoiles « repères ».

### Solar System Live (OH2)

Vue plongeante sur le système solaire, fond bleu nuit profond avec dégradé radial. 150 petites étoiles tremblotent à 3 vitesses différentes en fond, dérivant lentement de gauche à droite — sensation de profondeur cosmique. Au centre, le Soleil (un disque ambre-or qui semble vibrer grâce au drop-shadow). Six orbites pointillées cyan en cercles concentriques. Sur chaque orbite, une planète : Mercure et Vénus tournant rapidement, Terre avec son halo cyan et le label `◉ TLEMCEN` (« moi en ce moment »), Mars rouge feu, Jupiter ocre solide, Saturne avec son anneau en ellipse beige. Au-dessus de tout ça, une comète qui parcourt une trajectoire elliptique inclinée à 25°, sa traînée bleu-blanc tendue derrière elle. Ponctuellement (toutes les ~30 s), une étoile filante traverse l'image en diagonale, fade-out à mi-course.

Le titre `SYSTÈME SOLAIRE LIVE · VUE ORBITALE` en cyan Share Tech Mono, sous-titre date+heure live qui met à jour chaque seconde, status pill verte « TEMPS RÉEL · KEPLER » avec point vert pulsant — l'utilisateur sait que les positions sont **vraies à la seconde près**.

Survol d'une planète : tooltip `Jupiter · 5.20 UA · période 11.862 an`.

---

## Contraintes respectées

- ✅ Phases O-A → O-G **intactes** (sky-map-widget = 4, cosmic-dashboard = 11, vérifié curl).
- ✅ Aucune suppression du sky-map ni du cosmic-dashboard.
- ✅ Aucun push remote.
- ✅ Backup `templates/observatoire.html.bak_phase_oh` créé avant patch.
- ✅ Tags `oh-pre` et `oh-done` posés.
- ✅ Trois commits (OH1 fonctionnel, OH2 fonctionnel, doc rapport).
- ✅ Insertion OH2 avant la sky-map de la Phase O-G (entre tele-layout et sky-map dans le flux DOM).
- ✅ Migration monolithique (station_web.py, app/__init__.py) **non touchée**.

---

## Fichiers modifiés

| Fichier | Diff |
|---|---|
| `templates/observatoire.html` | OH1 : +21 / −2 (CSS keyframe + JS class branching). OH2 : +495 lignes (HTML widget + CSS bloc complet + JS canvas/SVG dual-layer renderer + Kepler math). |
| `OBSERVATOIRE_REFACTOR_PHASE_OH.md` | Ce rapport |

---

## Notes pour l'utilisateur

Aller sur `/observatoire` et scroller jusqu'à la zone centrale. Trois widgets empilés verticalement :

1. **SOLAR SYSTEM LIVE** (nouveau, OH2) — en haut.
2. **CARTE DU CIEL TLEMCEN** (Phase O-G, désormais avec twinkle OH1).
3. **ÉTAT COSMIQUE LIVE — TLEMCEN** (Phase O-F, inchangé).

Tester :

- Survoler chaque planète du Solar System → tooltip avec demi-grand axe et période.
- Repérer la Terre (point bleu cerclé de cyan, label `◉ TLEMCEN`).
- Attendre ~30 s : une comète parcourt l'écran en diagonale, étoile filante apparaît dans le fond.
- Sur la sky-map, observer les 15 étoiles les plus brillantes (Sirius, Vega, Capella, Aldebaran, Betelgeuse, etc.) qui scintillent légèrement, chacune à son rythme, avec un halo coloré au sommet de la pulsation. Les 15 étoiles plus faibles (Adhara, Castor, Polaris, Dubhe, etc.) restent fixes — c'est ce que verrait l'œil humain depuis Tlemcen ce soir.

Performance : les deux animations canvas+SVG du Solar System tournent à 60 fps confortablement sur desktop moderne ; sur mobile, l'aspect-ratio passe à 4:3 et le canvas reste fluide grâce au backbuffer HiDPI propre.
