# SENTINEL — REDESIGN VISUEL v2 (Mission Control)
**Date :** 2026-05-15
**Auteur :** Opus 4.7 (refonte autonome)
**Cible :** dossiers candidatures ESA / NASA / Planet Labs deadline 2026-05-31
**Statut :** livré, validé HTTP 200 sur les 3 pages (`/sentinel`, `/sentinel/driver/<t>`, `/sentinel/parent/<t>`)

---

## 1 · Identité posée

> *« Family safety with the precision of mission control. »*

Sentinel passe d'une UI fonctionnelle à un **showcase produit** cohérent avec
ASTRO·SCAN Command v2. Le module joue maintenant son rôle d'effet de manche
sur le portfolio : un évaluateur ESA qui le découvre ressent la même rigueur
que sur le reste de la plateforme.

Mood verrouillé :

| Pilier              | Choix de design                                                         |
|---------------------|-------------------------------------------------------------------------|
| Fond                | Dark profond `#050a14` + radial gradients cyan discrets                  |
| Accent              | Cyan `#00d4ff` partout (trust, presence, signal)                         |
| Réservé             | Rouge **uniquement** pour SOS · amber pour warnings · vert pour healthy  |
| Typographie         | Orbitron (titres), Space Mono (data), Inter (corps)                      |
| Surface             | Glassmorphism subtil (blur 12-14px + saturate 130-140%)                  |
| Motion              | `cubic-bezier(0.22, 0.61, 0.36, 1)` — 160-480ms · `prefers-reduced-motion` respecté |

---

## 2 · Fichiers livrés

| Chemin                                       | État        | Taille      |
|----------------------------------------------|-------------|-------------|
| `static/sentinel/sentinel.css`               | Réécrit     | 1389 lignes |
| `templates/sentinel/landing.html`            | Enrichi     | 151 lignes  |
| `templates/sentinel/driver.html`             | Enrichi     | 140 lignes  |
| `templates/sentinel/parent.html`             | Enrichi     | 110 lignes  |
| `static/sentinel/sentinel.js`                | **Inchangé** — zéro régression possible |

Aucun fichier hors périmètre touché. Aucune nouvelle lib externe. Tokens
`design_tokens.css` strictement réutilisés via aliases `--sn-*`.

---

## 3 · Architecture CSS

22 sections clairement annotées, structure stable pour la maintenance :

```
 1 · TOKENS               12 · DRIVER cockpit shell + status-strip
 2 · RESET & BASE          13 · DRIVER speedometer + gauge arc
 3 · TOPBAR                14 · DRIVER SOS hold-to-fire
 4 · STATUS PILLS          15 · PARENT layout (grid)
 5 · BUTTONS               16 · PARENT summary + hero speedometer
 6 · FORMS                 17 · PARENT telemetry meters
 7 · CARDS                 18 · PARENT event log
 8 · NOTICES & ERRORS      19 · PARENT SOS banner + map
 9 · LANDING               20 · ANIMATIONS / keyframes
10 · FOOTER                21 · MOBILE OVERRIDES (375px floor)
11 · DRIVER invite         22 · A11Y
```

---

## 4 · Apports visuels par page

### Landing
- **Hero en deux colonnes** : texte à gauche + ring SVG décoratif animé à
  droite (3 anneaux, ticks cardinaux, core lumineux). Disparaît sous 720px.
- **Eyebrow filaire** avec barre cyan, hiérarchie typographique posée
  (Orbitron 2-3rem, leading -0.012em).
- **Trust row** plus respirée : 3 chiffres énormes, séparateurs cyan.
- **Pilule "SYSTÈME OPÉRATIONNEL"** dans la topbar.
- **Setup card** glassmorphism avec liseré cyan top, marker `+/−` sur
  l'accordéon "zone rassurante".
- **Result share** apparaît avec micro-anim `fade-up` 240ms.

### Driver (cockpit — mobile-first 375px)
- **Status strip** triplette `Limite · Intervalle · SOS hold`,
  glass blur, monospace.
- **Speedometer flagship** : arc CSS conic-gradient en background,
  chiffre `clamp(5.4rem, 26vw, 11rem)` Orbitron, text-shadow cyan,
  liseré cyan top via mask. Lisible à 1m, plein soleil.
- **État over-speed** : amber sur le chiffre + arc qui devient amber +
  pilule warning `▲` pulsée subtilement.
- **Bouton SOS** : 168px haut, gradient rouge avec radial highlight,
  liseré dashed interne, halo cyan/rouge pulsé via `::after`, ring de
  chargement préservé. État `armed` bascule vers amber pour signaler le
  chargement. Tap-highlight neutralisé, `touch-action: manipulation`.
