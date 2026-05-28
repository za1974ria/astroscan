# ÉTAT DES LIEUX TECHNIQUE — ASTRO-SCAN

**Date du diagnostic :** 2026-05-28
**Hôte :** Hetzner 5.78.153.17 — Linux 6.8.0-110-generic
**Mode :** read-only, aucun service touché, aucun fichier source modifié.

---

## 1. IDENTITÉ & VERSION

| Élément | Valeur |
|---|---|
| Source de vérité coordonnées | `app/constants/observatory.py` |
| Station | Tlemcen, Algérie (DZ) |
| Latitude | 34.8753 °N |
| Longitude | **-1.3167 °W** (négatif, ouest de Greenwich — marqué CRITIQUE dans le code) |
| Altitude | 816 m |
| Timezone | Africa/Algiers (UTC+1, pas de DST) |
| Fichier `VERSION` | absent |
| Versions trouvées via grep | `version="1.0.0"` dans `sentinel/routes.py` (interne API), pas de constante `__version__` |
| Version affichée README | **v2.8.0** (badge → tag `v2.8.0-lighthouse-58pct-ui-clean`) |
| Dernier tag git réel | **v2.7.4-analytics-cockpit** |
| **Incohérence** | Le tag v2.8.0 annoncé par les badges README n'existe PAS dans `git tag` |

**Tags récents (top 10) :**
```
v2.7.4-analytics-cockpit
v2.7.3-a-propos-a11y-fix
v2.7.3-a-propos-email
v2.7.3-perf-nasa-apod-cache
v2.7.3-lazy-cesium-mc
v2.7.2-lighthouse-final
v2.7.1-lighthouse-97
v2.7.0-soiree-historique
v2.7.0-astrobrain-guardian-s1
v2.6.0-pytest-hardening
```

---

## 2. ÉTAT GIT

| Élément | Valeur |
|---|---|
| Branche active | `main` |
| HEAD | `a05d0b41a702e6664312a23d8aa1e05243df5896` |
| Dernier commit | **2026-05-22 23:35 UTC** (il y a 6 jours) |
| Branches locales | 25 |
| Branches remote | 14 |
| Fichiers modifiés non commités | **10** (M) + **1** supprimé (D) |
| Fichiers non trackés | **~40** dont 30+ `.bak-*` récents (dates 2026-05-21 à 2026-05-23) |
| Dossiers non trackés majeurs | `app/services/control_tower/`, `modules/telescope_bridge/`, `telescope_bridge_agent/`, `audit/{guardian,health,purify,sentinel}/`, plusieurs scripts |

**Modifs M sur main (non commitées) :**
```
app/__init__.py
app/blueprints/api/__init__.py
app/blueprints/cameras/__init__.py
app/blueprints/guardian/agent.py
app/blueprints/health/__init__.py
app/hooks.py
config/guardian_rules.yaml
templates/europe_live.html
wsgi.py
```

**15 derniers commits :**
```
a05d0b4 feat(analytics): refonte cockpit Mission Control · Visitors Analytics
87933bd fix(a-propos): restore a11y 100/100 — increase mailto tap target size
96a27d8 feat(a-propos): add personal email zakaria.chohra@gmail.com
86ccec3 perf(nasa-apod): cache 24h + sized images + preload API
3e77af6 perf(mission-control): lazy-load Cesium.js via IntersectionObserver
d3f1049 Merge PR #10 from fix/skip-flaky-concurrency-test
31a5e38 test(astrobrain): skip flaky test_concurrent_record_usage_no_lost_updates
da977b4 Merge PR #9 from perf/minify-js-css
cbca4da perf(ground_assets): minify JS+CSS via terser+clean-css
b436f13 Merge PR #8 from perf/defer-scripts-preconnect
f77d446 perf(ground_assets): self-host Leaflet + defer scripts (Lighthouse 86→97)
7fb00be Merge PR #7 from fix/perf-lighthouse-and-flaky-test
0d12061 perf(ground_assets) + fix(test): content-visibility CLS + de-flake rate_limit
98443b3 Merge PR #6 from fix/ground-assets-station-cards-css
f57335a fix(ground_assets): remove inline cls-fix v2/v3/v4 that broke right-pane layout
```

---

## 3. ARCHITECTURE

