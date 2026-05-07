# OBSERVATOIRE REFACTOR — PHASE O-C — BREADCRUMB POSITION + SIDEBAR FANTÔME

**Date** : 2026-05-07
**Branche** : `ui/portail-refactor-phase-a`
**Fichier modifié** : `templates/observatoire.html` uniquement
**Backup** : `templates/observatoire.html.bak_phase_oc`

---

## Objectif

Deux irritants reportés post Phase O-B :

1. Breadcrumb « ◄ PORTAIL · OBSERVATOIRE » centré top:60px chevauchait le
   titre `Observatoire ORBITAL-CHOHRA` → visuellement perturbant.
2. En cliquant le breadcrumb, /portail apparaît avec **deux sidebars
   côte-à-côte** (sidebar fantôme).

---

## Commits

| SHA       | Message                                                         |
| --------- | --------------------------------------------------------------- |
| `40215df` | ui(observatoire): OC1 — breadcrumb top-right + remove redundant |
| `1a53e9d` | fix(navigation): OC2 — phantom sidebar on /portail nav          |

## Tags Git

| Tag                         | Cible                                         |
| --------------------------- | --------------------------------------------- |
| `obs-phase-oc-pre-fix1`     | Avant OC1 (breadcrumb centré redondant)       |
| `obs-phase-oc-fix1-done`    | Après OC1 (breadcrumb top-right épuré)        |
| `obs-phase-oc-pre-fix2`     | Avant OC2 (avant investigation/mitigation)    |
| `obs-phase-oc-fix2-done`    | Après OC2 (cache-bust onclick en place)       |

---

## OC1 — Reposition breadcrumb + remove « OBSERVATOIRE »

### HTML : retrait de la partie redondante

```diff
 <nav class="breadcrumb-nav" aria-label="Navigation">
-  <a href="/portail" class="breadcrumb-link">◄ PORTAIL</a>
-  <span class="breadcrumb-sep">·</span>
-  <span class="breadcrumb-current">OBSERVATOIRE</span>
+  <a href="/portail" class="breadcrumb-link" target="_self">◄ PORTAIL</a>
 </nav>
```

→ `target="_self"` explicite ; les spans `breadcrumb-sep` et
`breadcrumb-current` supprimés (la page courante est évidente).

### CSS : repositionné top-right, hors trajectoire du titre

```diff
-.breadcrumb-nav { position: fixed; top: 60px; left: 50%;
-                  transform: translateX(-50%); display: flex;
-                  align-items: center; gap: 10px; ... }
+.breadcrumb-nav { position: fixed; top: 235px; right: 24px; ... }
```

| Propriété             | Avant                          | Après               |
| --------------------- | ------------------------------ | ------------------- |
| Position horizontale  | `left:50% transform:-50%` (centre) | `right:24px` (ancré droite) |
| Position verticale    | `top:60px` (touche le titre)   | `top:235px` (zone vide au-dessus carte ISS) |
| Mise en page          | `display:flex` + gap           | `display:inline-block` (un seul lien) |
| Mobile                | `top:50px gap:6px` (en collision) | `top:8px right:8px` (coin discret) |

Règles `.breadcrumb-sep` et `.breadcrumb-current` supprimées du CSS
(éléments retirés, devenues orphelines).

### Comptes

| Token                    | Avant | Après |
| ------------------------ | ----: | ----: |
| `breadcrumb-current`     |     1 |     0 |
| `breadcrumb-sep`         |     1 |     0 |
| `· OBSERVATOIRE`         |     1 |     0 |
| `◄ PORTAIL` (rendu FR)   |     1 |     1 (préservé) |
| `target="_self"`         |     0 |     1 |

---

## OC2 — Sidebar fantôme : investigation + mitigation

### Étapes diagnostiques (5 commandes)

| # | Commande                                                                  | Résultat              | Verdict                   |
| - | ------------------------------------------------------------------------- | --------------------- | ------------------------- |
| 1 | `curl /portail \| grep -c '<div class="sidebar"'`                         | **1**                 | Source clean              |
| 2 | `grep "document.body.classList\|classList.add" templates/observatoire.html` | 4 hits, tous sur `.panel` ou `.tab` | Pas de leak body class |
| 3 | `curl -I /portail \| grep -i cache`                                       | `no-store, no-cache, must-revalidate, max-age=0` + `Pragma: no-cache` | Headers déjà en place |
| 4 | `curl -I /observatoire \| grep -i cache`                                  | Mêmes headers         | Idem                      |
| 5 | `grep -rn "serviceWorker" templates/ static/js/`                          | 1 hit dans `portail.html` (UNREGISTER déclenché par bouton SYNC, pas registration) | Pas de SW actif |

