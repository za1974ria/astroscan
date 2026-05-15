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
| `main` | Actively maintained — receives security patches |
| `migration/phase-2c` | Historical — merged into `main` on 2026-05-09 via `95b2fb1` |
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

## Sentinel Hardening — Acte 1 (2026-05-15)

L'audit interne `SENTINEL_V1_AUDIT_20260515.md` (1238 lignes, lecture
seule) a chiffré la sécurité Sentinel V1 à **5.5/10** avant rebranchement
public. L'Acte 1 du chantier de durcissement couvre les bloquants
systémiques. Les bloquants applicatifs (P0-1, P0-3, P1-5) sont
documentés ouvertement plus bas et planifiés pour l'Acte 2.

### systemd hardening (P0-2, commit `a326c00`)

Avant : `astroscan.service` tournait `User=root` sans aucune directive
de confinement. Une RCE dans l'un des 32 blueprints du monolithe =
root shell sur `/`. Sentinel héritait de cette posture.

Après : 14 directives de confinement appliquées via drop-in pour ne pas
toucher l'unité de base :

```
/etc/systemd/system/astroscan.service.d/hardening.conf
```

| Directive | Valeur | Effet |
|-----------|--------|-------|
| `NoNewPrivileges` | `yes` | bloque `setuid`/capabilities après fork |
| `ProtectSystem` | `strict` | `/usr`, `/boot`, `/etc` en read-only |
| `ProtectHome` | `yes` | masque `/home`, `/root` (sauf RW explicites) |
| `PrivateTmp` | `yes` | `/tmp` privé au service |
| `PrivateDevices` | `yes` | pas d'accès `/dev` hors PTY/null/zero/random |
| `ProtectKernelTunables` | `yes` | `/proc/sys`, `/sys` en read-only |
| `ProtectKernelModules` | `yes` | bloque `init_module` / `finit_module` |
| `ProtectKernelLogs` | `yes` | bloque `dmesg`-style access |
| `ProtectControlGroups` | `yes` | `/sys/fs/cgroup` en read-only |
| `RestrictAddressFamilies` | `AF_UNIX AF_INET AF_INET6` | bloque `AF_PACKET`, `AF_NETLINK`… |
| `RestrictNamespaces` | `yes` | bloque `unshare`, `CLONE_NEW*` |
| `LockPersonality` | `yes` | bloque `personality(2)` |
| `MemoryDenyWriteExecute` | `yes` | bloque W^X (mmap RWX, mprotect→exec) |
| `CapabilityBoundingSet` | `` (vide) | drop toutes les capabilities |
| `ReadWritePaths` | `/root/astro_scan/data /root/astro_scan/static /root/astro_scan/logs /var/log/astroscan` | seules zones inscriptibles |

`systemd-analyze security astroscan` :
**score 9.6 (EXPOSED) → 6.6 (MEDIUM)**. Validé via 13 contrôles
post-déploiement (HTTP 200, journalctl propre, ReadOnlyDirectories
effectif, etc.).

### `SENTINEL_SECRET_KEY` isolation (P1-4, commit `a326c00`)

Avant : `tokens.py` signait les jetons parent/driver Sentinel avec le
`SECRET_KEY` Flask global, partagé avec tout le monolithe ASTRO-SCAN
(32 blueprints, 291 routes). Toute fuite de `SECRET_KEY` (debug toolbar
oubliée, traceback non capturé, exfiltration via Sentry) compromettait
**l'intégralité des sessions Sentinel live** : un attaquant pouvait
signer ses propres tokens parent/driver et accéder aux positions GPS
temps-réel jusqu'à expiration (90 min max).

