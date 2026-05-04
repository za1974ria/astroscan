# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
