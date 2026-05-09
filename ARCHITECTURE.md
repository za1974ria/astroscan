# ARCHITECTURE TECHNIQUE — ASTRO-SCAN / ORBITAL-CHOHRA

> ## Update — 2026-05-04 — Phase 2C Complete
>
> Phase 2C migration is functionally complete on `migration/phase-2c`.
> The application factory `app/__init__.py:create_app()` is the canonical
> entry point and `station_web.py` is preserved as a compatibility shim
> (≈ 5325 lines) re-exporting symbols still imported by hooks and
> services.
>
> | Indicateur | Valeur |
> |------------|--------|
> | **Blueprints enregistrés** | **25** (PASS 28: +`version`; PASS 26.B: +`nasa_proxy`) |
> | **Routes** | **266** |
> | **Hooks app-level** | **8** centralisés dans `app/hooks.py` (PASS 24) |
> | **Bootstrap threads** | centralisés dans `app/bootstrap.py` (PASS 25.1) |
> | **Helpers réponses** | `app/utils/responses.py` — `api_ok` / `api_error` (opt-in, PASS 28) |
>
> Récapitulatif des passes récentes :
>
> - **PASS 26.A** — `.gitignore` durci, `SECRET_KEY` enforcement en
>   production, déduplication de `sentry_sdk.init()`.
> - **PASS 26.B** — Blueprint `nasa_proxy` (`/api/nasa/*`) ; la
>   `NASA_API_KEY` n'est plus rendue dans le HTML.
> - **PASS 27** — Normalisation SQL des doublons `Netherlands` /
>   `The Netherlands` (5 fichiers, 7 SELECT) ; modal in-page « Tous
>   les pays » alimentée par `/api/export/visitors.json`.
> - **PASS 28** — `/api/system/server-info` et `/api/health`
>   sanitisés ; nouvel endpoint `/api/build` (commit, branche, boot
>   time) ; helpers `api_ok` / `api_error`.
>
> Le reste de ce document décrit l'architecture historique. Lire la
> section ci-dessus pour l'état courant.

---

**Plateforme d'observation astronomique temps réel — Tlemcen, Algérie**

| Champ | Valeur |
|-------|--------|
| **Directeur** | Zakaria Chohra |
| **Domaine** | https://astroscan.space |
| **Hébergement** | Hetzner Cloud — Hillsboro, Oregon (US-West) |
| **Coordonnées station** | 34.87° N · 1.32° E (Tlemcen, Algérie) |
| **Stack** | Flask 3.1 · Gunicorn · Nginx · SQLite (WAL) · Sentry |
| **Routes en production** | 262 |
| **Blueprints** | 21 |
| **Services** | 13 (`app/services/`) + 8 partagés (`services/`) |
| **Version** | 2.0 — 03/05/2026 (post-bascule PASS 18) |

---

## 1. Vue d'ensemble

ASTRO-SCAN agrège, transforme et expose en temps réel des données scientifiques issues de la NASA, NOAA SWPC, ESA, JPL Horizons, CelesTrak, Harvard MicroObservatory et d'autres sources institutionnelles. La plateforme sert :

- une **API HTTP publique** (262 routes, format JSON principalement) ;
- un **frontend** intégrant un globe orbital 3D Cesium, un suivi ISS et un dashboard observatoire ;
- un **moteur AEGIS** (raisonnement multi-IA, streaming SSE) ;
- un **calculateur Hilal** (visibilité du croissant lunaire — critères ODEH, UIOF, Oum Al Qura).

L'architecture cible est un **pattern application-factory Flask** avec 21 blueprints thématiques et 13 modules de service. Le module monolithe historique `station_web.py` est conservé en pré-chargement pour initialiser certains globals partagés (cache TLE, threads collecteurs, configuration runtime), mais ne sert plus aucune route métier — uniquement l'override `/static/<path>`.

---

## 2. Architecture globale

