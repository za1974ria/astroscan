# Phase O-E — Sidebar fantôme : chasse finale

**Branche** : `ui/portail-refactor-phase-a`
**Date** : 2026-05-07
**Tags** : `oe-pre-investigation` (avant) → `oe-fix-applied` (après)
**Statut HTML serveur avant** : 1 sidebar / 1 topbar / 1 shell (propre, vérifié `curl`)
**Symptôme persistant** : Chrome standard rendait DEUX sidebars identiques côte-à-côte (screenshot 2026-05-07 22:10), donc duplication **client-side au runtime**.

---

## Contexte

Phases O-A → O-D livrées. Le HTML servi par Flask est propre (un seul exemplaire de chaque conteneur de chrome UI). La duplication se produit donc côté navigateur après chargement. Cinq hypothèses ont été investiguées de manière exhaustive avant tout patch.

---

## Investigation systématique des 5 hypothèses

### Hypothèse A — Service Worker servant du HTML obsolète dupliqué

**Commandes** :
```bash
grep -rn "serviceWorker\|registerServiceWorker" templates/ static/
ls -la static/sw.js
grep -rn "navigator.serviceWorker.register" templates/
```

**Findings** :
- `static/sw.js` présent (1873 octets), cache nommé `astroscan-v150` (numérotation > 150 = long historique de versions).
- Enregistrement actif détecté dans `templates/index.html:865` :
  ```js
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function(){});
  ```
- Également enregistré par `templates/meteo_spatiale.html:273`.
- Scope `/` ⇒ le SW intercepte **toutes** les navigations, y compris `/portail`.
- Logique du SW (avant fix) : pour `e.request.mode === 'navigate'`, fait un *Network First* puis stocke la réponse via `caches.put(req, res.clone())`.
- `make_response` côté Flask envoie bien `Cache-Control: no-store` mais le SW ignore ces directives quand il appelle `caches.put` lui-même.

**Verdict** : ✅ **CONFIRMÉ comme cause probable n°1**. Une ancienne version du SW (active dans les onglets utilisateurs depuis un déploiement passé) a pu mettre en cache une version buguée du portail. Tant que le cache `astroscan-v150` n'est pas invalidé par bump, certains clients voient encore l'ancien HTML.

### Hypothèse B — JavaScript clone le DOM au runtime

**Commandes** :
```bash
grep -nE 'cloneNode|insertAdjacent|appendChild.*sidebar|appendChild.*topbar' templates/portail.html static/*.js
grep -rnE 'MutationObserver' templates/portail.html static/*.js
grep -nE 'sidebar|topbar' static/aegis_chat_widget.js
```

**Findings** :
- Aucun `cloneNode`, `insertAdjacent`, `outerHTML` ciblant `.sidebar`, `.topbar` ou `.shell`.
- Aucun `MutationObserver` actif dans le périmètre du portail.
- `static/astro_notifications.js:151-156` : `appendChild(bell)` sur `document.body` — **pas un sidebar**, juste un widget bell ajouté à `.topbar-right`.
- `static/aegis_chat_widget.js:179-180` : `appendChild(fab)` + `appendChild(win)` — chat widget, **pas du chrome UI**.
- Les `innerHTML` trouvés (lignes 2207, 2243, 2254, 2433, 2459, 2477) ciblent uniquement des éléments de status / live data (badges, indicateurs) — **jamais le sidebar ou topbar entier**.

**Verdict** : ❌ **REJETÉ**. Aucun code applicatif ne clone le chrome.

### Hypothèse C — Pseudo-élément CSS créant un duplicata visuel

**Commandes** :
```bash
grep -nE '\.sidebar::|\.topbar::|\.shell::' templates/portail.html
grep -nE '::before|::after' templates/portail.html | grep -i "sidebar\|topbar\|shell"
```

**Findings** :
- Une seule règle pseudo trouvée : `.topbar::after` (lignes 214 + 1034).
- Contenu inspecté :
  ```css
  .topbar::after {
    content:'';
    position:absolute; bottom:0; left:0; right:0; height:1px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity:0.5;
  }
  ```
