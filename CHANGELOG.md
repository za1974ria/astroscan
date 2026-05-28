# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Note semver : certains tags ne suivent pas une montée strictement croissante.
> `v2.8.0-lighthouse-58pct-ui-clean` (2026-05-18) précède chronologiquement
> `v2.7.x-*` (2026-05-21/22). La branche de dev est repartie sur `2.7.x` après
> `2.8.0` pour des raisons de continuité de nommage de chantier (axe Lighthouse
> séparé). À reprendre en clean tag `2.9.0` lors du prochain release officiel.

## [Unreleased] — 2026-05-28

### Added
- Versionnement de 10 modules prod-only (`984e550`) : `app/services/{sentinel_metrics,seo_constants,paths,api_spec,hilal_data,news_i18n}.py`, `app/blueprints/control_tower/__init__.py`, `templates/bridge_command_center.html`, `control_tower_guardian.py`, `snapshot.py`. ~1 900 lignes jusque-là présentes uniquement sur le serveur.
- `app/services/control_tower/` complet versionné dans le repo (10 fichiers ; design avancé YAML + registry, voir `docs/CONTROL_TOWER_FORK.md`).
- 2 caméras YouTube live honnêtes sur `/europe-live` : TOKYO (`dfVK7ld38Ys`) et JACKSON HOLE (`1EiC9bvVGnk`), iframes 16:9 avec horloges Asia/Tokyo et America/Denver, badge LIVE non mensonger.
- Rapport d'audit complet (`docs/AUDIT_2026-05-28.md`) — 6 axes notés, top 5 faiblesses, plan 3 jours pré-31/05.
- Décision archi documentée (`docs/CONTROL_TOWER_FORK.md`) — repo = cible avancée, prod = stable, déploiement post-validation.

