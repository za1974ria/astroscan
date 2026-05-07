# Phase O-F — Navigation top-level + Widget Cosmic Live Dashboard

**Branche** : `ui/portail-refactor-phase-a`
**Date** : 2026-05-07
**Tags** : `of-pre-fix1` → `of-fix1-done` → `of-pre-fix2` → `of-fix2-done` → `of-pre-fix3` → `of-fix3-done`
**Backups** : `templates/portail.html.bak_phase_of`, `templates/observatoire.html.bak_phase_of`

---

## Mission

Trois corrections enchaînées identifiées par l'utilisateur après les phases O-A → O-E :

1. **OF1** — clic OBSERVATOIRE depuis le portail doit faire une navigation **top-level** (pas un load dans l'iframe `frame-observatoire`).
2. **OF2** — bouton « ◄ PORTAIL » dans observatoire doit casser l'iframe (utiliser `window.top.location.href`) pour éviter l'effet « portail dans portail ».
3. **OF3** — combler le vide central d'observatoire avec un widget « Cosmic Live Dashboard » : 4 cards de données live (ISS, lune, météo spatiale, ciel Tlemcen).

---

## FIX OF1 — Navigation top-level pour OBSERVATOIRE

### Cible
`templates/portail.html`

### Avant

```html
<!-- ligne 1375 -->
<div class="nav-item nav-sub" id="nav-observatoire" onclick="navigate('observatoire')">

<!-- ligne 1696 -->
<div class="splash-btn" onclick="navigate('observatoire')">
```

### Après

```html
<!-- ligne 1375 -->
<div class="nav-item nav-sub" id="nav-observatoire" onclick="window.location.href='/observatoire'">

<!-- ligne 1696 -->
<div class="splash-btn" onclick="window.location.href='/observatoire'">
```

### Pourquoi

`navigate()` est conservé intact (toujours utilisé par les autres modules : sondes, lab, dashboards, etc.). On ne touche que les deux entrées « observatoire » qui doivent ouvrir la page en plein écran, hors du chrome portail. C'est la voie de moindre régression : un changement local et explicite, plutôt qu'une refonte de `navigate()` qui aurait risqué de casser les 30+ autres modules.

### Validation

```
$ curl -s http://127.0.0.1:5003/portail | grep -c "navigate('observatoire')"
0   # attendu 0 ✓

$ curl -s http://127.0.0.1:5003/portail | grep -c "location.href='/observatoire'"
2   # attendu ≥ 2 ✓
```

### Comportement visuel

- Avant : clic OBSERVATOIRE depuis sidebar → animation de panneau, iframe `frame-observatoire` chargeait `/observatoire?embed=1`, le chrome portail (sidebar, topbar) restait visible autour.
- Après : clic OBSERVATOIRE → vraie navigation HTTP, l'URL devient `/observatoire`, le portail laisse complètement la place à l'observatoire plein écran.

---

## FIX OF2 — Casser l'iframe via window.top dans `disconnectObservatory()`

### Cible
`templates/observatoire.html`, ligne 965.

### Avant

```js
function disconnectObservatory(){
  if(window.location.pathname!=='/portail') window.location.href='/portail';
  else window.location.href='/';
}
```

Problème : quand observatoire est embarqué dans l'iframe `frame-observatoire` du portail, `window.location` réfère à l'**iframe**, pas à la fenêtre parente. Le clic sur « ◄ PORTAIL » chargeait donc `/portail` à l'intérieur de l'iframe. Résultat : un portail rendu dans le portail, avec deux sidebars/topbars empilés (effet « sidebar fantôme »).

### Après

```js
function disconnectObservatory(){
  /* PASS UI O-F FIX 2 (2026-05-07) — utiliser window.top pour sortir
     de l'iframe portail si on est embarqué. Sinon naviguer normalement
     en top-level. Évite l'effet "portail dans portail" (sidebar fantôme). */
  try {
    if (window.top !== window.self) {
      window.top.location.href = '/portail';
      return;
    }
  } catch(e) {
    /* Cross-origin — pas dans notre iframe, on tombe en standalone. */
  }
  if (window.location.pathname !== '/portail') {
    window.location.href = '/portail';
  } else {
    window.location.href = '/';
  }
}
```

### Pourquoi

- `window.top !== window.self` détecte l'embarquement.
- `window.top.location.href` cible le sommet de la pile de frames → la navigation casse l'iframe.
- `try/catch` couvre l'éventualité d'un embarquement cross-origin (chez nous c'est same-origin, mais robustesse gratuite).
- Le code standalone est inchangé : si la page est ouverte directement (`/observatoire`), comportement identique à avant.

### Validation

```
$ curl -s http://127.0.0.1:5003/observatoire | grep -c "window.top.location.href"
1   # attendu 1 ✓
```

### Comportement visuel

- Avant : depuis observatoire embarqué, clic ◄ PORTAIL → portail dans portail, deux sidebars.
- Après : clic ◄ PORTAIL → navigation top-level vers `/portail` propre, capture 3 (état initial portail).
- Combiné à OF1, le scénario d'embarquement ne devrait plus se produire en pratique. OF2 est néanmoins une **défense en profondeur** : si un autre flow (lien direct vers `/observatoire?embed=1`, ouverture par un widget tiers, regression future) embarque la page, le bouton retour reste fonctionnel.

---

## FIX OF3 — Widget Cosmic Live Dashboard

### Cible
`templates/observatoire.html` — insertion dans la zone vide entre la section télescope (.tele-layout) et la liste des dernières observations (ligne 605 d'origine).

### HTML inséré

Après `</div></div>` de la `tele-layout` (l 604), avant la section « LATEST OBSERVATIONS » :

```html
<div class="cosmic-dashboard" id="cosmic-dashboard">
  <div class="cosmic-dashboard-header">
    <span class="cd-title">ÉTAT COSMIQUE LIVE — TLEMCEN 34.87°N · 1.32°E</span>
    <span class="cd-pulse"></span>
  </div>
  <div class="cosmic-dashboard-grid">
    <div class="cd-card" id="cd-iss">…POSITION ISS…</div>
    <div class="cd-card" id="cd-moon">…PHASE LUNAIRE…</div>
    <div class="cd-card" id="cd-space-weather">…MÉTÉO SPATIALE…</div>
    <div class="cd-card" id="cd-tlemcen">…CIEL TLEMCEN…</div>
  </div>
  <div class="cosmic-dashboard-footer">
    Données temps réel · Refresh 30s · Embryon de recherche en observabilité hyperlocale
  </div>
</div>
```

i18n complet (FR/EN) via `{% if lang == 'en' %}…{% else %}…{% endif %}`.

### CSS ajouté

100 lignes de CSS injectées juste avant `</style>` (ligne 466 d'origine). Système :

- Container avec `backdrop-filter: blur(6px)`, gradient cosmos (`#000c18` → `#001220`), bord cyan `rgba(0,212,255,0.25)`.
- Pseudo-élément `::before` qui dessine la même ligne lumineuse cyan que le `.topbar` (cohérence visuelle).
- Header avec `cd-title` Share Tech Mono + un point pulsant vert (`@keyframes cdPulse 2s`).
- Grid `auto-fit minmax(180px, 1fr)` → 4 colonnes sur desktop, 2 sur tablette, 1 sur très petit écran.
- Cards avec hover `translateY(-2px)` + glow box-shadow cyan.
- Typographie : Orbitron pour les valeurs (18 px, text-shadow), Share Tech Mono pour labels/meta.
- Media query `<768 px` : padding réduit, grid forcé à 2 colonnes, valeurs 14 px.

### JavaScript ajouté

Bloc `<script>` IIFE inséré entre `aegis_chat_widget.js` et `starfield.js` (chargement après UI initiale, avant fond animé).

Quatre fonctions :

- **`refreshISS()`** → `GET /api/iss` (endpoint existant, tolère lat/latitude + lon/longitude + alt/altitude).
- **`refreshMoon()`** → calcul **local** de la phase lunaire. Référence : nouvelle lune 2000-01-06 18:14 UTC, période synodique 29.53058867 j. Illumination = `(1 - cos(2π · phase/synodique)) / 2`. Huit labels avec emojis 🌑🌒🌓🌔🌕🌖🌗🌘 selon `phase/synodic` (8 octants). Précision ±1 j, suffisante pour un dashboard live.
- **`refreshSpaceWeather()`** → `GET /api/meteo-spatiale` (le prompt référençait `/api/alerts/all` qui n'expose **pas** `kp_index` ; vérifié par inspection des clés JSON, corrigé). Retourne `kp_index` (NOAA SWPC). Statut : Calme < 4, Actif < 5, Tempête mineure < 7, Tempête majeure ≥ 7.
- **`refreshTlemcenSky()`** → fetch direct **Open-Meteo** : `https://api.open-meteo.com/v1/forecast?latitude=34.87&longitude=-1.32&current=temperature_2m,cloud_cover,weather_code`. États : Ciel dégagé (<25 %), Partiellement couvert (<60 %), Nuageux (<85 %), Couvert (≥ 85 %).

`refreshAll()` est appelé sur `DOMContentLoaded` puis toutes les 30 000 ms via `setInterval`. Tous les `fetch().catch()` sont silencieux : panne réseau ou API laissée à l'état précédent (pas d'écran d'erreur intrusif sur un dashboard contemplatif).

### Note sur le prompt original

Le prompt fourni contenait une **erreur de paste** dans `refreshMoon()` aux lignes 291-292 :
```
var lp = 2551443; /* période synodique en + '% éclairée';
}
```
Code tronqué et inutilisable. J'ai écrit une implémentation propre basée sur la formule de phase lunaire (référence nouvelle lune 2000 + cosinus pour l'illumination).

### Validation

```
$ systemctl is-active astroscan
active

$ curl -sI http://127.0.0.1:5003/observatoire | head -1
HTTP/1.1 200 OK

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "cosmic-dashboard"
11   # attendu ≥ 4 ✓ (1 conteneur + IDs + classes + footer + bloc CSS)

$ curl -s http://127.0.0.1:5003/observatoire | grep -c 'class="cd-card"'
4    # 4 cards ✓

$ curl -s http://127.0.0.1:5003/observatoire | grep -c "Cosmic Live Dashboard refresh"
1    # bloc JS présent ✓

$ curl -s http://127.0.0.1:5003/api/iss | head -c 100
{"accuracy":{...,"alt":417.8,"lat":...,"lon":...    # endpoint OK ✓

$ curl -s http://127.0.0.1:5003/api/meteo-spatiale
{"kp_index":3.33,"source":"NOAA Space Weather Prediction Center",...}    # endpoint OK ✓
```

### Comportement visuel

- Avant : entre la zone télescope et la liste « DERNIÈRES OBSERVATIONS », un grand vide vertical.
- Après : un panneau cosmos sombre avec gradient subtil, un point vert pulsant à côté du titre « ÉTAT COSMIQUE LIVE — TLEMCEN », 4 cards en grille avec valeurs cyan glow Orbitron, footer mention « Embryon de recherche en observabilité hyperlocale ». Données qui se mettent à jour toutes les 30 secondes.

---

## Validation finale combinée

```
$ systemctl is-active astroscan
active

$ curl -sI http://127.0.0.1:5003/portail | head -1
HTTP/1.1 200 OK

$ curl -sI http://127.0.0.1:5003/observatoire | head -1
HTTP/1.1 200 OK

# OF1
$ curl -s http://127.0.0.1:5003/portail | grep -c "navigate('observatoire')"
0
$ curl -s http://127.0.0.1:5003/portail | grep -c "location.href='/observatoire'"
2

# OF2
$ curl -s http://127.0.0.1:5003/observatoire | grep -c "window.top.location"
1

# OF3
$ curl -s http://127.0.0.1:5003/observatoire | grep -c "cosmic-dashboard"
11
```

---

## Tags git

| Tag | Pointe sur | Sens |
|---|---|---|
| `of-pre-fix1` | a75ad40 (HEAD avant Phase O-F) | Snapshot avant tout changement OF |
| `of-fix1-done` | 1ed6c74 | OF1 appliqué (top-level nav portail) |
| `of-pre-fix2` | 1ed6c74 | Snapshot avant OF2 |
| `of-fix2-done` | dea2211 | OF2 appliqué (window.top) |
| `of-pre-fix3` | dea2211 | Snapshot avant OF3 |
| `of-fix3-done` | 42f238b | OF3 appliqué (widget Cosmic Live) |

```
$ git log --oneline -4
42f238b feat(observatoire): OF3 — widget Cosmic Live Dashboard (embryon Chemin B)
dea2211 fix(observatoire): OF2 — bouton ◄ PORTAIL casse iframe via window.top
1ed6c74 fix(portail): OF1 — clic OBSERVATOIRE → top-level navigation
af67de2 fix(portail): Phase O-E — investigation + fix [hypothesis A: SW cache + E preventive]
```

---

## Contraintes respectées

- ✅ `navigate()` du portail laissée intacte.
- ✅ Iframe `frame-observatoire` toujours dans le HTML (pas retirée).
- ✅ Aucun push remote.
- ✅ Phases O-A → O-E intouchées.
- ✅ Tout le contenu existant d'observatoire conservé — le widget est **inséré** dans le vide, rien n'est supprimé.
- ✅ Backups `portail.html.bak_phase_of` et `observatoire.html.bak_phase_of` créés avant patch.
- ✅ Six tags posés (3 pre / 3 done).
- ✅ Trois commits indépendants (OF1, OF2, OF3) pour traçabilité fine et rollback granulaire possible.

---

## Fichiers modifiés

| Fichier | Diff |
|---|---|
| `templates/portail.html` | OF1 — 2 onclick remplacés (lignes 1375, 1696) |
| `templates/observatoire.html` | OF2 — `disconnectObservatory()` (l 965) + OF3 — HTML widget (~36 l) + CSS widget (~100 l) + JS refresh (~110 l) |
| `OBSERVATOIRE_REFACTOR_PHASE_OF.md` | Ce rapport |

## Notes pour l'utilisateur

1. **Tester OF1** : ouvrir `/portail`, cliquer OBSERVATOIRE depuis la sidebar ou la splash → l'URL doit devenir `/observatoire` plein écran sans chrome portail.
2. **Tester OF2** : si vous arrivez à embarquer observatoire dans une iframe (par exemple en tapant directement `/observatoire?embed=1` dans une page tierce), le bouton ◄ PORTAIL doit ramener au portail top-level.
3. **Tester OF3** : aller sur `/observatoire`, scroller jusqu'au widget « ÉTAT COSMIQUE LIVE — TLEMCEN ». Les 4 cards doivent se peupler en quelques secondes. Le point vert pulse en continu. Refresh auto toutes les 30 s — observable en regardant le coin lat/lon ISS qui dérive.
4. **Données qui pourraient ne pas charger** :
   - **Open-Meteo** est en CORS direct ; si l'utilisateur a un bloqueur agressif, la card Tlemcen restera à `—`. C'est acceptable pour un embryon — quand le moment sera venu de durcir, on proxiera via `/api/weather/local`.
   - **`/api/iss`** et **`/api/meteo-spatiale`** sont same-origin, fonctionnels au moment du test.
