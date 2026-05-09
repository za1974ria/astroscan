# ASTRO-SCAN — Backlog Session 5 mai 2026

## ✅ LIVRÉ AUJOURD'HUI (11 victoires)

### Flight Radar
- [x] OpenSky OAuth2 (10 000+ avions)
- [x] ALGO-7 fiabilité ADS-B (4 axes Bayésien)
- [x] ALGO-7 destination (7 layers Bayésien complet)
- [x] HUD AIRPORT cyan SpaceX (stats trafic 100km)
- [x] Bug fix click-pollution + tooltip + z-index
- [x] Design hybride NASA/SpaceX/Eurocontrol

### Vessel Tracker
- [x] AISStream multi-worker bug fix (Redis distributed lock)
- [x] AISStream singleton opérationnel (1 worker élu, 3 standby)

### Portail
- [x] Header line alignment (48px)
- [x] Grid 3x3 cohérent (+ AEGIS Oracle)
- [x] Jaune ambre adouci
- [x] Hiérarchie visuelle (badges LIVE/ROADMAP/FEATURED)

### Infrastructure
- [x] Cleanup zombies systemd (aegis, web, watchdog maskés)

## 📋 BACKLOG — À ATTAQUER PROCHAINEMENT

### /scan-signal — Premium polish (3 items priorité haute)
- [ ] Trace historique polyline du navire sélectionné (5h+)
- [ ] Header AstroScan-Chohra cohérent avec /portail
- [ ] Reformulations textes HUD :
  - "0/12 ant. en portée" → "Réseau sol — 0 antenne en portée / 12 actives"
  - "SG SIN" → "Singapour 🇸🇬 (SG SIN)" (créer data/ais_ports.json)
  - Différence route fond/cap vrai → "DÉRIVE: XX°"

### /scan-signal — Améliorations secondaires
- [ ] Carte plein écran + HUD overlay (cohérence /flight-radar)
- [ ] Légende couleurs markers (rouge nav / cyan diamant antenne)
- [ ] Plus de navires visibles globalement (clustering fix)
- [ ] Conversions unités (kn ↔ km/h)
- [ ] Format dimensions visuel (183×32 m)
- [ ] Boussole textuelle (237° = SSW)

### Modules à auditer encore
- [ ] /ground-assets
- [ ] /aurores
- [ ] /apod
- [ ] /orbital-radio
- [ ] /analytics

### Investigation système
- [ ] astroscan-feeder.service — utile ou legacy ?
- [ ] astroscan-tunnel.service — tunnel actif ?
- [ ] Backup quotidien — qui le déclenche ? Erreur du 03/05

### Fortification (priorité moyen-long terme)
- [ ] Tests pytest sur ALGO-7 engine (target 70% coverage)
- [ ] Setup Sentry (5 min)
- [ ] Setup Prometheus + Grafana
- [ ] Docker + docker-compose
- [ ] GitHub Actions CI/CD
- [ ] Flask-Talisman + Flask-Limiter (sécu)
- [ ] pip-audit en CI
- [ ] Documentation OpenAPI

### Lancement futur (après fortification)
- [ ] README EN pro
- [ ] ARCHITECTURE.md complet
- [ ] Vidéo démo 7 min
- [ ] Pitch deck SpaceX/NASA-grade
- [ ] Page hommage parents
- [ ] Show HN posté
