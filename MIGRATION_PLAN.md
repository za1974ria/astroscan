# MIGRATION PLAN — ASTRO-SCAN PHASE 2C
**Date PASS 0 :** 2026-05-03  
**Objectif :** Migration totale station_web.py → Blueprints + create_app + bascule wsgi

---

## 1. INVENTAIRE EXACT (chiffres réels)

### Monolithe station_web.py
| Métrique | Valeur |
|----------|--------|
| Lignes totales | 11 657 (après PASS 4) |
| `@app.route` actifs | **198** |
| `# @app.route` commentés (migrés) | 38 |
| Total occurrences `@app.route` | 236 |

### Blueprints actifs en production (via station_web)
| Blueprint | Module | Routes |
|-----------|--------|--------|
| seo_bp | app/blueprints/seo/routes.py | 3 |
| apod_bp | app/blueprints/apod/routes.py | 3 |
| sdr_bp | app/blueprints/sdr/routes.py | 4 |
| iss_bp | app/blueprints/iss/routes.py | 5 |
| i18n_bp | app/blueprints/i18n/__init__.py | 1 |
| api_bp | app/blueprints/api/__init__.py | 13 |
| pages_bp | app/blueprints/pages/__init__.py | 3 |
| main_bp | app/blueprints/main/__init__.py | 6 |
| system_bp | app/blueprints/system/__init__.py | 19 (+11 PASS 4) |
| analytics_bp | app/blueprints/analytics/__init__.py | 6 |
| export_bp | app/blueprints/export/__init__.py | 5 (+2 PASS 4) |
| **TOTAL MIGRÉ** | | **69 routes** |

> **Note PASS 4 :** export_bp enregistré (était créé mais non enregistré). system_bp +11 routes (health, selftest, tle/refresh, latest, sync/state, telescope/sources, accuracy/export.csv, api/health, status, stream/status).  
> **⚠️ RESTART REQUIS** : `sudo systemctl restart astroscan` — modifications en attente de reload Gunicorn.

### Progression
- Routes migrées : **69 / 269** ≈ **26%**
- Routes restantes dans monolithe : **198 actives** (−15 vs PASS 3)

---

## 2. BLOCAGES IDENTIFIÉS (actions requises par l'utilisateur)

### 🔴 CRITIQUE — Permissions système
Le shell zakaria n'a PAS les droits d'écriture sur /root/astro_scan (tout est root:root).  
**Commandes à lancer MAINTENANT :**

```bash
# Fix permissions projet (écriture pour zakaria)
! sudo chmod g+w /root/astro_scan
! sudo find /root/astro_scan -type d -exec chmod g+w {} \;
! sudo find /root/astro_scan -type f -exec chmod g+w {} \;
! sudo chgrp -R zakaria /root/astro_scan

# Créer répertoire backup
! sudo mkdir -p /root/backups/migration
! sudo chmod 777 /root/backups/migration

# Fix permissions git pour créer branches
! sudo chgrp -R zakaria /root/astro_scan/.git
! sudo chmod -R g+w /root/astro_scan/.git

# Créer branche migration
! sudo git -C /root/astro_scan checkout -b migration/phase-2c
```

### 🟡 MOYEN — TODO pages /landing (voir /tmp/pages_init_patched_TODO.md)
pages_bp /landing ne passe pas seo_title/seo_description → route toujours dans station_web  
Fix : ajouter ces params dans app/blueprints/pages/__init__.py → PASS 3

### 🟡 MOYEN — create_app manque 5 blueprints
app/__init__.py : enregistre seo, i18n, export, main, api, pages (6)  
Manquants : analytics, apod, sdr, iss, system → à synchroniser en PASS 15

---

## 3. LISTE COMPLÈTE DES 213 ROUTES MONOLITHE (groupées par domaine)

### [A] Export CSV/JSON (5 routes) — L2198–2314
```
L2198  GET  /api/export/visitors.csv
L2226  GET  /api/export/visitors.json
L2263  GET  /api/export/ephemerides.json
L2286  GET  /api/export/observations.json
L2314  GET  /api/export/apod-history.json
```
→ export_bp couvre 3/5 (visitors.csv, visitors.json, observations.json)
→ Reste : ephemerides.json, apod-history.json → PASS 4

