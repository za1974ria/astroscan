# SECURITY HARDENING REPORT — PASS 28.SEC

**Date** : 2026-05-09
**Branche** : `security/rate-limit-admin`
**Auteur** : Zakaria Chohra (+ Claude Opus 4.7)
**Objectif** : verrouiller les endpoints à coût IA (anti-drainage financier)
et les endpoints qui mutent la DB (anti-troll).

---

## 1. Résumé exécutif

Deux décorateurs stdlib-only ajoutés dans `app/services/security.py` :

- `@require_admin` — fail-closed sur `ADMIN_TOKEN` env, header
  `X-Admin-Token` (ou `Authorization: Bearer` legacy).
- `@rate_limit_ip(max_per_minute, key_prefix)` — fenêtre glissante 60s,
  process-local, headers `X-RateLimit-*` + `Retry-After` sur 429.

8 endpoints IA rate-limités, 6 endpoints admin protégés. Aucune
nouvelle dépendance, pattern lazy-import préservé, prod inchangée
côté API publique (293 routes avant/après).

---

## 2. Avant / après par endpoint

### 2.1 Endpoints IA — rate-limit (anti-drainage Claude/Gemini/Groq/Grok)

| Endpoint | Backend IA | Avant | Après |
|----------|------------|-------|-------|
| `POST /api/chat` | Claude / Groq | aucune limite | **10/min/IP** |
| `POST /api/aegis/chat` | Claude haiku | aucune | **8/min/IP** |
| `POST /api/oracle-cosmique` | Claude streaming | aucune | **3/min/IP** |
| `POST /api/guide-stellaire` | Claude **OPUS** | aucune | **2/min/IP** |
| `POST /api/translate` | Gemini | aucune | **20/min/IP** |
| `POST /api/astro/explain` | Claude | aucune | **10/min/IP** |
| `POST /api/science/analyze-image` | Claude vision | aucune | **5/min/IP** |
| `POST /api/sky-camera/analyze` | Claude vision | aucune | **5/min/IP** |

### 2.2 Endpoints admin — auth (anti-troll DB)

| Endpoint | Mutation | Avant | Après |
|----------|----------|-------|-------|
| `POST /api/visits/reset` | reset compteur visites | public | **X-Admin-Token requis** |
| `POST /api/owner-ips` | ajout IP propriétaire | public | **X-Admin-Token requis** |
| `DELETE /api/owner-ips/<int:ip_id>` | suppression IP propriétaire | public | **X-Admin-Token requis** |
| `POST /api/system-heal` | auto-heal core | public | **X-Admin-Token requis** |
| `POST /api/telescope/trigger-nightly` | trigger capture nightly | public | **X-Admin-Token requis** |
| `POST /api/tle/refresh` | refresh TLE manuel | public | **X-Admin-Token requis** |

### 2.3 Sémantique des codes de retour

| Cas | Code | Body |
|-----|------|------|
| Admin sans `ADMIN_TOKEN` configuré (fail-closed) | **503** | `{"error":"Admin endpoint disabled (ADMIN_TOKEN not configured)"}` |
| Admin sans header / mauvais token | **401** | `{"error":"Unauthorized"}` |
| Rate-limit dépassé | **429** | `{"error":"Rate limit exceeded — retry later", "retry_after":N, "limit":N, "window_sec":60}` + headers `Retry-After` / `X-RateLimit-*` |

---

## 3. Validation locale

### 3.1 Tests unitaires (`tests/unit/test_security.py`)

13/13 PASS en 0.21s :

```
test_require_admin_fail_closed_when_token_unset                 PASSED
test_require_admin_401_without_header                            PASSED
test_require_admin_401_with_wrong_token                          PASSED
test_require_admin_200_with_correct_x_admin_token                PASSED
test_require_admin_200_with_authorization_bearer_fallback        PASSED
test_require_admin_uses_legacy_astroscan_admin_token             PASSED
test_rate_limit_passes_below_limit                               PASSED
test_rate_limit_blocks_above_limit                               PASSED
test_rate_limit_headers_present_on_success                       PASSED
test_rate_limit_headers_present_on_429                           PASSED
test_rate_limit_per_ip_isolation                                 PASSED
test_rate_limit_sliding_window_60s                               PASSED  (clock mocké, fenêtre 60s validée)
test_rate_limit_x_forwarded_for_used_for_keying                  PASSED
```

