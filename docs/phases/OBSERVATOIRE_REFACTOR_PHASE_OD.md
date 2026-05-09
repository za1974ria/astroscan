# OBSERVATOIRE REFACTOR — PHASE O-D — NAVIGATION PROPRE

**Date** : 2026-05-07
**Branche** : `ui/portail-refactor-phase-a`
**Fichier modifié** : `templates/observatoire.html` uniquement
**Backup** : `templates/observatoire.html.bak_phase_od`

---

## Objectif

Simplifier la navigation et neutraliser les éléments visuels parasites :

1. Bouton « Déconnexion » rouge (#ff4466) → trop alarmant pour une simple
   navigation. Couleur d'incident pour une fonction triviale.
2. Bouton « ℹ À PROPOS » top-right → doublon avec l'entrée déjà présente
   dans le sidebar gauche. Source d'un détour /a-propos identifié comme
   contributeur potentiel à la sidebar fantôme reportée en O-C.
3. Breadcrumb flottant OC1 « ◄ PORTAIL » top-right → devient redondant
   une fois que le bouton header (OD1) porte le même rôle.

---

## Commits

| SHA       | Message                                                             |
| --------- | ------------------------------------------------------------------- |
| `32a9dad` | ui(observatoire): OD1 — Déconnexion rouge → ◄ PORTAIL cyan         |
| `e604e94` | ui(observatoire): OD2 — remove duplicate À PROPOS top-right button  |
| `c1c67c6` | ui(observatoire): OD3 — remove redundant floating breadcrumb        |

## Tags Git

| Tag                         | Cible                                       |
| --------------------------- | ------------------------------------------- |
| `obs-phase-od-pre-fix1`     | Avant OD1 (Déconnexion rouge)               |
| `obs-phase-od-fix1-done`    | Après OD1 (◄ PORTAIL cyan)                  |
| `obs-phase-od-pre-fix2`     | Avant OD2 (À PROPOS top-right présent)      |
| `obs-phase-od-fix2-done`    | Après OD2 (doublon supprimé)                |
| `obs-phase-od-pre-fix3`     | Avant OD3 (breadcrumb flottant présent)     |
| `obs-phase-od-fix3-done`    | Après OD3 (breadcrumb retiré)               |

---

## OD1 — « Déconnexion » rouge → « ◄ PORTAIL » cyan

### HTML

```diff
-<button type="button" class="disconnect-btn"
-        onclick="disconnectObservatory()"
-        title="Retour au portail">Déconnexion</button>
+<button type="button" class="back-to-portal-btn"
+        onclick="disconnectObservatory()"
+        title="Retour au portail">◄ PORTAIL</button>
```

- `class` : `disconnect-btn` → `back-to-portal-btn` (évite tout leak du
  style rouge)
- Label : « Déconnexion » / « Disconnect » → « ◄ PORTAIL » / « ◄ PORTAL »
- Fonction `disconnectObservatory()` strictement inchangée
  (`window.location.href='/portail'`)

### CSS — nouvelle classe ajoutée près de l'ancienne

```css
.back-to-portal-btn{
  width:auto;min-width:110px;padding:10px 14px;font-size:11px;
  cursor:pointer;border-radius:4px;
  background:rgba(0,212,255,0.08);
  border:1px solid rgba(0,212,255,0.4);
  color:var(--cyan);
  font-family:'Share Tech Mono',monospace;
  letter-spacing:0.15em;
  transition:all 0.18s ease;
}
.back-to-portal-btn:hover{
  background:rgba(0,212,255,0.18);
  border-color:var(--cyan);
  box-shadow:0 0 14px rgba(0,212,255,0.5);
  color:#cce4ff;
}
```

Mobile : la nouvelle classe est ajoutée aux deux media queries existantes
(640px + version compacte) à côté de `.refresh-btn` et `.disconnect-btn`
pour cohérence layout.

### Préservation de `.disconnect-btn`

La règle CSS `.disconnect-btn` est **conservée** : le bouton « Fermer »
du `sonde-modal` (l.974) l'utilise encore comme bouton de fermeture
d'overlay. Ne pas la supprimer = pas de régression sonde-modal.

### Comptes

| Token                          | Avant | Après |
| ------------------------------ | ----: | ----: |
| `>Déconnexion<` / `>Disconnect<` |   1 |     0 |
| `◄ PORTAIL` / `◄ PORTAL`       |     0 |     1 (HTML rendu) |
| `back-to-portal-btn`           |     0 |     5 (HTML + 4 règles CSS / media queries) |
| `disconnect-btn` (préservé)    |     7 |     7 (sonde-modal + CSS) |

---

## OD2 — Suppression du bouton « ℹ À PROPOS » top-right

### Cible (l.567 avant correction)

```html
<button class="tab" onclick="window.location.href='/a-propos'"
        style="background:rgba(0,212,255,0.05);border-color:rgba(0,212,255,0.25);margin-left:auto">
  ℹ À PROPOS
</button>
```

→ Doublon : le sidebar gauche contient déjà une entrée « À propos ».

### Action

Suppression complète de la balise + ajout d'un commentaire de traçabilité :

```html
<!-- PASS UI O-D FIX 2 (2026-05-07) : bouton "ℹ À PROPOS" top-right
     supprimé (doublon — le sidebar gauche contient déjà l'entrée). -->
```

### Effet de bord positif

Le détour « observatoire → /a-propos → bouton 'Retour portail' depuis
/a-propos → /portail » était identifié en O-C comme contributeur
plausible à l'effet de sidebar fantôme. Le retirer simplifie la
navigation à un chemin unique : `observatoire → ◄ PORTAIL → /portail`.

### Comptes

| Token                | Avant | Après |
| -------------------- | ----: | ----: |
| `'/a-propos'` (button onclick) | 1 |     0 |
| `>À PROPOS<` / `>ABOUT<`       | 1 |     0 |

---

## OD3 — Suppression du breadcrumb flottant

### HTML retiré

```html
<nav class="breadcrumb-nav" aria-label="Navigation">
  <a href="/portail" class="breadcrumb-link" target="_self"
     onclick="this.href='/portail?_t='+Date.now();">◄ PORTAIL</a>
</nav>
```

### CSS retiré

- `.breadcrumb-nav` (règle complète)
- `.breadcrumb-link` (règle complète)
- `.breadcrumb-link:hover` (règle complète)
- `@media (max-width: 768px)` (règles breadcrumb à l'intérieur)
- `.breadcrumb-nav` retiré du selector `body.embed-mode` (commentaire
  associé mis à jour pour ne plus mentionner le breadcrumb)

### Justification

Le bouton header « ◄ PORTAIL » (OD1) couvre intégralement le rôle de
navigation retour. Deux éléments visuels « retour portail » créent du
bruit. Single-path = clarté.

### Comptes

| Token                  | Avant | Après |
| ---------------------- | ----: | ----: |
| `breadcrumb-nav`       |     2 (HTML + CSS) |     0 |
| `breadcrumb-link`      |     4 (HTML + 3 CSS) |   0 |
| `breadcrumb` (commentaires de trace) |  3 |  2 (commentaires de suppression conservés) |

---

## Validation finale

```
=== service ===                                    active
=== /observatoire HTTP ===                         HTTP/1.1 200 OK

OD1 — back-to-portal-btn (>=2) :                   5   ✓
OD1 — >Déconnexion< / >Disconnect< (=0) :          0   ✓
OD1 — ◄ PORTAIL / ◄ PORTAL (>=1) :                 3   ✓ (HTML + CSS comments)
OD2 — /a-propos dans rendu (=0) :                  0   ✓
OD3 — breadcrumb-nav OR breadcrumb-link (=0) :     0   ✓
=== /portail sidebar (=1) ===                      1   ✓ (préservé)
```

---

## Notes visuelles — Single-path navigation

Avant :
```
  ┌─ Header                                                       ┐
  │ [logo]    [refresh] [Déconnexion]<rouge>          [breadcrumb]│
  └────────────────────────────────────────────────────────────────┘
  ┌─ Tabs                                                         ┐
  │ [tel] [iss] [...] [LAB]                       [ℹ À PROPOS]   │
  └────────────────────────────────────────────────────────────────┘
```

Après :
```
  ┌─ Header                                                       ┐
  │ [logo]    [refresh] [◄ PORTAIL]<cyan>                        │
  └────────────────────────────────────────────────────────────────┘
  ┌─ Tabs                                                         ┐
  │ [tel] [iss] [...] [LAB]                                       │
  └────────────────────────────────────────────────────────────────┘
```

- **Une seule** entrée « retour portail » : le bouton header.
- **Une seule** entrée « À propos » : dans le sidebar gauche.
- Aucun élément flottant superposé au titre ou aux widgets.
- Cohérence chromatique totale : tout est cyan calme — plus de rouge
  qui hurle « incident » sur une simple navigation.

---

## Hors-scope (Phases ultérieures éventuelles)

- Compactage vertical des cards observatoire (équivalent D2/D3 du portail)
- Audit homogénéité couleurs résiduelles `#0CC` / `#7ddcff` / `#aabbcc`
- Restructuration sidebar AEGIS chat
- Audit cohérence visuelle inter-onglets

---

**Phase O-D : DONE — navigation propre, single-path, identité chromatique unifiée.**