### Changed
- `requirements.txt` : ajoute `gunicorn==20.1.0` (entrypoint runtime systemd jamais épinglé jusqu'ici).
- `.gitignore` durci : catch-all `*.bak-*` (format à tiret), `venv/`, `.venv/`, `audit/reports_archive_*.tar.gz`.
- `app/` aligné entre prod et repo sur 32 fichiers (`0165729` + `73b7942`) : `__init__.py`, `hooks.py`, `config.py`, `bootstrap.py` + 19 blueprints + 6 services/utils + 3 sentinel (routes/schemas/store).

### Fixed
- CI ruff redevenu vert (`344fa63`) — F841 unused-variable + format dans `tests/test_smoke_prod.py`, fichier nouvellement versionné jamais linté auparavant.
- `templates/europe_live.html` : retire le badge LIVE mensonger sur images Unsplash statiques (cartes avaient `data-hls=""` vide depuis le 23/05).
- Suppression de 310 fichiers `.bak-*` non gitignored (41 Mo de bruit).
- Suppression du fichier orphelin tracké `station_web.py.bak_shield`.

## [2.7.4-analytics-cockpit] — 2026-05-22

### Added
- Refonte cockpit Mission Control · Visitors Analytics (KPIs animés, timeline Chart.js 7j/30j, heatmap monde topojson, donut pages, barchart heures, live feed visiteurs).

## [2.7.3-a-propos-a11y-fix] — 2026-05-22
## [2.7.3-a-propos-email] — 2026-05-22
## [2.7.3-perf-nasa-apod-cache] — 2026-05-22
## [2.7.3-lazy-cesium-mc] — 2026-05-22

### Performance
- `nasa-apod` cache 24 h + sized images + preload API.
- `mission-control` lazy-load Cesium.js via IntersectionObserver.

### Fixed
- `a-propos` : a11y 100/100 restauré (tap target mailto).

### Added
- Email personnel `zakaria.chohra@gmail.com` sur la page À propos.

## [2.7.2-lighthouse-final] — 2026-05-22
## [2.7.1-lighthouse-97] — 2026-05-22

### Performance
- `ground_assets` : self-host Leaflet + defer scripts (Lighthouse 86 → 97), minif JS+CSS via terser+clean-css, content-visibility CLS.

### Fixed
- De-flake `test_rate_limit` (test concurrence flaky GHA isolé via `xfail`).

## [2.7.0-soiree-historique] — 2026-05-22
- Merge final série de fixes `ground_assets` station cards CSS, layout right-pane.

## [2.7.0-astrobrain-guardian-s1] — 2026-05-21

### Added
- **Guardian** — read-only monitoring agent + 9 collectors + rules engine (PHASE 4).
- **Astro Brain** — wrapper OpenAI GPT-5 (`app/services/llm_client.py`) + blueprint `app/blueprints/astrobrain/` + tests (PHASE 3, Session 1).

## [2.6.0-pytest-hardening] — 2026-05-21

### Added
- Makefile targets + CI badge + Development section (PASS 8).
- Pre-commit hooks scope Axe 1 (ruff lint+format sur `tests/`).
- Workflow `.github/workflows/test.yml` : matrice py3.11+3.12, coverage gate `--cov-fail-under=20`.

## [2.8.0-lighthouse-58pct-ui-clean] — 2026-05-18

### Performance
- Audit Lighthouse continu sur 50 modules. 21 modules à 100/100/100/100 stables.
- Outils audit Lighthouse + nettoyage `.gitignore`.

### Accessibility
- 100/100 sur 46 modules.

## [2.7.0-mission-control-live] — 2026-05-16

### Added
- Acte 1 — Veille Spatiale module · 11/11 LIVE · branchements sources scientifiques ESA-grade.

## [2.6.0-paris-gallery-definitive] — 2026-05-12
## [2.6.1-honest-tech-credibility] — 2026-05-12
## [2.6.2-credibility-green] — 2026-05-12
## [2.6.3-portail-embed-clean] — 2026-05-12

### Added
- Galerie Paris définitive sur `/europe-live`.

### Changed
- "Honest tech credibility" : nettoyage messages et badges pour ne pas sur-vendre.

### Fixed
- Disclaimer bouton N2YO sur `observatoire` + bump SW v188.
- Portail embed propreté (iframe `europe-live`).

## [2.5.0-maintenance-mission-control] — 2026-05-12
## [2.5.x-maintenance-i18n] — 2026-05-12
## [2.5.x-orbital-fr-*] — 2026-05-12
## [2.5.8-clean-portail-paris-live] — 2026-05-12
## [2.5.9-resilient-portail] — 2026-05-12

### Added
- Mission Control Center — SpaceX × Tesla × NASA dashboard (page maintenance).
- Galerie i18n server-driven.

### Changed
- Traductions FR Orbital (quick strings, badges, residual, danger).
- Portail clean Paris-live + résilience (fallbacks).

## [2.4.0-coords-fix] — 2026-05-10
## [2.4.1-coords-cleanup] — 2026-05-10
## [2.4.2-iss-observatoire] — 2026-05-10
## [2.4.3-iss-crew-cleanup] — 2026-05-10
## [2.4.4-polish-3pages] — 2026-05-10
## [2.4.5-ground-darksat] — 2026-05-11
## [2.4.6-translate-batch] / [2.4.7-translate-batch-fix] / [2.4.8-translate-multi-provider] — 2026-05-11
## [2.4.9-i18n-fortress] — 2026-05-11

### Fixed
- **Centralise coords observatoire Tlemcen à `-1.3167°W`** (source unique `OBSERVER_LON` dans `app/constants/observatory.py` avec garde-fou anti-Tiaret).
- ISS observatoire + crew cleanup.

### Added
- DarkSat ground assets.
- Translate multi-provider (anthropic + groq + gemini + xai), i18n fortress.

## [2.3.0-maps-harmonized] — 2026-05-09
## [2.3.1-aurora-gallery] — 2026-05-09
## [2.3.2-aurores-kp-fix] — 2026-05-09
## [2.3.3-aurora-magic] — 2026-05-13
## [2.3.4-killer-phrase] — 2026-05-13
## [2.3.5-readme-polish] — 2026-05-13
## [2.3.6-bulletin-fix] — 2026-05-13

### Added
- Harmonisation Mission Control — 9 cartes premium testées.
- Galerie Aurora + magic.
- Killer phrase bilingue EN/FR + polish README.

### Fixed
- KP aurores.
- Bulletin meteo bug.

## [2.2-maps-premium-day1] — 2026-05-09
## [2.2.1-maps-orbital-fix] / [2.2.2-orbital-final] / [2.2.3-orbital-pure] — 2026-05-09

### Added
- Mission Control — sélecteur 13 cartes premium.

### Fixed
- Orbital map corrections successives.

## [2.1-security-hardened] — 2026-05-09
## [2.1.1-cleaned] / [2.1.2-kaizen-day1] — 2026-05-09

### Security
- Rate-limit IA + auth admin (8 endpoints IA + 6 endpoints admin protégés).

### Changed
- Kaizen day 1 — cleanup transversal.

## [2.0.0] — 2026-05-04

End of Phase 2C migration: `station_web.py` monolith functionally
delegates to the application factory `app/__init__.py:create_app()`, with
25 blueprints registered and 266 routes total.

### Added

- **Application factory** (`app/__init__.py:create_app`) is the canonical
  entry point. `station_web.py` is preserved as a thin compatibility shim
  re-exporting symbols still imported by hooks/services.
- **PASS 26.B — `nasa_proxy` blueprint** (`app/blueprints/nasa_proxy/`):
  server-side relay for NASA APIs (`/api/nasa/insight-weather`,
  `/api/nasa/neo/<id>`, `/api/nasa/apod`) with in-memory TTL cache.
- **PASS 28 — `version` blueprint** (`app/blueprints/version/`): exposes
  `/api/build` with commit hash, branch and boot time. Cached at first
  call (subprocess runs once per worker).
- **PASS 28 — `app/utils/responses.py`** with `api_ok()` and `api_error()`
  helpers for a consistent JSON envelope. Existing routes were not
  migrated; helpers are opt-in for new code.
- **PASS 27 — Modal "Tous les pays"** on the orbital dashboard, fed by
  `/api/export/visitors.json` (no LIMIT), with search filter, ESC-close
  and click-outside-close.

### Changed

- **PASS 28 — `/api/system/server-info`**: response is now
  `{ok, status, zone, timestamp}`. The `ip` and `provider` fields were
  removed (DNS already exposes the host publicly; this endpoint no longer
  amplifies it).
- **PASS 28 — `/api/health`**: replaced the per-integration `services`
  dict with `integrations_ready` / `integrations_total` aggregate
  counters to prevent fingerprinting. Also dropped `ip` and `director`
  fields. `location` and `coordinates` are kept (public observatory
  metadata).
- **PASS 26.A — `SECRET_KEY` enforcement**: in production, missing or
  too-short `SECRET_KEY` now raises `RuntimeError` instead of silently
  falling back to ephemeral randomness.

### Fixed

- **PASS 27 — Netherlands / The Netherlands duplicate** in dashboard
  visitor stats. Root cause: cascade of two GeoIP providers
  (`ip-api.com` returns "Netherlands"; `ipinfo.io` fallback returns
  "The Netherlands"). Both map to country code `NL`. Fix: SQL
  normalization `CASE WHEN country_code = 'NL' THEN 'Netherlands' …`
  applied in 7 SELECT locations across `services/stats_service.py`,
  `app/services/analytics_dashboard.py`,
  `app/blueprints/analytics/__init__.py`,
  `app/blueprints/export/__init__.py`. No DB migration, no GeoIP code
  change.
- **PASS 27 — "VOIR TOUS LES PAYS" button**: previously linked to
  `/analytics`, which itself was `LIMIT 15` (broken promise). Replaced
  the anchor with an in-page modal fed by `/api/export/visitors.json`
  (no LIMIT, already filters bots and `Unknown`).

### Security

- **PASS 26.A — `.gitignore` hardening**: `.env`, `.env.save`,
  `.env.local`, `.env.bak*` are ignored, with `!.env.example` to keep
  the template trackable.
- **PASS 26.A — Sentry single init**: removed the duplicate
  `sentry_sdk.init()` from `station_web.py:41-54`. Sentry is initialised
  once in `app/__init__.py:_init_sentry`.
- **PASS 26.B — NASA_API_KEY no longer rendered in HTML**: previously
  injected via Jinja in `templates/observatoire.html`, visible in
  view-source. Now provided server-side via `nasa_proxy` blueprint;
  `nasa_key` removed from the `render_template()` context in
  `app/blueprints/pages/__init__.py`.

[2.0.0]: https://astroscan.space/
