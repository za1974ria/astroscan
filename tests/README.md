# ASTRO-SCAN — Test Suite

Pytest-based test suite for the ORBITAL-CHOHRA observatory platform.

## Quick start

```bash
# install dev dependencies (in addition to requirements.txt)
make install-dev   # or: pip install -r requirements-dev.txt

# run everything pytest can run on this host
make test

# run only the smoke layer (fast, no external deps if .env is readable)
make test-smoke

# run only the pure unit tier
make test-unit

# run integration (requires DB write access + Redis for full CB tests)
make test-integration

# generate a coverage report
make test-coverage
```

## Layout

```
tests/
├── conftest.py                       # shared fixtures: app, factory_app, clients
├── smoke/                            # smoke tests — high-level health
│   ├── test_factory.py               # NEW — validates create_app() factory
│   ├── test_critical_endpoints.py    # NEW — the 11 production-critical routes
│   ├── test_wsgi.py                  # NEW — wsgi.py 3-tier loader strategy
│   ├── test_legacy_routes.py         # legacy: monolith routes via station_web:app
│   ├── test_legacy_critiques.py      # legacy: pre-PASS-18 critical routes
│   ├── test_legacy_architecture.py   # legacy: factory tests written during migration
│   └── test_legacy_api_json.py       # legacy: JSON API shape checks
├── unit/                             # unit tests — pure logic, no I/O, no Flask
│   ├── test_blueprints.py            # NEW — blueprint registration invariants
│   ├── test_pure_services.py         # NEW — app/services/ pure functions
│   └── test_services.py              # services/ shared utilities
└── integration/                      # integration tests — DB / network / external
    ├── test_database.py              # NEW — SQLite WAL accessor + concurrency
    └── test_circuit_breakers.py      # circuit-breaker wiring around services
```

## Markers

Defined in `pytest.ini`:

| Marker | Meaning |
|---|---|
| `@pytest.mark.smoke` | High-level health checks — may touch DB but no network. |
| `@pytest.mark.unit` | Pure logic — no I/O, no Flask context. Runs in milliseconds. |
| `@pytest.mark.integration` | Requires DB / network / external services — opt-in. |
| `@pytest.mark.slow` | Reserved for tests > 1 s. |

Run a single tier:

```bash
pytest -m smoke
pytest -m unit
pytest -m "not integration"   # everything except integration
```

## Fixtures

Defined in `conftest.py` and available across the suite:

| Fixture | Scope | Purpose |
|---|---|---|
| `app` | session | Legacy monolith Flask app (`station_web:app`). |
| `client` | session | Test client bound to `app`. |
| `factory_app` | session | Clean Flask app from `app.create_app("testing")` — post-PASS-18 target. |
| `factory_client` | session | Test client bound to `factory_app`. |

Both app fixtures `pytest.skip()` cleanly when `/root/astro_scan/.env` is not
readable by the current user (production runs as root; CI typically does not).

## Skipped tests — by design

A baseline run on a non-root user produces ~85 skips. None are failures —
they are deliberate gates:

- **`.env` not readable** — the entire factory-app and monolith-app branch
  skips on hosts where the test runner cannot read `/root/astro_scan/.env`
  (mode 0600, root-owned). Run as root or grant read access to enable.
- **Redis-backed circuit breakers** — `OPEN`-state simulation requires a
  live Redis instance and direct state mutation. Skipped in the default
  tier; reintroduce with a Redis fixture for full CI.

A full root-account run produces 0 skips outside the Redis-CB branch.

## CI / GitHub Actions

`.github/workflows/test.yml` runs:

1. **smoke + unit** on every push and PR to `main` and `migration/phase-2c`,
   on Python 3.11 and 3.12.
2. **coverage** report on push (uploaded as an artifact).

Integration tests are intentionally **not** run in CI — they require DB
write access and external services that the public CI runner does not
have. They can be invoked locally with `make test-integration`.

## Adding a new test

1. Pick the right tier:
   - smoke → "does the app boot and serve the critical paths?"
   - unit → "is this pure function correct given known inputs?"
   - integration → "does this code path correctly interact with DB / network?"
2. Add `pytestmark = pytest.mark.<tier>` at the top of the file.
3. Use `factory_client` for new tests targeting the post-PASS-18 architecture;
   `client` only when you specifically need legacy monolith behaviour.
4. Keep unit tests under 100 ms each — they should run on every save.

## Baseline

As of PASS 21 (2026-05-03), running on a non-root user:

```
51 passed, 85 skipped, 0 failed in ~3 s
```

100 % of executable tests pass. Skips reflect environment constraints, not
regressions — running the suite as root collapses most skips to zero.