Après : `app/blueprints/sentinel/tokens.py` lit en priorité
`SENTINEL_SECRET_KEY` (variable d'environnement dédiée, 64 chars hex
générés via `secrets.token_hex(32)`, persistés dans
`/root/astro_scan/.env` en mode 600). Fallback transparent vers
`SECRET_KEY` si la variable dédiée est absente — aucune cassure de
compat pour les déploiements qui n'ont pas encore migré, et migration
sans downtime : il suffit d'ajouter la variable et de `systemctl restart
astroscan`.

Effet : une fuite du `SECRET_KEY` Flask global **n'exfiltre plus** la
capacité de forger des tokens Sentinel. La surface critique Sentinel
est désormais isolée d'un secret distinct, qui ne sort jamais d'un
seul module (`tokens.py`).

### Outstanding Sentinel risks — transparence

Les trois risques suivants restent ouverts. Ils sont documentés
publiquement plutôt que cachés, parce qu'un risque non divulgué est
plus dangereux qu'un risque connu :

| ID | Sévérité | Description | Mitigation prévue (Acte 2) |
|----|----------|-------------|-----------------------------|
| **P0-1** | Critique | `static/.well-known/assetlinks.json` ship avec `sha256_cert_fingerprints` vides → Android App Links non vérifiables, n'importe quel APK rebadgé sous `space.astroscan.sentinel.driver/parent` peut s'auto-certifier auprès du système. | Injecter les empreintes SHA-256 du keystore de production dès que la signing key Play Store est provisionnée. Pas avant rebranchement public. |
| **P0-3** | Critique | Les APK servis depuis `/modules/sentinel/*.apk` ne sont pas signés en prod, et le téléchargement HTTPS n'a pas de pinning côté client. Un MITM TLS device-side (CA d'entreprise installée, proxy parental, CA gouvernementale forcée) peut injecter un APK trojanisé. | Publier les deux APK sur Google Play (signature Play Integrity vérifiée par OS) et déprécier le téléchargement direct. Acte 2. |
| **P1-5** | Élevé | `public_state(sid, role)` retourne `last_lat`/`last_lon` à **quiconque détient un token parent ou driver valide**. Un token partagé par capture d'écran sur WhatsApp / indexé / fuité expose la position GPS temps-réel jusqu'à expiration (≤ 90 min). | Ajouter (a) un PIN à 4 chiffres optionnel exigé avant exposition de la position, (b) un masquage temporel (snap-to-grid 100 m + delay 30 s) en mode "public sharing", (c) un mode "blackout zones" pour la zone sûre. Acte 2. |

L'Acte 1 n'a **pas** levé ces 3 risques. Le statut "exposable publiquement"
reste **conditionnel** — voir verdict §1 de l'audit.

## Privacy & Anonymity by Design (Sentinel)

Sentinel est une plate-forme de « trajet protégé » familial. Le contrat
moral du produit est explicite : **jamais de surveillance, jamais de
tracking caché**. La posture privacy est encodée au niveau du code, pas
au niveau de la doc — chaque module Sentinel embarque l'invariant en
docstring d'ouverture, et le code respecte la promesse par construction.

### Architectural guarantees

| Surface | Garantie | Localisation dans le code |
|---------|----------|---------------------------|
| Position GPS temps-réel | écrite **uniquement** sur la ligne de session active (`sentinel_sessions.last_lat/last_lon`), jamais sur `sentinel_events`, jamais en log | `store.py:write_telemetry`, `audit_logger.py` strip défensif |
| Audit log applicatif | strip systématique des clés `lat`, `lon`, `latitude`, `longitude` dans les payloads d'event | `audit_logger.py` (94 lignes, défensif par construction) |
| Logs gunicorn / journalctl | aucune IP cliente loggée par Sentinel — les warnings du compteur GeoIP ne contiennent que `type(e).__name__` | `app/services/geoip_counter.py` |
| Anti-cut | DELETE SQL filtré sur états terminaux uniquement ; une session live n'est **jamais** supprimable silencieusement | `store.py:purge_old`, `anti_cut_engine.assert_no_silent_deletion` |
| Time-bound | TTL hard-cap 90 min, server-enforced, FSM `EXPIRED` automatique | `routes.py:MAX_TTL_SECONDS`, `session_manager.py` |
| Consent | conducteur doit accepter avant **toute** lecture GPS — pas de fallback silencieux | `consent_engine.py`, `routes.py:api_accept` |
| Dual-stop | aucune partie ne peut terminer unilatéralement une session live ; seul le TTL expire seul | `state_machine.py`, `store.py:request_stop`/`approve_stop` |

### Zero-knowledge country counters (Étape 2.6, 2026-05-15, commit `b30cfbb`)

Sentinel expose une page de stats publique (`GET /api/sentinel/stats`).
Elle ne contient **aucune IP, aucun token, aucun timestamp précis,
aucune session, aucun PII**. Le service derrière est `app/services/
geoip_counter.py`, dont le docstring d'ouverture est le contrat moral :

> ```
> Zero-knowledge GeoIP country counter for Sentinel.
>
> PRIVACY POSTURE — non-negotiable, baked into every method:
>
>   - IP addresses are resolved IN MEMORY ONLY.
>   - IPs are NEVER persisted (no DB, no log, no file, no exception payload).
>   - The only datum stored is the ISO 3166-1 alpha-2 country code (2 chars).
>   - Counters are aggregated and have NO link to a session, cookie, token,
>     or precise timestamp. Only first_seen_day / last_seen_day (YYYY-MM-DD).
>   - Private / loopback / link-local IPs and any lookup failure resolve
>     to the sentinel value ``"XX"`` — never raised, never logged with the IP.
>
> Conformity: GDPR Article 89 (aggregated statistical processing, no PII).
> ```

Schéma SQL associé (une seule table, 4 colonnes, aucune colonne IP) :

```sql
CREATE TABLE sentinel_country_counters (
    country_iso2    TEXT PRIMARY KEY,
    count           INTEGER NOT NULL DEFAULT 0,
    first_seen_day  TEXT NOT NULL,
    last_seen_day   TEXT NOT NULL
);
```

Le hook d'incrémentation vit dans `routes.py:api_create()` après création
de session : la variable `client_ip` est lue depuis `X-Forwarded-For` ou
`request.remote_addr`, passée à `resolve_country()` qui retourne 2 chars
en mémoire, puis **`del client_ip` immédiat**. La variable ne franchit
jamais une frontière de persistance.

### Public dashboard — `GET /api/sentinel/stats`

```json
{
  "ok": true,
  "data": null,
  "total_sessions_lifetime": 1247,
  "by_country": {
    "DZ": { "count": 821, "first_seen_day": "2026-04-12", "last_seen_day": "2026-05-15" },
    "FR": { "count": 312, "first_seen_day": "2026-04-13", "last_seen_day": "2026-05-15" },
    "DE": { "count": 64,  "first_seen_day": "2026-04-19", "last_seen_day": "2026-05-14" },
    "XX": { "count": 50,  "first_seen_day": "2026-04-12", "last_seen_day": "2026-05-15" }
  },
  "last_updated": "2026-05-15",
  "generated_at": "2026-05-15T18:30:00+00:00",
  "degraded": false,
  "privacy_note": "Zero-knowledge analytics. IP addresses are resolved in memory and never persisted. Only ISO 3166-1 alpha-2 country codes are stored, aggregated, with no link to any session, token, or precise time. Conforms to GDPR Article 89 (statistical processing)."
}
```

`"XX"` agrège : IP privées (LAN), loopback, link-local, IP non résolues
par MaxMind (anycast / nouvelles plages), et toute IP malformée. Aucune
de ces catégories ne fuite dans une bucket distincte — elles sont fondues.

### Legal posture

- **GDPR Article 89** (Union européenne) — traitement à fins
  statistiques. Sentinel ne stocke aucune donnée à caractère personnel
  dans les counters : ni IP, ni identifiant, ni timestamp précis. La
  granularité (pays + jour) est volontairement grossière pour rester
  hors du périmètre PII même au sens large.
- **Loi algérienne n° 18-07** relative à la protection des personnes
  physiques dans le traitement des données à caractère personnel
  (10 juin 2018). La nature agrégée et non-identifiante des compteurs
  les place hors champ. Les positions GPS temps-réel, elles, **sont**
  des données personnelles et restent encadrées par : consentement
  explicite du conducteur, time-bound 90 min, suppression automatique
  post-expiration via `purge_old(grace_seconds=600)`.

### What this does NOT promise

Honnêteté > marketing. Sentinel **ne garantit pas** :

- **Pas d'end-to-end encryption** sur le flux GPS conducteur → serveur →
  parent. Le canal TLS protège en transit ; le serveur (et donc
  l'opérateur de la prod, c'est-à-dire moi) voit les positions en clair
  pendant la durée de la session active. C'est volontaire : sans accès
  serveur aux positions, le SOS et les alertes survitesse ne peuvent
  pas être déclenchés côté serveur.
- **Pas de protection contre une réquisition judiciaire**. Si une
  autorité compétente exige les positions d'une session **en cours**,
  elles sont lisibles sur `sentinel_sessions.last_lat/last_lon` jusqu'à
  expiration. Après `ENDED`/`EXPIRED` + grâce de 10 min, la ligne est
  purgée — mais une copie système (backup, snapshot disque, swap) peut
  exister. Aucune promesse anti-forensic.
- **Pas de protection contre un device compromis**. Si l'OS Android ou
  le browser du conducteur est rooté / hooké / contrôlé par un MDM, la
  position est lisible avant même qu'elle n'arrive sur Sentinel. C'est
  hors périmètre.
- **Pas de protection contre un token fuité**. Si un parent ou un
  conducteur partage son lien sur un canal public (capture d'écran
  WhatsApp, screenshot Insta), n'importe quel détenteur du token lit la
  position jusqu'à expiration — voir P1-5 ci-dessus pour la mitigation
  Acte 2.

Cette section est le contrat que je peux tenir aujourd'hui. Le reste
est planifié, pas promis.

## Reference

- Audit complet PASS 26.A / 26.B :
  [`SECURITY_AUDIT_2026-05-04.md`](SECURITY_AUDIT_2026-05-04.md)
- Hardening endpoints PASS 28.SEC :
  [`SECURITY_HARDENING_REPORT.md`](SECURITY_HARDENING_REPORT.md)
- Audit complet Sentinel V1 (lecture seule, 1238 lignes) :
  [`SENTINEL_V1_AUDIT_20260515.md`](SENTINEL_V1_AUDIT_20260515.md)
- Plan de redesign Sentinel (cadrage produit + Mission Control pivot) :
  [`SENTINEL_REDESIGN_20260515.md`](SENTINEL_REDESIGN_20260515.md)
- Commits Acte 1 du durcissement Sentinel (branche `main`) :
  - `a326c00` — `feat(sentinel-security): Acte 1 — systemd hardening + SENTINEL_SECRET_KEY isolation`
  - `f19ecbb` — `chore(sentinel): Acte 1 — Étape 2.5 — MaxMind GeoLite2 infrastructure`
  - `b30cfbb` — `feat(sentinel-privacy): Acte 1 — Étape 2.6 — Zero-knowledge GeoIP country counters`

*Acte 1 of Sentinel hardening was co-architected with Anthropic's Claude
Opus 4.7 (via Claude Code) under human supervision and validation. All
patches were dry-run reviewed, applied chirurgically, and post-deploy
verified through 13 functional checks. The decision to mention this
explicitly follows the same disclosure principle as the threat model
above: an artefact whose origin is hidden is harder to audit.*