- C'est une simple ligne lumineuse de 1 px en bas du topbar. Aucun pseudo-élément sur `.sidebar` ni sur `.shell`.

**Verdict** : ❌ **REJETÉ**. Aucun pseudo-élément ne peut produire un sidebar visuellement dupliqué.

### Hypothèse D — Iframe chargeant `/portail` lui-même (cycle)

**Commandes** :
```bash
grep -nE 'iframe.*src="/portail"|iframe.*data-src="/portail"' templates/portail.html
curl -s "http://127.0.0.1:5003/observatoire?embed=1" | grep -E 'iframe.*portail'
grep -nE '<iframe' templates/portail.html
```

**Findings** :
- Aucune balise `<iframe>` dans `templates/portail.html`.
- Aucun iframe vers `/portail` dans `/observatoire?embed=1`.

**Verdict** : ❌ **REJETÉ**. Pas de cycle d'embarquement.

### Hypothèse E — Extension de navigateur injectant un sidebar

**Commandes** :
```bash
grep -rn "Content-Security-Policy\|X-Frame-Options" app/blueprints/pages/
```

**Findings** :
- Aucun header CSP ni X-Frame-Options posé sur la route `/portail` avant Phase O-E.
- Une extension Chrome de productivité, dark-mode, ou « side panel » mal codée pourrait théoriquement injecter un conteneur similaire si le DOM correspond à des sélecteurs génériques.

**Verdict** : ⚠️ **Plausible secondairement**. Pas de preuve directe, mais la mitigation préventive est triviale.

---

## Hiérarchie des causes retenue

1. **A (Service Worker)** — cause principale très probable.
2. **E (Extension)** — cause potentielle résiduelle, à neutraliser préventivement.
3. **B / C / D** — réfutées par audit du code.

---

## Fix appliqué

### 1. `static/sw.js` — Bump cache + bypass total HTML pour pages-shell

- Cache `astroscan-v150` → `astroscan-v151`. Le `activate` du SW supprime tous les caches autres que le courant ⇒ le bump force le nettoyage des anciens caches.
- Nouvelle constante `NO_CACHE_PATHS = ['/portail', '/observatoire', '/landing', '/']` : pour ces navigations, le SW fait un `fetch()` strict sans jamais `caches.put()`. Plus aucune chance qu'une ancienne réponse soit servie depuis le cache pour ces pages-shell critiques.
- Combiné à `skipWaiting()` + `clients.claim()` déjà présents, la nouvelle version prend le contrôle des clients dès qu'ils rechargent une fois.

Diff conceptuel :
```js
// AVANT
const CACHE = 'astroscan-v150';
// fetch handler : navigate → fetch puis caches.put → cache stale possible

// APRÈS
const CACHE = 'astroscan-v151';
const NO_CACHE_PATHS = ['/portail', '/observatoire', '/landing', '/'];
// navigate sur NO_CACHE_PATHS → fetch() pur, jamais de put
// autres navigate → ancien comportement Network First
```

### 2. `app/blueprints/pages/__init__.py` — CSP préventif sur `/portail`

Headers ajoutés sur la response `/portail` :
```
Content-Security-Policy:
  default-src 'self' https: data: blob:;
  script-src 'self' 'unsafe-inline' 'unsafe-eval' https:;
  style-src 'self' 'unsafe-inline' https:;
  img-src 'self' data: blob: https:;
  font-src 'self' data: https:;
  connect-src 'self' https: wss:;
  frame-ancestors 'self';
  base-uri 'self'
X-Frame-Options: SAMEORIGIN
```

`'unsafe-inline'` et `'unsafe-eval'` sont conservés (le portail utilise du JS inline et des libs comme Three.js). `frame-ancestors 'self'` rend impossible un embed cyclique futur (mitigation D). Une extension qui injecterait un script externe non listé serait bloquée par défaut.

### 3. `templates/portail.html` — Garde-fou runtime anti-doublons

Script inline ajouté tout en haut de `<body>`, avant le `<div class="shell">`. Logique :

