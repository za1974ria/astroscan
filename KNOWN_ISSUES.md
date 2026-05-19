# ASTRO-SCAN — Bugs connus & limitations à traiter ultérieurement

Date : 2026-05-07

---

## Issues UI

### #1 — Sidebar fantôme apparente sur /portail
**Statut** : ✅ MITIGÉ — 2026-05-19 (branche ui/bugs-portail-cleanup)
**Reproduction observée** : observatoire → ◄ PORTAIL en mode normal Chrome
**Vérification serveur** : HTML servi par /portail = PROPRE (1 sidebar, 1 topbar, 1 brand, 0 cycle iframe)
**Fixes successifs** :
- Phase O-C : cache-bust `onclick="this.href='/portail?_t='+Date.now()"` (commit 1a53e9d)
- Phase O-D : `?embed=1` sur iframe + CSS `body.embed-mode` (commit 864937f)
- Phase O-E : MutationObserver anti-doublons + CSP préventif
- **2026-05-19** :
  1. Headers serveur stricts `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` + `Pragma: no-cache` + `Expires: 0` sur /portail (override Sprint 1 bfcache)
  2. SW unregister proactif inline en début de body (déregistre tout SW + purge `caches`) — annule l'effet d'un sw.js antérieur ayant pré-caché /portail
  3. Cache name bumpé `astroscan-v190` → `astroscan-v191` (force `activate` → purge anciens caches même chez utilisateurs non-/portail)
  4. Asset versioning `?v={{ config.ASSET_VERSION }}` (timestamp de boot) sur les 3 CSS critiques (design_tokens, components, fixes)
**Workaround restant** : Ctrl+Shift+R reste utile si l'utilisateur a un proxy d'entreprise très agressif (hors de notre contrôle).

---

### #2 — Vide central dans observatoire
**Statut** : Esthétique — non bloquant fonctionnellement
**Description** : Espace noir entre image APOD et bloc suivant, sur la zone scrollée
**Plan futur** : Phase O-E "Habiter le vide" — widget `visibility_score` hyperlocal Tlemcen
**Lien stratégique** : Préfigure le Chemin B (donnée unique scientifique pour validation CRAAG)

---

### #3 — WebSocket /ws/view-sync : erreurs console répétées
**Statut** : ✅ RÉSOLU — 2026-05-19 (branche ui/bugs-portail-cleanup)
**Cause** : Routes Sock-WS définies dans station_web.py:3853 mais non démarrées via gunicorn worker config, ET non exposées via nginx upstream
**Résolution** : Client WS désactivé proprement côté frontend via feature flag `FEATURE_WS_VIEW_SYNC=False` (`app/__init__.py`). Le script `astroscan_view_sync.js` n'est plus chargé sur /observatoire (ni sur /portail via iframe). Commentaire HTML inséré : `<!-- WS view-sync désactivé : voir KNOWN_ISSUES #3 -->`
**État UI conservé** : VUE MASTER affiche STATION SOLO en cyan dim (HUD statique, data-state="open" hard-codé) — pas de régression visuelle.
**Réactivation future** : Configurer nginx WS upstream (proxy_pass + Upgrade headers) + basculer le flag à True.

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


## NASA APOD API timeout depuis Hetzner Hillsboro (2026-05-08)

**Symptôme** : `/api/apod` retourne 502 "circuit ouvert" pendant que NASA api.nasa.gov est inaccessible depuis le serveur Hetzner Hillsboro Oregon US-West.

**Diagnostic** :
- Test direct depuis serveur : `curl https://api.nasa.gov/planetary/apod` → status 000 timeout 15s
- Code APOD fonctionne quand testé directement (`get_nasa_apod()` retourne 1151 chars)
- Circuit breaker `CB_NASA` (failure_threshold=3, recovery_timeout=300s) protège correctement
- Cache local présent et valide :
  - `/root/astro_scan/telescope_live/apod_meta.json` (4.1 KB, daté 2026-05-07)
  - `/root/astro_scan/telescope_live/apod_hd.jpg` (39 MB)

**Cause racine probable** : 
- NASA API rate limit ou maintenance temporaire côté US-West
- Possible soft-ban après séries de retries
- Routing dégradé Hetzner Hillsboro ↔ NASA East Coast à certaines heures

**Workaround actuel** : 
- La page `/apod` (web) répond 200 en utilisant le cache (latence 10s)
- L'API `/api/apod` (JSON) retourne 502 jusqu'au reset CB

**Solution future (mini-PASS prévu)** : 
Implémenter un fallback cache dans la route `/api/apod` :
- Si CB ouvert ou timeout NASA → retourner `apod_meta.json` avec marker `degraded=true`
- Status HTTP 200 (cache valide) au lieu de 502
- Pattern standard "graceful degradation" production-grade

**Priorité** : Moyenne (bug externe, pas critique, cache existe, fallback simple à coder)
**Date détection** : 2026-05-08 ~02h00 UTC
**Branche** : ui/portail-refactor-phase-a (suite PASS 23.3)