### [B] Health/System simple (3 routes) — L2535–2648
```
L2535  GET   /health
L2610  GET   /selftest
L2648  POST  /api/tle/refresh
```
→ system_bp → PASS 4

### [C] Pages principales (8 routes) — L2672–3322
```
L2672  GET  /
L2680  GET  /portail
L2689  GET  /landing
L2699  GET  /technical
L2704  GET  /dashboard
L3292  GET  /overlord_live
L3296  GET  /galerie
L3322  GET  /observatoire
```
→ pages_bp + main_bp → PASS 5

### [D] Analytics/Vision pages (3 routes) — L3153–3348
```
L3153  GET  /analytics
L3337  GET  /vision-2026
L3348  GET  /telemetrie-sondes
```
→ analytics_bp / pages_bp → PASS 5

### [E] Sky Camera (3 routes) — L3354–3456
```
L3354  GET   /sky-camera
L3360  POST  /api/sky-camera/analyze
L3456  GET   /api/sky-camera/simulate
```
→ nouveau bp skycam_bp → PASS 14

### [F] Probes/Sondes (2 routes) — L3487–7150
```
L3487  GET  /api/sondes/live
L7150  GET  /api/sondes
```
→ PASS 14

### [G] API System (4 routes) — L3635–3813
```
L3635  GET   /api/latest
L3797  GET   /api/sync/state
L3802  POST  /api/sync/state
L3813  GET   /api/telescope/sources
```
→ system_bp → PASS 4

### [H] Observatory/Telescope (16 routes) — L3827–10267
```
L3827   GET   /api/observatory/status
L3838   GET   /observatory/status
L3850   GET   /api/telescope/live
L3946   GET   /api/image
L4002   GET   /api/title
L5074   GET   /api/telescope-hub
L6791   GET   /api/telescope/nightly
L6806   POST  /api/telescope/trigger-nightly
L6815   GET   /telescope_live/<path:filename>
L7691   GET   /telescopes
L10122  GET   /telescope
L10128  GET   /api/telescope/image
L10136  GET   /api/telescope/catalogue
L10146  GET   /api/telescope/proxy-image
L10220  GET   /api/telescope/stream
L10255  GET   /api/telescope/status
L10267  GET   /api/stellarium
```
→ nouveau bp telescope_bp → PASS 9

### [I] ISS étendu (9 routes) — L4148–10194
```
L4148   GET   /api/iss
L4318   GET   /api/passages-iss
L8266   GET   /api/iss/ground-track
L8277   GET   /api/iss/orbit
L8330   GET   /api/iss/crew
L8351   GET   /api/iss/passes
L8362   GET   /api/iss/passes/<float:lat>/<float:lon>
L8479   GET   /api/iss-passes
L10194  GET   /api/iss/stream
```
→ iss_bp (étendre) → PASS 6

### [J] Accuracy (1 route) — L4176
```
L4176  GET  /api/accuracy/export.csv
```
→ export_bp → PASS 4

### [K] Satellite/TLE (4 routes) — L4218–9532
```
L4218   GET   /api/satellite/<name>
L9423   GET   /api/satellites/tle
L9459   GET   /api/satellites/tle/debug
L9532   GET   /api/satellite/passes
```
→ api_bp ou nouveau satellites_bp → PASS 6

### [L] Space Weather/Aurores (13 routes) — L4293–9985
```
L4293   GET  /api/meteo-spatiale
L4313   GET  /meteo-spatiale
L5735   GET  /aurores
L5740   GET  /api/aurore
L6081   GET  /api/aurores
L6905   GET  /api/v1/solar-weather
L8003   GET  /api/nasa/solar
L8014   GET  /api/alerts/asteroids
L8020   GET  /api/alerts/solar
L8026   GET  /api/alerts/all
L8458   GET  /api/space-weather/alerts
L9962   GET  /api/space-weather
L9985   GET  /space-weather
```
→ nouveau bp spaceweather_bp → PASS 7