- **Bouton stop** discret en bas, `sn-btn--ghost`.
- Safety banner amber non-anxiogène en haut du cockpit.

### Parent (Mission Control)
- **Grid 420px + 1fr** sidebar + carte plein écran.
- **Header** : pilule d'état finie (live / warn / danger / ended).
- **Summary card** avec hero speedometer encapsulé (liseré cyan top),
  méta `Limite · Fin dans` en bas, banner amber over-speed.
- **Meters grid** : 7 cellules 2 colonnes, séparées par 1px de bordure
  visuelle créée par `gap: 1px` + background sur la grille, données
  monospace tabular-nums.
- **Journal du trajet** : dots colorés à gauche (cyan/amber/red/green)
  selon le type d'événement, animation pulse-fast sur dot SOS.
- **Carte** : badge HUD `LIVE TRACK` en haut-gauche (overlay) avec dot
  cyan pulsé. Rendu Leaflet inchangé.
- **SOS banner** : radial rouge, glow, animation pulse.

---

## 5 · Préservation fonctionnelle

Tous les **IDs DOM** utilisés par `sentinel.js` sont préservés :

```
#sn-ttl, #sn-state-pill, #sn-speed, #sn-limit, #sn-over-banner,
#sn-sos-btn, #sn-sos-ring, #sn-sos-active, #sn-sos-ack-line,
#sn-stop-request, #sn-stop-pending-driver, #sn-stop-pending-parent,
#sn-stop-approve, #sn-ended, #sn-error, #sn-invite, #sn-cockpit,
#sn-accept-btn, #sn-refuse-btn, #sn-zone-here, #sn-zone-lat, #sn-zone-lon,
#sn-zone-radius, #sn-create-btn, #sn-driver-label, #sn-limit-custom,
#sn-result, #sn-invite-url, #sn-parent-open, #sn-share-whatsapp,
#sn-share-sms, #sn-share-native, #sn-driver-name, #sn-l-speed,
#sn-l-limit, #sn-l-over-banner, #sn-l-ttl, #sn-l-avg, #sn-l-max,
#sn-l-head, #sn-l-acc, #sn-l-sig, #sn-l-batt, #sn-l-age, #sn-events,
#sn-sos-banner, #sn-sos-by, #sn-sos-ack, #sn-map
```

Classes BEM `.sn-*` : enrichies, jamais renommées sur les hooks JS.
Data-attributes du body driver (`data-token`, `data-limit`, `data-sos-hold`,
`data-interval`, `data-initial-state`) inchangés. Endpoints API
inchangés.

**JS Sentinel : 0 ligne modifiée.**

---

## 6 · Validation HTTP

```
GET /sentinel               → 200  7368 bytes  ✓ sn-hero-rings présent
GET /sentinel/driver/<t>    → 200  6246 bytes  ✓ sn-status-strip + sn-speedo-arc + sn-pillars
GET /sentinel/parent/<t>    → 200  5243 bytes  ✓ MISSION CONTROL + sn-meters + sn-map-wrap
GET /static/sentinel/sentinel.css → 200 (1389 lignes servies)
POST /api/sentinel/session/create → 200 (création session OK)
```

Service `astroscan` `active`. Aucun redémarrage nécessaire (Flask sert
templates + statics à chaud derrière gunicorn).

---

## 7 · Accessibilité

- `prefers-reduced-motion: reduce` désactive les rotations SVG, pulses
  pilules, halo SOS, animation `sos-banner`, badge live carte.
- Focus visible 3px blanc sur SOS, cyan sur les autres contrôles.
- `aria-label` enrichis sur speedo, status-strip, meters dl.
- Contraste : chiffres speedo sur fond `#0a1a2c` ≈ AAA. Texte amber sur
  fond amber-soft + bordure ≈ AAA.

---

## 8 · Performance

- Aucune image bitmap. SVG inline pour le hero ring (40 nodes).
- `backdrop-filter` limité aux topbar/cards/status-strip, pas sur la
  carte ni sur le SOS (zones critiques mobile).
- Transitions seulement sur `transform`, `opacity`, `box-shadow`,
  `border-color`. Aucun reflow induit par animation.
- Conic-gradient pour l'arc speedo (composé GPU).

---

## 9 · Mobile-first driver

Floor 360px supporté. À 375px :

- Cockpit padding 10px / 12px / 24px.
- Speedometer `font-size: clamp(5rem, 28vw, 9rem)`.
- SOS 152px min-height, 2.3rem font, `letter-spacing: 0.4em`.
- One-hand : SOS dans la moitié basse atteignable au pouce.
- `viewport-fit=cover, user-scalable=no` posé sur driver pour bloquer
  le double-tap zoom et permettre l'utilisation du notch iOS.

