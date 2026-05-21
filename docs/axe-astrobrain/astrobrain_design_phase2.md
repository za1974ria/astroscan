# PHASE 2 — Design AstroBrain + Guardian (Session 1)

**Branche** : `feature/astro-brain-guardian`
**Politique** : ADDITIF uniquement, localhost-only, GPT-5 observe-only

---

## 1. Arborescence cible (delta vs existant)

```
app/
  blueprints/
    astrobrain/                    [NEW]
      __init__.py                  ─ expose `bp`
      routes.py                    ─ /api/astrobrain/{ask,explain-telemetry,health}
      service.py                   ─ AstroBrainService (ask/explain/summarize)
      prompts.py                   ─ 4 system prompts (< 800 chars chacun)
      rate_limit.py                ─ budget JSON + fcntl lock
      security.py                  ─ @require_localhost (partagé via import depuis guardian)
    guardian/                      [NEW]
      __init__.py                  ─ expose `bp`
      routes.py                    ─ /api/guardian/{status,incidents,health}
      agent.py                     ─ thread daemon (60s poll, configurable)
      collectors.py                ─ 9 probes read-only
      rules.py                     ─ évaluateur + cooldown
      audit_log.py                 ─ append-only JSONL writer

services/
  llm_client.py                    [NEW] ─ LLMClient + LLMResponse (openai + tenacity)

config/
  guardian_rules.yaml              [NEW] ─ règles déclaratives YAML

logs/
  astrobrain/                      [NEW dir]
    llm_client.log                 ─ JSON Lines (timestamp, model, tokens, latency, status)
    access.log                     ─ requêtes routes (sans payload)
  guardian/                        [NEW dir]
    incidents.jsonl                ─ incidents append-only

tests/
  unit/
    test_llm_client.py             [NEW] ─ retry, fallback, dry-run, no secret in logs
    test_astrobrain_prompts.py     [NEW] ─ presence + < 800 chars
    test_astrobrain_service.py     [NEW] ─ ask/explain/summarize w/ LLM_DRY_RUN=1
    test_astrobrain_rate_limit.py  [NEW] ─ budget + reset midnight + concurrency
    test_guardian_collectors.py    [NEW] ─ mocks subprocess/HTTP/fs
    test_guardian_rules.py         [NEW] ─ evaluator + cooldown
    test_require_localhost.py      [NEW] ─ décorateur (partagé)
  integration/
    test_astrobrain_routes.py      [NEW] ─ 3 endpoints + localhost guard
    test_guardian_routes.py        [NEW] ─ 3 endpoints + thread alive
    test_guardian_thread_boot.py   [NEW] ─ thread ne bloque pas le boot
```

**Modifications de fichiers existants** (limitées et review-friendly) :
- `app/__init__.py` — ajout de **2 blocs try/except** en fin de `_register_blueprints()` (lignes ~211)
- `requirements.txt` — ajout **3 lignes** (`openai>=1.50,<2`, `tenacity>=8`, `pydantic>=2`)
- `.env` — ajout **6 vars** (Zakaria insère `OPENAI_API_KEY` à part)
- `.gitignore` — ajout `logs/astrobrain/`, `logs/guardian/`, `data/astrobrain_budget.json`

C'est tout. Aucun autre fichier existant touché.

---

## 2. Endpoints (TOUS `@require_localhost`)

| Méthode | URL | Body | Réponse | Notes |
|---|---|---|---|---|
| `POST` | `/api/astrobrain/ask` | `{question: str, context?: dict}` | `{ok, answer, model, tokens:{in,out}, error?}` | Modèle par défaut `gpt-5-mini` |
| `POST` | `/api/astrobrain/explain-telemetry` | `{telemetry: dict, focus?: str}` | idem + `interpretation: dict` | Modèle `gpt-5` (premium) |
| `GET` | `/api/astrobrain/health` | — | `{ok, openai_key_present, model_default, model_premium, budget_remaining_today, dry_run}` | Public-readable (localhost) |
| `GET` | `/api/guardian/status` | — | `{ok, ts, snapshots:[...]}` | Dernier snapshot collectors |
| `GET` | `/api/guardian/incidents?since=1h` | `since` enum `15m|1h|6h|24h` | `{ok, count, incidents:[...]}` | Cap 500 |
| `GET` | `/api/guardian/health` | — | `{ok, thread_alive, last_tick_ago_s, ticks_total, llm_summaries_today}` | Self-status |

**Décorateur `@require_localhost`** (placé dans `app/blueprints/astrobrain/security.py`, importé par guardian) :

```python
def require_localhost(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        ra = (request.remote_addr or "").strip()
        if ra not in ("127.0.0.1", "::1", "localhost"):
            log.warning("[localhost-guard] refused %s on %s", ra, request.path)
            return jsonify({"ok": False, "error": "localhost_only"}), 403
        return fn(*a, **kw)
    return wrapper
```

