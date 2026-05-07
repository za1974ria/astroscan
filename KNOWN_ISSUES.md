# ASTRO-SCAN — Bugs connus & limitations à traiter ultérieurement

Date : 2026-05-07

---

## Issues UI

### #1 — Sidebar fantôme apparente sur /portail
**Statut** : Cache navigateur soupçonné (non reproductible côté serveur)
**Reproduction observée** : observatoire → ◄ PORTAIL en mode normal Chrome
**Vérification serveur** : HTML servi par /portail = PROPRE
- 1 seule `<div class="sidebar">` ✓
- 1 seul `<div class="topbar">` ✓
- 1 seule marque cliquable ✓
- 0 duplication HTML
- 0 cycle iframe
**Fixes appliqués (sans résoudre côté navigateur normal)** :
- Phase O-C : cache-bust `onclick="this.href='/portail?_t='+Date.now()"` (commit 1a53e9d)
- Phase O-D : `?embed=1` sur iframe + CSS `body.embed-mode` (commit 864937f)
**Workaround utilisateur** : Ctrl+Shift+R (hard refresh)
**Action différée** : Si reproduit en navigation privée Chrome, investiguer extensions/OS/cookie. Sinon non-bloquant.

---

### #2 — Vide central dans observatoire
**Statut** : Esthétique — non bloquant fonctionnellement
**Description** : Espace noir entre image APOD et bloc suivant, sur la zone scrollée
**Plan futur** : Phase O-E "Habiter le vide" — widget `visibility_score` hyperlocal Tlemcen
**Lien stratégique** : Préfigure le Chemin B (donnée unique scientifique pour validation CRAAG)

---

### #3 — WebSocket /ws/view-sync : erreurs console répétées
**Statut** : Bruit console — non bloquant
**Cause probable** : Routes Sock-WS définies dans station_web.py:3853 mais non démarrées via gunicorn worker config, OU non exposées via nginx upstream
**Fonctionnement actuel** : Le widget VUE MASTER affiche STATION SOLO en cyan dim (Phase O-B FIX 2 OK)
**Action différée** : Configurer nginx WS upstream OU désactiver le client si la sync multi-observateurs n'est pas un priorité

---

## Architecture

### #4 — Phase 2C migration Blueprint en cours
**Progression** : 56/213 routes migrées (~21%)
**Phases livrées** : 2A (4 bugs fixés), 2B (8 Blueprints actifs en prod)
**Reste** : Pass 4+ (Export+Health, 17 routes), domaines restants
**Action différée** : Reprendre après stabilisation visuelle complète + livraison Chemin B

---

## Notes

Ces issues sont **archivées volontairement** pour permettre la concentration sur les priorités stratégiques :
1. Embellissement visuel des modules (ITS, Carte Orbitale, À PROPOS, etc.)
2. Création donnée unique (Chemin B — visibility_score Tlemcen)
3. Validation scientifique (CRAAG, AstroPy, laboratoires Maghreb)

La perfection est l'ennemi du livrable. — Zakaria Chohra, 2026