```
┌─────────────────────────────────────────────────────────────────┐
│                    Navigateur / Client API                       │
│              https://astroscan.space  (TLS Let's Encrypt)        │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Nginx (reverse proxy)                      │
│        TLS · gzip · static cache · proxy_pass → :5003            │
└────────────────────────────────┬────────────────────────────────┘
                                 │ HTTP
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│            Gunicorn — 4 workers × 4 threads                      │
│            unit systemd : astroscan.service                      │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                          wsgi.py                                 │
│                                                                  │
│   1. ASTROSCAN_FORCE_MONOLITH=1  →  fallback explicite           │
│   2. import station_web          →  init globals                 │
│   3. from app import create_app  →  factory propre               │
│   4. except                       →  fallback monolith            │
│                                                                  │
│   Renvoie `app` (Flask) à Gunicorn dans tous les cas.            │
└────────────────────────────────┬────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
┌────────────────┐     ┌──────────────────┐    ┌────────────────────┐
│  station_web   │     │  app/__init__.py │    │   app/services/    │
│  (legacy mod.) │     │                  │    │   (logique pure)   │
│                │     │  create_app()    │    │                    │
│  • env vars    │     │  ├ blueprints×21 │    │  • ai_translate    │
│  • DB WAL init │     │  ├ Sentry        │    │  • hilal_compute   │
│  • TLE cache   │     │  ├ SQLite WAL    │    │  • iss_compute     │
│  • threads     │     │  └ register_BPs  │    │  • oracle_engine   │
│  • lazy globals│     │                  │    │  • …               │
└────────────────┘     └──────────────────┘    └────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    services/  (couche partagée)                  │
│                                                                  │
│  circuit_breaker · cache_service · orbital_service · weather_    │
│  service · nasa_service · stats_service · ephemeris_service · db │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
              SQLite (archive_stellaire.db, mode WAL)
              + APIs externes (circuit-breakered)
```

---

## 3. Stratégie de chargement WSGI (PASS 18)

Le fichier `wsgi.py` met en œuvre une stratégie défensive en 3 niveaux :

```python
def _build_app():
    if _FORCE_MONOLITH:                           # niveau 1 : env var
        from station_web import app as _app
        return _app

    try:
        import station_web                         # niveau 2 : init globals
        from app import create_app
        _app = create_app("production")            # → 262 routes
        return _app
    except Exception:                              # niveau 3 : fallback
        from station_web import app as _app
        return _app
```

**Pourquoi ce design ?**

1. `station_web` est *toujours* importé en premier — il initialise des globals (cache TLE, threads collecteurs, configuration `.env`) que les blueprints consomment via `from station_web import _get_db_visitors, _fetch_iss_live, ...` en lazy-import.
2. Si `create_app()` échoue à l'import (régression silencieuse, dépendance manquante, config corrompue), l'application retombe automatiquement sur l'objet `app` du monolithe — qui enregistre lui-même les 21 BPs en interne (lignes 501+ de `station_web.py`). Le service reste servi.
3. `ASTROSCAN_FORCE_MONOLITH=1` permet un rollback opérationnel sans modifier le code (cf. `ROLLBACK_PASS18.md`).

---

## 4. Application factory (`app/__init__.py`)

```
create_app(config_name="production")
├── _init_sentry()           # Sentry SDK 2.58, DSN via env
├── _init_sqlite_wal()       # PRAGMA journal_mode=WAL
├── _register_blueprints()
│   ├── main_bp              # 11 routes : /, /sitemap, /robots
│   ├── api_bp               # 19 routes : /api/*
│   ├── feeds_bp             # 31 routes : /api/feeds/*
│   ├── analytics_bp         # 18 routes : /api/visitors, /dashboard
│   ├── ai_bp                # 16 routes : /api/ai/*, /api/aegis/*
│   ├── cameras_bp           # 15 routes : /cameras, /galerie
│   ├── system_bp            # 20 routes : /api/health, /api/system-status
│   ├── weather_bp           # 18 routes : /api/weather, /api/kp
│   ├── lab_bp               # 16 routes : /lab/*, /hilal
│   ├── telescope_bp         # 16 routes : /api/telescope/*
│   ├── iss_bp               # 14 routes : /api/iss, /api/iss/passes
│   ├── pages_bp             # 25 routes : pages HTML statiques
│   ├── satellites_bp        #  4 routes : SGP4 propagation
│   ├── export_bp            #  5 routes : exports CSV/JSON
│   ├── astro_bp             #  8 routes : éphémérides
│   ├── archive_bp           #  7 routes : observations archivées
│   ├── research_bp          #  6 routes : dashboard chercheur
│   ├── seo_bp               #  3 routes : sitemap, robots
│   ├── sdr_bp               #  5 routes : radio logicielle
│   ├── apod_bp              #  3 routes : NASA APOD
│   └── i18n_bp              #  1 route  : traduction
└── return app
```

**Total** : 261 routes blueprints + 1 route Flask par défaut (`/static/<path>`) = **262 routes**.

---

## 5. Couche de services (`app/services/`)

Logique métier pure, sans dépendance Flask, testable hors contexte HTTP :

