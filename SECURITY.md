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

## Endpoint Hardening — PASS 28.SEC (2026-05-09)

Two new decorators in `app/services/security.py`:

- `@require_admin` — vérifie `X-Admin-Token` (ou `Authorization: Bearer`)
  contre `ADMIN_TOKEN` (env). Fail-closed : si la variable n'est pas
  configurée, l'endpoint renvoie **503**. Tous les rejets sont loggés
  via `logging.getLogger("astroscan.security")`.
- `@rate_limit_ip(max_per_minute, key_prefix)` — rate-limit en mémoire
  process-local (fenêtre glissante 60s). Clé : `(prefix or endpoint, IP)`.
  Headers de réponse : `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
  `X-RateLimit-Reset` (+ `Retry-After` sur 429).

### Endpoints rate-limités (anti-drainage IA)

| Endpoint | Méthode | Limite | Backend IA |
|----------|--------:|-------:|------------|
| `/api/chat` | POST | 10/min/IP | Claude / Groq |
| `/api/aegis/chat` | POST | 8/min/IP | Claude |
| `/api/oracle-cosmique` | POST | 3/min/IP | Claude streaming |
| `/api/guide-stellaire` | POST | 2/min/IP | Claude **OPUS** |
| `/api/translate` | POST | 20/min/IP | Gemini |
| `/api/astro/explain` | POST | 10/min/IP | Claude |
| `/api/science/analyze-image` | POST | 5/min/IP | Claude vision |
| `/api/sky-camera/analyze` | POST | 5/min/IP | Claude vision |

### Endpoints admin (require X-Admin-Token)

| Endpoint | Méthode | Mutation |
|----------|--------:|----------|
| `/api/visits/reset` | POST | reset compteur visites |
| `/api/owner-ips` | POST | ajout IP propriétaire |
| `/api/owner-ips/<int:ip_id>` | DELETE | suppression IP propriétaire |
| `/api/system-heal` | POST | auto-heal core |
| `/api/telescope/trigger-nightly` | POST | déclenche capture nightly |
| `/api/tle/refresh` | POST | refresh TLE manuel |

### Génération du `ADMIN_TOKEN`

```bash
# 32 octets hex (64 chars) — recommandé
python3 -c "import secrets; print(secrets.token_hex(32))"

# Ou via openssl
openssl rand -hex 32
```

Persister dans `/root/astro_scan/.env` (mode 600, root-owned) :

```
ADMIN_TOKEN=<token généré>
```

### Procédure de rotation du token

1. Générer un nouveau token : `python3 -c "import secrets; print(secrets.token_hex(32))"`.
2. Éditer `/root/astro_scan/.env` (root, mode 600), remplacer la valeur de
   `ADMIN_TOKEN` (ou `ASTROSCAN_ADMIN_TOKEN` si compat legacy).
3. `systemctl restart astroscan` — les 4 workers gunicorn rechargent l'env.
4. Mettre à jour les clients (scripts de monitoring, cron admin) qui
   utilisent l'ancien token.
5. Vérifier : `curl -X POST -H "X-Admin-Token: <ancien>" /api/visits/reset`
   doit retourner **401** ; avec le nouveau, **200**.

Aucun mécanisme de blacklist n'est nécessaire : la rotation = invalidation
immédiate de l'ancien.

### Limites connues

- **Rate-limit non distribué** : le compteur vit dans la mémoire de chaque
  worker gunicorn. Avec 4 workers en prod, la limite **effective** par IP
  est d'environ `4 × max_per_minute` (le load balancer Nginx route les
  requêtes par hash, donc en pratique souvent un seul worker reçoit le
  burst, mais pas garanti). Acceptable pour bloquer l'abus naïf et le
  drainage de quotas IA. **Insuffisant** pour rate-limit strict global —
  voir `SECURITY_HARDENING_REPORT.md` (TODO Phase 2D : passage à Redis).
- **Token unique** : pas de support multi-utilisateurs admin. Suffisant
  pour le périmètre actuel (1 admin = Zakaria).
- **`X-Forwarded-For` confiance** : la clé de rate-limit utilise
  `X-Forwarded-For` en priorité (Nginx l'injecte). Un client direct
  (sans Nginx) pourrait spoofer le header — non exposé en prod (Nginx
  est le seul point d'entrée public).

### Compat legacy

Le décorateur `require_admin` accepte aussi `ASTROSCAN_ADMIN_TOKEN`
(déjà défini en prod) en fallback si `ADMIN_TOKEN` est vide, et accepte
le header `Authorization: Bearer <token>` (pattern utilisé par
`/api/admin/circuit-breakers`).

## Reference

- Audit complet PASS 26.A / 26.B :
  [`SECURITY_AUDIT_2026-05-04.md`](SECURITY_AUDIT_2026-05-04.md)
- Hardening endpoints PASS 28.SEC :
  [`SECURITY_HARDENING_REPORT.md`](SECURITY_HARDENING_REPORT.md)