| Métrique | Valeur |
|---|---|
| Pattern | `create_app()` factory dans `app/__init__.py:29` |
| Blueprints | **32** |
| **Routes totales** | **831** |
| Services | **31** modules `.py` (hors `.bak`) |
| LOC Python total (sous `app/`) | **30 460 lignes** |
| Sous-dossiers app/ | `blueprints/`, `services/`, `constants/`, `core/`, `routes/`, `utils/`, `workers/` |

**Distribution routes par blueprint (top 12) :**

| Blueprint | Routes |
|---|---|
| api | 111 |
| weather | 102 |
| sentinel | 96 |
| ai | 66 |
| analytics | 58 |
| health | 52 |
| pages | 52 |
| cameras | 45 |
| feeds | 31 |
| system | 31 |
| scan_signal | 30 |
| telescope | 16 |

**Liste complète blueprints (32) :** ai, analytics, api, apod, archive, astro, astrobrain, cameras, export, feeds, flight_radar, ground_assets, guardian, health, hilal, i18n, iss, lab, main, maintenance, nasa_proxy, pages, research, satellites, scan_signal, sdr, sentinel, seo, system, telescope, version, weather.

---

## 4. TESTS

| Métrique | Valeur |
|---|---|
| Fichiers de tests | **35** |
| Répartition | `unit/` (24), `smoke/` (7), `integration/` (4) |
| Résultat `pytest -q` | **479 passed, 124 skipped** en **16.7 s** |
| Échecs | **0** |
| Coverage local | **non mesuré** dans cette passe (gate CI = 20%, README annonce 25% → cible ≥60%) |

Aucun test ne casse. Le taux de skip (124/603 ≈ 20.5%) est élevé — concentré sur `integration/test_guardian_routes` (11), `smoke/test_legacy_*` (62), `smoke/test_critical_endpoints` (15).

---

## 5. CI/CD

| Élément | Valeur |
|---|---|
| Workflows | **1** : `.github/workflows/test.yml` |
| Déclencheurs | push sur `main`, `ci/**`, `migration/phase-2c` ; PR sur `main`, `migration/phase-2c` |
| Jobs | `lint` (ruff check + format), `test` (matrice py 3.11 + 3.12), `coverage` (py 3.12, gate `--cov-fail-under=20`) |
| Concurrency | annule les runs en cours sur même branche |
| Artefacts | `coverage-xml-py3.12`, `coverage-html-py3.12` (30 j) |
| Codecov | présent en commentaire, **non activé** (CODECOV_TOKEN manquant) |
| Badges README | License, Python 3.10+, Status live, Version **v2.8.0** (orphelin), Lighthouse, A11y, CI, Coverage |

---

## 6. RUNTIME & SYSTÈME

| Élément | Valeur |
|---|---|
| Python | **3.12.3** |
| Gunicorn binaire | `/usr/bin/gunicorn` v25.1.0 (CLI), **v20.1.0** chargé en venv (pip show) |
| Service systemd | `astroscan.service` — actif depuis 2026-05-28 14:17 UTC (**6 h**) |
| User | `astroscan`, WorkingDir `/opt/astroscan` |
| Workers / threads | **4 workers × 4 threads** (timeout 120 s, max-requests 1000+jitter 50) |
| Drop-ins | `env.conf`, `hardening.conf`, `limits.conf` |
| Bind | `127.0.0.1:5003` (nginx en reverse-proxy) |
| RAM service | **893.8 Mo** (peak 975 Mo) |
| Tasks | 63 |
| CPU cumulé | 57 min 15 s |
| Disque `/` | **104 G / 150 G — 73%** (41 G libres) |
| RAM système | 7.6 Gi total, 2.4 Gi utilisée, **5.2 Gi disponible** |
| Swap | 2.0 Gi, 340 Mi utilisés |

---

## 7. DÉPENDANCES

**`requirements.txt` (production, 33 lignes utiles) :**

| Lib | Version pinnée | Catégorie |
|---|---|---|
| Flask | 3.1.3 | core |
| Werkzeug | 3.1.6 | core |
| Jinja2 | 3.1.6 | core |
| numpy | 2.4.3 | scientifique |
| skyfield | >=1.46,<2 (installé 1.54) | astro |
| astropy | >=5.0,<8 (installé 7.2.0) | astro |
| sgp4 | >=2.21,<3 (installé 2.25) | satellites |
| pydantic | 2.12.5 | validation |
| httpx | 0.28.1 | http |
| requests | 2.32.5 | http |
| redis | >=5.0,<6 | cache |
| sentry-sdk | 2.58.0 | observabilité |
| openai | >=1.50,<2 | LLM (axe Astro Brain) |
| groq | 1.1.1 | LLM |
| tenacity | >=8,<10 | retry |
| flask-sock | 0.7.0 | websocket |