---

## 3. Modèles OpenAI

| Variable | Défaut | Usage |
|---|---|---|
| `ASTROBRAIN_MODEL_DEFAULT` | `gpt-5-mini` | `ask()`, `summarize_health()`, Guardian diagnostics |
| `ASTROBRAIN_MODEL_PREMIUM` | `gpt-5` | `explain_telemetry()`, anomaly analysis |

**Fallback runtime** : si l'API OpenAI rejette le modèle (`404 model_not_found` ou `BadRequestError`) :
1. Log WARNING avec le message exact d'erreur (sans clé)
2. Réessaie une fois avec un modèle "safe" (`gpt-4o-mini` si disponible, sinon `LLMResponse(ok=False, fallback=True)`)
3. **Ne crash jamais l'app**

GPT-5 family validation différée au runtime (PHASE 3.1) — si Zakaria n'a pas encore accès, mode `LLM_DRY_RUN=1` automatique.

---

## 4. Token budget protection

| Paramètre | Valeur | Justification |
|---|---|---|
| `max_tokens_output` (par requête) | 1500 | Réponse riche mais bornée |
| `max_tokens_input_estimate` (truncate) | 4000 | Évite surprise prompt-injection |
| `ASTROBRAIN_DAILY_TOKEN_BUDGET` | 200 000 | Env var, défaut |
| Stockage compteur | `data/astrobrain_budget.json` | Concurrency-safe via `fcntl.flock` |
| Reset | Minuit UTC | Lecture date courante au début |
| Dépassement | HTTP 429 | `{ok: false, error: "daily_token_budget_exceeded"}` |

**Fichier budget format** :
```json
{"date": "2026-05-21", "tokens_used": 12345, "tokens_budget": 200000, "requests": 14}
```

**Concurrency** : `fcntl.flock(LOCK_EX)` sur lecture et écriture. Gunicorn lance 4 workers → 4 lockers possibles. Test unit avec threading + flock simulé.

---

## 5. Sécurité endpoints

### Localhost-only
- Vérification `request.remote_addr ∈ {127.0.0.1, ::1, localhost}` — toute autre IP → 403 JSON
- Aucune dépendance Authorization header pour le moment (Session 2 ajoutera HMAC ou JWT)

### Nginx
- **PAS** de nouveau `location /api/astrobrain/*` ni `/api/guardian/*` côté Nginx ce soir
- Vérification finale : `grep -r "astrobrain\|guardian" /etc/nginx/sites-enabled/ → vide attendu`
- Si Nginx forwarde déjà `/` vers Gunicorn (catch-all), `@require_localhost` bloque côté Flask car `X-Forwarded-For` n'est PAS lu par défaut par Flask (utilise `remote_addr` direct = IP du socket = Gunicorn → 127.0.0.1, mais l'IP CLIENT vient via `X-Real-IP`/`X-Forwarded-For`)

**Mitigation `@require_localhost`** v2 :
```python
# Check both: socket peer must be loopback AND no proxy headers indicate external client
ra = request.remote_addr
xff = request.headers.get("X-Forwarded-For", "")
xri = request.headers.get("X-Real-IP", "")
if ra not in ("127.0.0.1", "::1") or xff or xri:
    return 403
```

→ Si Nginx forwarde, le header `X-Forwarded-For` sera présent → 403. Endpoint EXCLUSIVEMENT accessible via `curl localhost`/`curl 127.0.0.1` directement sur Gunicorn. Conforme à "Aucun endpoint exposé publiquement ce soir".

### Logs
- Pas de payload sensible loggé (question/réponse en clair seulement si DEBUG=1)
- Aucune clé d'API ni token JAMAIS dans les logs (tests vérifient)

---

## 6. Logs JSON Lines

### `logs/astrobrain/llm_client.log`
```json
{"ts":"2026-05-21T20:42:11Z","level":"info","model":"gpt-5-mini","tokens_in":523,"tokens_out":412,"latency_ms":1820,"status":"ok"}
{"ts":"...","level":"warn","model":"gpt-5","tokens_in":1024,"tokens_out":0,"latency_ms":20000,"status":"timeout","attempt":2}
```

### `logs/astrobrain/access.log`
```json
{"ts":"...","method":"POST","path":"/api/astrobrain/ask","remote_addr":"127.0.0.1","status":200,"latency_ms":1834}
```

### `logs/guardian/incidents.jsonl`
```json
{"ts":"...","rule":"disk_usage_critical","severity":"critical","metric":"disk.percent_used","value":92.1,"threshold":90,"cooldown_until":"..."}
```

Rotation : pas de logrotate dédié ce soir (Session 2). Tailles surveillées dans Guardian (rule future).

---

## 7. Rollback plan