### [M] Voyager/Feeds (8 routes) — L4396–7175
```
L4396  GET  /api/voyager-live
L7114  GET  /api/feeds/voyager
L7129  GET  /api/feeds/neo
L7134  GET  /api/feeds/solar
L7139  GET  /api/feeds/solar_alerts
L7145  GET  /api/feeds/mars
L7163  GET  /api/feeds/apod_hd
L7175  GET  /api/feeds/all
```
→ nouveau bp feeds_bp → PASS 13

### [N] Chat/AI/Aegis (7 routes) — L4772–5060
```
L4772  POST  /api/chat
L4852  POST  /api/aegis/chat
L4957  GET   /api/aegis/status
L5003  GET   /api/aegis/groq-ping
L5036  GET   /api/aegis/claude-test
L5052  POST  /api/translate
L5060  POST  /api/astro/explain
```
→ nouveau bp ai_bp → PASS 11

### [O] Shield/Classification/MAST (3 routes) — L5100–5149
```
L5100  GET  /api/shield
L5112  GET  /api/classification/stats
L5129  GET  /api/mast/targets
```
→ system_bp ou nouveau bp → PASS 14

### [P] SkyView (4 routes) — L5194–5214
```
L5194  GET   /api/skyview/targets
L5198  POST  /api/skyview/fetch
L5209  GET   /api/skyview/multiwave/<target_id>
L5214  GET   /api/skyview/list
```
→ nouveau bp skyview_bp → PASS 14

### [Q] PWA (3 routes) — L5224–5253
```
L5224  GET   /sw.js
L5234  GET   /manifest.json
L5253  POST  /api/push/subscribe
```
→ main_bp → PASS 5

### [R] Static override (1 route) — L5261
```
L5261  GET  /static/<path:filename>
```
→ À évaluer (Flask native) → PASS 5

### [S] Ce Soir (1 route) — L5295
```
L5295  GET  /ce_soir
```
→ pages_bp → PASS 5

### [T] Visitors Live + Audio (2 routes) — L5488–5498
```
L5488  GET  /visiteurs-live
L5498  GET  /api/audio-proxy
```
→ PASS 14

### [U] Guide/Oracle (5 routes) — L5555–5643
```
L5555  GET       /guide-stellaire
L5560  GET       /oracle-cosmique
L5565  POST      /api/oracle-cosmique
L5631  GET,POST  /api/guide-geocode
L5643  POST      /api/guide-stellaire
```
→ nouveau bp guide_bp → PASS 11

### [V] Weather (6 routes) — L5797–6043
```
L5797  GET   /api/weather
L5880  GET   /api/weather/local
L5903  GET   /api/weather/bulletins
L5938  GET   /api/weather/bulletins/latest
L5962  GET   /api/weather/history
L6043  POST  /api/weather/bulletins/save
```
→ nouveau bp weather_bp → PASS 7

### [W] APOD étendu (2 routes) — L6059–7963
```
L6059  GET  /api/apod
L7963  GET  /api/nasa/apod
```
→ apod_bp (étendre) → PASS 8

### [X] API Oracle/Catalog/Tonight/Moon (7 routes) — L6070–6243
```
L6070  POST  /api/oracle
L6092  GET   /api/catalog
L6100  GET   /api/catalog/<obj_id>
L6109  GET   /api/tonight
L6115  GET   /api/moon
L6121  GET   /api/ephemerides/tlemcen
L6243  GET   /api/v1/catalog
```
→ api_bp → PASS 8

### [Y] API v1 (4 routes) — L6136–6917
```
L6136  GET  /api/v1/iss
L6177  GET  /api/v1/planets
L6892  GET  /api/v1/asteroids
L6917  GET  /api/v1/tonight
```
→ api_bp → PASS 8

### [Z] MicroObservatory (3 routes) — L6255–6429
```
L6255  GET  /api/microobservatory
L6419  GET  /api/microobservatory/images
L6429  GET  /api/microobservatory/preview/<nom_fichier>
```
→ PASS 13

