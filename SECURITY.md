# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AstroScan, please report it
**privately and responsibly** to:

**Zakaria Chohra — zakaria.chohra@gmail.com**

Please include:

- A description of the issue and its potential impact.
- Steps to reproduce (URL, payload, expected vs. actual behavior).
- Any logs, screenshots, or proof-of-concept artefacts (avoid sharing
  visitor PII or production credentials).

**Do not** open public GitHub issues for security findings. We aim to
acknowledge reports within 72 hours and to ship a fix or mitigation as
quickly as the impact warrants.

## Supported Branches

| Branch | Status |
|--------|--------|
| `migration/phase-2c` | Actively maintained — receives security patches |
| `main` | Mirrors stable releases of `migration/phase-2c` |
| Older branches | Not supported |

## Security Hardening Posture

The following controls are in place at HEAD on `migration/phase-2c`:

- **Secrets at rest**: `.env` is `chmod 600` on the production host and
  is covered by `.gitignore` (PASS 26.A: `.env`, `.env.save`, `.env.local`,
  `.env.bak*`, with `!.env.example` negation to keep the template).
- **`SECRET_KEY` enforcement**: in production, the Flask factory raises
  `RuntimeError` if `SECRET_KEY` is missing or shorter than 16 characters
  (`app/__init__.py:_resolve_secret_key`, PASS 26.A). Dev/test fall back
  to `os.urandom(32)` with a warning log.
- **NASA API key proxy** (PASS 26.B): the `NASA_API_KEY` is no longer
  embedded in HTML. Frontend calls go through the server-side blueprint
  `app/blueprints/nasa_proxy/` (`/api/nasa/insight-weather`,
  `/api/nasa/neo/<id>`, `/api/nasa/apod`) which injects the key from the
  environment.
- **Sentry single init** (PASS 26.A): Sentry is initialised once in the
  factory (`app/__init__.py:_init_sentry`); the duplicate init that used
  to live in `station_web.py:41-54` was removed to avoid replacing the
  global hub.
- **Info disclosure reduction** (PASS 28):
  - `/api/system/server-info` no longer returns `ip` / `provider`.
  - `/api/health` exposes `integrations_ready` / `integrations_total`
    instead of enumerating individual external services, and no longer
    returns `ip` or `director`.
- **Reverse proxy**: Nginx terminates TLS in front of Gunicorn and is
  configured via `astroscan_shield_nginx.sh` (HSTS, security headers).

## Reference

For the full audit that produced PASS 26.A and PASS 26.B, see
[`SECURITY_AUDIT_2026-05-04.md`](SECURITY_AUDIT_2026-05-04.md).
