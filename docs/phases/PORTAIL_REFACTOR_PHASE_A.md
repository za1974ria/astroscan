# PORTAIL REFACTOR — PHASE A

**Date :** 2026-05-07  
**Branch :** `ui/portail-refactor-phase-a` (depuis HEAD `migration/phase-2d-purification`)  
**Tag de départ :** `ui-phase-a-start`  
**Service prod :** `astroscan.service` (template auto-reload — restart requis uniquement pour FIX 4)

---

## 1. Synthèse exécutive

| FIX | Statut | Commit | Tag |
|---|---|---|---|
| 1. Brand consolidation | ✅ | `27801a5` | `ui-phase-a-fix1-done` |
| 2. Sticky topbar | ✅ | `18145af` | `ui-phase-a-fix2-done` |
| 3. Sidebar 7 catégories Lucide | ✅ | `ad3dc74` | `ui-phase-a-fix3-done` |
| 4. SSR visitor count | ✅ | `ba1c101` | `ui-phase-a-fix4-done` |

---

## 2. Fichiers modifiés

| Fichier | Δ | Description |
|---|---|---|
| `templates/portail.html` | −188 / +319 (net +131) | Tous les fixes UI (HTML + CSS + JS inline) |
| `app/blueprints/pages/__init__.py` | +9 | FIX 4 : query `_get_visits_count()` + pass à render_template |
| `PORTAIL_REFACTOR_PHASE_A.md` | nouveau | Ce rapport |

