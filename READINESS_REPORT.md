# Orbital-Chohra — Rapport de vérification opérationnelle

**Date :** 2026-03-15  
**Périmètre :** Flask routes, navigation iframes, APIs, modules, liens, fichiers, JS, CSS.

---

## 1. Flask routes

### 1.1 Routes principales (pages)

| Route | Template | Statut |
|-------|----------|--------|
| `/` | redirect → `/observatoire` | OK |
| `/portail` | `portail.html` | OK |
| `/dashboard` | `research_dashboard.html` | OK (étiquette "Dashboard QG" = Research Dashboard) |
| `/overlord_live` | `overlord_live.html` | OK |
| `/galerie` | `galerie.html` | OK |
| `/observatoire` | `observatoire.html` | OK |
| `/vision` | `vision.html` | OK |
| `/vision-2026` | `vision_2026.html` | OK |
| `/sondes` | `sondes.html` | OK |
| `/scientific` | `scientific.html` | OK |
| `/mission-control` | `mission_control.html` | OK |
| `/space` | `space.html` | OK |
| `/space-intelligence` | redirect → `/space` | OK |
| `/space-intelligence-page` | `space_intelligence.html` | OK |
| `/space-weather` | `space_weather.html` | OK |
| `/orbital-map` | `orbital_map.html` | OK |
| `/globe` | `globe.html` | OK |
| `/lab` | `lab.html` | OK |
| `/research` | `research.html` | OK |
| `/research-center` | `research_center.html` | OK |
| `/ce_soir` | `ce_soir.html` | OK |
| `/telescopes` | `telescopes.html` | OK |
| `/favicon.ico` | `send_from_directory('static','favicon.ico')` | OK |
| `/module/<name>` | `{name}.html` si existant | OK |

**Total règles enregistrées :** 115 (dont APIs et static).

### 1.2 Templates référencés — existence

Tous les templates utilisés par `render_template()` existent dans `templates/` :

- `portail.html`, `research_dashboard.html`, `overlord_live.html`, `galerie.html`, `observatoire.html`, `vision.html`, `vision_2026.html`, `sondes.html`, `scientific.html`, `mission_control.html`, `space.html`, `space_intelligence.html`, `space_weather.html`, `orbital_map.html`, `globe.html`, `lab.html`, `research.html`, `research_center.html`, `ce_soir.html`, `telescopes.html`.

**Note :** `dashboard.html` existe mais n’est pas servi par une route ; la route `/dashboard` utilise `research_dashboard.html`. Cohérent avec le libellé "Dashboard QG".

---

## 2. Navigation iframes (portail)

### 2.1 Structure

- **Conteneur :** `#portal-pages` présent, CSS `position:absolute; left:0; right:0; top:0; bottom:0`.
- **Iframes :** 6 modules avec `id="frame-{page}"`, `class="page-frame"`, `data-src` sans `src` initial :
  - `frame-dashboard` → `/dashboard`
  - `frame-overlord` → `/overlord_live`
  - `frame-galerie` → `/galerie`
  - `frame-observatoire` → `/observatoire`
  - `frame-vision` → `/vision`
  - `frame-mission-control` → `/mission-control`

### 2.2 Fonction `navigate(page)`

- Présente et exposée : `window.navigate = navigate`.
- Masque tous les `.page-frame`, récupère `frame = document.getElementById("frame-" + page)`.
- Si `page === "home"` : affiche `#home-screen`, cache les iframes, pas d’iframe `frame-home` (comportement attendu).
- Sinon : cache `#home-screen`, charge `frame.src = frame.dataset.src` si vide ou `about:blank`, affiche l’iframe.
- **Point d’attention :** la classe `.active` des `.nav-item` n’est pas mise à jour dans `navigate()`. Seul "Accueil" a `active` au chargement ; en changeant de module, l’item de navigation actif ne change pas visuellement (cosmétique).

### 2.3 Boutons

- Sidebar et splash : `onclick="navigate('dashboard')"`, `navigate('overlord')`, `navigate('galerie')`, `navigate('observatoire')`, `navigate('vision')`, `navigate('mission-control')`, `navigate('home')`.
- Correspondance : chaque `navigate('x')` a un iframe `id="frame-x"` (ou cas `home` géré à part). Aucun lien cassé côté navigation.

---

## 3. Réponses API

### 3.1 Données utilisées par le portail

- **`/api/iss`** : position, altitude, équipage, etc. — implémenté, cache 5 s.
- **`/api/latest`** : stats (total, anomalies, sources, req_jour) — utilisé par la sidebar.
- **`/api/voyager-live`** : lecture de `static/voyager_live.json`. Format du fichier : `voyager_1`, `voyager_2` avec `distance_km` — compatible avec le widget "TÉLÉMÉTRIE INTERSTELLAIRE" du portail (`#voyager-live-container`).
- **`/api/sdr/status`** ou données SDR — utilisées par le portail si configuré.
- **`/api/feeds/hubble`** ou équivalent — utilisé par la sidebar Hubble.

### 3.2 APIs utilisées par Space Intelligence (`space.html`)

- `/api/orbits/live`, `/api/iss`, `/api/feeds/voyager`, `/api/voyager-live`, `/api/feeds/solar`, `/api/feeds/solar_alerts`, `/api/dsn`, `/api/space-weather`, `/api/feeds/apod_hd` — toutes définies dans `station_web.py`.