| Niveau | Action | RTO |
|---|---|---|
| **L1** | Commenter les 2 blocs try/except dans `app/__init__.py` + `systemctl restart astroscan` | 30s |
| **L2** | `git revert <merge-commit-feature>` puis `git push origin main` + restart | 2 min |
| **L3** | `git reset --hard pre-astrobrain-20260521-203827 && systemctl restart astroscan` | 30s (urgence) |

Tag de référence : `pre-astrobrain-20260521-203827` (poussé sur origin).

---

## 8. Variables d'environnement (.env additions)

```dotenv
# === Astro Brain (Session 1) ===
OPENAI_API_KEY=<INSERT_BY_ZAKARIA_IF_AVAILABLE>
ASTROBRAIN_MODEL_DEFAULT=gpt-5-mini
ASTROBRAIN_MODEL_PREMIUM=gpt-5
ASTROBRAIN_DAILY_TOKEN_BUDGET=200000
LLM_DRY_RUN=0

# === Guardian (Session 1) ===
GUARDIAN_POLL_INTERVAL=60
GUARDIAN_ENABLED=1
```

**Si `OPENAI_API_KEY` absent au démarrage** :
- `LLM_DRY_RUN=1` auto-activé (override interne, log WARNING)
- `AstroBrain.ask()` retourne réponses stubbées non-LLM
- Guardian fonctionne sans appels LLM (textes de diagnostic basiques)
- Aucun crash

Permission `.env` : reste `0600 root:root` (intouchée).

---

## 9. Plan d'enregistrement blueprints

Patch `app/__init__.py` (en FIN de `_register_blueprints()`, après ligne 211) :

```python
    # Axe Astro Brain + Guardian (Session 1) — registrations isolées
    # (si import/registration échoue, l'app continue à démarrer normalement)
    try:
        from app.blueprints.astrobrain import bp as astrobrain_bp
        app.register_blueprint(astrobrain_bp, url_prefix="/api/astrobrain")
        log.info("[astrobrain] blueprint registered")
    except Exception as e:
        log.warning("[astrobrain] registration failed (continuing): %s", e)

    try:
        from app.blueprints.guardian import bp as guardian_bp
        app.register_blueprint(guardian_bp, url_prefix="/api/guardian")
        log.info("[guardian] blueprint registered")
    except Exception as e:
        log.warning("[guardian] registration failed (continuing): %s", e)
```

12 lignes ajoutées, 0 ligne modifiée. Review-friendly.

---

## 10. Stratégie tests

| Layer | Type | Network | LLM_DRY_RUN |
|---|---|---|---|
| `services/llm_client.py` | unit | mocked openai client | n/a |
| `app/blueprints/astrobrain/{service,prompts,rate_limit}.py` | unit | n/a | 1 |
| `app/blueprints/astrobrain/routes.py` | integration via Flask test client | n/a | 1 |
| `app/blueprints/guardian/collectors.py` | unit | mocks subprocess/urllib/fs | n/a |
| `app/blueprints/guardian/rules.py` | unit | n/a | n/a |
| `app/blueprints/guardian/routes.py` | integration | n/a | 1 |
| Localhost guard | unit | n/a | n/a |
| Thread boot timing | integration | n/a | 1 |

Cible coverage modules NEW : ≥ 80%. Pas de fail-under change pour CI (déjà à 20%).

---

## 11. Décisions non-évidentes

1. **Pourquoi `@require_localhost` ET headers proxy-check ?** Le X-Forwarded-For présent indique passage par Nginx → public. Doubler le check empêche la fuite future si quelqu'un ajoute un `location /api/astrobrain/*` dans Nginx sans s'en rendre compte.

2. **Pourquoi `fcntl.flock` et pas SQLite ?** SQLite WAL apporte de la complexité (DB schema, init, migration). Le compteur quotidien tient en 100 octets JSON. `flock` est posix-native, zéro dépendance, testable.

3. **Pourquoi thread daemon vs systemd timer ?** Le brief impose `before_serving` (Flask). Un timer systemd nécessiterait un service séparé donc rupture du périmètre "intra-application". Thread daemon avec deque mémoire + JSONL append-only.

4. **Pourquoi pas de dashboard ce soir ?** Brief : "Command Center Dashboard" est explicitement reporté Session 2. Les endpoints JSON sont prêts à être consommés par un dashboard futur.

5. **Pourquoi un nouveau LLM provider alors qu'AEGIS existe ?** AEGIS = Claude/Groq (Anthropic + Groq). AstroBrain = OpenAI GPT-5. Coexistence pour redondance + comparaison qualité + portfolio multi-provider (ESA/CNES/NASA recruiters). Les deux layers ne se touchent JAMAIS.

---

## 12. Validation PHASE 2

Document fini, aucune modification de code. Service prod still `active`.

→ Feu vert PHASE 3.