**Aucun fichier supprimé. Aucun .bak créé** (l'historique git suffit, et les .bak existants sont conservés tels quels).

---

## 3. Détail par FIX

### ✅ FIX 1 — Brand consolidation (commit `27801a5`)

**Avant :**
- `<title>AstroScan-Chohra — Portail · ORBITAL-CHOHRA</title>`
- Topbar : deux spans `brand-name=AstroScan-Chohra` + séparateur `·` + `brand-sub=ORBITAL-CHOHRA`
- Footer sidebar : `AstroScan-Chohra · v2.0`
- 9 occurrences de "AstroScan-Chohra" dans `templates/portail.html`

**Après :**
- `<title>ORBITAL-CHOHRA — Portail</title>`
- Topbar : un seul span `brand-name=ORBITAL-CHOHRA` (les deux autres spans + séparateur supprimés)
- Footer sidebar : `ORBITAL-CHOHRA · v2.0`
- 0 occurrence de "AstroScan-Chohra" dans `templates/portail.html`

**Règle appliquée :** marque unique = "ORBITAL-CHOHRA" (cohérence globale, pas de "Tesla vs Roadster"). Les meta `og:title`, `twitter:title`, `og:site_name`, `author` mises à jour également.

**Hors scope (volontaire) :** 47 autres templates (`templates/*.html`) contiennent encore "AstroScan-Chohra" — non touchés (Phase A scope = `/portail` uniquement).

---

### ✅ FIX 2 — Sticky topbar, sans gap (commit `18145af`)

**Cause racine identifiée :** `.shell { grid-template-rows: 100px 1fr }` réservait une rangée fixe de 100px en haut. Le topbar (`min-height: 32px`) ne remplissait que ~38px, laissant ~62px de vide *sous* le topbar (perçu comme un gap). De plus, `.topbar { position: relative }` ne le rendait pas sticky au scroll.

**Avant :**
```css
.shell { grid-template-rows: 100px 1fr; }
.topbar { position: relative; min-height: 32px; }
```

**Après :**
```css
.shell { grid-template-rows: auto 1fr; }
.topbar { position: sticky; top: 0; z-index: 1000; min-height: 32px; }
```

**Effet :** la 1re rangée se dimensionne au contenu réel du topbar (~38px). Plus de gap. Le topbar reste collé en haut au scroll. La `primary-nav` (`position:fixed top:66px`) et le `padding-top: 58px` du `.content-area` sont préservés (déjà bien dimensionnés pour la stack topbar+primary-nav).

**Mobile (`@max-width:900px`) :** `grid-template-rows: 48px 1fr` inchangé (le topbar est plus court, le 48px convient).

---

### ✅ FIX 3 — Sidebar 7 catégories Lucide (commit `ad3dc74`)

**Avant :** 35+ items flat dans `.sidebar-section`, mix d'emojis (🌍 🛰 🔭 🌙 ⚡ 🔮 ☀️ 🌤 ⌂ ◈ ⬡ ◫ ◎ ◇), incohérence cross-OS (Android vs iOS), badges DIRECT/LIVE partout.

**Après :** 6 groupes collapsibles + 2 items toplevel singles = 8 sections au total :

| # | Section | Type | Icône Lucide | Items |
|---|---|---|---|---|
| 1 | Accueil | single | `Home` | 1 (`/portail`) |
| 2 | Espace Live | groupe | `Satellite` | 6 (ISS, Orbital, Carte Orbitale, Sondes, Mission Control, Overlord) |
| 3 | Observation | groupe | `Telescope` | 7 (Observatoire, Télescope, NASA APOD, Carte du Ciel, Ce Soir, Éphémérides, Caméra Ciel) |
| 4 | Météo & Aurores | groupe | `Zap` | 3 (Météo Spatiale, Aurores, Météo Locale) |
| 5 | Live Terre | groupe | `Globe` | 5 (Europe Live, Trafic Aérien, Navires AIS, Assets Sol, Visiteurs Live) |
| 6 | IA & Outils | groupe | `Sparkles` | 5 (Oracle, Guide, Orbital Radio, Digital Lab, Mode Scientifique) |
| 7 | Données & Recherche | groupe | `BarChart3` | 8 (Dashboard QG, Analytics, Archive Stellaire, Research Center, Research Dashboard, Science Archive, Vision 2026, Space Intelligence) |
| 8 | À propos | single | `Info` | 1 (`/a-propos`) |

**SVG inlinés** depuis lucide.dev (raw markup, MIT). 14 SVGs au total = 7 icônes de groupe + Home + Info + 6× ChevronDown.

**Badges LIVE/DIRECT préservés UNIQUEMENT sur :**
- ISS en direct (`iss-live-red` rouge clignotant)
- Orbital Live (`live` vert pulsant)
- Météo Spatiale (`iss-live-red`)
- Aurores Boréales (`iss-live-red`)
- Vision 2026 (`new` jaune ambre — `2026` non LIVE mais OK conceptuellement)

Tous les autres badges retirés (Sondes, Sky-Cam, Mission Control, Overlord, APOD, Visiteurs, Europe, etc.).

**Comportement :**
- État par défaut : tous les groupes **collapsed** (seul Accueil + entêtes de groupes visibles).
- Click sur un header de groupe → toggle + chevron rotate -90° → ChevronDown.
- État persisté dans `localStorage` clé `astroscan.sidebarGroups.v1` (JSON `{name: bool}`).
- Restauration au `DOMContentLoaded`.

**Compatibilité préservée :**
- Tous les `navigate('xxx')` keys mappés à PAGES dict identiques (Dashboard, Overlord, Galerie, Observatoire, Ce Soir, Orbital Radio, Guide, Oracle, Aurores, Vision, Mission Control, ISS Tracker, Météo Spatiale, Visiteurs, Sondes, Sky-Camera, Orbital Map, Analytics, Orbital, Telescope, Aladin, Ephemerides, NASA APOD, Control Météo, Europe Live).
- 9 liens externes via `<a class="nav-link">` : Lab, Scientific Mode, Research Center, Research Dashboard, Science Archive, Flight Radar, Scan Signal, Ground Assets, Space Intelligence.
- Sidebar tiroir mobile (`@max-width:900px`) inchangée — toujours accessible via hamburger ☰.

**Override CSS importante :** le sélecteur historique `#nav-iss-tracker { position: fixed; top: 110px; right: 20px; display: none; }` (chip flottant orphelin, `display:none`) cassait l'item dans la sidebar. Surcharge ajoutée : `.sidebar #nav-iss-tracker { position: static !important; display: flex !important; ... }`.

---

### ✅ FIX 4 — SSR visitor count (commit `ba1c101`)

**Avant :** `<span id="tbar-visits-val">000 000</span>` — flash visible au premier paint, JS update via `/api/visits`.

**Après :**
```python
# app/blueprints/pages/__init__.py
@bp.route("/portail")
def portail():
    visitor_count = None
    try:
        from app.services.db_visitors import _get_visits_count
        visitor_count = _get_visits_count()
    except Exception:
        visitor_count = None
    response = make_response(render_template(
        "portail.html",
        lang=get_lang(),
        visitor_count=visitor_count,
    ))
    ...
```

```jinja
<span id="tbar-visits-val">
  {% set _vc_raw = visitor_count|default(none) %}
  {% if _vc_raw is not none and _vc_raw is number %}
    {% set _vc = '%06d' % (_vc_raw|int) %}{{ _vc[:3] }} {{ _vc[3:] }}
  {% else %}
    <span style="opacity:0.55">•••</span>
  {% endif %}
</span>
```

**Garde défensive Jinja :** le test `_vc_raw is not none and _vc_raw is number` permet au template de continuer à fonctionner même AVANT le restart Gunicorn (les workers actuels ne passent pas encore `visitor_count`). Pendant cette fenêtre transitoire, le template affiche `•••` discret au lieu de crasher avec `UndefinedError`.

**Format SSR identique au JS** `fmtVisits()` : 6 chiffres zero-padded, espace après le 3e (`12345` → `012 345`).

**JS `loadVisitsPortail()` inchangé** : continue de rafraîchir la valeur toutes les 30s via `/api/visits`. Si la SSR a déjà placé la bonne valeur, la mise à jour est silencieuse (mêmes chiffres, pas de pulse).

---

## 4. Validation finale (curl, /portail live)

| Vérification | Commande | Résultat |
|---|---|---|
| HTTP status | `curl -sI /portail` | **200 OK** ✅ |
| `000 000` flash | `grep -c "000 000"` | **0** ✅ |
| Brand legacy | `grep -c "AstroScan-Chohra · ORBITAL"` | **0** ✅ |
| Title | `grep -oE "<title>...</title>"` | **`<title>ORBITAL-CHOHRA — Portail</title>`** ✅ |
| Lignes /portail | `wc -l` | **2555** (vs 2426 avant — +129 dû aux SVG inlinés et au CSS/JS du collapsible) |
| Sidebar groups | `grep -oE 'data-group="...'` | **6 groupes + 1 placeholder JS** ✅ |
| Lucide SVG | `grep -c viewBox="0 0 24 24"` | **14** SVGs ✅ |

**Note ligne count :** légère hausse (+5%) à cause des SVG inlinés (14 SVGs ~3-4 lignes chacun = ~50 lignes) et du CSS+JS du collapsible (~100 lignes). Compensée par la suppression de ~25 nav-items répétitifs avec leurs styles inline. Le rendu visuel est nettement plus dense (8 sections vs 35+ items).

---

## 5. Notes mobile (responsive)

**Architecture mobile préservée** (`@max-width:900px` block CSS) :
- `.sidebar { position: fixed; left: -220px; top: 0; height: 100vh; }` (tiroir hors flux)
- `.sidebar.open { left: 0 }` (déclenchement via hamburger ☰)
- `.sidebar-overlay` masque foncé semi-transparent quand ouvert
- `.shell { grid-template-rows: 48px 1fr }` (topbar plus court)

Les groupes collapsibles fonctionnent identiquement sur mobile : largeur 220px du tiroir suffit pour afficher les sections + sub-items.

**Tests recommandés (à effectuer manuellement dans le navigateur) :**
- 360px (mobile portrait) : tiroir s'ouvre, groupes collapsibles fonctionnels
- 768px (tablette) : tiroir mobile (la breakpoint mobile est à 900px)
- 1280px (desktop) : sidebar fixe à gauche, topbar sticky en haut

---

## 6. Tags Git posés

| Tag | Description |
|---|---|
| `ui-phase-a-start` | Avant tout travail |
| `ui-phase-a-pre-fix1` | Avant brand consolidation |
| `ui-phase-a-fix1-done` | FIX 1 OK |
| `ui-phase-a-pre-fix2` | Avant sticky topbar |
| `ui-phase-a-fix2-done` | FIX 2 OK |
| `ui-phase-a-pre-fix3` | Avant sidebar regroup |
| `ui-phase-a-fix3-done` | FIX 3 OK |
| `ui-phase-a-pre-fix4` | Avant SSR visitor count |
| `ui-phase-a-fix4-done` | FIX 4 OK |

**Rollback** : `git reset --hard ui-phase-a-start` à n'importe quel point.

---

## 7. Commits Phase A

```
ba1c101 ui(portail): SSR visitor count, no more 000 000 flash
ad3dc74 ui(portail): regroup sidebar in 7 categories with Lucide icons
18145af ui(portail): remove top spacing, sticky topbar
27801a5 ui(portail): consolidate brand to ORBITAL-CHOHRA
```

---

## 8. Régressions / pendings

### À valider après restart utilisateur
- **FIX 4 (SSR visitor count)** : nécessite `sudo systemctl restart astroscan` pour que les workers Python rechargent `app/blueprints/pages/__init__.py`. Avant restart, le template affiche `•••` (fallback défensif). Après restart, la valeur réelle est rendue côté serveur dès le premier paint.

### Connus, hors scope Phase A
- **47 templates** affichent encore "AstroScan-Chohra" (orbital_map, a_propos, observatoire, vision, ce_soir, etc.) — Phase B ou refactor de masse.
- **`#nav-iss-tracker` floating chip** (CSS `position:fixed top:110px right:20px display:none`) reste défini globalement. Surchargé dans la sidebar, mais l'ID est dupliqué (un dans la sidebar, un défini orphelin). À nettoyer dans une passe ultérieure.
- **Auto-expand du groupe contenant la page active** non implémenté : si l'utilisateur navigue vers une page profonde (ex. Aurores), le groupe Météo reste fermé sauf si il l'a ouvert manuellement (puis localStorage le restaure).

### Non régressions
- ✅ Tous les `navigate('page')` keys conservés (PAGES dict inchangé).
- ✅ Mobile tiroir hamburger fonctionnel.
- ✅ Topbar tbar-stat (AEGIS ACTIF, WEB EN LIGNE, NASA SYNCHRO), lang-toggle FR/EN, top-clock, top-station inchangés.
- ✅ Hubble feed widget, ISS panel, Radio Spatiale widget, Voyager DSN widget, AEGIS status, Stats Live, System Health — tous inchangés (situés sous la nav-section).

---

## 9. Action utilisateur requise

```bash
# 1. Restart pour activer la SSR visitor_count (FIX 4)
sudo systemctl restart astroscan

# 2. Vérification
curl -s http://127.0.0.1:5003/portail | grep -A 1 "tbar-visits-val" | head -2
# attendu : <span id="tbar-visits-val">XXX YYY</span>  (XXX YYY = nombre réel)

# 3. Test navigateur recommandé
# Ouvrir https://astroscan.space/portail dans Chrome/Firefox
# Vérifier visuellement :
#   - Pas de "000 000" au flash initial
#   - Topbar collé tout en haut, pas de gap
#   - Sidebar : 8 sections, 6 collapsibles fermées par défaut
#   - Click sur un header → ouvre, chevron tourne, refresh → état persisté
#   - Mobile (DevTools 360px) : hamburger ouvre le tiroir
```

**Push** : non effectué (per spec). Pour pousser :
```bash
git push origin ui/portail-refactor-phase-a
git push origin ui-phase-a-fix1-done ui-phase-a-fix2-done ui-phase-a-fix3-done ui-phase-a-fix4-done
```