**Note :** Aucun test HTTP réel (serveur non démarré dans l’environnement de scan). À valider en live avec le serveur lancé.

---

## 4. Chargement des modules (iframes)

Chaque module chargé dans le portail correspond à une route et un template valides :

| Module | URL iframe | Template | Statut |
|--------|------------|----------|--------|
| Dashboard QG | `/dashboard` | `research_dashboard.html` | OK |
| Overlord Live | `/overlord_live` | `overlord_live.html` | OK |
| Galerie | `/galerie` | `galerie.html` | OK |
| Observatoire | `/observatoire` | `observatoire.html` | OK |
| Vision 2026 | `/vision` | `vision.html` | OK |
| Mission Control | `/mission-control` | `mission_control.html` | OK |

Aucun module iframe ne pointe vers un template manquant.

---

## 5. Liens (portail et cohérence)

### 5.1 Liens sidebar / splash (target="_blank" ou iframe)

- `/scientific`, `/lab`, `/research-center`, `/research`, `/space`, `/api/archive/reports` — routes existantes.
- Liens des cartes du splash : `/orbital-map`, `/space-weather`, `/module/observatoire`, `/module/vision`, `/module/scientific`, `/module/lab`, `/mission-control`, `/space-intelligence-page`, `/module/galerie` — tous valides (routes ou `module/<name>` avec template présent).

### 5.2 Fichiers statiques référencés

- **Favicon :** `/static/favicon.ico?v=2` et route dédiée `/favicon.ico` (envoi depuis `static`). **À confirmer :** présence effective de `static/favicon.ico` sur l’environnement (fichier signalé présent côté utilisateur).
- **Scripts :** aucun `<script src="/static/...">` dans le portail pour les modules (conformément à la refactorisation). Les scripts spécifiques (ex. `sondes_aegis.js`) sont chargés dans les templates des modules (ex. `observatoire.html`, `overlord_live.html`).

---

## 6. Fichiers manquants ou à vérifier

- **`static/favicon.ico`** : requis par la route et le `<link>` du portail. À vérifier en production.
- **`static/space_weather.json`** : utilisé par `/api/space-weather` et `/api/meteo-spatiale`. Présent dans la liste des fichiers static.
- **`static/voyager_live.json`** : présent, format compatible portail.
- **`static/passages_iss.json`** : utilisé par `/api/passages-iss`. Présent.

Aucun template référencé par une route n’est manquant.

---

## 7. JavaScript (portail)

- **Syntaxe :** pas d’erreur évidente dans les blocs `<script>` du portail (IIFE, `navigate()`, `loadStats()`, PWA sync, `syncVoyagerPortal()`).
- **`syncVoyagerPortal`** : utilise `data.voyager_1` / `data.voyager_2` ; le JSON dans `static/voyager_live.json` fournit bien ces clés → pas d’erreur attendue.
- **`navigate()`** : gère `frame.dataset.src` et `about:blank` ; pas de référence à un élément manquant (sauf si `#home-screen` est absent — il est bien présent).
- **Exposition globale :** `window.navigate = navigate` présent.

Aucune incohérence bloquante détectée.

---

## 8. CSS (portail)

- **Variables :root** : définies une seule fois (void, panel, border, cyan, amber, green, red, text, font, mono, sidebar).
- **Sélecteurs critiques :** `.page-frame`, `#portal-pages`, `.content-area`, `.nav-item.active` définis sans doublon conflictuel.
- **Conteneur iframes :** `#portal-pages` en `position:absolute; left:0; right:0; top:0; bottom:0` ; `.page-frame` en `display:none; width:100%; height:100%; border:0; background:black` — pas de conflit détecté.
- **Responsive :** media query `@media (max-width: 900px)` pour le shell ; pas de conflit repéré.

Aucun conflit CSS majeur identifié.

---

## 9. Synthèse — Prêt pour exploitation

| Catégorie | Statut | Remarques |
|-----------|--------|-----------|
| Flask routes | OK | Toutes les routes utilisent des templates existants. |
| Navigation iframes | OK | 6 modules, `navigate()` cohérente avec les ids et `data-src`. |
| API (structure) | OK | Endpoints utilisés par le portail et Space Intelligence présents. |
| Modules (templates) | OK | Aucun template manquant pour les routes ou `/module/<name>`. |
| Liens | OK | Liens du portail pointent vers des routes ou modules valides. |
| Fichiers static | À vérifier | `favicon.ico` à confirmer sur l’environnement. |
| JS portail | OK | Pas d’erreur de syntaxe ou d’usage détectée. |
| CSS portail | OK | Pas de conflit identifié. |

**Recommandations rapides :**

1. **Optionnel (UX) :** Dans `navigate(page)`, mettre à jour la classe `.active` des `.nav-item` (retirer `active` de tous, l’ajouter à `#nav-{page}` ou `#nav-home` selon `page`) pour que la sidebar reflète le module affiché.
2. **Opérationnel :** Vérifier que `static/favicon.ico` existe sur chaque déploiement.
3. **Validation finale :** Lancer le serveur et tester en navigateur : `/portail`, clics sur chaque module, rafraîchissement ISS/Voyager/Stats, puis ouvrir la console (F12) pour confirmer l’absence d’erreurs JS et de 404.

---

*Rapport généré par scan opérationnel Orbital-Chohra (AstroScan).*
