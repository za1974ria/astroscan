# PHASE 1 — Audit architecture ASTRO-SCAN

**Date** : 2026-05-21 20:39 UTC
**Branche** : `feature/astro-brain-guardian` (depuis `main` post-merge PR #2)
**Tag snapshot** : `pre-astrobrain-20260521-203827` (poussé)
**Service prod** : `astroscan.service` — `active`, HTTP 200 sur `/` et `/api/sentinel/health`

---

## 1. IA / LLM existants dans le repo

### 1.1 Modules service
| Fichier | Rôle |
|---|---|
| `app/services/ai_translate.py` | Pipeline traduction multi-provider (Claude haiku-4-5 + Groq fallback) avec compteur `CLAUDE_CALL_COUNT` / `CLAUDE_MAX_CALLS` |
| `app/services/oracle_engine.py` | Streaming Claude Oracle (`call_claude_oracle_messages`, `oracle_claude_stream`) |
| `app/services/observatory_feeds.py` | Utilise `_call_claude` pour génération descriptions |
| `app/utils/llm_errors.py` | **Classifier d'erreurs LLM (déjà couvert 89% par Axe 1)** — `friendly_message`, `llm_error_response`, mapping bilingue |
| `app/workers/translate_worker.py` | Worker traduction (134 lignes, 0% cov, network-bound) |

### 1.2 Endpoints AI/explain existants (blueprint `ai_bp`)
| Route | Fichier | Note |
|---|---|---|
| `POST /api/astro/explain` | `app/blueprints/ai/__init__.py:405` | **DÉJÀ ROUTÉ** — Claude haiku, jamais à recoder |
| `POST /api/chat` | `app/blueprints/ai/__init__.py` | Chat AEGIS |
| `GET /api/aegis/status` | `app/blueprints/ai/__init__.py:259` | Compteurs AEGIS (claude_calls/claude_limit) |
| `POST /api/aegis/chat` | `app/blueprints/ai/__init__.py` | AEGIS chat |
| `POST /api/aegis/groq-ping`, `/api/aegis/claude-test` | idem | Diagnostics fournisseurs |
| `POST /api/translate` | `app/blueprints/ai/__init__.py` | Traduction front |

`app/blueprints/astro/__init__.py:7` confirme : "**Différé** : /api/astro/explain (deps _translate_to_french/_call_claude → PASS 11)" — la migration depuis monolithe a déjà été faite dans `ai_bp`.

### 1.3 Traces AEGIS
- `nasa_feeder.py`, `recovery/nasa_feeder.py` — feeders existants
- `aegis_auto.py`, `aegis_ireland_tracker.py`, `aegis_weekend_report.py` — scripts utilitaires racine
- `core/eye_of_aegis.py` — module séparé
- `app/blueprints/system/__init__.py`, `app/services/ai_translate.py` — références internes
- `backup/station_web_healthfix_20260501_030955.py` — backup

**AEGIS = existant et opérationnel.** Le nouveau `AstroBrain` est un layer DISTINCT (provider OpenAI GPT-5) qui coexiste sans interférer.

---

## 2. Modules pertinents pour la mission

### 2.1 Blueprints en place (32 enregistrés via `app/__init__.py:_register_blueprints`)

```
seo, apod, sdr, iss, i18n, api, pages, main, system, health, analytics,
export, export_global, cameras, archive, weather, astro, feeds, telescope,
ai, lab, research, satellites, nasa_proxy, version, ground_assets,
scan_signal, flight_radar, hilal, maintenance, paris_weather, sentinel
```

Aucun blueprint nommé `astrobrain` ou `guardian` — **les noms sont libres**.

### 2.2 Sentinel V1 (PRODUCTION — INTOUCHABLE)
- Path : `app/blueprints/sentinel/`
- Modules : `state_machine.py`, `speed_engine.py`, `battery_engine.py`, `anti_cut_engine.py`, `geo_engine.py`, `schemas.py`, `tokens.py`, `routes.py` (22 routes, 287 lignes)
- Couverture pytest Axe 1 : 89–100% sur les pure engines
- Politique : ZÉRO modification ce soir. C'est le module flagship de sécurité véhicule.

### 2.3 Services data publics
- `services/nasa_service.py` (86 stmts, cov 24%)
- `services/weather_service.py` (301 stmts, cov 13%)
- `services/orbital_service.py` (78 stmts, cov 27%)
- `services/circuit_breaker.py` (cov 87% post-Axe1)

Ces services sont consommables par `AstroBrain.explain_telemetry` via **import lecture seule**.

---

## 3. Variables d'environnement

`.env` est `0600 root:root` — non lisible par `zakaria`. Inspection via journalctl/grep environnement :

| Variable | Présence inférée |
|---|---|
| `SECRET_KEY` | Présent (Flask) |
| `ANTHROPIC_API_KEY` | **Présent** (Claude haiku-4-5 fonctionnel via `ai_bp`) |
| `GROQ_API_KEY` | **Présent** (référencé `ai_translate.py:407`) |
| `OPENAI_API_KEY` | **Inconnu — à vérifier en PHASE 3** |
| `SENTINEL_SECRET_KEY` | Présent (isolation P1-4 audit) |
| `SENTRY_DSN` | Référencé |

**Action PHASE 3** : si `OPENAI_API_KEY` absent → AstroBrain démarre en `LLM_DRY_RUN=1` automatique + warning log. L'app ne plante PAS.

---

## 4. Health endpoints existants

```
/api/sentinel/health        → ai_sentinel (probe production, 200)
/api/scan-signal/health     → blueprint scan_signal
/api/telescope/status       → blueprint telescope
/api/flight-radar/health    → blueprint flight_radar
/api/ground-assets/health   → blueprint ground_assets
/api/cache/status           → blueprint api (Redis)
/api/tle/status             → blueprint api (TLE freshness)
/api/modules-status         → blueprint api (module map)
/api/aegis/status           → blueprint ai (Claude/Groq counters)
/api/observatory/status     → blueprint cameras
```

**Nouveaux endpoints prévus PHASE 3/4** (préfixes uniques, pas de collision) :
```
/api/astrobrain/ask
/api/astrobrain/explain-telemetry
/api/astrobrain/health
/api/guardian/status
/api/guardian/incidents
/api/guardian/health
```

---

## 5. Logs

| Path | Contenu |
|---|---|
| `/root/astro_scan/logs/astroscan_structured.log` (+ rotations .1 à .5) | Logs JSON principaux (5.9 MB courant), `0640 root:root` |
| `/root/astro_scan/logs/gunicorn.out` | Sortie gunicorn (3.4 KB) |
| `/root/astro_scan/logs/backup.log`, `jwst_refresh.log`, `contact_messages.log` | Logs auxiliaires |
| `/root/astro_scan/logs/logrotate.conf` | Rotation configurée |

**Dir parent** : `drwxrwxr-x root:zakaria` — zakaria PEUT créer des sous-dirs.

**Nouveau (PHASE 3/4)** :
```
/root/astro_scan/logs/astrobrain/llm_client.log     (JSON append-only)
/root/astro_scan/logs/astrobrain/access.log         (requêtes routes)
/root/astro_scan/logs/guardian/incidents.jsonl      (incidents append-only)
```

`journalctl -u astroscan.service` : non accessible par zakaria sans `sudo` (groupe `systemd-journal` manquant). Les logs prod restent visibles via les fichiers locaux.

---

## 6. Exposition Nginx

| Site | Présent dans `sites-enabled/` |
|---|---|
| `astroscan` | ✓ |
| `astroscan.space` | ✓ |

Configs nginx non lisibles par zakaria (root-owned). **Action prudente** : tous les nouveaux endpoints `astrobrain/*` et `guardian/*` bind **localhost only** via décorateur `@require_localhost`. Aucune modification Nginx ce soir. Brief le confirme : "Aucun endpoint exposé publiquement via Nginx ce soir."

---

## 7. Factory `create_app()` — point d'extension

Fichier : `app/__init__.py`, fonction `_register_blueprints(app)` (lignes 140–211).

- 32 blueprints enregistrés en série
- Log final : `"[Blueprints] 32 blueprints + 8 hooks enregistrés"`
- Pas de try/except global → un blueprint qui échoue à l'import casse l'app

**Plan PHASE 3.7 / 4.5** : ajout EN BAS de `_register_blueprints()` AVEC try/except isolé par blueprint :

```python
try:
    from app.blueprints.astrobrain import bp as astrobrain_bp
    app.register_blueprint(astrobrain_bp, url_prefix='/api/astrobrain')
    log.info("[astrobrain] registered")
except Exception as e:
    log.warning("[astrobrain] registration failed (continuing): %s", e)

try:
    from app.blueprints.guardian import bp as guardian_bp
    app.register_blueprint(guardian_bp, url_prefix='/api/guardian')
    log.info("[guardian] registered")
except Exception as e:
    log.warning("[guardian] registration failed (continuing): %s", e)
```

C'est la SEULE modification d'un fichier existant prévue. Tout le reste = fichiers neufs.

---

## 8. Risk map (classification)

### ADDITIF (vert — sûr)
- Création `app/blueprints/astrobrain/` (5 fichiers : __init__.py, routes.py, service.py, prompts.py, rate_limit.py)
- Création `app/blueprints/guardian/` (6 fichiers : __init__.py, routes.py, agent.py, collectors.py, rules.py, audit_log.py)
- Création `services/llm_client.py` (wrapper bas niveau)
- Création `config/guardian_rules.yaml`
- Création `logs/astrobrain/`, `logs/guardian/` (sous-dirs)
- Création `tests/unit/test_*.py` et `tests/integration/test_*.py` neufs

### EXTENSION (orange — prudent, ADDITIVE-only)
- `app/__init__.py` : ajout de 2 blocs try/except register_blueprint EN FIN de fonction (pas de modif des 32 lignes existantes)
- `requirements.txt` : ajout 3 lignes (`openai>=1.50,<2`, `tenacity`, `pydantic`)
- `requirements-dev.txt` : éventuellement
- `.env` : ajout 6 vars (`OPENAI_API_KEY`, `ASTROBRAIN_MODEL_DEFAULT`, `ASTROBRAIN_MODEL_PREMIUM`, `ASTROBRAIN_DAILY_TOKEN_BUDGET`, `LLM_DRY_RUN`, `GUARDIAN_POLL_INTERVAL`, `GUARDIAN_ENABLED`) — Zakaria insère `OPENAI_API_KEY` séparément

### COLLISION (rouge — INTERDIT ce soir)
- `station_web.py` (11918 lignes — monolithe historique)
- `app/blueprints/sentinel/*` (V1 production)
- `app/blueprints/ai/*` (Claude + Groq existants — chevauchement fonctionnel mais ZÉRO modif)
- `app/blueprints/iss/*`, `app/blueprints/apod/*`, `app/blueprints/astro/*`
- `app/services/ai_translate.py`, `app/services/oracle_engine.py`
- `/etc/nginx/sites-enabled/*` (exposition publique)
- Branche `migration/phase-2c` (réservée Axe 2)
- Toute db dans `data/` (lecture seule via SQL si besoin)

---

## 9. Validation PHASE 1 (read-only respecté)

```
$ git status --short | wc -l
0  (working tree clean après checkout feature/astro-brain-guardian)

$ systemctl is-active astroscan.service
active

$ curl -sf http://127.0.0.1:5003/ -w "%{http_code}"
200

$ curl -sf http://127.0.0.1:5003/api/sentinel/health -w "%{http_code}"
200

$ make test (post-merge main)
338 passed, 101 skipped, 0 failed
```

Aucune création, modification, suppression. PHASE 1 = lecture exclusive.

---

## 10. Synthèse / next steps

| Item | Décision PHASE 2 |
|---|---|
| Noms blueprints `astrobrain` / `guardian` | Libres, retenus |
| Préfixes URLs `/api/astrobrain/*`, `/api/guardian/*` | Libres, retenus |
| Provider IA | OpenAI GPT-5 (`gpt-5-mini` défaut / `gpt-5` premium) — coexiste avec Claude/Groq existants |
| Décorateur `@require_localhost` | À créer en commun, partagé entre les 2 blueprints |
| Logs JSONL | Sous-dirs neufs sous `logs/` (zakaria a write sur le parent) |
| Modification `app/__init__.py` | Try/except blocs EN FIN de `_register_blueprints`, 2x ~6 lignes |
| `OPENAI_API_KEY` manquant | Mode `LLM_DRY_RUN=1` automatique, app démarre normalement |
| Rollback | Tag `pre-astrobrain-20260521-203827` + retrait blueprint 1 ligne (L1) |
