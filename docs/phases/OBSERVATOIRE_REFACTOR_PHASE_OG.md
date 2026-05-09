# Phase O-G — Carte du ciel Tlemcen ce soir

**Branche** : `ui/portail-refactor-phase-a`
**Date** : 2026-05-07
**Tags** : `og-pre` (avant) → `og-done` (après)
**Backup** : `templates/observatoire.html.bak_phase_og`
**Commit** : `380dcb8`

---

## Mission

Combler la zone vide entre la section télescope (`.tele-layout`) et le widget Cosmic Live Dashboard de la Phase O-F par une **carte du ciel scientifique** de Tlemcen ce soir, calculée 100 % côté client. Étoiles brillantes, Lune, planètes visibles, statut Soleil. Précision visuelle ±1–2°. Refresh 60 s.

> « Une vraie carte du ciel calculée depuis Tlemcen — c'est ça un VRAI observatoire. »

---

## Spécification scientifique

### Projection

**Stéréographique zénithale** : zénith au centre du disque, horizon sur le cercle, direction nord en haut.

```
r = R · tan((90° − Alt) / 2)        R = 280 (rayon du disque)
x = CX + r · sin(Az)                Az mesuré depuis N dans le sens horaire
y = CY − r · cos(Az)                CX = CY = 300 (centre 600 × 600)
```

