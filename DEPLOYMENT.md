# DEPLOYMENT — ORBITAL-CHOHRA / ASTRO-SCAN

**Operations runbook for the production observatory platform.**

| Field | Value |
|---|---|
| Environment | Production (single-tenant) |
| Host | Hetzner Cloud — Hillsboro, Oregon (US-West) |
| Domain | astroscan.space |
| Service unit | `astroscan.service` (systemd) |
| Document version | 1.0 — 2026-05-03 (post-PASS-18 bascule) |

---

## 1. Production Stack

```
Internet  →  Nginx (TLS, :443)  →  Gunicorn (:5003)  →  Flask app
                                                        ├── 21 blueprints
                                                        └── SQLite (WAL)
```

| Component | Version | Notes |
|---|---|---|
| OS | Ubuntu 22.04 LTS | x86_64 |
| Python | 3.11+ | system Python |
| Flask | 3.1.3 | application factory pattern |
| Gunicorn | latest | 4 workers × 4 threads |
| Nginx | system pkg | reverse proxy + TLS |
| SQLite | system pkg | WAL mode |
| Sentry SDK | 2.58.0 | error tracking |
| systemd | system | service supervision |
| Let's Encrypt | certbot | TLS auto-renewal |

---

## 2. systemd Service Unit

File: `/etc/systemd/system/astroscan.service`

```ini
[Unit]
Description=AstroScan (Gunicorn / Flask wsgi:app)
After=network.target

[Service]
User=root
WorkingDirectory=/root/astro_scan
TimeoutStopSec=150
ExecStart=/usr/bin/env python3 -m gunicorn --workers 4 --threads 4 \
  --timeout 120 --graceful-timeout 120 --keep-alive 5 \
  --max-requests 1000 --max-requests-jitter 50 \
  --bind 127.0.0.1:5003 wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Why these flags**

- `--workers 4 --threads 4` — 16 concurrent requests; tuned for current load (≤ 50 req/s peak).
- `--timeout 120` — long-running AI streaming requests need ≥ 60 s headroom.
- `--max-requests 1000 --max-requests-jitter 50` — periodic worker recycling to bound memory drift from long-lived caches.
- `--bind 127.0.0.1:5003` — only Nginx talks to Gunicorn; never exposed publicly.
- `User=root` — required for direct access to `/root/astro_scan/.env` and the SQLite file. **No privilege drop is performed; the service should be migrated to a dedicated user in a future hardening pass.**

---

## 3. Nginx Configuration

File: `/etc/nginx/sites-available/astroscan` (symlinked to `sites-enabled/`).

Key directives:

```nginx
server {
    listen 443 ssl http2;
    server_name astroscan.space;

    ssl_certificate     /etc/letsencrypt/live/astroscan.space/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/astroscan.space/privkey.pem;

    client_max_body_size 10M;

    location /static/ {
        alias /root/astro_scan/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass         http://127.0.0.1:5003;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_buffering    off;        # for SSE streaming
    }
}

server {
    listen 80;
    server_name astroscan.space;
    return 301 https://$host$request_uri;
}
```

`proxy_buffering off` is required — Server-Sent Events (used by the AEGIS chat endpoints) must flush per-event.

---

## 4. Environment & Secrets

File: `/root/astro_scan/.env` — `chmod 600`, owner `root:root`.

Required keys:

```
SECRET_KEY=<flask session signing key>
SENTRY_DSN=<sentry project DSN>
NASA_API_KEY=<api.nasa.gov>
N2YO_API_KEY=<n2yo.com>
GEMINI_API_KEY=<google ai studio>
ANTHROPIC_API_KEY=<console.anthropic.com>
GROQ_API_KEY=<console.groq.com>
XAI_API_KEY=<x.ai console>
CESIUM_ION_TOKEN=<cesium.com>
```

Optional:

```
ASTROSCAN_FORCE_MONOLITH=0      # set 1 for emergency rollback
REDIS_URL=redis://127.0.0.1:6379/0
```

**Never** commit `.env` to git. The `.gitignore` already excludes it; verify before any push.

---

## 5. Initial Deployment

```bash
# 1. clone
git clone <repo-url> /root/astro_scan
cd /root/astro_scan