### [AA] Lab (13 routes) — L8631–9746
```
L8631  GET        /lab
L8636  POST       /lab/upload
L8677  GET        /lab/images
L8687  GET        /api/lab/images
L8708  GET        /lab/raw/<path:filename>
L8714  GET        /api/lab/metadata/<path:filename>
L8730  POST       /lab/analyze
L8779  GET        /lab/dashboard
L8807  POST       /api/lab/run_analysis
L8838  GET        /api/lab/skyview/sync
L9668  POST       /api/lab/upload
L9697  POST       /api/lab/analyze
L9746  GET        /api/lab/report
```
→ nouveau bp lab_bp → PASS 10

### [AB] Analysis/Research/Archive (10 routes) — L9761–9896
```
L9761  POST      /api/analysis/run
L9777  POST      /api/analysis/compare
L9795  GET       /api/analysis/discoveries
L9811  GET       /research-center
L9817  GET       /api/research/summary
L9828  GET       /api/research/events
L9840  GET       /api/research/logs
L9856  GET,POST  /api/archive/reports
L9875  GET,POST  /api/archive/objects
L9896  GET,POST  /api/archive/discoveries
```
→ nouveau bp research_bp → PASS 10

### [AC] Status/Health étendu (3 routes) — L7191–7572
```
L7191  GET  /api/health
L7563  GET  /status
L7572  GET  /stream/status
```
→ system_bp → PASS 4

### [AD] Live APIs (5 routes) — L8036–8468
```
L8036  GET  /api/live/spacex
L8071  GET  /api/live/news
L8081  GET  /api/live/mars-weather
L8087  GET  /api/live/iss-passes
L8468  GET  /api/live/all
```
→ nouveau bp live_bp → PASS 13

### [AE] Space Science (8 routes) — L7691–7992
```
L7691  GET   /telescopes
L7863  GET   /api/hubble/images
L7872  GET   /api/mars/weather
L7885  GET   /api/bepi/telemetry
L7908  GET   /api/jwst/images
L7920  POST  /api/jwst/refresh
L7932  GET   /api/neo
L7992  GET   /api/nasa/neo
```
→ PASS 13

### [AF] Globe/Survol (2 routes) — L8544–8551
```
L8544  GET  /globe
L8551  GET  /api/survol
```
→ PASS 14

### [AG] Pages supplémentaires (8 routes) — L9598–10183
```
L9598   GET  /research
L9604   GET  /space
L9609   GET  /space-intelligence
L9614   GET  /module/<name>
L9925   GET  /demo
L10096  GET  /space-intelligence-page
L10182  GET  /aladin
L10183  GET  /carte-du-ciel
```
→ pages_bp → PASS 5

### [AH] Orbits/Science/Missions (4 routes) — L9931–10067
```
L9931   GET       /api/orbits/live
L9994   POST      /api/science/analyze-image
L10024  GET       /api/missions/overview
L10067  GET,POST  /api/space/intelligence
```
→ PASS 13

### [AI] Visitors/Analytics étendu (11 routes) — L10283–10910
```
L10283  POST    /api/owner-ips
L10307  DELETE  /api/owner-ips/<int:ip_id>
L10327  POST    /api/visitor/score-update
L10363  GET     /api/analytics/summary
L10441  GET     /api/visitors/globe-data
L10457  GET     /api/visitors/stream
L10495  POST    /api/visitors/log
L10506  GET     /api/visitors/geo
L10582  GET     /api/visitors/stats
L10629  GET     /api/visitors/connection_time
L10910  POST    /track-time
```
→ analytics_bp (étendre) → PASS 12

### [AJ] Hilal (2 routes) — L11363–11378
```
L11363  GET  /api/hilal/calendar
L11378  GET  /api/hilal
```
→ PASS 14

### [AK] Météo réelle + Control + Meteo page (4 routes) — L11403–11437
```
L11403  GET  /api/meteo/reel
L11429  GET  /meteo-reel
L11436  GET  /control
L11437  GET  /meteo
```
→ weather_bp → PASS 7