Seuls les objets avec `Alt > 0` (au-dessus de l'horizon Tlemcen) sont rendus.

### Pipeline de coordonnées

1. **Julian Day** : `JD = Date.now() / 86400000 + 2440587.5`
2. **GMST** (Greenwich Mean Sidereal Time, deg) :
   `GMST = 280.46061837 + 360.98564736629·(JD − 2451545) + 0.000387933·T²` avec `T = (JD − J2000) / 36525`
3. **LST Tlemcen** : `LST = (GMST + LON_DEG) mod 360`, longitude `−1.32°`
4. **Équatorial → horizontal** :
   ```
   HA = LST − RA
   sin(Alt) = sin(Dec)·sin(Lat) + cos(Dec)·cos(Lat)·cos(HA)
   sin(Az) = −cos(Dec)·sin(HA)
   cos(Az) = sin(Dec) − sin(Alt)·sin(Lat)
   Az = atan2(sinAz, cosAz)
   ```

### Étoiles — catalogue J2000 hardcodé

30 étoiles les plus brillantes (Sirius mag −1.46 → Polaris mag 1.97), positions J2000 (RA en heures, Dec en degrés), couleur réaliste par classe spectrale (bleu B/A, blanc F/G, jaune G2, orange K, rouge M).

Taille SVG : `size = max(1.2, 4.5 − mag · 1.1)` — étoiles brillantes plus grosses.
Opacité : pleine la nuit, 0.15 le jour. Étoiles `mag < 0.5` étiquetées en clair.

### Planètes — Keplerian simplifié J2000 (Meeus ch. 32)

Mercure, Vénus, Mars, Jupiter, Saturne. Éléments orbitaux : `a` (UA), `e`, `i`, `L0`, `peri`, `asc`, `period` (années). Pipeline :

1. **Anomalie moyenne** : `M = (L0 − peri) + (360°/period·365.25)·d`, `d = JD − J2000`.
2. **Équation de Kepler** : Newton sur `E − e·sin E = M`, 12 itérations.
3. **Coords héliocentriques** dans le plan orbital : `(x, y) = (a(cosE − e), a√(1−e²)·sinE)`.
4. **Rotations** ω (`peri − asc`), `i` (inclinaison), Ω (asc) → coords héliocentriques 3D.
5. **Géocentrique** : ph − eh (Terre traitée comme planète avec `a=1, L0=100.466, peri=102.937, period=1`). **Note** : le prompt original oubliait `eh.z` dans `dz` ; j'ai corrigé en `dz = ph.z − eh.z`.
6. **Écliptique → équatoriale** par rotation d'obliquité `ε = 23.439°`.
7. **(RA, Dec) → (Alt, Az)** comme pour les étoiles.

Précision attendue : ±1–2° sur les planètes (suffit largement pour une carte visuelle).

### Lune — algorithme Meeus simplifié

```
d = JD − J2000
L = (218.316 + 13.176396·d) mod 360       longitude moyenne
M = (134.963 + 13.064993·d) mod 360       anomalie moyenne
F = (93.272  + 13.229350·d) mod 360       argument de latitude
λ = L + 6.289·sin(M)                       longitude écliptique
β = 5.128·sin(F)                            latitude écliptique
RA  = atan2(sinλ·cosε − tanβ·sinε, cosλ) / 15
Dec = asin(sinβ·cosε + cosβ·sinε·sinλ)
```

Précision ~±2°, parfait pour positionner la Lune sur la carte. Phase calculée localement (référence nouvelle lune 2000-01-06 18:14 UTC, période synodique 29.53058867 j) → emoji 🌑→🌘 affiché à la position calculée.

### Soleil — détection jour/nuit/crépuscules

```
n = JD − J2000
L  = (280.460 + 0.9856474·n) mod 360
g  = (357.528 + 0.9856003·n) mod 360
λ  = L + 1.915·sin(g) + 0.020·sin(2g)
ε  = 23.439 − 0.0000004·n
```

L'altitude solaire pilote le mode visuel et le label de statut :

| Altitude solaire | Statut | Couleur pill | Effet sur carte |
|---|---|---|---|
| `> 0°` | ☀ JOUR · ciel non visible | `#ffcc66` ambre | étoiles à 0.15, planètes à 0.4 |
| `> -6°` | ◐ CRÉPUSCULE CIVIL | `#ff9966` orange | nuit complète |
| `> -12°` | ◑ CRÉPUSCULE NAUTIQUE | `#ff7799` rose | nuit complète |
| `> -18°` | ◒ CRÉPUSCULE ASTRO | `#aa77ff` violet | nuit complète |
| `≤ -18°` | ● NUIT ASTRONOMIQUE | `#00ff9c` vert | nuit complète |

---

## Insertion confirmée

```
$ grep -n "PASS UI O-G\|PASS UI O-F FIX 3.*Widget COSMIC" templates/observatoire.html
467:/* PASS UI O-F FIX 3 (2026-05-07) — Widget COSMIC LIVE DASHBOARD.
574:/* PASS UI O-G (2026-05-07) — Sky Map widget.       ← CSS bloc O-G
709:  <!-- PASS UI O-G (2026-05-07) — CARTE DU CIEL TLEMCEN CE SOIR.
736:  <!-- PASS UI O-F FIX 3 (2026-05-07) — Widget COSMIC LIVE DASHBOARD.
```

Le widget HTML est **avant** la marque O-F dans le DOM (ligne 709 < 736), donc visuellement au-dessus du Cosmic Live Dashboard, comme demandé. Le bloc CSS O-G est inséré dans le `<style>` avant le bloc CSS O-F (ligne 574 < 467 — non, en fait 574 > 467 — mais le marker O-F à 467 est le **début** du bloc CSS O-F qui se poursuit jusqu'à la fin de ses règles ; le bloc O-G est inséré **avant** le `<style>`-end après que tous les blocs O-F sont écrits, ce qui place les règles O-G dans une cascade postérieure — ordre acceptable car les sélecteurs des deux blocs sont disjoints).

---

## Validation curl

```
$ systemctl is-active astroscan
active

$ curl -sI http://127.0.0.1:5003/observatoire | head -1
HTTP/1.1 200 OK

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "sky-map-widget"
4   # 1× HTML <div class+id> + 1× CSS .sky-map-widget + 1× CSS .sky-map-widget::before + 1× id sky-map-widget interne — OK

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "var STARS = \["
1   # catalogue déclaré une fois

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "var PLANETS = \["
1   # catalogue planètes déclaré une fois

$ curl -s http://127.0.0.1:5003/observatoire | grep -cE "'Sirius'|'Vega'|'Polaris'"
3   # 3 étoiles emblématiques présentes

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "cosmic-dashboard"
11  # INCHANGÉ vs Phase O-F ✓ (pas de régression)
```

> Note : le prompt attendait `≥ 5` pour `sky-map-widget`. Réel = 4. La différence vient de ce que la déclaration HTML cumule `class="sky-map-widget" id="sky-map-widget"` sur **une même ligne** (`grep -c` compte les lignes). Toutes les autres références attendues sont bien là.

---

## Validation astronomique

Test exécuté en Node avec les mêmes formules que le widget, datetime `2026-05-07 22:30 Tlemcen` :

```
JD = 2461168.3958
LST Tlemcen = 186.92°

Polaris : alt = 34.24°, az = 359.44°
  → attendu ≈ 34.87° (latitude Tlemcen) et 0° (plein nord)
  → écart < 0.7° en altitude, < 0.6° en azimut. ✓

Vega : alt = 19.40°, az = 60.74° (ENE)
  → en mai à 22h30 Tlemcen, Vega vient de se lever au NE et monte. ✓

Sirius : alt = −6.00°, az = 256.58° (WSW)
  → étoile d'hiver, en mai à 22h30 elle vient juste de passer sous
    l'horizon ouest. Sirius ne sera donc pas affichée à cette heure
    (alt < 0 ⇒ filtre `project()` retourne null). ✓
```

Les trois cas tests confirment :
1. La conversion (RA, Dec) → (Alt, Az) est mathématiquement correcte (Polaris à hauteur = latitude, plein nord, c'est le test canonique).
2. La saisonnalité est respectée (Sirius hiver/Vega printemps-été).
3. Le filtre horizon fonctionne (objets sous l'horizon non rendus).

---

## Bugs du prompt original corrigés

Le prompt fourni contenait trois défauts critiques que j'ai corrigés en cours d'implémentation :

1. **CSS ligne 220 tronquée** :
   ```css
   .sky-map-status {
     ...
     border: 1px solid rgba(0, 255, 15; }     ← coupé en plein milieu
   .sky-bg-disk { fill: rgba(0,4,12,0.95); }
   ```
   Plus une dizaine de classes CSS référencées dans HTML/JS (`.sky-horizon`, `.sky-cardinal`, `.sky-star`, `.sky-planet`, `.sky-shooting`, `.sky-map-canvas-wrap`, `.sky-map-svg`, `.sky-map-legend`, `.legend-item`, `.lg-dot`, `.lg-star`, `.lg-planet`, `.lg-moon`, `.sky-map-footer`) **non définies**. Réécrit un bloc CSS complet, cohérent avec la palette cyan du portail/observatoire.

2. **JS ligne 586 typo** :
   ```js
   var lteElementNS(NS, 'line');     ← non parsable
   line.setAttribute(...)
   ```
   Corrigé en `var line = document.createElementNS(NS, 'line');`. Sans ce fix, l'animation d'étoile filante levait une SyntaxError et bloquait tout le widget.

3. **`planetRaDec` calcul géocentrique erroné** :
   Le prompt avait `var dx = ph.x - eh.x, dy = ph.y - eh.y, dz = ph.z;` — la composante z de la Terre était oubliée. Corrigé en `dz = ph.z - eh.z` pour cohérence (Terre est traitée comme planète avec `i = 0`, donc `eh.z = 0` et le résultat numérique est identique en pratique, mais la formule devient correcte si on étend à des plans non-coïncidents).

J'ai également ajouté les **cercles d'altitude 30° et 60°** que le commentaire du prompt mentionnait (« Altitude rings (30°, 60° ») mais que la suite du code oubliait de tracer.

---

## Aspect visuel

- **Disque cosmos** : gradient radial bleu nuit profond, point lumineux subtil au centre.
- **Cercles d'altitude** 30° et 60° en pointillés cyan très discrets (0.13 alpha, dasharray 2 4).
- **Horizon** cyan plus marqué (0.5 alpha, 1.2 px).
- **Cardinaux N E S O** Orbitron 13 px, cyan, à l'extérieur du cercle.
- **Étoiles** : disques colorés selon spectre, tooltip `Sirius (mag -1.46 · alt 33.2°)` au survol. Les étoiles `mag < 0.5` ont un label permanent (Sirius, Canopus, Arcturus, Vega, Capella, Rigel, Procyon, Achernar, Betelgeuse) → repères immédiats.
- **Lune** : halo crème + emoji de phase calculé. Tooltip `Lune · alt 22.4° · az 195°`.
- **Planètes** : disque coloré (gris Mercure, crème Vénus, rouge Mars, ocre Jupiter/Saturne) + label mono à côté. Tooltip alt/az.
- **Étoiles filantes** : 35 % de chance par refresh (60 s) en mode nuit. Trait blanc 800 ms qui s'étire et fade out.
- **Légende** : 3 pastilles en bas-droite (étoile, planète, lune).
- **Statut** : pill colorée selon altitude solaire (vert nuit, violet crépuscule astro, ambre jour…).
- **Header** : titre Share Tech Mono cyan, sous-titre date+heure FR `JEU. 07 MAI · 22H30 · TLEMCEN`.
- **Footer** : « Projection stéréographique · 30 étoiles + Lune + planètes visibles · Calcul local · Refresh 60s ».

Responsive : sous 768 px, header en colonne, légende inline en bas, taille adaptée.

---

## Tags git

| Tag | Pointe sur | Sens |
|---|---|---|
| `og-pre` | d4febe3 (HEAD avant Phase O-G) | Snapshot avant insertion widget |
| `og-done` | 380dcb8 | Phase O-G appliquée |

```
$ git log --oneline -4
380dcb8 feat(observatoire): OG — Carte du ciel Tlemcen ce soir (calcul local)
d4febe3 doc(observatoire): rapport final Phase O-F (OF1+OF2+OF3)
42f238b feat(observatoire): OF3 — widget Cosmic Live Dashboard (embryon Chemin B)
dea2211 fix(observatoire): OF2 — bouton ◄ PORTAIL casse iframe via window.top
```

---

## Contraintes respectées

- ✅ Phases O-A → O-F intouchées. Widget Cosmic Live Dashboard préservé (validation curl : 11 occurrences inchangées).
- ✅ Aucun push remote.
- ✅ Backup `templates/observatoire.html.bak_phase_og` créé avant patch.
- ✅ Insertion **avant** la div `.cosmic-dashboard` (Phase O-F marker).
- ✅ Tags `og-pre` et `og-done` posés.
- ✅ Calcul 100 % client-side, aucune API externe — autonomie maximale.

---

## Fichiers modifiés

| Fichier | Diff |
|---|---|
| `templates/observatoire.html` | +528 lignes (bloc CSS sky-map ~140 l + HTML widget ~22 l + JS calcul/rendu ~365 l) |
| `OBSERVATOIRE_REFACTOR_PHASE_OG.md` | Ce rapport |

---

## Notes pour l'utilisateur

Aller sur `/observatoire` et scroller jusqu'à la section centrale : la carte stéréographique apparaît au-dessus du Cosmic Live Dashboard. Selon l'heure de visite :

- **Soir/nuit Tlemcen** (heure locale −18° solaire ≈ 21h30 → 5h en mai) : carte pleine luminosité, status pill verte « ● NUIT ASTRONOMIQUE », étoiles filantes occasionnelles, planètes brillantes positionnées, Lune au phase actuelle.
- **Crépuscule** : pill violette/rose/orange selon profondeur, étoiles dimmées.
- **Jour** : pill ambre « ☀ JOUR · ciel non visible », étoiles à 15 % d'opacité, mais la carte reste informative pour vérifier où **seraient** les objets dans le ciel masqué.

Survoler une étoile/planète/Lune affiche son altitude et azimut. Les 9 étoiles les plus brillantes (mag < 0.5) sont labellisées en permanence pour orientation rapide.

Refresh automatique toutes les 60 secondes — la rotation diurne (≈ 0.25°/minute) est visible pour les objets bas sur l'horizon.