# 2. system dependencies
apt update && apt install -y python3 python3-pip python3-venv \
                              nginx certbot python3-certbot-nginx \
                              sqlite3

# 3. python dependencies
pip3 install -r requirements.txt

# 4. environment
install -m 600 .env.example .env
# edit .env with real keys

# 5. database (creates archive_stellaire.db on first run)
python3 -c "from wsgi import app; print('init OK')"

# 6. nginx
cp deploy/nginx-astroscan /etc/nginx/sites-available/astroscan
ln -sf /etc/nginx/sites-available/astroscan /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# 7. TLS
certbot --nginx -d astroscan.space

# 8. systemd
cp deploy/astroscan.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now astroscan

# 9. verify
curl -fsS https://astroscan.space/api/health
```

---

## 6. Update / Redeploy

Standard update flow (no schema change):

```bash
cd /root/astro_scan
git fetch origin
git log HEAD..origin/main --oneline      # review what's coming
git pull --ff-only

# optional: smoke-test imports without touching prod
SECRET_KEY=test STATION=$(pwd) python3 -c "import wsgi; \
  print(len(list(wsgi.app.url_map.iter_rules())), 'routes')"

systemctl restart astroscan
sleep 8

# verify
curl -fsS https://astroscan.space/api/health
journalctl -u astroscan -n 50 --no-pager | grep -E "WSGI|create_app"
```

---

## 7. Smoke Test (post-deploy)

The 11 critical endpoints — **all must return HTTP 200**:

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

If any endpoint returns ≠ 200 → trigger **Rollback Level 1** immediately (see §10).

---

## 8. Health Checks & Observability

| Endpoint | Use |
|---|---|
| `GET /api/health` | Liveness probe — no external deps. Use for load-balancer health checks. |
| `GET /api/system-status` | Full readiness — DB, cache, circuit-breakers, worker count. |

**Logs**

```bash
# tail live
journalctl -u astroscan -f

# last 200 lines
journalctl -u astroscan -n 200 --no-pager