### [AL] SEO/Infra/Geo (7 routes) — L10106–11687
```
L10106  GET  /favicon.ico
L11514  GET  /ephemerides
L11528  GET  /sitemap.xml
L11567  GET  /robots.txt
L11572  GET  /europe-live
L11577  GET  /flight-radar
L11687  GET  /proxy-cam/<city>.jpg
```
→ seo_bp + main_bp → PASS 5/8

### [AM] Contact/Flights (2 routes) — L11741–11777
```
L11741  POST  /contact
L11777  GET   /api/flights
```
→ PASS 14

### [AN] DSN (1 route) — L8510
```
L8510  GET  /api/dsn
```
→ PASS 14

### [AO] Mission Control (2 routes) — L6825–6830
```
L6825  GET  /mission-control
L6830  GET  /api/mission-control
```
→ PASS 9

### [AP] Astro Object + News (2 routes) — L6840–6851
```
L6840  GET,POST  /api/astro/object
L6851  GET       /api/news
```
→ api_bp → PASS 8

---

## 4. PLAN D'ORDRE DE MIGRATION

| Pass | Label | Domaines | Routes | Cible BP |
|------|-------|----------|--------|---------|
| **1** | B-cache | Infra cache | 0 (refactoring) | app/utils/cache.py |
| **2** | B-db | Infra db | 0 (refactoring) | app/utils/db.py |
| **3** | B-config | Config + fix landing | 1 (fix) | app/config.py |
| **4** | Export+Health | A, B, G, J, AC | 17 | export_bp, system_bp |
| **5** | Pages+PWA | C, D, Q, R, S, AG, AL | 25 | pages_bp, main_bp, seo_bp |
| **6** | ISS+Satellite | I, K | 13 | iss_bp, satellites_bp |
| **7** | Weather | L, V, AK | 23 | weather_bp, spaceweather_bp |
| **8** | APOD+APIv1 | W, X, Y, AP | 15 | apod_bp, api_bp |
| **9** | Telescope | H, AO | 18 | telescope_bp |
| **10** | Lab+Research | AA, AB | 23 | lab_bp, research_bp |
| **11** | AI+Guide | N, U | 12 | ai_bp, guide_bp |
| **12** | Visitors | AI | 11 | analytics_bp |
| **13** | Feeds+Live+Science | M, AD, AE, AH, Z | 26 | feeds_bp, live_bp |
| **14** | Résiduel | E, F, O, P, T, AF, AJ, AM, AN | 18 | divers |
| **15** | create_app sync | Synchroniser factory | — | app/__init__.py |
| **16** | Bascule wsgi | wsgi → create_app | — | wsgi.py |
| | **TOTAL** | | **~206** | |

---

## 5. CRITÈRES VALIDATION PAR PASS (11 endpoints obligatoires)

```bash
for url in \
  "https://astroscan.space/" \
  "https://astroscan.space/api/iss" \
  "https://astroscan.space/api/health" \
  "https://astroscan.space/portail" \
  "https://astroscan.space/dashboard" \
  "https://astroscan.space/api/apod" \
  "https://astroscan.space/sitemap.xml" \
  "https://astroscan.space/robots.txt" \
  "https://astroscan.space/api/weather" \
  "https://astroscan.space/api/satellites" \
  "https://astroscan.space/api/system-status"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  echo "$code $url"
done
```

**Rollback immédiat si un endpoint != 200 :**
```bash
cp /root/backups/migration/station_web_TIMESTAMP.py /root/astro_scan/station_web.py
systemctl restart astroscan && sleep 15 && curl -I https://astroscan.space/
```

---

*PASS 0 — 2026-05-03 — Audit complet terminé*  
*PASS 1-3 — 2026-05-03 — Infra cache/db/config + 56 routes BP*  
*PASS 4 — 2026-05-03 — Export+Health : +13 routes (export_bp +2, system_bp +11), enregistrement export_bp, station_web −127 lignes — RESTART ROOT REQUIS*
