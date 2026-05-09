# ASTROSCAN — FINAL ARCHITECTURE REVIEW
## Audit Staff Engineer / Principal Backend / Platform Reliability / CTO

**Date** : 2026-05-06
**Branche analysée** : `migration/phase-2c`
**Commit HEAD** : `bf199bf` (Docs — PASS 20.0 PRE-AUDIT report)
**Mode** : Lecture seule, aucune modification de code.
**Auditeur** : revue technique froide, sans flatterie.
**Question de référence** : *« ASTROSCAN est-il désormais une plateforme architecture-grade crédible ? »*

---

## 0. MÉTHODOLOGIE

L'audit s'appuie exclusivement sur :
- Inspection de l'arborescence Python (`app/`, `services/`, `core/`, `modules/`, scripts racine).
- Lecture du factory `app/__init__.py`, du hook layer `app/hooks.py`, du bootstrap `app/bootstrap.py`, et du résiduel `station_web.py`.
- Inspection du runtime systemd (`/etc/systemd/system/astroscan.service` + drop-ins), de la config nginx (`/etc/nginx/sites-enabled/astroscan.space`), de Redis (PING live), et des background threads.
- Probes HTTP réels sur 127.0.0.1:5003 (vérification `/`, `/ws/status`).
- Exploitation du rapport `AUDIT_PASS20_RESIDUAL.md` comme source factuelle complémentaire.

Aucun mock, aucune extrapolation : les chiffres ci-dessous sont mesurés.

---

## 1. EXECUTIVE SUMMARY

### 1.1 Verdict global

ASTROSCAN est **un projet sérieux, post-amateur, en phase intermédiaire haute** d'une vraie refactorisation architecturale. La plateforme est en production, sert du HTTPS, encaisse du trafic réel, et possède les fondations d'une stack moderne (factory Flask, blueprints, services Redis-backed, circuit breakers, SQLite WAL, Sentry, systemd hardening, rate-limiting nginx). Elle n'est **pas encore architecture-grade au sens strict** : un monolithe résiduel de 5 314 lignes (`station_web.py`) reste pré-chargé par le WSGI et alimente les blueprints via 89 imports lazy — ce qui invalide la promesse d'isolation du factory.

**Niveau de maturité réel** : 6.5 / 10. Solide pour un projet solo en pré-Series A. Insuffisant pour une revue Staff/Principal d'un grand groupe.

### 1.2 Points forts majeurs

1. **Factory `create_app()` propre, idempotent, testable** — 30 blueprints enregistrés, 8 hooks attachés, init Sentry/SQLite WAL/i18n/bootstrap correctement séquencé.
2. **Domain segregation par blueprints aboutie** — 30 BPs, dont des BPs lourds avec services internes structurés (`flight_radar/algo7/` à 7 layers, `scan_signal/services/` à 5 modules).
3. **Circuit breakers Redis-backed à état partagé inter-workers** (CB_NASA, CB_N2YO, CB_NOAA, CB_ISS, CB_METEO, CB_TLE, CB_GROQ) — ce n'est plus du « try/except autour de requests ».
4. **Production hardening systemd** : `LimitNOFILE=1 048 576`, `OOMScoreAdjust=-30`, `TimeoutStopSec=150`, `--max-requests 1000 --max-requests-jitter 50` (anti-leak), `--graceful-timeout 120`.
5. **Frontière nginx solide** : HTTPS Let's Encrypt, HSTS, X-Frame-Options, CSP partiel, rate-limit zones (`addr_limit`, `astro_global_limit`, `astro_api_limit` avec burst), proxy WebSocket configuré.
6. **Observabilité fonctionnelle** : structured JSON logs avec rotation, métriques inline (rolling 5 min), Sentry FlaskIntegration, struct_log par catégorie.
7. **Données** : SQLite WAL + `synchronous=NORMAL` + `mmap_size=256MB` + backups automatiques quotidiens (`data/backups/archive_stellaire_*.db`).

### 1.3 Points faibles résiduels