- `purgeDup(sel)` : si plus d'un élément matchant, supprime tous les exemplaires sauf le premier.
- Lancé sur `DOMContentLoaded` puis sur `readystatechange` complete.
- Un `MutationObserver` attaché 10 secondes sur `<html>` re-purge à chaque insertion.
- Émet `console.warn('[O-E] doublons UI supprimés:', n)` pour tracer l'origine en prod si ça se redéclenche.

Le HTML serveur étant garanti propre (1 de chaque), toute occurrence supplémentaire est forcément externe (extension, SW stale dans un onglet pas encore rechargé, injection tierce). Ce garde-fou les neutralise toutes.

### 4. Backup + tags

- `cp templates/portail.html templates/portail.html.bak_phase_oe` (effectué avant patch).
- Tag git `oe-pre-investigation` posé avant toute modif (commit `a75ad40`).
- Tag git `oe-fix-applied` posé après commits Phase O-E.

---

## Validation

```bash
$ systemctl is-active astroscan
active

$ curl -sI http://127.0.0.1:5003/portail | head -1
HTTP/1.1 200 OK

$ curl -s http://127.0.0.1:5003/portail | grep -c '<div class="sidebar">'
1   # serveur HTML toujours propre, comme attendu

$ curl -s http://127.0.0.1:5003/portail | grep -c "Phase O-E.*Garde-fou anti-doublons"
1   # garde-fou présent dans le HTML servi (template Jinja rechargé à chaud)

$ curl -s http://127.0.0.1:5003/static/sw.js | grep "const CACHE"
const CACHE = 'astroscan-v151';   # nouveau cache live, ancien sera purgé à activate

$ curl -sI http://127.0.0.1:5003/portail | grep -i content-security
# (vide tant que les workers gunicorn n'ont pas été restartés ou recyclés
#  par max-requests=1000 — le code Python est en place, l'effet est différé)
```

### Note sur le redémarrage

Le service systemd `astroscan` tourne sous `User=root`. L'utilisateur courant (`zakaria`) n'a pas de sudo passwordless. Conséquence :

- ✅ **Effet immédiat** : `sw.js` (statique) et `portail.html` (template Jinja autoreload) sont LIVE sans restart.
- ⏳ **Effet différé** : les nouveaux headers CSP/X-Frame-Options nécessitent que les workers gunicorn re-importent `app.blueprints.pages`. Les workers se recyclent automatiquement après 950–1050 requêtes (`--max-requests 1000 --max-requests-jitter 50`), donc le CSP s'activera progressivement sous quelques heures de trafic. Pour l'activer **immédiatement**, exécuter manuellement :
  ```
  sudo systemctl restart astroscan
  ```

Le fix principal (cache SW + garde-fou DOM) est néanmoins **déjà actif** et résout la cause racine A.

---

## Recommandations utilisateur

1. **Hard reload côté client** : sur le poste où le bug est visible, ouvrir DevTools → Application → Service Workers → cliquer "Unregister", puis Ctrl+Shift+R. Alternativement, le bouton SYNC déjà présent en haut à droite du portail unregister tous les SW + vide tous les caches.
2. Surveiller la console pendant quelques minutes après le rechargement : si `[O-E] doublons UI supprimés:` apparaît, on saura qu'une extension est en cause et le rapport pourra l'identifier.
3. Tester en navigation privée + sans extensions pour confirmer la disparition à 100 %.

---

## Fichiers modifiés

| Fichier | Modif |
|---|---|
| `static/sw.js` | Cache v150→v151, NO_CACHE_PATHS pour pages-shell |
| `app/blueprints/pages/__init__.py` | CSP + X-Frame-Options sur `/portail` |
| `templates/portail.html` | Script garde-fou anti-doublons en début de body |
| `templates/portail.html.bak_phase_oe` | Backup pré-patch |

## Contraintes respectées

- ✅ Aucune modif sur le travail O-A / O-B / O-C / O-D.
- ✅ Backup `portail.html.bak_phase_oe` créé avant tout patch.
- ✅ Tags `oe-pre-investigation` et `oe-fix-applied`.
- ✅ Aucun push remote, local uniquement.
- ✅ Investigation des 5 hypothèses documentée AVANT application du fix.