# filter by level
journalctl -u astroscan -p err -n 100 --no-pager
```

**Sentry** — exceptions and 10 % of traces are sent automatically when `SENTRY_DSN` is set.

---

## 9. Common Operations

### Restart cleanly
```bash
systemctl restart astroscan
```

### Reload Nginx (config change, no app restart)
```bash
nginx -t && systemctl reload nginx
```

### Renew TLS manually
```bash
certbot renew --dry-run     # test
certbot renew                # apply
systemctl reload nginx
```

### Force monolith mode (emergency)
```bash
systemctl edit astroscan
# add under [Service]:
# Environment="ASTROSCAN_FORCE_MONOLITH=1"
systemctl daemon-reload
systemctl restart astroscan
journalctl -u astroscan -n 30 --no-pager | grep WSGI
# expect: "[WSGI] Monolith loaded (forced) — N routes"
```

### Backup database
```bash
sqlite3 /root/astro_scan/archive_stellaire.db ".backup /backup/astroscan-$(date +%Y%m%d).db"
```

The `.backup` command is online-safe — it cooperates with WAL and does not block writers.

---

## 10. Rollback Procedure (PASS 18)

Three documented levels — start with the lowest-risk that achieves recovery.

### Level 1 — Force monolith via env var (fastest, no code change)

```bash
systemctl edit astroscan
# add: Environment="ASTROSCAN_FORCE_MONOLITH=1"
systemctl daemon-reload
systemctl restart astroscan
```

Verify: `journalctl -u astroscan -n 30 | grep WSGI` shows `Monolith loaded (forced)`.

### Level 2 — Git revert of the bascule commit

```bash
cd /root/astro_scan
git log --oneline | grep "PASS 18"
git revert <PASS-18-commit-hash> --no-edit
systemctl restart astroscan
```

`wsgi.py` reverts to `from station_web import app` (pre-PASS-18 state).

### Level 3 — Hard reset to permanent restore tag (destructive)

**Loses PASS 18+ commits. Use only if Level 1 and 2 both fail.**

```bash
cd /root/astro_scan
git fetch --all --tags
git checkout migration/phase-2c
git reset --hard phase-2c-97pct
systemctl restart astroscan
```

After any rollback, re-run the smoke test (§7) and capture journalctl output for post-mortem.

---

## 11. Incident Runbook

### Symptom: HTTP 502 from Nginx

1. `systemctl status astroscan` — is Gunicorn running?
2. If not running: `journalctl -u astroscan -n 100` — look for import errors at boot.
3. Common causes: missing env var (`SECRET_KEY` unset), broken Python dependency, syntax error in last commit.
4. Fix or rollback (see §10).

### Symptom: HTTP 500 on specific endpoint, others OK

1. `journalctl -u astroscan -n 200 | grep -i error` — find the traceback.
2. Check Sentry for grouped occurrences.
3. If isolated to one blueprint, this does not warrant a full rollback — patch and redeploy.

### Symptom: One external API failing

Check `/api/system-status` for circuit-breaker state. The breaker should already be open and serving cached / degraded responses. No operator action needed unless the breaker stays closed during a sustained outage — in which case adjust thresholds in `services/circuit_breaker.py`.

### Symptom: Disk full

```bash
du -sh /root/astro_scan/*.db* /var/log/* /tmp/*
# common culprits: SQLite WAL > 1 GB, journalctl unbounded, /tmp accretion
```

Vacuum SQLite if needed:
```bash
sqlite3 /root/astro_scan/archive_stellaire.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

### Symptom: High memory per worker

Workers recycle every 1000 requests (`--max-requests 1000`) — bounded by design. If RSS still grows unbounded between recycles, suspect a leak in a long-lived service module; capture `tracemalloc` snapshots and inspect `app/services/`.

---

## 12. Backup & Recovery

**What to back up**
- `/root/astro_scan/archive_stellaire.db` (+ `*.db-wal`, `*.db-shm`)
- `/root/astro_scan/.env`
- `/etc/nginx/sites-available/astroscan`
- `/etc/systemd/system/astroscan.service`
- `/etc/letsencrypt/` (cert bundle)

**Recommended schedule**
- DB: daily online backup via `sqlite3 .backup`, retention 30 days off-host.
- Configs: snapshot on every change (commit to ops repo).
- Certs: backed up by certbot itself; verify periodically.

**Recovery test** — restore the DB to a scratch host monthly and run the smoke test against a Gunicorn pointed at the restored file.

---

## 13. Performance Tuning

Current sizing (4 × 4 = 16 concurrent requests) handles observed peak comfortably. Tuning levers if load grows:

| Lever | When to use |
|---|---|
| Increase `--workers` | CPU-bound saturation — check `top` during peak |
| Increase `--threads` | I/O-bound saturation — most external API calls |
| Add Redis cache backend | Cross-worker cache hit rate matters (currently per-worker) |
| Move to PostgreSQL | Sustained > 100 writes/s — SQLite WAL becomes a bottleneck |
| CDN for `/static/*` | If static asset traffic dominates outbound |

Always benchmark before scaling — over-provisioning workers wastes RAM without latency gains.

---

## 14. Security Hardening Checklist

- [x] `.env` permissions `600`, root-owned
- [x] TLS via Let's Encrypt, auto-renewed
- [x] Gunicorn bound to loopback (`127.0.0.1:5003`)
- [x] Nginx terminates TLS; HTTP redirects to HTTPS
- [x] No secrets in git history (verified via `git log -p | grep -i 'api.\?key'`)
- [x] Circuit-breakers prevent cascade on upstream API failure
- [x] Sentry redacts request bodies on capture
- [ ] **TODO**: drop service privileges from `root` to a dedicated `astroscan` user
- [ ] **TODO**: enable systemd sandboxing (`PrivateTmp=`, `ProtectSystem=`, `NoNewPrivileges=`)
- [ ] **TODO**: rate-limit `/api/ai/*` at Nginx layer

---

## 15. Contacts

**Director / Operator**: Zakaria Chohra — ORBITAL-CHOHRA Observatory, Tlemcen, Algeria.

For security disclosures, contact via the platform's contact form on `astroscan.space`.

---

**End of runbook.**
*Maintained by: Zakaria Chohra · Director, ORBITAL-CHOHRA Observatory · Tlemcen, Algeria.*