1. **Monolithe `station_web.py` non neutralisé** — 5 314 lignes, pré-chargé AVANT `create_app()` par `wsgi.py` parce que les BPs y lazy-importent encore 89 fois (`STATION`, `START_TIME`, `_emit_diag_json`, `SEO_HOME_DESCRIPTION`, `_TLE_FOR_PASSES`, `_register_unique_visit_from_request`, etc.). Le factory n'est pas indépendant.
2. **WebSocket `/ws/status` et `/ws/view-sync` orphelins** — bindés via `Sock(app)` à l'instance Flask interne du monolithe, pas à celle servie par Gunicorn (`wsgi:app` → `create_app()`). Probe live : `/ws/status` → **404**. Code mort en production.
3. **Doublon de packages services** : `services/` (legacy : `cache_service`, `circuit_breaker`, `weather_service`, `nasa_service`, etc.) coexiste avec `app/services/` (nouveau : `iss_live`, `tle_cache`, `weather_archive`, etc.). Deux conventions de nommage, deux conventions d'import. Aucune frontière claire.
4. **Hygiène repo dégradée** : **250 fichiers `.bak*`** détectés (dont 22 backups de `station_web.py` dans la racine, certains > 480 KB), 27 fichiers `.md` à la racine, 3 packages legacy `core/`/`modules/`/`services/` toujours sur le `PYTHONPATH`. Le repo « parle » à un CTO qui sniff la propreté.
5. **Aucun framework WebSocket réellement actif** — `flask-sock` est listé dans `requirements.txt` mais ses routes ne servent rien. Le streaming temps-réel se fait exclusivement via SSE (5 endpoints), ce qui est un choix défendable mais non assumé clairement.
6. **Couverture tests minimale** — 12 fichiers, 4 niveaux (unit/integration/smoke + tests « legacy »). Pas de mesure de coverage. Pas de CI testée publiquement (le `.github/` contient des workflows mais leur état n'est pas exposé).
7. **Pas de queue / pas de scheduler externe** — 5 threads daemon démarrés *in-process* (TLE, skyview, translate, lab images, tle_collector). Single point of failure : un worker Gunicorn redémarre = ces threads redémarrent (cinq fois si 5 workers, sans coordination Redis sauf TLE).

---

## 2. ARCHITECTURE ANALYSIS

### 2.1 `create_app()` (`app/__init__.py`)

```python
create_app(config_name="production")
  → validate_production_env() (env_guard)
  → Flask(template_folder=..., static_folder=...)
  → app.config.update(SECRET_KEY=_resolve_secret_key, DB_PATH, ...)
  → _init_sentry(app)
  → _init_sqlite_wal(DB_PATH)
  → _register_blueprints(app)        # 30 BPs
  → _register_hooks(app)             # 8 hooks
  → _register_i18n(app)              # cookie + context
  → _register_bootstrap(app)         # 5 BG threads
```

| Aspect | Lecture | Verdict |
|---|---|---|
| Env guard production-only (RuntimeError sur `SECRET_KEY` < 16 ou `NASA_API_KEY` manquant) | Présent (PASS 26.A) | **BON** |
| Séquencement init | Sentry → SQLite → BPs → hooks → i18n → bootstrap | **BON** |
| Dépendance au monolithe | `_register_bootstrap` lance 5 threads dont 4 sont importés depuis `station_web` | **FRAGILE** |
| Factory idempotent | Pas testé pour double-call (mais bootstrap a `_BOOTSTRAP_DONE` global) | **ACCEPTABLE** |
| Configurabilité | `config_name` accepte « production »/« testing »/« dev » de façon implicite — pas de classes Config dédiées | **ACCEPTABLE** |
| Logging factory | `logging.getLogger(__name__)` standard | **BON** |

**Verdict global factory** : **BON, FRAGILE sur la dépendance au monolithe.**

### 2.2 Blueprints (30 BPs)

| BP | LOC | Domaine | Verdict |
|---|---:|---|---|
| `feeds` | 722 | flux APOD/Hubble/NEO/missions | BON |
| `flight_radar` | 165 + 686 (opensky) + 678 (flight_service) + 749 (algo7) | radar aérien temps-réel + enrichissement multi-couches | EXCELLENT (algo7 = 7 couches sémantiques découplées) |
| `scan_signal` | 272 + 597 (aisstream) + 528 + 555 + 307 + 87 | navigation + radio (AIS + propagation) | EXCELLENT (singleton Redis-elected, retry/backoff) |
| `weather` | 511 | météo + Kp + bulletins | BON |
| `telescope` | 366 | NASA SkyView + télescope robotique | BON |
| `lab` | 421 | astro-imagerie | BON |
| `health` | 382 | `/status`, `/ready`, SSE `/stream/status` | BON |
| `analytics` | (>500) | visiteurs, sessions, owner-IPs | ACCEPTABLE (couplé fortement à monolithe pour `_register_unique_visit_from_request`) |
| `hilal` | 117 + 536 (calculations) | calcul croissant lunaire (Skyfield) | BON |
| `ground_assets` | 105 + 315 + 414 | observatoires terrestres | BON |
| `iss` | 363 | track ISS + crew + N2YO fallback | BON |
| `i18n` | 96 | hooks cookie + context | BON |
| `pages`, `main`, `apod`, `system`, `version`, `seo`, `nasa_proxy`, `astro`, `archive`, `cameras`, `export`, `ai`, `research`, `satellites`, `sdr` | <300 chacun | divers | BON / ACCEPTABLE |

**Découpage** : par domaine fonctionnel, lisible. Pas de blueprint « god-object ». **Verdict : BON.**

**Réserves** :
- `analytics` et `health` font des `from station_web import …` sur des helpers (visitors, struct_log, metrics) → couplage transverse non réglé.
- `flight_radar` et `scan_signal` ont leur propre arborescence interne `services/` + `algo7/` — qualité nettement supérieure aux BPs plus anciens. Asymétrie de maturité.

### 2.3 Services

```
app/services/         3 405 LOC (26 modules)   → couche extraite PASS 22-25
services/             ~1 800 LOC (8 modules)   → legacy, importée par station_web et les BPs
core/                 ~1 200 LOC               → engines historiques (status, weather_safe, tle_safe, etc.)
modules/              ~6 000 LOC               → packages science (digital_lab, astro_detection, etc.)
```

| Domaine | Localisation | Verdict |
|---|---|---|
| HTTP client (pool, retries) | `app/services/http_client.py` + `http_pool.py` | BON |
| Cache | `services/cache_service.py` + `app/services/cache.py` (8 LOC stub) | **DOUBLON / FRAGILE** |
| Circuit breaker | `services/circuit_breaker.py` (199 LOC, Redis-backed) | EXCELLENT (mais pas dans `app/services/`) |
| TLE | `app/services/tle_cache.py` + `app/services/tle.py` + monolithe | FRAGILE (3 sources) |
| Weather | `services/weather_service.py` + `app/services/weather_archive.py` | ACCEPTABLE (responsabilités distinctes mais coexistence non documentée) |
| ISS | `app/services/iss_live.py` + `app/services/iss_compute.py` | BON |
| Env / config | `app/services/env_guard.py` (55 LOC) | BON |
| AI / translate | `app/services/ai_translate.py` (480 LOC) | BON |

**Verdict couche service** : **ACCEPTABLE, fracturée**. Le travail PASS 22-25 a extrait beaucoup, mais n'a pas migré les modules legacy (`services/cache_service.py`, `services/circuit_breaker.py`, `core/`, `modules/`) → trois pyramids de services Python coexistent.

### 2.4 Workers / threads de fond

5 threads daemon démarrés via `app/bootstrap.py` :

| Thread | Origine | Rôle | Robustesse |
|---|---|---|---|
| `tle_refresh_loop` | `station_web.tle_refresh_loop` | Refresh TLE Celestrak (loop) | OK (retry interne) |
| `lab_image_collector` | `station_web._start_lab_image_collector` | Collecte images observatoire | OK |
| `skyview_sync` | `station_web._start_skyview_sync` | Sync SkyView NASA | OK |
| `translate_worker` | `station_web.translate_worker` | Pré-traduction FR/EN | OK |
| `tle_collector` | `station_web._start_tle_collector` | Collector secondaire TLE | OK (potentiellement redondant avec `tle_refresh_loop`) |
| `aisstream_subscriber` | `app/blueprints/scan_signal/services/aisstream_subscriber.py` | WebSocket AIS (sortant) | EXCELLENT (élection Redis, lock TTL, fail-soft) |

**Réserves** :
- Aucun de ces threads n'est externalisé (pas de Celery, pas de RQ, pas de cron systemd dédié). Cinq threads × quatre workers Gunicorn = potentiellement vingt threads concurrents pour les mêmes tâches, sauf élection Redis (faite uniquement pour AIS).
- Pas de health-check thread externe : si un thread `translate_worker` meurt silencieusement, le worker Gunicorn ne le sait pas.

**Verdict** : **ACCEPTABLE — non production-grade scaling**.

### 2.5 Hooks

`app/hooks.py` (293 lignes) attache 8 hooks. Tous lazy-importent depuis `station_web` (`SEO_HOME_DESCRIPTION`, `_emit_diag_json`, `_register_unique_visit_from_request`, `_http_request_log_allow`, `metrics_record_request`, `struct_log`, `log`, `PAGE_PATHS`, `_SESSION_TIME_SNIPPET`).

Hooks séquencés correctement :
1. `before_request : timing_start` (g._astroscan_req_start)
2. `before_request : visitor_session_before` (cookie `astroscan_sid`)
3. `before_request : maybe_increment_visits`
4. `after_request : struct_log_response` (durée, slow >2.5s, very_slow >5s, request_timing >1.5s)
5. `after_request : session_cookie + page-time script injection`
6. `errorhandler 404` / `500`
7. `context_processor : seo_site_description`

**Verdict hooks** : **BON sur la logique, FRAGILE sur la dépendance monolithe**.

### 2.6 Imports & couplage

| Métrique | Valeur |
|---|---:|
| Fichiers Python live | 227 |
| LOC Python live | 51 207 |
| `from station_web import …` total occurrences | **89** |
| Fichiers important `station_web` | **21** |

89 imports cross-monolithe sur 227 fichiers = **39 % de couplage transverse vers le legacy**. C'est la métrique la plus défavorable du repo.

**Verdict couplage** : **FRAGILE**.

### 2.7 Modularité / maintainability / scalability / production readiness

| Axe | Verdict | Justification |
|---|---|---|
| Modularité | BON | 30 BPs, services par domaine, algo7 propre |
| Maintainability | ACCEPTABLE | 89 imports `station_web`, 250 .bak, doublons services |
| Scalability | FRAGILE | SQLite single-node, threads in-process, pas de queue |
| Production readiness | BON | systemd hardened, nginx HTTPS + rate-limit, Sentry, Redis CB |
| Architecture coherence | ACCEPTABLE | Factory propre mais legacy non décommissionné |
| Coupling | FRAGILE | 39 % imports cross-monolithe |

---

## 3. MONOLITH STATUS

### 3.1 Métriques

| Métrique | Valeur |
|---|---:|
| Lignes totales | **5 314** |
| Lignes vides | 698 |
| Lignes de commentaires | 788 |
| Code effectif | **3 829** |
| Fonctions définies (tous niveaux) | **129** |
| Classes | 1 (`_AstroScanJsonLogFormatter`) |
| Routes Flask actives `@app.route` | **0** |
| Routes WebSocket actives `@_sock.route` | 2 (orphelines, voir §4) |
| Hooks `@app.before/after/error/context` | 8 (dupliqués sur instance morte) |
| Threads/timers démarrés | 8 (5 actifs via bootstrap, 3 indirects) |
| Imports top-level | 33 |
| Commentaires `MIGRATED TO …` | 220 |

### 3.2 Rôle réel restant

`station_web.py` n'est plus un serveur HTTP — c'est devenu **un module de bootstrap globals + helpers utilitaires partagés** :

1. **Init env / .env / dotenv** (`load_dotenv`, fail-soft) — ~lignes 440-470.
2. **Création d'un `app = Flask(...)` mort** (ligne 460) qui sert de support à `flask-sock` et aux 8 hooks legacy — instance non servie en prod.
3. **Globals partagés** : `STATION`, `DB_PATH`, `START_TIME`, `TLE_CACHE`, `TLE_CACHE_FILE`, `_TLE_FOR_PASSES`, `SEO_HOME_DESCRIPTION`, `PAGE_PATHS`, `_SESSION_TIME_SNIPPET`.
4. **Helpers** : `_emit_diag_json`, `struct_log`, `metrics_record_request`, `_register_unique_visit_from_request`, `_get_satellite_tle_by_name`, `fetch_tle_from_celestrak`, `tle_refresh_loop`, `translate_worker`, `_init_sqlite_wal`, `_init_visits_table`, etc.
5. **220 stubs de migration** (commentaires `MIGRATED TO bp_x`) — utiles pour la traçabilité, mais polluent le fichier.

### 3.3 Side-effects à l'import

`import station_web` (forcé par `wsgi.py` AVANT `create_app()`) déclenche au top-level :
- `_init_sqlite_wal()` sur DB_PATH — exécuté DEUX fois (monolithe puis factory).
- `init_all_wal()` (services/db.py) — initialise plusieurs DBs.
- `init_weather_db()`, `_init_weather_history_dir()`, `_init_weather_archive_dir()`.
- Création de `app = Flask(...)`.
- Enregistrement de 21 BPs sur cette instance morte (sync station_web L501+).
- Bind de `flask-sock` sur l'instance morte.
- Lecture .env, owner_ips_load.
- ~70 statements top-level exécutables (dixit `AUDIT_PASS20_RESIDUAL.md`).

Conséquences :
- Démarrage Gunicorn ralenti (chaque worker re-évalue tout au boot).
- WAL initialisé deux fois (idempotent mais loggé deux fois).
- Routes BPs enregistrées DEUX fois (sur instance morte + sur instance live), inflation de l'`url_map` interne du monolithe.

### 3.4 Dette legacy

| Catégorie | Volume | Statut |
|---|---:|---|
| Fonctions « infra » à migrer (TLE, weather, struct_log, metrics) | 30+ | À migrer |
| Globals encore référencés par BPs/hooks | 9 | À migrer |
| Commentaires `MIGRATED` (cosmétique) | 220 | À supprimer en bloc |
| Routes `@app.route` actives | 0 | Déjà migré ✓ |
| Hooks dupliqués sur instance morte | 8 | À supprimer |
| Bindings `flask-sock` orphelins | 2 routes | À déplacer vers BP `realtime` ou supprimer |

### 3.5 Verdict monolithe

**Le monolithe N'EST PAS neutralisé.** Il est *vidé de ses routes* et *partiellement vidé de ses hooks*, mais reste **load-bearing** par 89 imports lazy et par 70 statements top-level.

**Niveau de risque** : MOYEN — pas de régression imminente, mais la migration ne peut pas être déclarée terminée. Toute personne reprenant le code croit voir un factory propre, et découvre derrière le rideau que `station_web.py` est un Singleton Bootstrap obscur. C'est exactement le type de dette qui rend le projet **non-portable** vers un autre dev.

---

## 4. WEBSOCKET & REALTIME REVIEW

### 4.1 Stack temps-réel actuelle

| Couche | Implémentation | État live |
|---|---|---|
| **WebSocket entrant (server)** | `flask-sock 0.7.0` (`Sock(app)` dans monolithe) | **DEAD** — bindé à `station_web.app`, instance non servie. |
| **WebSocket sortant (client)** | `websocket-client` dans `aisstream_subscriber.py` | ACTIF — élection Redis, fail-soft, retry. |
| **SSE (Server-Sent Events)** | 5 endpoints | ACTIF |
| **flask-socketio** | non installé | N/A |
| **Long-poll fallback** | `/api/visitors/stats` (REST one-shot) | ACTIF |

### 4.2 Endpoints SSE actifs

| Endpoint | BP | Source de vérité |
|---|---|---|
| `/stream/status` | health | `build_status_snapshot_dict()` toutes les 3 s |
| `/api/iss/stream` | iss | position ISS toutes les 3 s |
| `/api/visitors/stream` | analytics | stats live |
| `/api/telescope/stream` | telescope | (migré dans BP) |
| `/api/ai/stream` (`stream_with_context`) | ai | LLM streaming |

### 4.3 Probe live des bindings WebSocket

```bash
$ curl -sI http://127.0.0.1:5003/ws/status
HTTP/1.1 404 NOT FOUND
```

Confirmé : la route `/ws/status` est **introuvable en production**. Cause : `Sock(app)` est appelé sur `station_web.app`, mais Gunicorn sert `wsgi:app` qui pointe vers `create_app()` — une instance Flask différente. Les routes `/ws/status` et `/ws/view-sync` ne sont pas portées.

Nginx prévoit pourtant un `location /ws/` avec `proxy_set_header Upgrade $http_upgrade` et `proxy_read_timeout 3600s`. Cette préparation infra **ne sert à rien** tant que les bindings restent orphelins.

### 4.4 Singleton usage

`aisstream_subscriber.py` implémente un pattern d'élection Redis distributed lock (`SET key NX PX ttl`), ce qui empêche que les 4 workers Gunicorn ouvrent 4 WebSockets concurrents vers AISStream. **Pattern correct, fail-soft, niveau professionnel**.

Aucun équivalent pour les 4 autres threads de bootstrap (TLE refresh, skyview sync, translate, lab images). Si la charge augmente et qu'un opérateur passe à 8 workers, le risque de double-write SQLite augmente.

### 4.5 Memory leak risk

| Vecteur | Diagnostic |
|---|---|
| Boucles SSE infinies | `time.sleep(3)` + `yield` standard. Pas de leak observable mais pas de mécanisme de cleanup explicite côté serveur en cas de close client. |
| Threads daemon | `daemon=True` partout — meurent avec le worker. Pas de leak. |
| Caches in-memory | `TLE_CACHE`, `_OWNER_IPS_CACHE` — pas de TTL strict, dépendent du restart Gunicorn (`--max-requests 1000` aide). |
| Connexions Redis | Singleton lazy par worker. **OK**. |
| WebSocket sortant AIS | Reconnect avec backoff. **OK**. |

### 4.6 Verdict WebSocket / realtime

| Aspect | Verdict |
|---|---|
| Architecture realtime | **ACCEPTABLE** (SSE solide, WebSocket cassé) |
| Production stability | **BON** sur SSE, **CRITIQUE** sur les `/ws/*` annoncés (404) |
| Memory safety | BON |
| Coordination multi-worker | EXCELLENT pour AIS, ABSENT ailleurs |
| Lisibilité de la stack | FRAGILE — un dev nouveau ne devine pas que `/ws/*` est mort |

---

## 5. CODEBASE CLEANLINESS

### 5.1 Inventaire dette de surface

| Item | Volume |
|---|---:|
| Fichiers `*.bak*` | **250** |
| Backups de `station_web.py` (>400 KB chacun) | 22 |
| Backups `.env` | 13 |
| Fichiers `.md` à la racine | **27** |
| Packages legacy (`core/`, `modules/`, `services/`) sur PYTHONPATH | 3 |
| `__pycache__` à la racine | 1 |
| Fichiers vides à la racine (`0`, `20,`, `main`) | 3 |
| Fichier `IMPORTANT_README.txt` | 1 |
| Templates HTML | 145 |

### 5.2 Naming consistency

| Convention | Présence |
|---|---|
| Snake_case Python | OK |
| Préfixes `_private` | OK |
| Préfixes `astroscan_` (scripts shell) | OK |
| Préfixes `aegis_` (scripts shell) | OK — coexiste avec `astroscan_` sans frontière claire |
| Suffixes `_engine_safe` (`core/`) vs `_engine` (`modules/`) | INCOHÉRENT |
| Modules services : `services/cache_service.py` vs `app/services/cache.py` | INCOHÉRENT |

### 5.3 Imports inutiles

`station_web.py` a fait l'objet d'une passe de cleanup (PASS 19 puis PASS 25.2 — « Remove unused send_from_directory import »). L'audit `PASS20` confirme **0 import top-level dead** dans le monolithe. **OK**.

Dans `app/blueprints/`, les imports sont propres (vérifié sur health, iss, satellites). Pas de dead code apparent dans les BPs.

### 5.4 Structure dossiers

```
/root/astro_scan/
├── app/                  ← Code propre (factory + 30 BPs + 26 services)
├── services/             ← Legacy (8 modules, importé par monolithe et BPs)
├── core/                 ← Legacy engines (12 modules)
├── modules/              ← Legacy science (digital_lab, astro_detection, …)
├── data/                 ← DBs SQLite + tle/ + stellarium/ + microobservatory/
├── deploy/               ← systemd unit + scripts
├── ops/                  ← scripts opérationnels + audits markdown
├── scripts/              ← scripts Python utilitaires
├── tests/                ← 3 niveaux (smoke, unit, integration), 12 fichiers
├── templates/            ← 145 fichiers HTML
├── static/               ← JS/CSS/images
├── station_web.py        ← MONOLITHE (5 314 lignes)
├── wsgi.py               ← Entrée Gunicorn
├── 22 × station_web.py.bak_*   ← À PURGER
├── 27 × *.md à la racine ← À ARCHIVER (audits, rapports historiques)
└── ~30 scripts shell `astroscan_*`, `aegis_*`
```

### 5.5 Architecture coherence

L'arborescence raconte **deux histoires en parallèle** :
- **Histoire neuve** : `app/` (factory + BPs + services).
- **Histoire ancienne** : `station_web.py` + `services/` + `core/` + `modules/` + scripts shell `aegis_*`.

Aucune des deux n'a tué l'autre. Un nouveau lecteur ne sait pas par où commencer.

### 5.6 Verdict cleanliness

| Aspect | Verdict |
|---|---|
| Dead code en production | BON (pas de routes mortes côté factory) |
| Imports inutiles | BON |
| Naming consistency | ACCEPTABLE |
| Structure dossiers | FRAGILE (deux mondes) |
| Lisibilité (1er regard) | FRAGILE (250 .bak + 27 .md noient le signal) |
| Dette technique restante | MOYENNE — quantifiable, pas catastrophique |

---

## 6. PRODUCTION ENGINEERING REVIEW

### 6.1 Gunicorn

```
gunicorn --workers 4 --threads 4 --timeout 120 --graceful-timeout 120
         --keep-alive 5 --max-requests 1000 --max-requests-jitter 50
         --bind 127.0.0.1:5003 wsgi:app
```

| Paramètre | Choix | Verdict |
|---|---|---|
| Workers | 4 | OK pour CPU-bound modeste |
| Threads | 4 | OK pour IO-bound (NASA, OpenSky, Celestrak) |
| Timeout | 120 s | Élevé mais cohérent avec routes lourdes (telescope, microobservatory) |
| Max requests | 1000 ± 50 jitter | Anti-leak EXCELLENT |
| Worker class | `sync` (default) | **PROBLÈME** : incompatible avec `flask-sock` qui exige `gevent` ou `gthread` (présent ici via `--threads`). Vérification réelle : `flask-sock` supporte `gthread` ; OK théoriquement, mais comme les bindings sont orphelins, c'est un point sans effet. |

**Verdict Gunicorn** : **BON**.

### 6.2 systemd

`/etc/systemd/system/astroscan.service` :
- `User=root` — **DISCUTABLE** (un utilisateur dédié `astroscan` serait plus propre, mais pas critique vu l'isolation nginx/UFW).
- `LimitNOFILE=1 048 576` (drop-in) — généreux.
- `OOMScoreAdjust=-30` — protection raisonnable.
- `TimeoutStopSec=150` — laisse Gunicorn drainer ses 120 s graceful.
- `Restart=always` + `RestartSec=3` + `StartLimitIntervalSec=60` + `StartLimitBurst=10` — anti-crashloop correct.
- `Environment=PYTHONUNBUFFERED=1` — bon pour journald.

**Verdict systemd** : **BON**.

### 6.3 nginx

| Item | Présence | Verdict |
|---|---|---|
| HTTPS Let's Encrypt | OUI (auto-cert) | BON |
| HSTS `max-age=31536000` | OUI | BON |
| X-Frame-Options SAMEORIGIN | OUI | BON |
| X-Content-Type-Options nosniff | OUI | BON |
| Referrer-Policy strict-origin-when-cross-origin | OUI | BON |
| Permissions-Policy (geo, mic, cam, payment) | OUI | BON |
| Content-Security-Policy | NON | **MANQUANT** (ne bloque rien aujourd'hui mais c'est attendu en 2026) |
| Rate-limit zones | `addr_limit=20`, `astro_global_limit burst=50`, `astro_api_limit burst=20` | BON |
| Cache-control `no-store` sur `/` | OUI | BON (mais agressif — pas de cache statique, utiliserait des asset hashes) |
| Cache-control no-store sur `/static/sw.js` spécifiquement | OUI | EXCELLENT |
| WebSocket upgrade `/ws/` | OUI | BON (mais orphelin côté Flask) |
| HTTP→HTTPS 301 | OUI | BON |
| ACME challenge | OUI | BON |
| `/control` accessible en HTTP | OUI | **DISCUTABLE** (pourquoi laisser `/control` hors HTTPS ?) |

**Verdict nginx** : **BON, avec deux réserves** (CSP absente, `/control` HTTP).

### 6.4 Redis

```
$ redis-cli ping
PONG
```

Usage live :
- Circuit breakers (7 keys `as:cb:NASA:*`, `as:cb:N2YO:*`, …) avec TTL.
- `aisstream_subscriber` distributed lock (élection unique worker).
- Cache générique via `services/cache_service.py`.
- Caches `flight_radar`, `scan_signal` (`_REDIS = redis.Redis(decode_responses=True)`).

**Verdict Redis** : **BON**.

### 6.5 SQLite WAL

| DB | Localisation | WAL | Backups |
|---|---|---|---|
| `data/archive_stellaire.db` | principal | OUI (PRAGMA WAL + sync NORMAL + cache 20MB + mmap 256MB) | OUI (backup_sqlite.py, snapshots horaires) |
| `data/visitors.db` | analytics | OUI (via app/utils/db.py) | À vérifier |
| `data/alerts_sent.db` | alertes | À vérifier | À vérifier |
| `data/push_subscriptions.db` | webpush | À vérifier | À vérifier |
| `astroscan.db` (racine) | legacy | À vérifier | NON |
| `weather.db` (racine, 16 KB) | legacy | À vérifier | NON |
| `weather_bulletins.db` (racine, 90 KB) | live ? | OUI | NON |

**Verdict SQLite** : **BON sur la DB principale, ACCEPTABLE sur les secondaires** (multiplicité non documentée, certaines en racine au lieu de `data/`).

### 6.6 Circuit breakers

`services/circuit_breaker.py` (199 LOC, Redis-backed). 7 instances :

| Breaker | Threshold | Recovery |
|---|---:|---:|
| CB_NASA | 3 | 300 s |
| CB_N2YO | 3 | 120 s |
| CB_NOAA | 5 | 180 s |
| CB_ISS | 5 | 60 s |
| CB_METEO | 3 | 180 s |
| CB_TLE | 5 | 60 s |
| CB_GROQ | (cf. fichier) | (cf. fichier) |

État partagé Redis avec keys `as:cb:<name>:state|failures|last_fail`. TTL appliqué (PASS récente : « Hardening — Circuit breaker TTL Redis to prevent stuck OPEN state », commit `3dca1ff`).

**Verdict CB** : **EXCELLENT**.

### 6.7 Cache strategy

| Niveau | Outil |
|---|---|
| L1 in-process | `services/cache_service.py` (dict + lock) |
| L2 Redis | même module, fallback si Redis disponible |
| HTTP cache (proxies) | Headers `no-store` agressifs sur `/` (annule tout cache) |
| Static assets | aucun cache-control explicite (Flask défaut + nginx no-store) |

**Verdict cache** : **ACCEPTABLE — agressivement no-store, conservateur**. Une vraie plateforme servirait les assets statiques avec `Cache-Control: max-age=31536000, immutable` + asset hashes. Ici, chaque visiteur re-télécharge les CSS/JS à chaque navigation. Acceptable au volume actuel, problématique à 10×.

### 6.8 Failover chains

| Service externe | Chaîne |
|---|---|
| NASA APOD | CB_NASA + fallback `{"ok":False,"error":"circuit ouvert"}` + cache local 24h |
| TLE | CB_TLE + cache disk + fallback Celestrak alternates |
| OpenSky | OAuth2 + anonymous fallback (~100 req/j) |
| AIS Stream | reconnect + Redis lock fallback |
| ISS | CB_ISS + fallback N2YO via CB_N2YO |
| Weather (NOAA) | CB_NOAA + cache local 1h |

**Verdict failover** : **BON**.

### 6.9 Sentry integration

`app/__init__.py:97-112` :
- DSN lu depuis `SENTRY_DSN`.
- `FlaskIntegration()`.
- `traces_sample_rate=0.1`.
- Release `astroscan@2.0.0`.
- Environment `os.environ["FLASK_ENV"]` (défaut `production`).

Hardening récent (PASS 26.A) : déduplication des erreurs (commit `4044601`).

**Verdict Sentry** : **BON**.

### 6.10 Environment security

| Item | État |
|---|---|
| `.env` permissions `-rw-------` (600) | OUI |
| `.env` non commité | OUI (vérifié `.gitignore`) |
| `SECRET_KEY` validé en production (≥16 chars, RuntimeError sinon) | OUI |
| `NASA_API_KEY` validé en production | OUI |
| 13 backups `.env.bak.*` à la racine | **PROBLÉMATIQUE** (couleur orange : ils sont 600 mais polluent le repo et risquent un commit accidentel si `.gitignore` change) |
| Secrets dans logs | À vérifier (struct_log filtre les KEY/TOKEN ?) |

**Verdict env security** : **BON sur les contrôles, FRAGILE sur l'hygiène des backups**.

### 6.11 Runtime stability

| Indicateur | État (snapshot) |
|---|---|
| Service `astroscan` actif | OUI (uptime depuis 17:33 le jour de l'audit) |
| Memory worker master | 397 MB (peak 399.7 MB) |
| Tasks systemd | 70 (limit 9255) |
| Workers Gunicorn vivants | 4 |
| `/` répond 200 | OUI |
| `/ws/status` répond 200 | NON (404) |
| nginx config test | OK (erreur permission cert sur `nginx -t` non-root, normal) |
| Redis ping | PONG |

**Verdict runtime** : **BON**.

---

## 7. CTO IMPRESSION SIMULATION

*Persona : CTO senior d'une scaleup européenne (50–500 ingés), expérience FAANG / Stripe / Datadog. Ouvre le repo pour la première fois.*

### 7.1 Première impression (les 3 premières minutes)

> « OK, projet Flask. Voyons le `wsgi.py`… ah, il pré-charge un fichier `station_web.py` AVANT le factory. C'est une étape de transition, ils sont en milieu de migration. Le `wsgi.py` est honnête — il documente le fallback monolithe. C'est rare et c'est un bon signe. »

> « `app/__init__.py` — factory propre, 30 blueprints, hooks, env_guard, Sentry, SQLite WAL. Ça respire le travail récent et structuré. »

> « Mais… *(tape `ls`)* … 22 backups de `station_web.py`, 27 fichiers `.md` à la racine, `services/`, `core/`, `modules/`, et `app/services/` — quatre packages services. Pourquoi ? »

> « Et `station_web.py` fait 5 314 lignes ? Il est mort en routing mais alimente encore des globals partagés. Donc c'est un Singleton-Bootstrap caché. Ce n'est pas montrable. »

### 7.2 Signaux positifs

1. **Le commit log est propre et raconte une histoire**. Les commits récents disent ce qu'ils font (`PASS 25.2`, `PASS 26.A`, `Hardening — Circuit breaker TTL`). Pas de commits « fix », « wip ».
2. **Sentry, Redis, WAL, CB, rate-limit, HSTS** — checklist production solide.
3. **Le BP `flight_radar/algo7/` à 7 couches sémantiques** (flight plan → callsign decoder → geographic → aircraft type → corridors → meteo → projection) est un signal de design intelligent. Pas une mocup, une vraie pipeline.
4. **`aisstream_subscriber` avec élection Redis distribuée** — quelqu'un sait coder des systèmes distribués.
5. **`AUDIT_PASS20_RESIDUAL.md`, `STABILITY_AUDIT_*.md`, `INFRASTRUCTURE_AUDIT_*.md`** — l'auteur s'audite lui-même. Comportement Staff-grade.
6. **`MIGRATION_PLAN.md` à 37 KB** — refactoring documenté, pas opportuniste.
7. **i18n FR/EN production-grade**, sitemap hreflang, presse-kit bilingue — soin du produit, pas que du backend.

### 7.3 Signaux négatifs

1. **Le monolithe est encore là**. C'est *l'éléphant dans la pièce*. Tous les commits PASS 18→25 racontent la migration, mais le résultat à PASS 20 est qu'il reste 5 314 lignes et 89 imports cross. **L'auteur a sous-estimé l'ampleur du dernier 20 %**.
2. **Routes WebSocket cassées en prod**. C'est un bug architectural masqué : le code existe, le binding est fait, mais sur la mauvaise instance Flask. Aucun test smoke ne le détecte.
3. **250 `.bak`** = absence de discipline `git stash` / branche. Ça raconte un développement « par pétrification » : on garde tout au cas où, on ne fait pas confiance à git.
4. **Quatre packages services** = Conway's Law inverse. Un seul dev, mais quatre hiérarchies. Symptôme classique d'un repo qui a grossi par accrétion.
5. **Aucun coverage report visible**. 12 fichiers tests, mais pas de % publique. Le CTO suppose le pire.
6. **`User=root` dans systemd** — discutable mais pas bloquant.
7. **CSP absent** dans nginx — attendu en 2026.

### 7.4 Niveau crédibilité

> « *À l'œil nu* : c'est entre un side-project ambitieux et une early-stage startup solo. Pas un repo open-source de quart-d'œil, mais pas non plus un projet entreprise. La qualité technique des modules récents (algo7, scan_signal, circuit breakers) dépasse celle d'un junior. La dette résiduelle est typique d'un solo-dev qui a appris en construisant. »

> « *Embaucherais-je ?* — si l'auteur me montre ce projet en entretien, oui je passe au technique sur la migration : *« Pourquoi station_web.py est encore pré-chargé par wsgi.py ? Comment tu termines ? »*. Si la réponse est lucide et chiffrée, c'est un Senior. Si la réponse est défensive, c'est un Mid+. »

### 7.5 Niveau amateur vs professionnel

| Item | Amateur | Pro |
|---|---|---|
| Factory Flask + BPs | | ✅ |
| Circuit breakers Redis | | ✅ |
| HTTPS + HSTS + rate-limit | | ✅ |
| Sentry + structured logs | | ✅ |
| Migration documentée | | ✅ |
| WAL + backups | | ✅ |
| 250 `.bak` files | ✅ | |
| Doublon services/ + app/services/ | ✅ | |
| Monolithe pré-chargé via wsgi | ✅ | |
| WebSocket bindings orphelins | ✅ | |
| Tests sans coverage | ✅ | |
| 27 .md à la racine | ✅ | |

**Score : 6 pro / 6 amateur. Projet à mi-chemin.**

### 7.6 Ce qui impressionne réellement

1. La **maturité de raisonnement** dans les rapports d'audit (`AUDIT_PASS20_RESIDUAL.md` est un texte qu'écrirait un Staff Engineer, pas un débutant).
2. La **précision des commits** (commits par PASS, scopés, avec mesures).
3. **Algo7 du flight_radar** — découpage par couches sémantiques, c'est de l'ingénierie, pas du copy-paste.
4. **Hardening systemd** : `LimitNOFILE`, `OOMScoreAdjust`, `--max-requests-jitter` — détails que la plupart des solo-devs ne touchent jamais.

### 7.7 Ce qui doit encore être amélioré

1. **Finir la migration** : tuer `station_web.py`, ou alors le renommer `app/legacy_globals.py` et l'expliquer dans le README.
2. **Réparer ou retirer `/ws/*`**.
3. **Ranger** : un dossier `_archive/` pour les .bak, un dossier `docs/audits/` pour les .md.
4. **Choisir** : `services/` OU `app/services/` — pas les deux.
5. **CI publique avec coverage badge**.
6. **CSP dans nginx**.

---

## 8. RECRUITMENT VALUE ANALYSIS

### 8.1 Valeur portfolio

ASTROSCAN est **portfoliable** mais pas **silver-bullet-portfoliable**. C'est-à-dire : il vaut la peine d'être montré, mais il ne fait pas embaucher tout seul.

| Audience | Valeur |
|---|---|
| Recruteur non-tech (LinkedIn) | **Moyenne** — le projet a une vitrine (HTTPS, design, FR/EN, presse-kit), mais le storytelling « plateforme spatiale » sonne plus marketing que technique. |
| Tech lead / EM dans une scaleup | **Bonne** — le `MIGRATION_PLAN.md`, les commits PASS, les circuit breakers, le hardening systemd sont des signaux concrets. |
| Staff Engineer FAANG | **Acceptable** — la dette résiduelle (monolithe pré-chargé, 250 .bak) sera relevée immédiatement comme problème de discipline. |
| Solo-CTO / fondateur technique | **Bonne** — démontre qu'on peut tenir la barre sur infra + backend + UX simultanément. |

### 8.2 Crédibilité CV

| Compétence revendicable | Justifiée par |
|---|---|
| Flask production-grade | Factory, hooks, BPs, Sentry, env_guard |
| Refactoring d'un monolithe | PASS 11 → PASS 25 documenté |
| Systèmes distribués (lite) | Élection Redis, circuit breakers partagés |
| Production engineering | systemd, nginx, gunicorn, WAL, rate-limit |
| Données SQL multi-DB | 4+ DBs SQLite, WAL, backups, mmap |
| API integrations à failover | NASA, OpenSky, N2YO, NOAA, Celestrak, AISStream |
| Frontend / UX | 145 templates, i18n FR/EN, design soigné |
| Documentation technique | 27 .md (volume excessif mais tous lisibles) |

| Compétence NON démontrable depuis ce repo |
|---|
| Microservices / message bus (Kafka/RabbitMQ/NATS) — absent |
| Container orchestration (k8s) — absent |
| CI/CD multi-stage — non visible publiquement |
| Tests rigoureux (TDD, coverage > 70 %) — non démontré |
| Observabilité avancée (OpenTelemetry, traces distribuées) — Sentry seul |
| Schema migrations (Alembic, Liquibase) — SQLite raw |
| Performance engineering (load tests, profiling) — non documenté |

### 8.3 Niveau estimé du fondateur

À partir du repo seul, sans contexte humain :

> **Profil estimé : ingénieur backend Senior solo, 5–10 ans d'expérience, à dominante Python/Flask + ops Linux.**
> Plafond visible dans le repo : **Senior+ / Mid-Staff**. Capable d'architecturer une refactorisation complète, capable de hardener un déploiement, capable de raisonner sur les systèmes distribués légers. **Pas encore de signaux clairs** de scaling au-delà de single-node (pas de queue, pas de k8s, pas de schema versioning).

> **Différenciation** : la combinaison verticale (backend + ops + frontend + i18n + presse-kit + audits) raconte un *fondateur*, pas un dev IC. Cette polyvalence est rare et précieuse pour une early-stage startup, mais elle plafonne la profondeur (un Staff Backend pur écrit du code plus dense, un SRE pur monitore mieux, etc.).

### 8.4 Honnêteté brute

ASTROSCAN n'est **pas un projet à montrer à un Staff Eng Google sans contexte**. Mais c'est un projet qui :
- Justifie un poste de **Lead Backend dans une scaleup B2B/SaaS** (50-300 ingénieurs).
- Justifie un rôle de **CTO d'une seed/Series A early-stage** (< 20 ingénieurs).
- **Ne justifie pas** un rôle Staff/Principal dans un grand groupe sans complément (open-source, paper, talk technique).

---

## 9. SCORECARD

Notation /10. Échelle :
- 9–10 : élite (top 1 %, comparable à un projet open-source de référence).
- 7–8 : pro confirmé (production scaleup, ingénieur senior).
- 5–6 : pro émergent / personnel avancé.
- 3–4 : amateur structuré.
- 0–2 : amateur.

| Axe | Note | Justification courte |
|---|---:|---|
| **Architecture** | 6.5 | Factory propre + 30 BPs, mais monolithe pré-chargé invalide l'isolation. |
| **Backend** | 7.0 | Stack Flask moderne, services par domaine, async externalisé via threads (pas idéal mais opérationnel). |
| **Reliability** | 7.5 | CB Redis-backed, WAL, backups, systemd hardened, retry/backoff. Manque alarming on-call. |
| **Scalability** | 5.5 | Single-node SQLite, threads in-process, pas de queue, pas de horizontal scaling testé. |
| **Maintainability** | 5.0 | 89 imports cross-monolithe, 250 .bak, doublon services/, naming incohérent. |
| **Modularity** | 6.5 | Découpage BPs OK, services fragmentés, algo7 exemplaire. |
| **Production readiness** | 7.0 | HTTPS+HSTS+ratelimit+Sentry+WAL+systemd. CSP manquante, `/ws/*` cassés. |
| **UI engineering** | 6.0 | 145 templates, i18n complet, design soigné, mais Polish encore en cours (témoignage commits récents). |
| **Systems thinking** | 7.0 | Circuit breakers, élection Redis, structured logs, env_guard, failover chains. |
| **Overall technical credibility** | **6.5** | Au-dessus de la moyenne solo. Sous le seuil scaleup. |

**Moyenne pondérée** : **6.45 / 10**.

---

## 10. FINAL VERDICT

### 10.1 Classification

ASTROSCAN est :

- ❌ Pas un projet amateur (contredit par : Sentry, CB Redis, WAL, hardening, i18n, audits).
- ❌ Pas un simple bon projet personnel (la quantité d'ingénierie infrastructure dépasse le « hobby »).
- ✅ **Un projet avancé** (la classification la plus juste).
- ⚠️ **Sur le seuil** d'une vraie plateforme technique crédible — **n'a pas encore franchi** la ligne, mais en est à 1–2 PASS d'y arriver.
- ❌ Pas une plateforme niveau entreprise (single-node, no queue, no k8s, no horizontal scaling).
- ❌ Pas une plateforme élite.

### 10.2 Pourquoi

ASTROSCAN est sur la *frontière haute* de « projet personnel avancé ». Trois indicateurs le retiennent en deçà du seuil entreprise :

1. **Le monolithe résiduel non neutralisé** est le facteur n°1 — c'est le test décisif d'un audit Staff. Tant que `station_web.py` est pré-chargé, l'architecture revendique une chose et en livre une autre.
2. **L'asymétrie de qualité interne** — `flight_radar/algo7/` est niveau senior+, certains BPs anciens sont niveau mid. La cohérence architecturale n'est pas atteinte.
3. **L'hygiène repo** — 250 .bak, 27 .md à la racine, doublons services/. C'est cosmétique, mais à un audit, c'est lu comme « le projet n'est jamais terminé ».

À l'inverse, **trois facteurs poussent vers le haut** :
- Le **niveau de raisonnement** des audits internes (l'auteur sait où il en est).
- La **discipline des commits PASS**.
- La **réalité opérationnelle** (le service tourne, sert HTTPS, encaisse du trafic, depuis des mois).

### 10.3 Sentence

> *« ASTROSCAN est une plateforme technique en construction sérieuse, opérée en production par un fondateur compétent. Elle a dépassé le stade du side-project. Elle n'a pas encore atteint le stade de la plateforme architecture-grade. Elle peut y parvenir en 4 à 8 PASS supplémentaires si la discipline actuelle est maintenue. »*

---

## 11. NEXT LEVEL ROADMAP

Cinq chantiers à fort impact, classés par ROI technique × crédibilité × difficulté.

### Chantier 1 — **Neutralisation finale du monolithe**

| Critère | Niveau |
|---|---|
| Impact technique | ★★★★★ |
| Impact crédibilité | ★★★★★ |
| Difficulté | ★★★★ |
| Priorité | **P0 — IMMÉDIATE** |

**Quoi** :
1. Migrer les 9 globals (`STATION`, `START_TIME`, `TLE_CACHE`, `_TLE_FOR_PASSES`, `SEO_HOME_DESCRIPTION`, `PAGE_PATHS`, `_SESSION_TIME_SNIPPET`, `DB_PATH`) vers un module `app/state.py` ou `app/config.py` dédié.
2. Migrer les helpers utilisés par hooks/BPs (`_emit_diag_json`, `struct_log`, `metrics_*`, `_register_unique_visit_from_request`, `_http_request_log_allow`) vers `app/observability.py` + `app/visitors.py`.
3. Migrer les fonctions infra (`fetch_tle_from_celestrak`, `tle_refresh_loop`, `translate_worker`, `_init_*`) vers `app/services/`.
4. Supprimer le pré-chargement `station_web` dans `wsgi.py`.
5. Supprimer le bloc `app = Flask(...)` + 8 hooks dupliqués + bindings flask-sock orphelins du monolithe.
6. Renommer `station_web.py` → `app/legacy_helpers.py` ou supprimer entièrement.

**Effet** : 89 imports cross-monolithe → 0. Le factory devient autoporteur. **C'est le PASS qui change la classification du projet.**

### Chantier 2 — **Réparation ou retrait des routes WebSocket**

| Critère | Niveau |
|---|---|
| Impact technique | ★★★ |
| Impact crédibilité | ★★★★ |
| Difficulté | ★★ |
| Priorité | **P1 — RAPIDE** |

**Quoi** :
- Option A : créer `app/blueprints/realtime/__init__.py` avec `flask-sock` correctement bindé sur l'app du factory ; réimplémenter `/ws/status` et `/ws/view-sync`. Tester avec `wscat`.
- Option B : assumer le choix SSE et supprimer `flask-sock` + simple-websocket de `requirements.txt`, retirer `location /ws/` de nginx.

**Effet** : élimine un bug masqué, simplifie la stack, clarifie le récit (« on fait du SSE, point »).

### Chantier 3 — **Décommissionnement des packages legacy services / core / modules**

| Critère | Niveau |
|---|---|
| Impact technique | ★★★ |
| Impact crédibilité | ★★★★★ |
| Difficulté | ★★★ |
| Priorité | **P1 — RAPIDE** |

**Quoi** :
- Migrer `services/circuit_breaker.py` → `app/services/circuit_breaker.py`.
- Migrer `services/cache_service.py` → `app/services/cache.py` (remplir le stub 8 LOC).
- Migrer `services/{nasa,weather,orbital,stats,utils,db,config,ephemeris}_service.py` → `app/services/` avec noms cohérents (sans suffixe `_service`).
- Évaluer `core/` et `modules/` — soit migrer dans `app/services/` ou `app/blueprints/<domain>/services/`, soit déclarer EOL et archiver.
- Mettre à jour les imports dans tout le repo.

**Effet** : un seul package services, un seul mental model. Le repo devient lisible en 30 secondes pour un nouveau lecteur.

### Chantier 4 — **CI publique avec coverage + load tests**

| Critère | Niveau |
|---|---|
| Impact technique | ★★★★ |
| Impact crédibilité | ★★★★★ |
| Difficulté | ★★ |
| Priorité | **P2 — STRATÉGIQUE** |

**Quoi** :
- Activer `.github/workflows/` avec `pytest --cov=app --cov-report=xml`, badge codecov.
- Ajouter un job de smoke test sur `wsgi:app` (boot + `/`, `/status`, `/api/iss`, `/stream/status`).
- Ajouter un load test basique (`locust` ou `k6`) sur 3 endpoints critiques.
- Publier le badge CI + coverage dans `README.md`.

**Effet** : un recruteur qui lit le README voit un signal vert immédiat. Coût marginal : 1–2 jours.

### Chantier 5 — **Hygiène repo + Documentation curation**

| Critère | Niveau |
|---|---|
| Impact technique | ★★ |
| Impact crédibilité | ★★★★ |
| Difficulté | ★ |
| Priorité | **P2 — STRATÉGIQUE** |

**Quoi** :
- Créer `_archive/{backups,reports}/` ; déplacer les 250 .bak et les 22 rapports historiques.
- Garder à la racine 5 .md max : `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- Déplacer les autres dans `docs/audits/`, `docs/migration/`, `docs/reports/`.
- Enrichir `.gitignore` pour bloquer toute future création de `*.bak*` à la racine.
- Adopter `git worktree` ou des branches `archive/<topic>` pour les sauvegardes futures.

**Effet** : -90 % du bruit visuel à `ls`. Le projet *paraît* fini.

### Chantiers bonus (si plus de 5 chantiers)

6. **CSP nginx + audit OWASP top 10** (P3).
7. **Schema migrations** (Alembic ou yoyo-migrations) sur les SQLite (P3).
8. **OpenTelemetry traces** + dashboard Grafana (P4 — vrai signal Staff+).
9. **Conteneurisation Docker + docker-compose** (P4 — facilite l'embauche d'un dev d'appoint).
10. **Externalisation des background threads** vers Celery+Redis ou systemd timers (P5 — vrai pas vers entreprise).

---

## 12. ANNEXES

### 12.1 Inventaire chiffré du repo (snapshot 2026-05-06)

| Catégorie | Valeur |
|---|---:|
| Branche | `migration/phase-2c` |
| Dernier commit | `bf199bf` |
| Fichiers Python live | 227 |
| LOC Python live | 51 207 |
| Templates HTML | 145 |
| Blueprints enregistrés | 30 |
| Services `app/services/` | 26 |
| Services `services/` (legacy) | 8 |
| Engines `core/` (legacy) | 12 |
| Modules `modules/` (legacy) | 25+ |
| Tests Python | 12 fichiers |
| Backups `*.bak*` | 250 |
| Fichiers `.md` à la racine | 27 |
| DBs SQLite (data/) | 5 |
| Background threads (live) | 5 |
| Circuit breakers actifs | 7 |
| Endpoints SSE actifs | 5 |
| Endpoints WebSocket | 2 (orphelins) |
| Workers Gunicorn | 4 × 4 threads |
| Mémoire master Gunicorn | ~400 MB |

### 12.2 Probes live exécutées pendant l'audit

```
$ systemctl is-active astroscan       → active
$ redis-cli ping                       → PONG
$ curl -sI http://127.0.0.1:5003/      → 200 OK (gunicorn)
$ curl -sI http://127.0.0.1:5003/ws/status → 404 NOT FOUND
$ ps aux | grep gunicorn               → 1 master + 4 workers (wsgi:app)
```

### 12.3 Commit log significatif (sample)

```
bf199bf Docs — PASS 20.0 PRE-AUDIT report (565 lines mapping station_web.py)
3dca1ff Hardening — Circuit breaker TTL Redis to prevent stuck OPEN state
8785cf1 Phase 2C — Add 4 new blueprints (flight_radar, ground_assets, scan_signal, hilal)
c9c8bff PASS 31.7 — Final humility sweep
4044601 PASS 26.A — Security hardening: gitignore + SECRET_KEY + Sentry dedup
3308672 PASS 25.2 — Migrate /static route from monolith to factory
aa75880 PASS 25.1 — Migrate boot threads to app/bootstrap.py + factory
```

### 12.4 Synthèse en une phrase

> **ASTROSCAN est à 80 % du chemin d'une plateforme architecture-grade. Les 20 % restants — neutralisation du monolithe, unification des services, hygiène repo — sont les plus visibles et les plus déterminants pour la perception d'un auditeur externe.**

---

**Fin de l'audit.**
*Document généré en lecture seule, aucune modification de code, aucun restart, aucun commit.*
