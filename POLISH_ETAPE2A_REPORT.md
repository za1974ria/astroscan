# POLISH — ÉTAPE 2A — RAPPORT

Branche : `migration/phase-2c`
Date : 2026-05-06
Mode : Texte + CSS + JS d'animation visuelle uniquement (aucun backend touché)

---

## Correction 1 — STATUT SYSTÈME (accent)

- **Fichier :** `templates/research_dashboard.html`
- **Ligne modifiée :** 273
- **Occurrences avant :** 1 (`Statut systeme`)
- **Occurrences après :** 0 (`Statut systeme`) / 1 (`Statut système`)

### Diff before/after

```diff
-      <h2>Statut systeme</h2>
+      <h2>Statut système</h2>
```

---

## Correction 2 — Boutons cockpit (Portail / Actualiser)

### Diagnostic

- **Route `/space-intelligence` :** `app/blueprints/pages/__init__.py:156-158` → `redirect("/space")` → rend `templates/space.html`.
- **Constat :** `templates/space.html` ne contient qu'**un seul** lien `← Portail` (l. 151). Aucun bouton « Actualiser » n'y existe.
- **Page réelle qui contient les 2 boutons « Portail » + « Actualiser » :** `templates/research_dashboard.html` (rendue par `/dashboard`, `app/blueprints/pages/__init__.py:84-86`).
  - Bouton `Portail` : ligne **309** (avant), maintenant **323**, dans `<article class="card actions">`.
  - Bouton `Actualiser` : ligne **327** (avant), maintenant **341**, dans la section GEO-IP TRACKER (en bas à droite).
- **Décision (mode autonome) :** appliquer la correction sur `research_dashboard.html` puisque c'est la seule page contenant ces 2 boutons « petits, en bas à droite ». À confirmer visuellement avec l'utilisateur si la cible était bien /dashboard et non /space.

### Classes CSS existantes

- `.btn` (définie à `templates/research_dashboard.html:85` — style générique réutilisé partout dans le dashboard).
- `.btn:hover` (l. 96).
- `.btn-danger` (l. 97).

### Fichier CSS modifié