**`requirements-dev.txt` :** pytest>=7,<9, pytest-cov, pytest-mock — uniquement CI/CD.

**Paquets outdated : 107**. Échantillon notable :

| Paquet | Installé | Dernier |
|---|---|---|
| **gunicorn** | **20.1.0** | **26.0.0** (4 majeures de retard) |
| anthropic | 0.88.0 | 0.105.0 |
| cryptography | 46.0.6 | 48.0.0 |
| bcrypt | 3.2.2 | 5.0.0 |
| google-genai | 1.66.0 | 2.7.0 |
| certbot | 2.9.0 | 5.6.0 |
| acme | 2.9.0 | 5.6.0 |

**Anomalie :** `gunicorn` est **absent de `requirements.txt`** alors qu'il est l'entrypoint runtime (systemd). Il dépend donc de l'install système.

---

## 8. SOURCES DE DONNÉES EXTERNES

| Source | URL / endpoint | Usage | Fallback |
|---|---|---|---|
| **NASA APOD** | `api.nasa.gov/planetary/apod` | Image du jour, gallery × 6 | `telescope_sources.py` a une liste statique de 6 images APOD historiques |
| **NASA Images Library** | `images-api.nasa.gov/search` | Recherche images Webb | implicite (cache) |
| **NASA SkyView** | `skyview.gsfc.nasa.gov` | Imagerie astro | aucun |
| **NASA Mars Rovers** | `api.nasa.gov/mars-photos/.../rovers/...` | Photos rovers | aucun |
| **NASA NEO** | `api.nasa.gov/neo/rest/v1/feed` | Géocroiseurs | aucun |
| **JPL Horizons** | `ssd.jpl.nasa.gov/api/horizons.api` | Éphémérides | aucun |
| **NOAA SWPC** | `services.swpc.noaa.gov/{products,json}/*` | Vent solaire, alertes, X-ray flares | aucun |
| **OpenSky** | `opensky-network.org/api/states/all` + `auth.opensky-network.org` | Trafic aérien | **oui** → `api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}` + ScrapingBee |
| **wheretheiss.at** | `api.wheretheiss.at/v1/satellites/25544` | Position ISS | autre source SGP4 locale |
| **STScI** | `stsci-opo.org/STScI-*.png` | Images Webb statiques | embarquées |
| **Anthropic** | `api.anthropic.com/v1/messages` | LLM | groq + openai + gemini |
| **Groq** | `api.groq.com/openai/v1/chat/completions` | LLM | autres providers |
| **Google Gemini** | `generativelanguage.googleapis.com/v1beta/models/*` | Traduction IA | autres |
| **xAI** | `api.x.ai/v1/chat/completions` | LLM | autres |

---

## 9. SÉCURITÉ

| Contrôle | Résultat |
|---|---|
| `DEBUG=True` en dur dans `app/` ou `wsgi.py` | **0 occurrence** (clean) |
| `app.debug = True` | **0 occurrence** |
| Fichier `.env` | **présent**, perms `-rw------- root:zakaria`, 5625 octets |
| Lecture `.env` depuis ce shell | refusée (Permission denied) — **bon signe** |
| `config/` à la racine | ne contient que `guardian_rules.yaml` (pas de config Flask en clair) |
| Secrets en dur (regex `secret|token|password|api_key = "..."`) | **0** détection après filtrage `os.environ/getenv/config[/self/kwargs/request` |
| `SECRET_KEY` en prod | enforced via `_resolve_secret_key()` dans `app/__init__.py`, lève `RuntimeError("SECRET_KEY")` si absent ou < `MIN_SECRET_KEY_LEN_PRODUCTION` |
| `env_guard.validate_production_env` | présent et appelé au démarrage |
| `SECURITY.md` | présent (378 lignes — politique publique) |

Aucun trou évident détecté en lecture statique sur l'arbre `app/`.

---

## 10. DETTE TECHNIQUE