Suite complète : 42 passed / 5 skipped (skips préexistants liés à
`.env` non lisible par l'utilisateur de test ; production tourne en
root et n'est pas affectée).

### 3.2 Boot de la factory en mode `production`

```
PROD APP BOOTED: 293 routes
TARGETS PRESENT: 13/13
```

Les 13 endpoints ciblés (8 IA + 6 admin, dont `/api/owner-ips` qui
combine GET/POST/DELETE) sont tous enregistrés. Aucune régression
sur le compte de routes (293 avant/après).

### 3.3 Smoke test endpoints (Flask test_client sur factory `production`)

```
--- ADMIN endpoints (token = "smoke-token-xyz") ---
  POST /api/visits/reset (no token)            -> 401  ✓
  POST /api/visits/reset (bad token)           -> 401  ✓
  POST /api/visits/reset (X-Admin-Token OK)    -> 500  ✓ décorateur passé,
                                                       handler échoue car DB
                                                       en read-only dans
                                                       l'env de smoke
  POST /api/visits/reset (Authorization Bearer)-> 500  ✓ idem (compat legacy)

--- RATE-LIMIT /api/guide-stellaire (limit=2/min) ---
  5 hits successifs                            -> [502, 502, 429, 429, 429]  ✓
  Headers 429                                  -> Retry-After=57
                                                   X-RateLimit-Limit=2
                                                   X-RateLimit-Remaining=0  ✓

--- PUBLIC endpoints (non touchés) ---
  GET /api/health                              -> 200  ✓
  GET /api/version                             -> 200  ✓
  GET /api/visits                              -> 200  ✓
```

Les 502 sur les 2 premiers hits de `/api/guide-stellaire` proviennent
de l'absence de clé Claude dans l'env de smoke (le décorateur a
correctement laissé passer la requête, c'est le handler qui a échoué
en aval). Comportement attendu : c'est exactement la sémantique
"décorateur transparent → handler classique" recherchée.

> **Note** : le smoke test live via `gunicorn 127.0.0.1:5004` tel que
> décrit dans le workflow nécessite root (DB `archive_stellaire.db` en
> `root:zakaria 644`, `.env` en `root:zakaria 600`, `logs/` non
> writable par zakaria). Le test équivalent via `Flask.test_client()`
> sur la factory `production` complète a été utilisé et a validé les
> mêmes invariants (codes HTTP, headers, comportement RL).

---

## 4. Métriques à monitorer en prod

### 4.1 Indicateurs principaux

| Métrique | Source | Alerte si |
|----------|--------|-----------|
| Taux de 429 sur les 8 endpoints IA | logs `astroscan.security` (`rate_limit_block`) | > 5% des requêtes IA sur 5 min ⇒ tuning des limites ou attaque |
| Taux de 401 sur les 6 endpoints admin | logs `astroscan.security` (`admin_unauthorized`) | > 10/min ⇒ scan / brute-force ⇒ envisager fail2ban + ban IP |
| Taux de 503 admin | logs `astroscan.security` (`admin_endpoint_disabled`) | > 0 ⇒ `ADMIN_TOKEN` non chargé en env (incident config) |
| Latence p95 sur les 8 endpoints IA | logger `[WEB]` (`http_request`) | inchangée vs baseline (overhead RL ≈ 1µs) |
| Mémoire `_API_RATE_HITS` | introspection process | > 8000 entrées ⇒ garde-fou interne se déclenche, OK |

### 4.2 Commandes utiles

```bash
# Distribution des codes HTTP sur la dernière heure
journalctl -u astroscan --since "1 hour ago" \
  | grep '"event": "http_request"' \
  | jq -r '.status_code' | sort | uniq -c | sort -rn

# Compte des rejets RL par endpoint (5 dernières min)
journalctl -u astroscan --since "5 min ago" \
  | grep "rate_limit_block" | grep -oP "prefix=\K[^ ]+" | sort | uniq -c

# IPs qui tapent admin sans token (5 dernières min)
journalctl -u astroscan --since "5 min ago" \
  | grep "admin_unauthorized" | grep -oP "ip=\K[^ ]+" | sort | uniq -c
```

### 4.3 Tableau de bord (à câbler)

- Grafana / Prometheus exporter optionnel (Phase 2D) :
  `astroscan_rate_limit_blocks_total{endpoint=…}`,
  `astroscan_admin_unauthorized_total{endpoint=…}`.

---

## 5. Limites connues

### 5.1 Rate-limit non distribué (process-local)

Le compteur `_API_RATE_HITS` vit dans la mémoire de chaque worker
gunicorn. Avec **4 workers** en production :

- En théorie : limite effective ≈ `4 × max_per_minute` (un client
  malveillant peut émettre jusqu'à 4× la limite en touchant chaque
  worker).
- En pratique : Nginx avec un load-balancer round-robin par défaut
  répartit les requêtes ; pour `/api/guide-stellaire` à 2/min, un
  burst de 8 requêtes en 60s peut effectivement passer (2 par worker).

**Acceptabilité** :
- ✅ Bloque l'abus naïf et les boucles `for i in range(100)`.
- ✅ Limite l'exposition au drainage de quotas IA d'un facteur ~10×
  (cas typique : un troll lance 50 req → seules ~8 passent).
- ⚠️ Insuffisant pour un rate-limit strict global (besoin légal,
  quota dur opérateur, etc.).

### 5.2 Token unique

`require_admin` valide un token unique. Pas de support multi-utilisateurs
(suffisant tant que l'admin = Zakaria). Pas de scopes / permissions.

### 5.3 `X-Forwarded-For` confiance

La clé de rate-limit utilise `X-Forwarded-For` en priorité (Nginx
l'injecte). Un client direct sans Nginx pourrait spoofer. Non exposé
en prod (Nginx est le seul point d'entrée public, 127.0.0.1:5003 est
loopback uniquement).

### 5.4 Pas de blacklist persistante

Un attaquant qui dépasse le RL est juste mis en attente. Pas de ban
progressif. À combiner avec fail2ban Nginx si volume devient
problématique.

---

## 6. TODO Phase 2D — Rate-limit distribué (Redis)

### 6.1 Pourquoi

Les limites du § 5.1 deviennent gênantes si :
- on monte à 8+ workers gunicorn,
- on déploie un second backend (HA),
- un quota IA opérateur (Anthropic) impose un plafond global strict.

### 6.2 Architecture cible

```
Client → Nginx → Gunicorn worker N
                    │
                    └─> @rate_limit_ip ──> Redis (INCR + EXPIRE)
                                           ├── clé : rl:{prefix}:{ip}
                                           ├── TTL : 60s
                                           └── pipeline atomique
```

Pattern fixed window via `INCR` + `EXPIRE` (atomique, simple), ou
fenêtre glissante via `ZADD`/`ZRANGEBYSCORE` (plus précis, plus cher).

### 6.3 Plan de migration

1. Ajouter `redis` à `requirements.txt`.
2. `app/services/security.py` : nouveau backend `_rate_limit_redis_allow`
   sélectionné via env `RATE_LIMIT_BACKEND=redis|memory` (default
   `memory`, fallback automatique sur erreur Redis).
3. Ajouter `REDIS_URL=redis://127.0.0.1:6379/1` à `.env.example`.
4. Conserver les tests existants (backend mémoire), ajouter un set
   `tests/integration/test_security_redis.py` derrière un `@pytest.mark.skipif`
   sur l'absence de Redis local.
5. Bench avant/après sur `/api/chat` (overhead attendu ≈ 0.3–0.5 ms).
6. Rollout progressif : `RATE_LIMIT_BACKEND=memory` (état actuel) →
   `redis` après validation 24h sur staging.

### 6.4 Coûts estimés

- Redis local (déjà déployé pour cache circuit-breaker — voir
  `app/utils/cache.py`) : **0 €** d'infra supplémentaire.
- Latence ajoutée : 0.3–0.5 ms par appel rate-limité (loopback Redis).
- Effort dev : ~0.5 j (extension propre, pas de réécriture).

### 6.5 Autres pistes Phase 2D

- [ ] Rotation périodique automatique d'`ADMIN_TOKEN` (cron
      mensuel + notification Slack/email).
- [ ] Métrique Prometheus `astroscan_rate_limit_*_total` pour Grafana.
- [ ] Fail2ban Nginx sur 401 répétés (admin scan brute-force).
- [ ] Audit log structuré séparé pour les actions admin
      (qui a appelé quoi quand, indépendant du log app).

---

## 7. Procédure de mise en production

> **Étape 7 du workflow** — à exécuter en root après merge de la branche.

```bash
# 1. Générer un token solide (32 octets hex)
TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "Generated: ${TOKEN:0:8}…"

# 2. Persister dans /root/astro_scan/.env
#    (root only, mode 600)
sed -i "/^ADMIN_TOKEN=/d" /root/astro_scan/.env
echo "ADMIN_TOKEN=$TOKEN" >> /root/astro_scan/.env
chmod 600 /root/astro_scan/.env

# 3. Restart
systemctl restart astroscan
sleep 5
systemctl is-active astroscan
journalctl -u astroscan -n 50 --no-pager | grep -E "ERROR|Traceback" || echo "no errors"

# 4. Vérifs live
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:5003/api/visits/reset
# Attendu : 401

curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:5003/api/visits/reset \
  -H "X-Admin-Token: $TOKEN"
# Attendu : 200

for i in {1..5}; do
  curl -s -o /dev/null -w "%{http_code} " -X POST http://127.0.0.1:5003/api/guide-stellaire \
    -H "Content-Type: application/json" -d '{}'
done; echo
# Attendu : 2 ou 3 codes "valides" puis des 429

curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5003/api/health
# Attendu : 200
```

### Rollback

Si quoi que ce soit casse (gunicorn crash, /api/health passe à 401,
etc.) :

```bash
git checkout main
systemctl restart astroscan
journalctl -u astroscan -n 100 --no-pager
```

---

## 8. Fichiers modifiés

```
 .env.example                         |  24 ++++++
 app/blueprints/ai/__init__.py        |   7 ++
 app/blueprints/analytics/__init__.py |   5 ++
 app/blueprints/cameras/__init__.py   |   2 +
 app/blueprints/health/__init__.py    |   3 +
 app/blueprints/research/__init__.py  |   2 +
 app/blueprints/system/__init__.py    |   3 +
 app/blueprints/telescope/__init__.py |   3 +
 app/services/security.py             | 146 +++++++++++++++++++++++++-
 SECURITY.md                          |  76 ++++++++++++++
 SECURITY_HARDENING_REPORT.md         | (ce fichier)
 tests/unit/test_security.py          | 195 +++++++++++++++++++++++++++++++++++ (nouveau)
```