| Module | LOC | Responsabilité |
|---|---:|---|
| `ai_translate.py` | 480 | Routage multi-IA (Claude, Gemini, Groq, Grok), streaming SSE |
| `hilal_compute.py` | 404 | Calcul de visibilité du croissant — ODEH, UIOF, Oum Al Qura |
| `analytics_dashboard.py` | 319 | Agrégation visiteurs, géo-distribution, séries temporelles |
| `external_feeds.py` | 307 | Agrégateur NASA / NOAA / ESA / DSN |
| `weather_archive.py` | 238 | Historique météo spatial |
| `oracle_engine.py` | 207 | Cœur de raisonnement AEGIS |
| `observatory_feeds.py` | 187 | Sources observatoires partenaires |
| `iss_compute.py` | 183 | Prédiction passages ISS (SGP4 + horizon Tlemcen) |
| `microobservatory.py` | 168 | Interface Harvard MicroObservatory (FITS) |
| `telescope_sources.py` | 137 | Sources de données télescope |
| `guide_engine.py` | 107 | Guide d'observation |
| `http_client.py` | 86 | Client HTTP durci (timeouts, retries, UA) |

---

## 6. Couche de services partagée (`services/`)

Modules transverses utilisés à la fois par les blueprints et par `station_web` :

- **`circuit_breaker.py`** — état per-API (NASA, N2YO, NOAA, ISS, Météo). Ouvre après N erreurs consécutives, half-open après cooldown, ferme après succès. Exposé via `/api/system-status`.
- **`cache_service.py`** — cache mémoire avec TTL par clé, invalidation manuelle ou par cron, métriques.
- **`orbital_service.py`** — chargement TLE depuis CelesTrak, propagation SGP4, calcul de pistes.
- **`weather_service.py`** — NOAA SWPC : Kp, alertes, profils premium, fallback local.
- **`nasa_service.py`** — client NASA avec rotation de clés, API key fallback.
- **`stats_service.py`** — agrégations visiteurs (global, top pays, today, distinct).
- **`ephemeris_service.py`** — Sun/Moon, twilight, full ephemeris (Skyfield).
- **`db.py`** — accesseur SQLite WAL avec context manager.

---

## 7. Modèle de données

SQLite mode WAL (`PRAGMA journal_mode=WAL`) — fichier unique `archive_stellaire.db`.

Tables principales :

```
visitors_log     (id, ip, country, city, ts, path, ua)
ai_chat_history  (id, session_id, role, content, ts, provider)
observations     (id, target, ts, fits_url, notes)
accuracy_history (id, prediction_id, observed_ts, error_seconds)
hilal_records    (id, date_hijri, criteria, result, ts)
```

Le mode WAL permet la lecture concurrente pendant l'écriture (workers Gunicorn parallèles). Les écritures restent sérialisées via lock SQLite — non bloquant pour les lectures.

---

## 8. Orchestration multi-IA

Le module `app/services/ai_translate.py` route chaque requête vers le provider optimal selon :

- **disponibilité** — circuit-breaker par provider ;
- **type de tâche** — traduction → Gemini, raisonnement long → Claude, latence faible → Groq ;
- **coût** — fallback gratuit si quota dépassé ;
- **contexte utilisateur** — langue détectée, longueur prompt.

Les réponses chat sont diffusées en **Server-Sent Events** (`text/event-stream`) pour permettre l'affichage progressif côté client. Le worker thread `translate_worker` traite en arrière-plan les traductions différées (APOD du jour, observations entrantes).

---

## 9. Calcul Hilal

Implémentation des trois critères principaux de visibilité du croissant lunaire :

- **ODEH** — combinaison ARCV + W' (largeur du croissant) ;
- **UIOF** (Union Internationale des Organisations de la Fatwa) — élongation + altitude ;
- **Oum Al Qura** — critère officiel saoudien.

Calculs basés sur Skyfield (éphémérides JPL DE440), validés contre les bases de référence ICOUK et HM Nautical Almanac. Précision typique : ±2 minutes sur le coucher du soleil, ±3 minutes sur le coucher lunaire.

---

## 10. Observabilité

- **Sentry SDK 2.58** — capture des exceptions non gérées, traces de performance (sample 10 %).
- **Logs structurés** — `astroscan.*` (logging Python), redirigés vers journalctl via systemd.
- **Health probes** — `/api/health` (sans dépendances externes), `/api/system-status` (avec circuit-breakers).
- **Métriques runtime** — endpoint `/api/system-status` expose : workers, mémoire, cache hit rate, état des 5 circuit-breakers.

---

## 11. Sécurité

- **TLS** — Let's Encrypt + auto-renew (certbot timer systemd).
- **Secrets** — `/root/astro_scan/.env` (chmod 600, owner root). Aucun secret en clair dans le repo.
- **CORS** — restrictif par défaut, ouvert sur `/api/public/*` uniquement.
- **CSP** — défini par Nginx, autorise Cesium Ion + Google Analytics.
- **Rate-limiting** — au niveau Nginx (limit_req_zone) sur les endpoints AI coûteux.
- **Validation** — toute entrée utilisateur passe par les schémas de chaque blueprint avant traitement.

---

## 12. Historique de migration (PASS 1 → 19)