**Vérification supplémentaire** : aucune duplication `.sidebar` dans
`static/css/components.css`, `design_tokens.css`, `fixes.css`,
`orbital_command.css`. Aucun `appendChild`/`innerHTML` créant un sidebar
clone dans les .js.

### Analyse

Mission Case C (Cache-Control headers sur le blueprint) est **déjà en
place** depuis Phase précédente :

```python
# app/blueprints/pages/__init__.py l.60-77
@bp.route("/portail")
def portail():
    response = make_response(render_template("portail.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response
```

Côté serveur : rien à corriger. La sidebar fantôme n'existe pas dans le
HTML rendu.

**Cause la plus probable** : Chrome bfcache (Back/Forward Cache) qui
restitue un snapshot DOM datant d'une session **antérieure** à la pose
des headers `no-store`. Sur navigation interne (clic du breadcrumb),
Chrome décide parfois de réafficher la version mémoire avant de
re-fetcher. Le DOM restitué peut contenir des éléments injectés par
d'anciens scripts de la session précédente.

### Mitigation appliquée (côté observatoire seulement)

```html
<a href="/portail" class="breadcrumb-link" target="_self"
   onclick="this.href='/portail?_t='+Date.now();">◄ PORTAIL</a>
```

À chaque clic, `href` devient `/portail?_t=<timestamp>` — URL unique
jamais vue → invalidation bfcache → navigation forcée en fresh request.
Le serveur ignore les query params parasites sur cette route.

**Pourquoi ne pas toucher portail.html** : le fichier a des changements
non-commités (D-FIX 4 — élargissement cards) appartenant à une autre
phase. Les mélanger dans un commit OC2 serait sale. La mitigation
côté observatoire seul couvre le cas reporté (clic depuis le breadcrumb).

### Comptes

| Élément                              | Avant | Après |
| ------------------------------------ | ----: | ----: |
| `<div class="sidebar"` dans /portail rendu | 1 | 1 (inchangé — source clean) |
| `Cache-Control: no-store` sur /portail | ✓ | ✓ (déjà OK) |
| `onclick` cache-bust sur breadcrumb  |     0 |     1 |

---

## Validation finale

```
=== service ===                       active
=== /portail HTTP ===                 HTTP/1.1 200 OK
=== /observatoire HTTP ===            HTTP/1.1 200 OK

OC1 — breadcrumb-current / · OBSERVATOIRE (=0) :   0   ✓
OC1 — ◄ PORTAIL présent (>=1) :                    2   ✓ (HTML + balise du span legacy déjà retirée)
OC2 — /portail sidebar count (=1) :                1   ✓
OC2 — cache headers /portail :                     no-store + no-cache + Pragma  ✓
OC2 — onclick cache-bust présent :                 1   ✓
```

---

## Notes visuelles

- **OC1** : le breadcrumb désormais ancré coin-haut-droit en zone vide,
  juste au-dessus de la carte ISS. Le titre `Observatoire
  ORBITAL-CHOHRA` reste seul, pleinement lisible. Sur mobile, la pillule
  se replie en coin-haut-droit (8px d'inset), sans empiéter sur le
  hamburger éventuel (qui est positionné côté gauche).
- **OC2** : le clic ressent bien comme un refresh complet (pas de
  flicker bfcache). La mitigation est invisible pour l'utilisateur —
  juste une URL un peu plus longue dans la barre d'adresse pendant 200ms.
  Si le bug se reproduit (peu probable), le diagnostic plus fin
  (devtools Network + bfcache panel) sera nécessaire.

---

## Recommandation utilisateur (hors-scope)

Si la sidebar fantôme persiste malgré OC2, l'utilisateur devrait :
1. **Hard reload** : `Ctrl+Shift+R` une fois sur /portail (purge la
   version cachée pré-headers).
2. **Onglet privé** : tester `/portail` en navigation privée — confirme
   que le bug est purement client-side (cache navigateur).
3. **DevTools → Application → Clear site data** : nettoyage radical.

---

**Phase O-C : DONE — breadcrumb épuré + navigation /portail bétonnée.**