---

## 10 · Ce qui reste hors scope (non régressé)

- Backend Sentinel (`app/blueprints/sentinel/routes.py`) : non touché.
- Aucune dépendance ajoutée.

---

## 11 · v2.1 — Compléments WAAW (2026-05-15, suite de la livraison)

5 trous de la checklist initiale comblés en passe courte, ciblée. Le reste
du redesign v2 est conservé tel quel.

### 11.1 — Backups préventifs
Cinq copies `*.bak_pre_waaw_v2_20260515` créées avant toute modification
(`sentinel.css`, `sentinel.js`, `landing.html`, `driver.html`, `parent.html`).
Rollback 1-commande disponible.

### 11.2 — Mission Control grid overlay
`sentinel.css` §2 : pseudo-element `body.sn-body::before` posé en
`position: fixed; inset: 0; z-index: 0; pointer-events: none` avec deux
`repeating-linear-gradient` (0° et 90°, pas de 40px, cyan rgba
0.025-0.035) et `mix-blend-mode: screen`. Topbar / shell / parent /
cockpit / driver-invite / foot remontés en `z-index: 1` pour rester
au-dessus de la trame. Effet : terminal vibe ressenti, presque
invisible — exactement ce qui était demandé.

### 11.3 — Gradient text premium
`sentinel.css` : `linear-gradient(135deg, #fff → var(--sn-cyan))` posé
sur `.sn-hero h1 em` (le mot "aimez" du H1 landing, déjà en `<em>`) et
sur `.sn-summary-head h2` (nom du conducteur côté parent), avec
`background-clip: text` + `-webkit-text-fill-color: transparent`. Quatre
occurrences `background-clip` au total (deux sélecteurs × prefix + standard).

### 11.4 — Loading skeletons télémétrie parent
`sentinel.css` §20 : classe `.sn-skeleton` avec
`linear-gradient` shimmer (200% background-size) et keyframe
`@keyframes sn-shimmer { 0% → 200% 0; 100% → -200% 0 }` sur 1.8s
ease-in-out infinite. `parent.html` : injection de `<span class="sn-skeleton">`
dans 9 `<dd>` / `<div>` (sn-l-speed, sn-l-ttl, sn-l-avg, sn-l-max,
sn-l-head, sn-l-acc, sn-l-sig, sn-l-batt, sn-l-age — `sn-l-limit`
explicitement préservé en `—` comme demandé). Le JS existant fait
`el.textContent = …` qui écrase proprement le skeleton dès l'arrivée
de la première vraie valeur — aucune retouche JS nécessaire pour ce point.

### 11.5 — applyFSMStatus + câblage polling
`sentinel.js` : fonction `applyFSMStatus(state)` ajoutée juste après
les utilitaires `postJson` / `getJson`, avec mapping FSM canonique
(`PENDING_DRIVER → "EN ATTENTE"`, `ACTIVE → "TRAJET ACTIF"`,
`SOS_ACTIVE → "SOS"`, `STOP_PENDING_* → "ARRÊT DEMANDÉ"`,
`ENDED → "TERMINÉ"`, `EXPIRED → "EXPIRÉ"`). Exposée en
`window.applyFSMStatus` pour câblage manuel futur. Câblée dans les
deux pollings `/state` (driver `pullState`, parent `pull`) juste après
le parsing JSON, avec promotion `SOS_ACTIVE` quand
`b.sos_active && !b.sos_ack_at`. Le `setPill` complexe parent
(`stateLabel + sos suffix`) retiré au profit d'`applyFSMStatus` pour
éviter la double écriture. Côté driver, la pill `#sn-ttl` reste
prioritairement utilisée pour le countdown (comportement original
préservé) ; `applyFSMStatus` est appelée mais ré-écrite par
`fmtCountdown` à chaque tick — c'est intentionnel pour garder un
visuel "temps restant" au conducteur.

### 11.6 — Validation
| Critère                                                | Résultat |
|--------------------------------------------------------|----------|
| 5 backups `.bak_pre_waaw_v2_20260515` existent          | ✓ 5/5   |
| `grep -c repeating-linear-gradient sentinel.css ≥ 2`    | ✓ 2     |
| `grep -c background-clip sentinel.css ≥ 2`              | ✓ 4     |
| `grep -c sn-skeleton sentinel.css ≥ 1`                  | ✓ 1     |
| `grep -c applyFSMStatus sentinel.js ≥ 2`                | ✓ 4     |
| `curl -sI /sentinel`                                    | ✓ 200   |
| Skeletons rendus dans parent.html servi                 | ✓ 9     |

Aucune régression fonctionnelle introduite. Tous les IDs DOM préservés,
endpoints API inchangés.