Migration progressive du monolithe `station_web.py` (12 159 lignes) vers l'architecture cible, exécutée sans interruption de service :

| Pass | Périmètre | Impact |
|---|---|---|
| 1–4 | Bootstrap factory + premiers BPs | 4 BPs |
| 5 | Pages + PWA | +25 routes |
| 6 | Caméras + galerie | +20 routes |
| 7 | Astropy + météo + éphémérides | +18 routes |
| 8 | Feeds NASA/NOAA externes | +14 routes |
| 9 | Domaine télescope | +16 routes |
| 10 | IA + extraction `ai_translate.py` | +15 routes, service extrait |
| 11 | Audit + nettoyage ciblé | 78 % cible |
| 12 | Visiteurs + analytics | +10 routes |
| 13 | Lab + research | 86 % |
| 14 | ISS compute + satellites | 92 % |
| 15 | Extraction agressive helpers | 96 % |
| 16 | Bascule registration BPs | 99 % |
| 17 | 2 dernières routes IA lourdes | 99 % |
| 18 | **Bascule production wsgi → create_app()** | bascule effective |
| 19 | Cleanup dead code monolithe | −1 781 lignes |

**État final** : `station_web.py` réduit de 11 918 → 5 466 lignes (−54 %), monolithe ne servant plus qu'`/static/<path>` (override Flask intentionnel) et l'initialisation des globals.

---

## 13. Procédure de rollback

Trois niveaux documentés dans `ROLLBACK_PASS18.md` :

1. **Niveau 1 (le plus rapide, sans code)** — `Environment="ASTROSCAN_FORCE_MONOLITH=1"` dans le drop-in systemd, `daemon-reload`, `restart`. Le monolithe reprend la main en quelques secondes.
2. **Niveau 2 (revert git)** — `git revert <PASS-18-commit-hash> --no-edit`, restart. `wsgi.py` redevient `from station_web import app`.
3. **Niveau 3 (destructif)** — `git reset --hard phase-2c-97pct` sur le tag de restauration permanent. À utiliser seulement si les niveaux 1 et 2 échouent.

Critère de déclenchement : si **un seul** des 11 endpoints obligatoires (`/`, `/api/iss`, `/api/health`, `/portail`, `/dashboard`, `/api/apod`, `/sitemap.xml`, `/robots.txt`, `/api/weather`, `/api/satellites`, `/api/system-status`) renvoie autre chose que HTTP 200 après restart, déclencher rollback niveau 1 immédiatement.

---

## 14. Déploiement & exploitation

Voir [DEPLOYMENT.md](./DEPLOYMENT.md) pour la procédure complète : provisionnement serveur, configuration Nginx, unit systemd, rotation certificats, sauvegarde DB, runbook incidents.

---

## 15. Décisions architecturales notables

| # | Décision | Justification |
|---|---|---|
| 1 | Conservation de `station_web.py` post-bascule | Init de globals partagés (cache TLE, threads, env) consommés par lazy-import depuis les BPs. Migrer ces globals casserait l'équilibre de chargement. |
| 2 | Override `/static/<path>` non migré | Identique au handler Flask par défaut. Aucun gain à migrer, risque non nul. |
| 3 | Fallback monolithe dans `wsgi.py` | Filet de sécurité production. Si `create_app()` casse silencieusement à l'import, le service reste servi sur le monolithe legacy (qui enregistre les mêmes BPs en interne). |
| 4 | SQLite + WAL plutôt que PostgreSQL | Charge actuelle (≤ 50 req/s pic) tient largement sur SQLite WAL. Pas de besoin opérationnel justifiant la complexité d'une DB serveur séparée. |
| 5 | Multi-IA avec circuit-breaker par provider | Chaque provider a des modes de panne différents (rate-limit Gemini, instabilité Groq, coût Claude). Routage adaptatif + circuit-breakers permettent disponibilité ≥ 99 % de la couche IA. |
| 6 | Cesium côté client (pas de rendu serveur) | Le globe 3D est trop coûteux à rasteriser côté serveur. Cesium Ion délivre les tiles, le client fait le rendu WebGL. |

---

## 16. Roadmap technique

- **Tests d'intégration end-to-end** — couverture des 11 endpoints critiques + scénarios IA streaming.
- **Migration cache mémoire → Redis** (optionnel) — utile si > 4 workers ou > 1 instance.
- **API publique versionnée** (`/api/v1/`) — séparer les contrats publics des endpoints internes.
- **Documentation OpenAPI 3.0** auto-générée depuis les schémas de blueprint.
- **Métriques Prometheus** — exporter `/metrics` pour intégration Grafana.

---

**Fin du document.**
*Maintenu par : Zakaria Chohra · Directeur, ORBITAL-CHOHRA Observatory · Tlemcen, Algérie.*