- `templates/research_dashboard.html` (CSS inline dans le `<style>` du template).
- **Nouvelle classe ajoutée :** `.btn-cockpit-primary` (additionnelle à `.btn`, n'écrase aucune règle existante hors propriétés explicitement spécifiées).

### Diff before/after — CSS

```diff
   .btn:hover{background:rgba(0,212,255,.2)}
+  .btn-cockpit-primary{
+    padding:12px 24px;
+    font-size:14px;
+    border:1px solid rgba(0,220,255,.4);
+    background:rgba(0,30,50,.6);
+    color:#00DCFF;
+    letter-spacing:.05em;
+    transition:all .25s ease;
+  }
+  .btn-cockpit-primary:hover{
+    background:rgba(0,50,80,.8);
+    box-shadow:0 0 12px rgba(0,220,255,.5);
+    transform:translateY(-1px);
+  }
   .btn-danger{
```

### Diff before/after — HTML

```diff
-      <a href="/portail"><button class="btn">Portail</button></a>
+      <a href="/portail"><button class="btn btn-cockpit-primary">Portail</button></a>
```

```diff
-      <button class="btn" id="btnGeoRefresh" onclick="fetchGeoStatsAndVisitors()" style="margin:0;width:auto;padding:6px 10px">Actualiser</button>
+      <button class="btn btn-cockpit-primary" id="btnGeoRefresh" onclick="fetchGeoStatsAndVisitors()" style="margin:0;width:auto">Actualiser</button>
```

> Note : le `padding:6px 10px` inline du bouton « Actualiser » a été retiré car il aurait écrasé le padding 12px/24px de `.btn-cockpit-primary` (les styles inline ont priorité). `width:auto` et `margin:0` sont conservés tels quels.

---

## Correction 3 — Animation compteur header

### Diagnostic

- **Élément HTML cible :** `<span id="tbar-visits-val">000 000</span>` (`templates/portail.html:1145`).
- **Fonction JS qui met à jour le compteur :** `loadVisitsPortail()` à `templates/portail.html:2037` (devenue ligne 2043 après ajout CSS plus haut).
- **Polling :** `setInterval(loadVisitsPortail, API_INTERVALS.visits)` — non touché.
- **Périodicité de fetch :** non touchée.

### CSS ajouté

```diff
 .tbar-visits { display:flex; align-items:center; ... }
+.header-counter-pulse { animation: counterFlash 0.4s ease-out; display:inline-block; }
+@keyframes counterFlash {
+  0%   { transform: scale(1); color: inherit; text-shadow: none; }
+  35%  { transform: scale(1.08); color: #00DCFF; text-shadow: 0 0 8px rgba(0, 220, 255, 0.8); }
+  100% { transform: scale(1); color: inherit; text-shadow: none; }
+}
 @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
```

> Note : `display:inline-block` ajouté sur la classe pulse car `transform: scale(...)` n'a pas d'effet sur un `<span>` qui reste en `inline` par défaut.

### JS modifié

```diff
-  function loadVisitsPortail(){fetch('/api/visits').then(function(r){return r.ok?r.json():null;}).then(function(d){var el=document.getElementById('tbar-visits-val');if(el&&d)el.textContent=fmtVisits(d.count||0);}).catch(function(){});}
+  function loadVisitsPortail(){fetch('/api/visits').then(function(r){return r.ok?r.json():null;}).then(function(d){var el=document.getElementById('tbar-visits-val');if(el&&d){var newVal=fmtVisits(d.count||0);if(el.textContent!==newVal){el.textContent=newVal;el.classList.remove('header-counter-pulse');void el.offsetWidth;el.classList.add('header-counter-pulse');setTimeout(function(){el.classList.remove('header-counter-pulse');},450);}}}).catch(function(){});}
```

Décomposé pour lecture :

```js
function loadVisitsPortail() {
  fetch('/api/visits')
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(d) {
      var el = document.getElementById('tbar-visits-val');
      if (el && d) {
        var newVal = fmtVisits(d.count || 0);
        if (el.textContent !== newVal) {
          el.textContent = newVal;
          el.classList.remove('header-counter-pulse'); // reset si pulse en cours
          void el.offsetWidth; // force reflow pour relancer animation
          el.classList.add('header-counter-pulse');
          setTimeout(function() { el.classList.remove('header-counter-pulse'); }, 450);
        }
      }
    })
    .catch(function() {});
}
```

### Portée

Appliqué uniquement à `portail.html` (page d'accueil principale). D'autres templates utilisent aussi `tbar-visits-val` (`a_propos.html`, `ce_soir.html`, `ephemerides.html`) — non modifiés ici, à étendre dans une étape ultérieure si désiré.

---

## Validation

| Vérification | Résultat |
| --- | --- |
| `python -m py_compile station_web.py` | **OK** |
| Routes (`create_app('production')`) | **291** (cible 291) ✅ |
| Backend touché ? | **Non** |
| Templates de secours touchés ? | **Non** (aucun `_live`/`_50ko`/`_mediocre`/`_backup`) |
| `git commit` exécuté ? | **Non** |
| `systemctl restart` exécuté ? | **Non** |

### Fichiers touchés par cette étape 2A

- `templates/research_dashboard.html` — Correction 1 + Correction 2 (CSS + 2 buttons)
- `templates/portail.html` — Correction 3 (CSS + JS du compteur header)

> NB : `git diff --stat` affiche d'autres fichiers (de session(s) précédente(s) — ex. `flight_radar.html`, `orbital_map.html`, `ce_soir.html`, etc.). Ces modifications ne sont pas issues de cette étape 2A.

---

## Recommandation pour la suite

### Vérifications visuelles à faire (Chrome incognito + Ctrl+Shift+R)

1. **`/dashboard`** → bloc "Statut système" doit afficher l'accent `è` correct (`Statut système`).
2. **`/dashboard`** (et non `/space-intelligence` qui ne contient pas ces boutons) :
   - Bouton `Portail` (carte « Actions rapides ») → padding plus généreux (12px 24px), couleur cyan plus vive, glow cyan au hover, léger soulèvement 1px.
   - Bouton `Actualiser` (section GEO-IP TRACKER, en bas à droite) → idem.
   - **À confirmer avec l'utilisateur :** la cible visée est-elle bien `/dashboard` ou `/space` (`/space-intelligence`) ? `/space` n'a qu'un seul bouton `← Portail` actuellement.
3. **`/portail`** → compteur `👁 NNN NNN` doit flasher cyan (scale 1.08 + glow + couleur `#00DCFF`) à chaque incrémentation détectée par le polling `/api/visits`.

### Cache-buster / restart

- Tous les changements sont inline dans les templates (CSS + JS embarqués) → **aucun cache-buster CSS externe nécessaire**.
- Restart du service `astroscan` à faire **uniquement** après validation utilisateur (les templates Flask sont chargés avec auto-reload activé en dev mais en prod un restart est requis pour la mise en cache Jinja).

### Points ouverts / propositions

- **Q1** Si l'utilisateur voulait bien parler de `/space-intelligence` (page `space.html`) et non de `/dashboard`, il faudrait :
  1. y ajouter un vrai bouton "Actualiser" (refresh général) à côté de "← Portail",
  2. appliquer `.btn-cockpit-primary` aux deux.
- **Q2** Étendre l'animation du compteur header aux autres templates qui utilisent `tbar-visits-val` (`a_propos.html`, `ce_soir.html`, `ephemerides.html`) → 4 modifs JS triviales.