| Indicateur | Valeur |
|---|---|
| Total `TODO\|FIXME\|XXX\|HACK` dans `app/` | **1** (seulement `app/blueprints/sdr/routes.py:23` — `# TODO B-config futur`) |
| **Fichiers `.bak*` dans l'arbre** | **453** (≈ **41.1 Mo**) |
| Fichiers Python > 500 lignes | 11 |
| Plus gros fichiers (hors `.bak`) | `analytics/__init__.py` 793 · `weather/__init__.py` 737 · `feeds/__init__.py` 722 · `flight_radar/opensky_client.py` 686 · `flight_radar/flight_service.py` 678 · `ai/__init__.py` 661 · `cameras/__init__.py` 601 |
| Modifs non commitées sur `main` | 10 fichiers M + 1 D |
| Backups récents (3 derniers jours) | `app/__init__.py.bak*`, `wsgi.py.bak*`, `analytics_dashboard.py.bak*`, `cameras/__init__.py.bak*`, `guardian/agent.py.bak*` (2), `hooks.py.bak*`, `health/__init__.py.bak*` |
| Branches locales obsolètes | sprint1…sprint18 (16) + fix/* (5) + ui/* (3) + perf/* (3) — beaucoup de mergées non purgées |

Le code lui-même est **remarquablement propre** côté TODO. La dette est concentrée dans :
1. La pollution `.bak*` à la racine et dans tout `app/`.
2. L'inflation des `__init__.py` de blueprints (plusieurs > 600 lignes).
3. L'état git non commité sur `main` avec services nouveaux (`control_tower`, `telescope_bridge`, `sentinel`, `guardian`) jamais versionnés.

---

## 11. DOCUMENTATION

### Racine (14 fichiers `.md`)

| Fichier | Lignes | Sujet |
|---|---|---|
| `README.md` | 214 | Présentation projet + badges + statut Lighthouse |
| `ARCHITECTURE.md` | 357 | Architecture technique ASTRO-SCAN / ORBITAL-CHOHRA |
| `AUDIT_CARTOGRAPHIES_2026-05-09.md` | 411 | Audit total des cartographies |
| `AUDIT_IMPERFECTIONS_2026-05-09.md` | 597 | Audit imperfections anodines |
| `CHANGELOG.md` | 78 | Keep-a-Changelog (s'arrête à v2.0.0 du 2026-05-04 — **désynchro** vs tags v2.7.x) |
| `CONTRIBUTING.md` | 105 | Guide contribution |
| `DEPLOYMENT.md` | 436 | Procédure de déploiement |
| `FICHE_TECHNIQUE.md` | 342 | Fiche détaillée projet |
| `KNOWN_ISSUES.md` | 97 | Bugs connus & limitations |
| `MANIFESTE_SCIENTIFIQUE_2026.md` | 3 | **stub cassé** (contient `$(cat /root/astro_scan/VISION_2026.md)` — variable non substituée) |
| `MANIFESTO.md` | 37 | Manifeste |
| `SECURITY.md` | 378 | Politique de sécurité |
| `SENTINEL_REDESIGN_20260515.md` | 260 | Refonte UI Sentinel v2 |
| `SENTINEL_V1_AUDIT_20260515.md` | 1238 | Audit complet code Sentinel v1 |

### `docs/`

| Fichier | Lignes | Sujet |
|---|---|---|
| `docs/README.md` | 15 | Index documentation |
| `docs/RAPPORT_ASSURANCE_CONTINUITE_ASTROSCAN.md` | 553 | Rapport assurance continuité |
| `docs/view_sync_deployment.md` | 124 | Déploiement synchro vue WebSocket |
| `docs/{audits,axe-astrobrain,images,migration,phases,reports,sessions}/` | — | sous-dossiers thématiques |

---

## SYNTHÈSE

### 🟢 Solide
- **Test suite verte** : 479 passed / 0 failed en 16.7 s sur 35 fichiers.
- **CI structurée** : lint ruff + matrice py 3.11/3.12 + coverage gate (faible mais réel).
- **Architecture factory propre** : `create_app()` unique, 32 blueprints découplés, source unique pour les coords (`observatory.py` avec garde-fou écrit en dur).
- **Hygiène secrets** : aucun secret en dur détecté, `.env` en perms 600, `SECRET_KEY` enforced via `env_guard` en production.
- **Service systemd stable** : actif 6 h, 893 Mo RAM, 4×4 workers, drop-ins de hardening présents.

### 🟡 À surveiller
- **Désynchronisation versions** : README/badges parlent de v2.8.0, dernier tag réel = v2.7.4, `CHANGELOG.md` s'arrête à 2.0.0 du 4 mai → ni source de vérité ni constante `__version__`.
- **107 paquets pip outdated**, dont des libs sécurité (`cryptography`, `bcrypt`, `certbot`).
- **20,5% de skips pytest** (124 skipped) — concentré sur smoke/legacy → tests désactivés sans suivi explicite.
- **Branches git non purgées** : 25 locales + 14 remote (sprint*, fix/*, ui/*, perf/* mergés).
- **Inflation `__init__.py` blueprints** : 7 fichiers > 600 lignes (analytics 793, weather 737, feeds 722) — candidats au split.
- **Disque à 73%** : pas critique mais à surveiller (croissance lente attendue).

### 🔴 Bloquant / urgent
- **`gunicorn` absent de `requirements.txt`** alors que c'est l'entrypoint runtime — risque concret si déploiement froid. Version installée 20.1.0 (4 majeures de retard).
- **10 fichiers modifiés non commités sur `main`** dont `app/__init__.py`, `wsgi.py`, `app/blueprints/guardian/agent.py`, `app/blueprints/cameras/__init__.py`, `config/guardian_rules.yaml` — code en prod (service tourne sur `/opt/astroscan` cf. unit file) non sauvegardé dans git.
- **40+ fichiers/dossiers non trackés** dont des nouveautés majeures jamais versionnées : `app/services/control_tower/`, `modules/telescope_bridge/`, `telescope_bridge_agent/`, `audit/{guardian,health,purify,sentinel}/`, `scripts/{deploy_europe_live.py,post_deploy_check.sh,smoke_tests.sh,astroscan_status.sh}`.
- **453 fichiers `.bak*` (41 Mo)** dans l'arbre source, jusque dans `app/` — bruit qui pollue grep, IDE, et les commits accidentels (et que les regex de routes scannent).
- **`MANIFESTE_SCIENTIFIQUE_2026.md` cassé** : 3 lignes avec `$(cat VISION_2026.md)` non substitué.

### 📊 Score technique par axe (/10)

| Axe | Score | Justification |
|---|---|---|
| Architecture | **8/10** | Factory, blueprints découplés, source unique constants. Pénalisé par l'inflation des __init__ |
| Tests | **7/10** | 479 verts, mais 124 skips et coverage non mesuré localement (gate CI à 20%) |
| Sécurité | **8/10** | Aucun secret en dur, .env protégé, env_guard en prod. Outdated `cryptography`/`bcrypt` pénalisent |
| Documentation | **6/10** | Riche (14 .md racine + docs/) mais désynchro versions, CHANGELOG figé, manifeste cassé |
| Performance | **8/10** | Lighthouse 97, lazy-load Cesium, cache APOD 24h, minif JS+CSS, 893 Mo RAM stable |
| **Hygiène repo / git** | **4/10** | 453 `.bak`, code prod non commité, branches non purgées, gunicorn hors requirements |

### ▶️ Recommandation — par où démarrer

Démarrer par **l'hygiène repo + git** : c'est le seul axe qui aggrave passivement chaque jour et qui masque/freine tous les autres diagnostics.

Séquence courte :
1. **Commiter l'état réel de `main`** (10 fichiers M + nouveaux dossiers `control_tower`, `telescope_bridge`, `sentinel`, `guardian`) ou décider quoi rejeter. Sans ça, le service tourne sur du code orphelin.
2. **Purger les 453 `.bak*`** (déplacer dans `audit/backups/` hors arbre, ou supprimer après tag de sauvegarde).
3. **Ajouter `gunicorn==25.x` à `requirements.txt`** (alignement install runtime).
4. **Synchroniser version** : créer un `VERSION` ou `app/__version__.py` source unique, mettre à jour `CHANGELOG.md` jusqu'à v2.7.4, corriger les badges README.
5. Puis bump `cryptography`/`bcrypt`/`gunicorn` dans une PR de sécurité.

Tout le reste (refacto `__init__` géants, remontée coverage, purge branches) viendra plus naturellement une fois `main` redevenu la vérité.
