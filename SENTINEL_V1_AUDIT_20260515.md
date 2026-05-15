# SENTINEL V1 — AUDIT COMPLET (CODE EN PRODUCTION)

> Cible auditée : `/root/astro_scan/app/blueprints/sentinel/` (Flask blueprint intégré au monolithe ASTRO-SCAN, Gunicorn :5003, service `astroscan.service`).
> V2 (squelette `/home/zakaria/sentinel_prod/` archivé sous `/home/zakaria/.archive_sentinel_v2_squelette_20260515/`) est **ignoré** sauf section 8.
> Lecture seule. Aucune modification de code. Pas de secret reproduit.

---

## 1. RESUME EXECUTIF

**Que fait Sentinel V1 ?** Une plate-forme web/mobile de « trajet protégé » familial avec sessions à durée limitée, FSM dual-stop anti-coupure, alertes survitesse/zone-sûre/batterie/signal, SOS non-terminal et notifications FCM (parent + conducteur), distribuée publiquement via deux APK Android signés liés à `astroscan.space` via Digital Asset Links.

| Axe | Note /10 | Justification courte |
|-----|----------|----------------------|
| Architecture | **8.5** | Découpage propre route→manager→engines→store, FSM isolée, audit-logger central, contrat « pas de lat/lon dans events » respecté par construction. |
| Sécurité | **5.5** | Tokens itsdangerous propres + rate-limit IP par endpoint, mais service tourne en `User=root` sans aucun `ProtectSystem/NoNewPrivileges`, assetlinks vide (App Links non vérifiable), SECRET_KEY = clé Flask globale partagée avec tout le reste, pas de CSRF côté HTML, headers HSTS/COOP/CSP absents au niveau app. |
| Qualité code | **8** | PEP-8 propre, docstrings sur chaque module, aucun TODO/FIXME/HACK, aucun code mort détecté, séparation pure des engines. Zéro test unitaire. |
| Prod-readiness | **4** | Code stable et en `active` sur :5003, mais : pas de backup DB dédié, pas de log file persistant pour `astroscan.sentinel.*`, journalctl muet (faute de droits côté audit), pas de monitoring, FCM non provisionné (PyJWT absent du requirements + service account non posé), assetlinks sans fingerprint → App Links cassés. |
| Documentation | **6.5** | Excellents commentaires en tête de chaque module (posture légale, invariants, FSM) ; aucun README opérationnel, aucun runbook, aucune doc API exposée. |
| Complétude métier | **8** | Toute la boucle : create → accept → update → SOS → stop_request → stop_approve → ended ; FCM Phase A intégré dans tous les triggers ; deprecation redirects propres ; APK servis correctement. Manque : Web Push (le code FCM est Android-only par schéma), réémission SOS périodique, persistance audit côté logs externes. |

**Top 5 risques bloquants pour rebranchement public :**

1. **P0 — `assetlinks.json` ne contient AUCUN `sha256_cert_fingerprints`.** Tous les Digital Asset Links Android échoueront → autoVerify off → l'APK ouvrira un chooser au lieu de capturer ses propres liens. Et n'importe quel APK rebadgé sous le même `package_name` peut s'auto-certifier.
2. **P0 — `astroscan.service` tourne `User=root` sans `NoNewPrivileges`, `ProtectSystem`, `PrivateTmp`, `ReadWritePaths`.** Une RCE n'importe où dans les 32 blueprints du monolithe = root shell sur tout `/`. Sentinel hérite de cette posture.
3. **P0 — APK servis publiquement non signés en prod (fingerprints vides) et téléchargés en clair depuis HTTPS sans pinning.** Un MITM TLS sur le device (CA installée, proxy d'entreprise, etc.) injecterait un APK trojanisé. Le `package_name` est lisible (`space.astroscan.sentinel.driver/parent`).
4. **P1 — Le `SECRET_KEY` qui signe les tokens parent/driver est le SECRET_KEY Flask global de tout le monolithe ASTRO-SCAN.** Si une autre route du monolithe leak la SECRET_KEY (debug toolbar, traceback non capturé, fuite Sentry), un attaquant signe ses propres tokens Sentinel et accède à toutes les sessions live.
5. **P1 — Aucun garde sur le contenu lat/lon servi.** `public_state` retourne `last_lat/last_lon` à quiconque détient un token parent OU driver valide. Si un token est partagé sur WhatsApp puis indexé (capture d'écran, lien copié), la position GPS temps-réel est lisible jusqu'à expiration (jusqu'à 90 min).

**Top 5 forces :**

1. **FSM purement fonctionnelle isolée** (`state_machine.py`, 40 lignes) — un seul endroit pour comprendre toutes les transitions valides.
2. **Anti-cut by design** : `assert_no_unilateral_termination` + DELETE SQL filtré sur états terminaux + dual-stop SQL (UPDATE conditionnel sur `state IN (...)`). C'est cohérent à 3 niveaux.
3. **Audit-logger central et défensif** : strip `lat/lon/latitude/longitude` au cas où un appelant slip la position dedans → impossible de polluer `sentinel_events` avec de la PII GPS.
4. **Rate-limiting déjà câblé sur les 11 endpoints API** via `@rate_limit_ip` (granularité par endpoint, fenêtre glissante 60s, headers `X-RateLimit-*`).
5. **Fail-soft total sur FCM** : `is_configured()` court-circuite tout si pas de service-account → la session lifecycle est strictement orthogonale au push (jamais une dépendance dure).

**Verdict final :** Exposable publiquement avant le 31 mai **conditionnellement**. Trois bloquants doivent être levés (durcissement systemd, fingerprints APK injectés dans assetlinks, isolation SECRET_KEY Sentinel) **avant** retrait du `return 404` nginx. Tout le reste (tests, monitoring, backups DB) peut suivre post-rebranchement. Estimation effort minimal : **6–9 h ingénieur** (détail section 9).

---

## 2. INVENTAIRE FONCTIONNEL COMPLET

### 2.1 Modules — comparaison réel vs attendu

| Module | Lignes attendues | Lignes réelles | Δ | Statut |
|--------|------------------|----------------|---|--------|
| `routes.py` | 429 | 429 | 0 | complet |
| `store.py` | 428 | 428 | 0 | complet |
| `push_engine.py` | 225 | 225 | 0 | complet (mais non provisionné) |
| `session_manager.py` | 178 | 178 | 0 | complet |
| `schemas.py` | 151 | 151 | 0 | complet |
| `alert_engine.py` | 113 | 113 | 0 | complet |
| `audit_logger.py` | 94 | 94 | 0 | complet |
| `geo_engine.py` | 84 | 84 | 0 | complet |
| `speed_engine.py` | 66 | 66 | 0 | complet |
| `telemetry_engine.py` | 65 | 65 | 0 | complet |
| `anti_cut_engine.py` | 46 | 46 | 0 | complet |
| `tokens.py` | 46 | 46 | 0 | complet |
| `consent_engine.py` | 45 | 45 | 0 | complet |
| `state_machine.py` | 40 | 40 | 0 | complet |
| `battery_engine.py` | 15 | 15 | 0 | complet |
| `__init__.py` | 4 | 4 | 0 | complet |
| **TOTAL** | **2029** | **2029** | **0** | — |

Cohérence parfaite avec l'inventaire annoncé. Aucun stub. Aucun module fantôme.

### 2.2 Détail par module

#### `__init__.py` (4 lignes)
Importe `sentinel_bp` depuis `routes.py` pour exposition externe. Pas d'effet de bord. **Complet.**

#### `state_machine.py` (40 lignes)
- Constantes : `PENDING_DRIVER`, `ACTIVE`, `STOP_PENDING_PARENT`, `STOP_PENDING_DRIVER`, `ENDED`, `EXPIRED`, `LIVE` (tuple), `TERMINAL` (tuple).
- Fonctions : `can_driver_update(state)`, `can_request_stop(state, requester)`, `state_after_request(requester)`, `approver_for(state)`.
- **Logique :** FSM pure, sans I/O ni dépendance externe. Module-feuille.
- **Dépendances :** aucune.
- **Statut :** complet.

#### `tokens.py` (46 lignes)
- `_serializer()` → `URLSafeTimedSerializer(SECRET_KEY, salt="sentinel-v1")`.
- `make_tokens(session_id) -> (parent_token, driver_token)`.
- `load_token(token, max_age_seconds, expected_role=None) -> dict`.
- `class TokenError(Exception)`.
- **Logique :** signature HMAC-SHA1 (itsdangerous default) avec timestamp ; `expected_role` vérifié si fourni.
- **Dépendances :** `itsdangerous`, `flask.current_app.config["SECRET_KEY"]`.
- **Statut :** complet, mais voir §4 sur le risque de partage de SECRET_KEY.

#### `consent_engine.py` (45 lignes)
- `ConsentResult` (slots `ok`, `reason`).
- `attempt_accept(session_id)` : PENDING_DRIVER → ACTIVE via `store.mark_accepted`.
- `assert_consent_for_update(state) -> bool` : update GPS autorisée seulement si `state in fsm.LIVE`.
- **Logique :** garde-fou légal — aucune position acceptée tant que `driver_consent_at` n'a pas été posé.
- **Dépendances :** `state_machine`, `store`, `audit_logger`.
- **Statut :** complet.

#### `anti_cut_engine.py` (46 lignes)
- `class AntiCutViolation(Exception)`.
- `assert_no_unilateral_termination(session_id, current_state, requester)` : rejette role inconnu, ignore les états terminaux.
- `assert_no_silent_deletion(session_id, current_state)` : interdit DELETE sur état non-terminal (re-asserte au niveau policy ce que `store.purge_old` enforce déjà au niveau SQL).
- **Logique :** invariants anti-coupure ; double protection SQL + policy.
- **Dépendances :** `state_machine`, `audit_logger`.
- **Statut :** complet. NB : `assert_no_silent_deletion` n'est **jamais appelé** par le reste du code — c'est une garde dormante explicitement déclarée pour les futures évolutions.

#### `battery_engine.py` (15 lignes)
- `LOW_BATTERY_THRESHOLD_PCT = 15`.
- `should_fire(battery_pct, already_fired) -> bool`.
- **Logique :** one-shot — un seul `low_battery` event par session, jamais répété.
- **Dépendances :** aucune.
- **Statut :** complet.

#### `speed_engine.py` (66 lignes)
- `STREAK_REQUIRED_SECONDS = 15`, `CLEAR_MARGIN_KMH = 5`.
- `evaluate(speed_kmh, limit_kmh, now_ts, streak_started_at, over_speed_active)` → dict `{streak_started_at, over_speed_active, event}` où `event in {None, "over_speed", "over_speed_cleared"}`.
- `update_running_stats(speed, max, sum, n)` et `avg_from(sum, n)`.
- **Logique :** streak continu 15 s + hystérésis -5 km/h sur clear → anti-flapping et anti-blip.
- **Dépendances :** aucune.
- **Statut :** complet.

#### `geo_engine.py` (84 lignes)
- `EARTH_RADIUS_M = 6_371_000.0`, `SAFE_ZONE_STREAK_SECONDS = 60`.
- `haversine_m(lat1, lon1, lat2, lon2)`.
- `signal_quality(accuracy_m) -> str` ∈ `{"unknown","excellent","good","fair","poor"}`.
- `evaluate_safe_zone(...)` → dict `{outside_streak_start, safe_zone_exit_active, event, distance_m}`, event ∈ `{None, "safe_zone_exit", "safe_zone_return"}`.
- **Logique :** sortie streakée 60 s, retour immédiat. Asymétrie volontaire (entry = acte délibéré, exit = bruit GPS possible).
- **Dépendances :** `math` stdlib.
- **Statut :** complet.

#### `telemetry_engine.py` (65 lignes)
- `public_state(sid, role) -> dict | None` — composeur unique du payload renvoyé par `GET /api/sentinel/session/<token>/state`.
- **Logique :** SSOT du contrat client ; mélange champs du row + agrégats `avg_from(sum, n)` + 30 derniers events + `server_time` + `time_remaining`.
- **Dépendances :** `speed_engine.avg_from`, `store.get_session`, `store.list_events`.
- **Statut :** complet. NB : aucune différenciation `role` (parent/driver) dans le payload — les deux voient exactement la même chose. Voir P2-04 §10.

#### `audit_logger.py` (94 lignes)
- 14 fonctions typées : `session_created`, `driver_accepted`, `over_speed`, `over_speed_cleared`, `safe_zone_exit`, `safe_zone_return`, `low_battery`, `signal_lost`, `sos_triggered`, `sos_acknowledged`, `stop_requested`, `stop_approved`, `session_expired`, `consent_blocked`, `anti_cut_blocked`.
- `_emit` privé : strip défensif des clés `lat/lon/latitude/longitude` avant `store.add_event`.
- **Logique :** seul chemin légal vers `sentinel_events`. Aucune position GPS jamais persistée dans les events.
- **Dépendances :** `store`, `logging`.
- **Statut :** complet.

#### `alert_engine.py` (113 lignes)
- `evaluate_update(session_id, row, pos)` → orchestre `speed_engine` + `geo_engine` + `battery_engine`, persiste via `store.write_telemetry`, émet events audit + push, retourne `{signal, fired:[...], distance_to_safe_zone_m}`.
- **Logique :** point d'entrée unique pour toute évaluation post-update. Route et session_manager n'appellent **jamais** les détecteurs directement.
- **Dépendances :** `audit_logger`, `battery_engine`, `geo_engine`, `push_engine`, `speed_engine`, `store`.
- **Statut :** complet.

#### `schemas.py` (151 lignes)
- `class ValidationError(ValueError)`.
- Constantes : `ALLOWED_DURATIONS = (30·60, 60·60, 90·60)`, `SPEED_LIMIT_MIN/MAX = 30/200`, `DEFAULT_DURATION = 3600`, `DEFAULT_SPEED_LIMIT = 90`, `SAFE_ZONE_RADIUS_MIN/MAX = 50 / 50_000` (50 km).
- `validate_create(payload)` — TTL whitelist, speed range, label ≤ 24 chars, safe_zone lat/lon/radius range-checked.
- `validate_position(payload)` — lat ∈ [-90,90], lon ∈ [-180,180], accuracy ∈ [0, 100k], speed ∈ [0, 500], heading ∈ [0, 360], battery ∈ [0,100].
- `validate_push_register(payload)` → `(fcm_token, platform)` — fcm ≤ 4096 chars, platform whitelist `{android}` (iOS pas supporté).
- `validate_batch(payload)` — `positions` ≤ 50 par batch.
- **Logique :** stdlib only, aucune dépendance pydantic.
- **Dépendances :** aucune.
- **Statut :** complet.

#### `push_engine.py` (225 lignes)
- `is_configured() -> bool` — vérifie `FCM_PROJECT_ID` env, fichier service account, import `jwt`.
- `_mint_access_token` / `_access_token` — JWT RS256 signé par la clé privée du service account, échangé contre access_token OAuth Google, **cache thread-safe 50 min**.
- `_send_fcm(fcm_token, title, body, data)` — POST FCM HTTP v1 endpoint `messages:send`, channel `sentinel_alerts`, priority HIGH.
- `_render(event, payload, row)` — i18n FR uniquement, 8 events templated + fallback générique.
- `notify(session_id, target_role, event, payload=None)` — fail-soft : strip lat/lon du data payload avant envoi, supporte `target_role="both"`.
- **Logique :** module FCM minimal sans dépendance lourde (`firebase-admin` évité), JWT-only via PyJWT.
- **Dépendances :** `jwt` (PyJWT) **non listé dans `requirements.txt`** — voir P0-05 §10. `requests` (présent en 2.32.5).
- **Statut :** complet mais **non provisionné** en prod (env `FCM_PROJECT_ID` vide → `is_configured()=False`, et donc `/api/sentinel/health` retourne `push_enabled: false` — confirmé live).

#### `session_manager.py` (178 lignes)
- `class SessionError(Exception)` avec `code` HTTP + `error` string.
- `create_session(params)` → row inséré + tokens parent/driver mintés + event `session_created` + purge_old + payload de retour.
- `accept_session(driver_sid)` → délègue à `consent_engine.attempt_accept`, mappe vers HTTP 404/409.
- `push_position(driver_sid, pos)` → check `expires_at`, check consent, délègue à `alert_engine.evaluate_update`.
- `public_state(sid, role)` → auto-expire lazy + détection signal-lost + telemetry.
- `trigger_sos(driver_sid)` / `ack_sos(parent_sid)`.
- `request_stop(sid, requester)` / `approve_stop(sid, approver)`.
- **Logique :** orchestrateur du lifecycle ; routes restent fines.
- **Dépendances :** tous les engines + store + tokens + state_machine.
- **Statut :** complet. NB : import cyclique différé `from app.blueprints.sentinel.routes import SIGNAL_LOSS_THRESHOLD` à la ligne 116 (anti-pattern toléré ici — voir P2-05 §10).

#### `store.py` (428 lignes)
- `_DEFAULT_DB = "/root/astro_scan/data/archive_stellaire.db"`, override via env `DB_PATH`.
- `init_schema()` idempotent + `CREATE INDEX` + ALTER de rattrapage Phase-A push (colonnes `*_fcm_token`, `*_platform`).
- Fonctions : `insert_session`, `get_session`, `mark_accepted`, `write_telemetry`, `trigger_sos`, `ack_sos`, `request_stop`, `approve_stop` (avec gestion `cannot_approve_own_request`), `mark_expired_if_due`, `detect_signal_loss`, `fire_low_battery_once`, `add_event`, `list_events`, `set_push_token`, `purge_old`, `health_counters`.
- **Logique :** sqlite3 stdlib, `isolation_level=None` (autocommit), `PRAGMA busy_timeout=3000`, row_factory `Row`. Toutes les opérations passent par `init_schema()` en idempotent.
- **Dépendances :** `sqlite3` stdlib, JSON pour `payload_json`.
- **Statut :** complet. NB : 100 % des requêtes utilisent placeholders `?` paramétrés sauf la concaténation `f"UPDATE sentinel_sessions SET {tok_col} = ?, {plt_col} = ?"` à la ligne 369 — **inputs `tok_col`/`plt_col` sont whitelistés** (`role in ("parent","driver")` ligne 363) donc pas d'injection. Voir §4.

#### `routes.py` (429 lignes)
- 22 routes définies (détail §2.3).
- `_auth(token, role=None)` wrapper sur `tokens.load_token` avec `max_age_seconds=MAX_TTL_SECONDS=5400`.
- `_handle_session_error` mapper HTTP.
- Constants exposées via `/health` : `MAX_TTL_SECONDS=5400`, `SOS_HOLD_SECONDS=3`, `SIGNAL_LOSS_THRESHOLD=30`, `UPDATE_INTERVAL_SECONDS=5`.
- **Logique :** couche HTTP fine, aucune logique métier.
- **Dépendances :** tous les modules + `app.services.security.rate_limit_ip` + `app.utils.responses.api_ok/api_error`.
- **Statut :** complet.

### 2.3 Inventaire des 22 routes (live)

> Auth : « token » = `URLSafeTimedSerializer` signé avec `SECRET_KEY` salt `"sentinel-v1"`. « public » = ouverte. « rl=N/min » = `@rate_limit_ip(max_per_minute=N)` par IP par endpoint.

| # | Méthode | Path | Auth | Rate-limit | Payload (entrée) | Réponse (succès) | Logique | Statut |
|---|---------|------|------|-----------|------------------|------------------|---------|--------|
| 1 | GET | `/sentinel` | public | — | — | HTML landing | Rendu `sentinel/landing.html` avec `max_ttl_seconds` injecté. | complet |
| 2 | GET | `/sentinel/driver/<token>` | token role=driver | — | — | HTML driver cockpit | Charge le row par `sid` du token, injecte label/limit/ttl/sos_hold/update_interval/initial_state. | complet |
| 3 | GET | `/sentinel/parent/<token>` | token role=parent | — | — | HTML parent live | Rendu `parent.html` avec `parent_token` + `update_interval`. | complet |
| 4 | GET | `/vehicle-secure-locator` | public | — | — | 301 → `/sentinel` | Deprecation redirect (legacy URL #1). | complet |
| 5 | GET | `/vehicle` | public | — | — | 301 → `/sentinel` | Deprecation redirect (legacy URL #2). | complet |
| 6 | GET | `/guardian-family` | public | — | — | 301 → `/sentinel` | Deprecation redirect (legacy URL #3). | complet |
| 7 | GET | `/.well-known/assetlinks.json` | public | — | — | JSON | Sert le fichier `static/.well-known/assetlinks.json`. **Fingerprints vides** → P0-01. | complet (mais inutilisable) |
| 8 | GET | `/modules/sentinel/<filename>` | public | — | — | APK binaire | Whitelist `{sentinel-parent.apk, sentinel-driver.apk}` → `send_from_directory`. | complet |
| 9 | POST | `/api/sentinel/session/create` | public | 6/min | `{ttl_seconds?, speed_limit_kmh?, driver_label?, safe_zone?}` | `{session_id, parent_token, driver_token, parent_url, invite_url, expires_at, ttl_seconds, speed_limit_kmh, driver_label, safe_zone, update_interval}` | Valide → insert row PENDING_DRIVER → mint tokens → audit `session_created` → purge_old → URLs absolues. | complet |
| 10 | POST | `/api/sentinel/session/accept` | token role=driver | 12/min | `{token}` | `{status:"active"}` | PENDING_DRIVER → ACTIVE (`mark_accepted`) → audit `driver_accepted`. | complet |
| 11 | POST | `/api/sentinel/session/update` | token role=driver | 30/min | `{token, lat, lon, accuracy?, speed_kmh?, heading_deg?, battery_pct?}` | `{status:"ok", signal, fired:[...], distance_to_safe_zone_m}` | `validate_position` → `push_position` (vérifie expiry + consent + delegate alert_engine). | complet |
| 12 | GET | `/api/sentinel/session/<token>/state` | token role=parent OR driver | 120/min | — | full state dict (voir telemetry_engine) | Auto-expire lazy + signal-loss + `public_state`. | complet |
| 13 | POST | `/api/sentinel/session/sos` | token role=driver | 6/min | `{token}` | `{status:"sos_active", was_new: bool}` | `trigger_sos` (idempotent, `WHERE sos_active=0`) → audit + push parent. | complet |
| 14 | POST | `/api/sentinel/session/sos_ack` | token role=parent | 12/min | `{token}` | `{status:"sos_acknowledged"}` | `ack_sos` → audit + push driver. **Notabene** : SOS reste actif après ack (alerte non-terminale). | complet |
| 15 | POST | `/api/sentinel/session/stop_request` | token role=parent OR driver | 6/min | `{token}` | `{status:"stop_pending_*", awaiting_approval_from:"driver|parent"}` | Anti-cut check → FSM `can_request_stop` → UPDATE conditionnel `state='ACTIVE'` → audit + push counter-party. | complet |
| 16 | POST | `/api/sentinel/session/stop_approve` | token role=parent OR driver | 6/min | `{token}` | `{status:"ended"}` | Refus si même role que requester (`cannot_approve_own_request`) → UPDATE → audit + push autre party. | complet |
| 17 | POST | `/api/sentinel/session/push/register` | token role=parent OR driver | 12/min | `{token, fcm_token, platform:"android"}` | `{status:"registered", push_enabled: bool}` | Bind FCM token sur la colonne du role. | complet |
| 18 | POST | `/api/sentinel/session/push/unregister` | token role=parent OR driver | 12/min | `{token}` | `{status:"unregistered"}` | Clear FCM token. | complet |
| 19 | POST | `/api/sentinel/session/update/batch` | token role=driver | 12/min | `{token, positions:[...≤50]}` | `{status:"ok", accepted:N, summary:{...}}` | Re-joue `push_position` séquentiellement, stop sur première erreur métier. | complet |
| 20 | GET | `/api/sentinel/health` | public | — | — | `{module, version:"1.0.0", max_ttl_seconds, sos_hold_seconds, over_speed_streak_seconds, signal_loss_threshold_seconds, update_interval_seconds, push_enabled, sessions:{...}}` | Aggrégats `health_counters()`. **Confirmé live** : `version:1.0.0`, `push_enabled:false`. | complet |

> **Recompte : 20 routes nommées + 2 alias `@sentinel_bp.route` redondants sur la fonction `deprecated_redirect` (vehicle-secure-locator + vehicle + guardian-family → 3 routes pour 1 fonction).** En réalité 22 routes effectives sont enregistrées dans `url_map`. La documentation initiale de routes.py (`URL surface — UNIFIED:`) liste 12 entrées car les routes APK/push/batch/redirects étaient absentes au moment de la rédaction → la docstring d'en-tête n'a pas été mise à jour avec les ajouts Phase A (push) et Phase APK. Voir P2-02 §10.

---

## 3. ARCHITECTURE TECHNIQUE

### 3.1 Diagramme des dépendances

```
                       ┌─────────────────────────────────────────┐
                       │           routes.py (429 LOC)           │
                       │  22 endpoints HTTP — aucune logique     │
                       │  métier, juste auth+validate+delegate.  │
                       └────────────┬────────────────────────────┘
                                    │
                                    ▼
                       ┌─────────────────────────────────────────┐
                       │   session_manager.py (178 LOC)          │
                       │   Orchestrateur lifecycle.              │
                       └─────┬──────────┬───────────┬─────────┬──┘
                             │          │           │         │
                ┌────────────┘          │           │         └────────────┐
                ▼                       ▼           ▼                      ▼
   ┌──────────────────────┐  ┌─────────────────┐  ┌─────────────┐  ┌───────────────┐
   │ consent_engine.py    │  │ alert_engine.py │  │anti_cut.py  │  │telemetry.py   │
   │ (45)                 │  │ (113)           │  │(46)         │  │(65)           │
   │ attempt_accept       │  │ evaluate_update │  │assertions   │  │public_state   │
   └──────┬───────────────┘  └────┬────────────┘  └─────┬───────┘  └─────┬─────────┘
          │                       │                     │                │
          │            ┌──────────┼────────┬────────────┘                │
          │            │          │        │                             │
          ▼            ▼          ▼        ▼                             ▼
   ┌─────────────┐ ┌──────┐ ┌────────┐ ┌─────────────┐         ┌───────────────────┐
   │state_machine│ │speed │ │geo     │ │battery      │         │store.py (428)     │
   │.py (40)     │ │_eng  │ │_eng    │ │_eng (15)    │         │ SQLite WAL        │
   │PURE FSM     │ │(66)  │ │(84)    │ │one-shot     │         │ + idempotent ALTER│
   └─────────────┘ └──────┘ └────────┘ └─────────────┘         └─────────┬─────────┘
                                                                         │
                            ┌────────────────────┐                       │
                            │ audit_logger.py    │◄──────────────────────┘
                            │ (94)               │   (store.add_event /
                            │ strip lat/lon      │    store.list_events)
                            └────────────────────┘
                                       ▲
                                       │
                            ┌──────────┴─────────┐
                            │ push_engine.py     │
                            │ (225)              │
                            │ FCM HTTP v1        │
                            │ (fail-soft)        │
                            │ deps: PyJWT,       │
                            │ requests           │
                            └────────────────────┘

   schemas.py (151) — validation pure stdlib, importé directement par routes.py
   tokens.py (46)   — itsdangerous URLSafeTimedSerializer, importé par routes + session_manager (via consent)
```

**Propriété d'architecture :** zéro cycle d'import direct. Une seule indirection différée volontaire : `session_manager.py:116` importe `SIGNAL_LOSS_THRESHOLD` depuis `routes.py` au runtime pour éviter le cycle (constante config-only).

### 3.2 Flow complet d'une session

```
TIME    ACTOR     HTTP                                       FSM          ENGINES DÉCLENCHÉS
────────────────────────────────────────────────────────────────────────────────────────────
t0      parent    POST /api/sentinel/session/create          ∅→PENDING    schemas.validate_create
                  body {ttl=3600, speed_limit=90,                          tokens.make_tokens × 2
                  driver_label="Anis", safe_zone={...}}                    store.insert_session
                                                                           store.purge_old (gc)
                                                                           audit.session_created

t0+1s   parent    (envoie invite_url par SMS au driver)      —            —

t0+30s  driver    GET /sentinel/driver/<driver_token>        PENDING      tokens.load_token(role=driver)
                  → HTML cockpit, geolocation prompt                       store.get_session

t0+32s  driver    POST /api/sentinel/session/accept          PENDING→ACT  consent_engine.attempt_accept
                  body {token}                                             store.mark_accepted
                                                                           audit.driver_accepted

t0+37s  driver    POST /api/sentinel/session/update          ACTIVE       schemas.validate_position
                  body {token, lat, lon, accuracy,                         consent.assert_consent_for_update
                  speed_kmh, heading_deg, battery_pct}                     speed_engine.evaluate
                                                                           geo_engine.evaluate_safe_zone
                                                                           battery_engine.should_fire
                                                                           store.write_telemetry
                                                                           [si over_speed 15s] audit.over_speed
                                                                                              push.notify(parent)
                                                                           [si safe_zone_exit 60s] audit + push
                                                                           [si low_battery ≤15%] audit + push (1×)

t0+5s..  parent   GET /api/sentinel/session/<parent_token>   any LIVE     tokens.load_token(role=parent)
        every 5s  /state                                                   [si expiry passé] mark_expired_if_due
                                                                                              audit.session_expired
                                                                                              push.notify(both)
                                                                           store.detect_signal_loss (>30s)
                                                                              → audit.signal_lost + push parent
                                                                           telemetry.public_state

t0+10m  driver    POST /api/sentinel/session/sos             ACTIVE       store.trigger_sos (idempotent)
                  body {token}                                             audit.sos_triggered
                                                                           push.notify(parent, "sos_triggered")
                                                                           ⚠ session NE TERMINE PAS

t0+11m  parent    POST /api/sentinel/session/sos_ack         ACTIVE       store.ack_sos
                  body {token}                                             audit.sos_acknowledged
                                                                           push.notify(driver, "sos_acknowledged")

t0+50m  parent    POST /api/sentinel/session/stop_request    ACT→SPP      anti_cut.assert_no_unilateral_term
                  body {token}                                             fsm.can_request_stop
                                                                           store.request_stop (UPDATE WHERE
                                                                              state='ACTIVE')
                                                                           audit.stop_requested
                                                                           push.notify(driver, "stop_requested")

t0+50m+5s driver  POST /api/sentinel/session/stop_approve    SPP→ENDED    store.approve_stop
                  body {token}                                             (refuse si même role que requester)
                                                                           audit.stop_approved
                                                                           push.notify(parent, "stop_approved")
```

**Alternative terminale unilatérale : EXPIRY (TTL).** À chaque `public_state` ou `push_position`, si `expires_at <= now()`, `mark_expired_if_due` fait `UPDATE state='EXPIRED', ended_at=now`. Aucun cron/worker dédié — c'est de l'**auto-expiry paresseuse, déclenchée par le trafic**.

### 3.3 Schéma DB complet (live, vérifié sur `archive_stellaire.db`)

**Table `sentinel_sessions`** (PK : `session_id`) :

| Colonne | Type | NULL | Default | Notes |
|---------|------|------|---------|-------|
| `session_id` | TEXT | NOT NULL | — | PK, `secrets.token_urlsafe(16)` |
| `parent_token` | TEXT | NOT NULL | — | itsdangerous signé |
| `driver_token` | TEXT | NOT NULL | — | itsdangerous signé |
| `driver_label` | TEXT | NULL | — | ≤24 chars |
| `state` | TEXT | NOT NULL | — | PENDING_DRIVER \| ACTIVE \| STOP_PENDING_PARENT \| STOP_PENDING_DRIVER \| ENDED \| EXPIRED |
| `speed_limit_kmh` | INTEGER | NOT NULL | — | 30..200 |
| `ttl_seconds` | INTEGER | NOT NULL | — | 1800 \| 3600 \| 5400 |
| `created_at` | INTEGER | NOT NULL | — | epoch s |
| `started_at` | INTEGER | NULL | — | epoch s, set au accept |
| `expires_at` | INTEGER | NOT NULL | — | created_at + ttl |
| `ended_at` | INTEGER | NULL | — | set sur ENDED ou EXPIRED |
| `driver_consent_at` | INTEGER | NULL | — | = `started_at` (proof) |
| `safe_zone_lat/lon` | REAL | NULL | — | optionnel |
| `safe_zone_radius_m` | INTEGER | NULL | — | 50..50000 |
| `last_lat/lon` | REAL | NULL | — | **PII GPS temps-réel** |
| `last_accuracy` | REAL | NULL | — | m |
| `last_signal` | TEXT | NULL | — | excellent\|good\|fair\|poor\|unknown |
| `last_speed_kmh` | REAL | NULL | — | |
| `last_heading_deg` | REAL | NULL | — | 0..360 |
| `last_battery_pct` | INTEGER | NULL | — | 0..100 |
| `last_update_at` | INTEGER | NULL | — | epoch s |
| `max_speed_kmh` | REAL | NOT NULL | 0 | running max |
| `avg_speed_sum` | REAL | NOT NULL | 0 | running sum |
| `avg_speed_samples` | INTEGER | NOT NULL | 0 | running n |
| `updates_count` | INTEGER | NOT NULL | 0 | counter |
| `over_speed_active` | INTEGER | NOT NULL | 0 | bool |
| `over_speed_streak_start` | INTEGER | NULL | — | epoch s |
| `safe_zone_exit_active` | INTEGER | NOT NULL | 0 | bool |
| `safe_zone_outside_start` | INTEGER | NULL | — | epoch s |
| `signal_lost_active` | INTEGER | NOT NULL | 0 | bool |
| `low_battery_fired` | INTEGER | NOT NULL | 0 | one-shot bool |
| `sos_active` | INTEGER | NOT NULL | 0 | bool, orthogonal au state |
| `sos_triggered_at` | INTEGER | NULL | — | epoch s |
| `sos_ack_at` | INTEGER | NULL | — | epoch s |
| `stop_requested_by` | TEXT | NULL | — | "parent" \| "driver" |
| `stop_requested_at` | INTEGER | NULL | — | epoch s |
| `parent_fcm_token` | TEXT | NULL | — | added by ALTER Phase-A |
| `driver_fcm_token` | TEXT | NULL | — | idem |
| `parent_platform` | TEXT | NULL | — | "android" |
| `driver_platform` | TEXT | NULL | — | "android" |

**Index :** `idx_sentinel_expires ON sentinel_sessions(expires_at)` — utile pour purge ; pas d'index sur `state` (acceptable au volume actuel).

**Écritures :**
- INSERT : un seul site (`store.insert_session`).
- UPDATE in-place pour : telemetry (le plus chaud), alert flags, SOS, stop request, push tokens, expiry, signal-loss flag.
- DELETE : uniquement via `purge_old` (terminal + grace + no unack SOS).

**Table `sentinel_events`** (PK auto-incrémentée) :

| Colonne | Type | NULL | Notes |
|---------|------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | NOT NULL | |
| `session_id` | TEXT | NOT NULL | FK logique (pas FK SQL) |
| `event_type` | TEXT | NOT NULL | enum non contraint, 15 valeurs émises |
| `payload_json` | TEXT | NULL | JSON, lat/lon stripés par `audit_logger._emit` |
| `created_at` | INTEGER | NOT NULL | epoch s |

**Index :** `idx_sentinel_events_sid ON sentinel_events(session_id, created_at)`.

**Pragma DB :** WAL mode activé app-level (`_init_sqlite_wal` dans `app/__init__.py`), `busy_timeout=3000ms` par connexion Sentinel.

**Volumes live (2026-05-15 12:25 UTC) :** 1 session ENDED + 6 events. Bonne foi, données de test.

### 3.4 FSM — états + transitions valides

```
                   ┌──────────────────┐
                   │  PENDING_DRIVER  │  (initial, créé par parent)
                   └────────┬─────────┘
                            │ POST /accept (driver only)
                            │ consent_engine.attempt_accept
                            ▼
                   ┌──────────────────┐         POST /update (driver)
                   │      ACTIVE      │◄────────── push_position
                   └────┬─────────┬───┘
                        │         │
        parent /stop_req│         │ driver /stop_req
                        ▼         ▼
       ┌─────────────────────┐  ┌─────────────────────┐
       │STOP_PENDING_PARENT  │  │ STOP_PENDING_DRIVER │
       │(parent demandé,     │  │ (driver demandé,    │
       │ attend approval     │  │  attend approval    │
       │ driver)             │  │  parent)            │
       └─────────┬───────────┘  └─────────┬───────────┘
                 │ driver approves         │ parent approves
                 │ (refuse si self-approve)│
                 ▼                         ▼
                          ┌────────────────────┐
                          │       ENDED        │ (terminal, dual-stop)
                          └────────────────────┘

  + Toute non-terminal → EXPIRED si expires_at <= now()
                        (unilatéral, server-driven, lazy)

  + sos_active est ORTHOGONAL : un flag boolean indépendant
    qui peut être true/false dans n'importe quel état LIVE.
    Un SOS n'est jamais terminal.
```

**Invariants :**
- Une seule colonne `state`. Pas d'état composite.
- `EXPIRED` uniquement par le serveur (lazy sur trafic).
- `ENDED` uniquement par approval counter-party.
- `STOP_PENDING_*` ne peut pas être atteint depuis un état terminal (UPDATE filtré `WHERE state='ACTIVE'`).
- Aucune transition ENDED → ACTIVE ni EXPIRED → quoi que ce soit.

### 3.5 Comparaison routes.py actuel vs backups

**Trois versions chronologiques :**
1. `routes.py.bak_pre_pushA_20260514_191944` (286 lignes, baseline pre-push)
2. `routes.py.bak_pre_apk_20260514_215650` (377 lignes, après Phase A push)
3. `routes.py` (429 lignes, après Phase APK — actuel)

**Δ baseline → Phase A push (286 → 377 LOC) :**
- Import `push_engine` + `Response`, `os`, `json`.
- Ajout route `/.well-known/assetlinks.json` (sert le placeholder Digital Asset Links).
- Ajout `/api/sentinel/session/push/register` + `/push/unregister`.
- Ajout `/api/sentinel/session/update/batch`.
- Ajout `push_enabled: push_engine.is_configured()` dans `/health`.

**Δ Phase A → Phase APK (377 → 429 LOC) :**
- Import `send_from_directory` ajouté.
- Ajout route `/modules/sentinel/<path:filename>` avec whitelist `{sentinel-parent.apk, sentinel-driver.apk}` et mimetype `application/vnd.android.package-archive`.

**Δ store.py baseline → actuel :** ajout de 4 colonnes FCM (`parent_fcm_token`, `driver_fcm_token`, `parent_platform`, `driver_platform`) à la fois dans le `CREATE TABLE` et en `ALTER TABLE ADD COLUMN` idempotent pour les bases déjà existantes ; ajout fonction `set_push_token`.

**Δ schemas.py baseline → actuel :** ajout `validate_push_register` + `validate_batch`.

**Δ alert_engine.py baseline → actuel :** ajout des `push_engine.notify(...)` sur les 3 trigger paths (over_speed, safe_zone_exit, low_battery).

**Δ session_manager.py baseline → actuel :** ajout `push_engine.notify` sur 6 sites : session_expired (both), signal_lost (parent), sos_triggered (parent), sos_acknowledged (driver), stop_requested (counter-party), stop_approved (other party).

**Aucune suppression de code observée.** Les 3 phases sont additives. Pas de régression possible côté logique métier baseline.

---

## 4. AUDIT SÉCURITÉ

### 4.1 Auth / Authz — tokens.py

**Schéma cryptographique :**
- `itsdangerous.URLSafeTimedSerializer` (HMAC-SHA1 par défaut sur la version 2.2.0 listée) sur payload JSON `{"sid": "...", "role": "parent|driver"}`.
- Salt fixe global : `"sentinel-v1"`.
- Secret : `current_app.config["SECRET_KEY"]` — **clé Flask globale du monolithe**.
- TTL : `max_age=5400s` enforcé côté `loads()` ; **redondé** par `expires_at` en DB (defense-in-depth correct).

**Rotation :** aucune mécanisme d'invalidation prématurée (pas de revocation list, pas de versioning de salt). Si SECRET_KEY est rotée, **tous les tokens vivants deviennent invalides** instantanément (acceptable mais non documenté). Pas d'option de re-mint pour le user.

**Expiration :** double couche OK. TTL crypto (`SignatureExpired`) + TTL DB (`expires_at`).

**Revocation :** absente. Un token volé reste valide jusqu'à TTL (max 90 min). Compensation : `purge_old(grace=600)` supprime les rows terminales 10 min après end, ce qui invalide implicitement les tokens vivants pointant vers une session purgée → mais entre `now` et `expires_at`, la fenêtre est large.

**Choix d'algorithme :** HMAC-SHA1 est techniquement obsolète pour la signature ; preferable SHA-256. `URLSafeTimedSerializer` accepte `signer_kwargs={"digest_method": hashlib.sha256}` mais ce n'est **pas** configuré ici. Acceptable au vu du contexte (durée 90 min max, pas de chiffrement), pas un P0.

**Risque majeur :** **partage de SECRET_KEY avec les 31 autres blueprints**. Toute fuite ailleurs casse Sentinel.

### 4.2 Validation input — schemas.py

Couverture :

| Endpoint | Schéma utilisé | Couverture |
|----------|----------------|-----------|
| `POST /create` | `validate_create` | TTL whitelist, speed_limit range, label ≤24, safe_zone lat/lon/radius range. ✅ |
| `POST /accept` | présence `token` seulement | ⚠ aucune validation au-delà de la signature. OK car payload minimal. |
| `POST /update` | `validate_position` | lat/lon/accuracy/speed/heading/battery range-checked. ✅ |
| `GET /state` | token-only | ✅ |
| `POST /sos` | présence `token` | ✅ |
| `POST /sos_ack` | présence `token` | ✅ |
| `POST /stop_request` | présence `token` | ✅ |
| `POST /stop_approve` | présence `token` | ✅ |
| `POST /push/register` | `validate_push_register` | fcm ≤4096, platform=android. ✅ |
| `POST /push/unregister` | présence `token` | ✅ |
| `POST /update/batch` | `validate_batch` → N×`validate_position` | ≤50 positions/batch. ✅ |

**Trou notable :** la route 2 `GET /sentinel/driver/<token>` charge le row puis fait `row["speed_limit_kmh"]` — si row est `None` (token expiré entre vérif et lookup), c'est gardé par `abort(404)`. OK.

### 4.3 Rate-limiting

Présent dans le code via `@rate_limit_ip(max_per_minute=N, key_prefix=...)` sur **les 11 routes API** (toutes les POST + 1 GET state). Granularité par endpoint, fenêtre glissante 60 s, headers `X-RateLimit-Limit/Remaining/Reset`.

**Limite documentée :** compteur **process-local** (mémoire du worker Gunicorn). 4 workers ⇒ effectif ≈ 4× la limite annoncée avant blocage global. La docstring de `app/services/security.py:13-17` mentionne explicitement « migrer vers Redis si besoin ».

**Limites effectives par IP :** create 6×4=24/min, accept 12×4=48/min, update 30×4=120/min, state 120×4=480/min, sos 6×4=24/min, push/* 12×4=48/min, batch 12×4=48/min.

**Nginx complète :** `limit_req_status 429; zone=astro_api_limit burst=20 nodelay` sur `/api/` — vérifié dans `/etc/nginx/sites-enabled/astroscan.space:79+`.

**Manquant :** rate-limit par session_id (pas seulement par IP). Un attaquant CGNAT pourrait sortir d'une seule IP avec plusieurs sessions valides.

### 4.4 CORS / headers sécurité

**App-level :** aucun header sécurité injecté côté Flask (pas de `Talisman`, pas de hook `after_request` Sentinel).

**Nginx-level (sites-enabled/astroscan.space) :**
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` ✅
- `X-Frame-Options: SAMEORIGIN` ✅
- `X-Content-Type-Options: nosniff` ✅
- `Referrer-Policy: strict-origin-when-cross-origin` ✅
- `Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()` ⚠ **`geolocation=()` BLOQUE l'API geolocation côté navigateur** → si le bloc Sentinel est retiré du `return 404`, la page driver ne pourra pas appeler `navigator.geolocation`. **À corriger en `geolocation=(self)` lors du rebranchement.** Voir P0-04.

**CORS :** non configuré côté Flask. Acceptable car même-origine (astroscan.space + APK Android via Digital Asset Links). Mais l'APK pourrait avoir besoin d'un CORS explicite si le WebView est cross-origin.

**CSP :** absente. Pour une page qui fait fetch JS vers son propre origin, ce n'est pas critique, mais le défaut est notable.

### 4.5 Injection SQL — audit des requêtes store.py

Inspection ligne par ligne de toutes les requêtes :

- `init_schema` : 3× `CREATE TABLE/INDEX` littéraux + boucle `ALTER TABLE ... ADD COLUMN {col}` où **`col` provient d'une whitelist hard-codée** `("parent_fcm_token", "driver_fcm_token", "parent_platform", "driver_platform")` (ligne 92-96 de store.py). ✅ Sûr.
- `insert_session` : 11 placeholders `?` ✅.
- `get_session` : 1× `?` ✅.
- `mark_accepted` : 3× `?` ✅.
- `write_telemetry` : 16× `?` ✅.
- `trigger_sos` : 2× `?` ✅.
- `ack_sos` : 2× `?` ✅.
- `request_stop` : 4× `?` ✅.
- `approve_stop` : 1 SELECT + 1 UPDATE, tous paramétrés ✅.
- `mark_expired_if_due` : 3× `?` ✅.
- `detect_signal_loss` : 1× `?` + UPDATE 1× `?` ✅.
- `fire_low_battery_once` : 1× `?` ✅.
- `add_event` : 4× `?` ✅.
- `list_events` : 2× `?` ✅.
- **`set_push_token` (ligne 368-372) : interpolation f-string sur les noms de colonnes** `tok_col = f"{role}_fcm_token"`, `plt_col = f"{role}_platform"`. **`role` est whitelisté** (`role not in ("parent","driver"): return False` ligne 363-364). ✅ Sûr mais cosmetic risk : un futur reviewer pourrait élargir la whitelist sans réaliser l'enjeu. Voir P3-01 §10.
- `purge_old` : SELECT paramétré + DELETE in-loop paramétrés ✅.
- `health_counters` : SELECT littéral (aucun input) ✅.

**Verdict :** **aucune injection SQL détectée.** La whitelist sur `role` rend la concaténation sûre, mais elle mériterait un `assert` ou un commentaire explicite.

### 4.6 Secrets / clés hardcodées

Recherche exhaustive :
- `tokens.py:12` : `_SALT = "sentinel-v1"` → salt, **pas secret** (par construction itsdangerous, le salt est public).
- `push_engine.py:39-44` : chemins par défaut `/root/.config/sentinel/firebase-sa.json` et env `FCM_PROJECT_ID` — **pas hardcodé**, env-driven.
- `store.py:15` : `_DEFAULT_DB = "/root/astro_scan/data/archive_stellaire.db"` — chemin, pas secret.

**Aucun secret en clair dans le code Sentinel.**

**État du provisioning FCM (vérifié, sans lire les contenus) :**
- `/root/.config/sentinel/` existe (permission denied à un utilisateur non-root → bon point d'hygiène).
- `is_configured()` retourne `false` côté `/health` → soit `FCM_PROJECT_ID` env vide, soit le fichier service account absent, soit PyJWT absent du venv → **les trois sont possibles** ; le test `import jwt` échoue silencieusement.

### 4.7 RGPD — données GPS humaines temps-réel

**Posture déclarée (routes.py:3-19) :** « protected trip », « family safety », pas de surveillance, consentement explicite avant tout API geolocation, time-bounded 30/60/90 min, dual-stop, positions live exclusivement sur le row session (jamais dans events ni logs), audit logs = session_id + event_type seulement.

**Posture observée dans le code :**
- ✅ `audit_logger._emit` strip activement `lat/lon/latitude/longitude` du payload events.
- ✅ `push_engine.notify` strip aussi `lat/lon/latitude/longitude` du data FCM (ligne 219-221).
- ✅ `driver_consent_at` writé uniquement à l'accept, jamais modifié ensuite (proof timestamp).
- ✅ Aucun log INFO/DEBUG ne logge lat/lon. Vérifié : tous les `log.info` Sentinel loggent `sid=%s role=%s event=%s` — jamais une position.
- ⚠ **`last_lat`/`last_lon` sont retournés au full state** dans `telemetry_engine.public_state` — mais c'est par design (le parent doit voir la position du driver). Le risque c'est : (1) si un token fuite, position lue jusqu'à TTL ; (2) si un dump SQLite fuite, on a l'historique des dernières positions de toutes les sessions live.
- ⚠ **Aucune rétention DB explicite.** `purge_old` ne tourne qu'à `create_session` (chaque création purge). Si l'usage est calme (0 création/jour), les sessions ENDED restent indéfiniment avec `last_lat/lon` dedans. Pas RGPD-compliant si tu veux annoncer une rétention <90 jours.
- ⚠ **Aucun mécanisme « right to be forgotten »** explicite. Possible manuellement (DELETE), mais pas exposé via API.
- ⚠ **Aucune mention CNIL/registre traitements** côté projet.

**Verdict RGPD :** L'architecture est **correcte par construction**, mais la **politique opérationnelle** (rétention, registre, DPIA, point de contact) n'est pas documentée. Si tu lances publiquement en UE, c'est P1 légal.

### 4.8 Anti-cut — robustesse

**Triple verrou :**
1. **policy** (`anti_cut_engine.assert_no_unilateral_termination`) — rejette les rôles inconnus, log via audit.
2. **FSM** (`state_machine.can_request_stop` exige `state==ACTIVE`).
3. **SQL** (`store.request_stop` UPDATE WHERE state='ACTIVE' ; `store.approve_stop` refuse `requester==approver`).

**Cas limites testés à la lecture :**
- Driver demande stop, driver re-essaie d'approuver son propre stop → `approve_stop` ligne 257 refuse avec `cannot_approve_own_request`. ✅
- Race condition deux requests concurrents → la deuxième UPDATE échoue car `state` n'est plus ACTIVE → `stop_request_failed` 409. ✅
- Session EXPIRED entre request et approve → `approve_stop` filtre `state IN ('STOP_PENDING_PARENT','STOP_PENDING_DRIVER')` → race → 409. ✅
- DELETE silencieux : `purge_old` filtre `state IN ('ENDED','EXPIRED')` et `sos_active=0 OR sos_ack_at IS NOT NULL`. ✅

**Faille théorique :** `mark_expired_if_due` est unilatéral serveur. Si l'horloge serveur dérive, un parent pourrait théoriquement « expirer prématurément » via un proxy MITM modifiant la response. Sans authentification du contenu de la response (pas de signature), un client malveillant pourrait faire croire au driver que la session est ENDED. Mitigé en pratique par HTTPS + HSTS. Acceptable.

**Verdict :** **anti-cut solide.** Triple verrou cohérent. C'est l'aspect le mieux conçu de Sentinel.

### 4.9 SOS — abus / spam / forge

- **Forge :** impossible sans token driver valide (vérifié par `_auth(token, "driver")`).
- **Spam :** rate-limit `6/min` côté API + `trigger_sos` idempotent (`WHERE sos_active=0` → premier trigger seul écrit, les suivants no-op). Push FCM envoyé une seule fois.
- **Boucle :** un driver malveillant pourrait `sos` → `parent ack` → driver ne peut **pas** re-trigger tant que `sos_active=1`. Si on imagine `parent stop_request` qui force `sos_active=0` ? **Non**, aucune route ne reset `sos_active` à 0 explicitement. Le flag reste à 1 jusqu'à end de session. Donc 1 SOS par session. ✅
- **Trou potentiel :** rien n'oblige le driver à appuyer le bouton pendant `SOS_HOLD_SECONDS=3` côté **serveur** — c'est annoncé comme un hold UX côté driver mais le serveur accepte un SOS sans hold. Si le frontend driver est compromis, un POST direct envoie SOS instantanément. Acceptable (un SOS faussement positif n'a pas d'impact destructif, juste UX).
- **Impact d'un SOS frauduleux :** push FCM au parent + event en DB. Pas critique.

**Verdict :** **SOS robuste.**

### 4.10 Push notifications — VAPID / endpoints validés

**Stack :** FCM HTTP v1 (pas Web Push VAPID). Cible : APK Android uniquement (`platform="android"` hard-whitelisted dans schemas).

**Provisioning :**
- Service account JSON attendu en `/root/.config/sentinel/firebase-sa.json` mode 0600 (docstring push_engine.py:7-9). Pas vérifié à 0600 (permission denied à l'audit).
- Env vars : `FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_PATH`.
- État live : `push_enabled: false` → non provisionné.

**Validation endpoint :** aucune. Le `fcm_token` reçu est juste range-checked (`≤4096 chars`, non-empty) ; pas de format check, pas de probe initial. Un attaquant pourrait soumettre un fake token de 4096 chars → FCM échouera silencieusement à l'envoi (return 200 ou 404 selon le format, `_send_fcm` log-info en cas d'échec). Acceptable.

**Trous :**
- ⚠ **Aucune Web Push** (VAPID). Si l'utilisateur n'installe pas l'APK, il n'a aucune notification. C'est par design Phase A, mais ça bloque le pitch « usage instantané navigateur ».
- ⚠ **Pas de réémission SOS si push échoue** — c'est fire-and-forget. Une cellule offline = parent ne reçoit jamais l'alerte critique. Pour un produit « safety », c'est un trou fonctionnel.
- ⚠ **PyJWT absent du `requirements.txt`** → si tu redéploies depuis zero, `is_configured()` retourne `false` même avec un service account valide. P0.

### 4.11 Vulnérabilités classées

| ID | Sévérité | Vulnérabilité | Localisation | Impact |
|----|----------|---------------|--------------|--------|
| V-P0-01 | P0 | `assetlinks.json` avec `sha256_cert_fingerprints: []` | static/.well-known/assetlinks.json | Android App Links cassés ; n'importe quel APK même `package_name` peut se réclamer. |
| V-P0-02 | P0 | Service `astroscan.service` tourne `User=root` sans hardening systemd | /etc/systemd/system/astroscan.service | RCE n'importe où dans 32 BPs ⇒ root shell complet. |
| V-P0-03 | P0 | PyJWT absent de `requirements.txt` malgré `import jwt` requis | push_engine.py:54,64 + requirements.txt | Phase A push inutilisable au redéploiement. Silently fail-soft (push_enabled=False). |
| V-P0-04 | P0 | Header nginx `Permissions-Policy: geolocation=()` | nginx/astroscan.space:53 | Navigateur bloque navigator.geolocation → la page driver ne peut PAS envoyer de position. |
| V-P1-01 | P1 | SECRET_KEY Sentinel = SECRET_KEY Flask globale du monolithe | tokens.py:16 + app/__init__.py | Fuite côté autres routes = compromission complète Sentinel. |
| V-P1-02 | P1 | Token parent et driver partagent les mêmes droits de lecture sur `last_lat/lon` | telemetry_engine.public_state | Si un token fuite (SMS, capture écran), position GPS live exposée jusqu'à 90 min. |
| V-P1-03 | P1 | Aucune rétention DB automatique sur sessions ENDED | store.purge_old | RGPD : positions GPS persistent indéfiniment si pas de trafic create. |
| V-P1-04 | P1 | Rate-limit process-local (4 workers ⇒ 4× la limite) | app/services/security.py | Bypass facile par burst, surtout sur /sos (6/min ⇒ 24/min effectif). |
| V-P1-05 | P1 | APK servis publiquement sans hash check, sans signature externe documentée | routes.py:171-180 | MITM TLS device-side → APK trojanisé. Aucun checksum/signature published. |
| V-P2-01 | P2 | itsdangerous SHA-1 par défaut au lieu de SHA-256 | tokens.py:16 | Crypto vieillissante ; pas critique sur TTL court mais notable. |
| V-P2-02 | P2 | Pas de revocation/blacklist tokens | tokens.py | Token volé valide jusqu'à TTL (90 min max). |
| V-P2-03 | P2 | Pas de CSP ni COOP/COEP côté nginx | sites-enabled/astroscan.space | Aucun bouclier XSS hors `nosniff`/`X-Frame-Options`. |
| V-P2-04 | P2 | parent et driver voient le même payload state | telemetry_engine.public_state:23-65 | Driver voit aussi `last_lat/lon` (sa propre position) — pas un risque réel, mais le `role` paramètre est ignoré. |
| V-P2-05 | P2 | Import cyclique différé `from app.blueprints.sentinel.routes import SIGNAL_LOSS_THRESHOLD` | session_manager.py:116 | Anti-pattern. Devrait être dans `state_machine` ou un `constants.py`. |
| V-P2-06 | P2 | Aucun rate-limit par session_id (juste par IP) | tous les API endpoints | Plusieurs sessions derrière une seule IP → bypass possible. |
| V-P2-07 | P2 | Aucun lock applicatif sur opérations concurrentes write_telemetry | store.write_telemetry | SQLite WAL gère, mais sous charge un last-write-wins peut perdre un over_speed flag. |
| V-P3-01 | P3 | Interpolation f-string sur noms de colonnes dans `set_push_token` | store.py:369 | Whitelist couvre, mais code fragile pour reviewer junior. |
| V-P3-02 | P3 | Docstring d'en-tête routes.py liste 12 routes, 22 en réalité | routes.py:20-32 | Drift documentaire. |
| V-P3-03 | P3 | `assert_no_silent_deletion` jamais appelé | anti_cut_engine.py:39 | Garde dormante, intention louable mais dead-code. |
| V-P3-04 | P3 | DB file `archive_stellaire.db` mode 644 lisible par groupe `zakaria` | data/archive_stellaire.db | Sur un serveur multi-user, le groupe `zakaria` peut lire toutes les positions GPS. Single-user serveur Hetzner → faible impact. |

**Note sécurité globale : 5.5 / 10.** Sentinel a une architecture défensive solide (anti-cut, audit-logger PII-clean, FSM isolée) mais souffre de **trois P0 environnementaux** (systemd nu, App Links cassés, PyJWT manquant) et d'un **P1 SECRET_KEY partagée** qui sont des failles d'ops, pas de code.

---

## 5. QUALITÉ DE CODE

### 5.1 Style PEP-8

Inspection visuelle des 16 modules :
- Indentation 4 espaces uniforme.
- Imports ordonnés `stdlib → third-party → app local`.
- `from __future__ import annotations` partout.
- Type hints modernes (`str | None`, `tuple[str, str]`) cohérents.
- Lignes ≤100 caractères majoritairement, quelques dépassements bénins.
- snake_case partout, PascalCase pour les exceptions et `ConsentResult`.
- Aucune ligne morte évidente. Aucun `print()`.

**Note style : 9/10.**

### 5.2 Tests

```bash
find /root/astro_scan/tests -iname "*sentinel*"
→ (vide)
```

**Aucun test unitaire ni intégration Sentinel.** `/root/astro_scan/tests/` existe (smoke + unit + integration sous-dirs) mais aucun fichier Sentinel.

C'est le **trou le plus grave en qualité code**. Toutes les invariants critiques (anti-cut, FSM, consent gate, audit PII-strip) ne sont vérifiées que par lecture statique.

**Note tests : 0/10.**

### 5.3 Logging

- 2 loggers déclarés : `astroscan.sentinel` et `astroscan.sentinel.push`, plus `astroscan.sentinel.audit`.
- Niveau utilisé : `log.info` (events business), `log.warning` (erreurs FCM), `log.exception` (health failure).
- **Format des logs :** `sid=%s role=%s event=%s ok=%s` — **jamais** de lat/lon, **jamais** de token, **jamais** de driver_label.
- **Sensibilité PII :** ✅ exemplaire. Le seul scope qui pourrait logger PII est `_render` dans push_engine qui injecte `driver_label` dans le body de notification — mais c'est par design (le parent doit voir « Anis dépasse 90 km/h »).

**Trou opérationnel :** journalctl pour `astroscan.service` est **vide à l'audit** (« No entries »). Soit le service ne loggue jamais en stdout/stderr (gunicorn capture), soit l'audit tourne avec un user sans accès journal. Pas de log file persistant configuré → **les events Sentinel ne sont accessibles qu'en DB** (`sentinel_events`), pas dans `/var/log/`.

**Note logging : 7/10 (qualité parfaite, opérationnalisation faible).**

### 5.4 Error handling

Chaque exception métier (`SessionError`, `TokenError`, `AntiCutViolation`, `ValidationError`) a une classe propre, un code HTTP associé, un mapper en route. Pas de `except Exception: pass` silencieux côté logique métier.

**Exceptions silencieuses observées :**
- `push_engine` : fail-soft total (par design — push est un layer optionnel).
- `audit_logger._emit` : aucune capture → si la DB plante au `add_event`, ça remonte → c'est OK.
- `routes.py:151-156` (assetlinks) : `FileNotFoundError` → 404 JSON vide. OK.
- `routes.py:412-429` (health) : `except Exception` → 503. OK car endpoint de monitoring.

**Note error handling : 8/10.**

### 5.5 Docstrings

Chaque module commence par un docstring de 5-20 lignes expliquant le pourquoi (legal posture, invariants, design). Les fonctions publiques sont moins documentées (justifications « le nom suffit ») — acceptable.

**Note docstrings : 7/10.**

### 5.6 TODO/FIXME/XXX/HACK

```
grep -rnE "TODO|FIXME|XXX|HACK" app/blueprints/sentinel/*.py
→ (aucun match)
```

**Code zéro-dette commentaire.** C'est inhabituel et bon signe.

### 5.7 Code mort

- `anti_cut_engine.assert_no_silent_deletion` jamais appelé → dead-code intentionnel (garde dormante documentée).
- Aucun autre code mort détecté.

### 5.8 Note qualité code globale

**8/10.** Style propre, error handling typé, zéro TODO, docstrings utiles. La seule lacune est l'absence totale de tests.

---

## 6. ÉTAT PRODUCTION

### 6.1 Service `astroscan.service` — durcissement

```ini
[Service]
User=root                            # ⚠ devrait être un user dédié non-privilégié
WorkingDirectory=/root/astro_scan
TimeoutStopSec=150
ExecStart=/usr/bin/env python3 -m gunicorn \
    --workers 4 --threads 4 --timeout 120 --graceful-timeout 120 \
    --keep-alive 5 --max-requests 1000 --max-requests-jitter 50 \
    --bind 127.0.0.1:5003 wsgi:app
Restart=always
RestartSec=3
StartLimitIntervalSec=60
StartLimitBurst=10
# ABSENT : NoNewPrivileges, ProtectSystem, PrivateTmp, ReadWritePaths,
#          ProtectHome, ProtectKernelTunables, RestrictAddressFamilies,
#          MemoryMax, LimitNOFILE, CapabilityBoundingSet
```

État : **`active`** (vérifié `systemctl is-active`).

**Manquants vs V2 archive (qui était sensiblement mieux durci) :**
- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict` + `ReadWritePaths=/root/astro_scan/data /root/astro_scan/logs /tmp`
- `ProtectHome=read-only`
- `LimitNOFILE=4096`, `MemoryMax=512M`
- `User=` non-root

**Note durcissement : 3/10.**

### 6.2 Logs

- Logger Python actif (`astroscan.sentinel.*`) mais sortie capturée par Gunicorn.
- Aucun fichier log dédié Sentinel.
- journalctl muet (faute de droits ou absence de stdout/stderr config).
- Pas de logrotate Sentinel.

**Note logs : 2/10.**

### 6.3 Backup DB sentinel

- Base : `/root/astro_scan/data/archive_stellaire.db` (9.3 Mo).
- **Aucun backup dédié observable** dans `/root/astro_scan/data/data.bak/` (le dossier `data.bak/` existe pour le contenu de date 2026-03-08/09 — pas pour la DB elle-même).
- Aucun cron user `root` actif (`crontab -l` vide).
- Aucun service systemd timer pour backup.

**Note backup : 1/10.**

### 6.4 Healthcheck `/api/sentinel/health`

Réponse live (vérifiée) :
```json
{
  "data": null,
  "module": "astroscan_sentinel",
  "version": "1.0.0",
  "max_ttl_seconds": 5400,
  "sos_hold_seconds": 3,
  "over_speed_streak_seconds": 15,
  "signal_loss_threshold_seconds": 30,
  "update_interval_seconds": 5,
  "push_enabled": false,
  "sessions": {
    "pending": 0, "active": 0, "stop_pending": 0,
    "ended": 1, "expired": 0,
    "sos_unack": 0, "total": 1,
    "server_time": 1778848063
  },
  "ok": true,
  "timestamp": "2026-05-15T12:27:43.439302+00:00"
}
```

Couverture : version, constants exposées, push status, counters par état, sos_unack monitoring. **Excellent niveau.**

**Note healthcheck : 9/10.**

### 6.5 Monitoring externe

Sentry possible (clé `SENTRY_DSN` opt-in, code dans `app/__init__.py:96-112`). Si `SENTRY_DSN` non setté, aucune télémétrie sortante. **À vérifier en env.** Pas de Prometheus/StatsD. Pas d'alerting sur `sos_unack > 0`.

**Note monitoring : 3/10.**

### 6.6 Note prod-readiness globale

**4/10.** Le service tourne et le healthcheck est riche, mais service `User=root` nu + zéro backup + zéro alerting + zéro logging fichier = pas du tout prod-grade pour un produit safety.

---

## 7. INTÉGRATION APK ANDROID

### 7.1 `/.well-known/assetlinks.json`

**Chemin de service :** route Flask `@sentinel_bp.route("/.well-known/assetlinks.json")` → lit `/root/astro_scan/static/.well-known/assetlinks.json` et le sert avec `mimetype=application/json`.

**Contenu actuel :**
```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "space.astroscan.sentinel.driver",
      "sha256_cert_fingerprints": []      ← VIDE
    }
  },
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "space.astroscan.sentinel.parent",
      "sha256_cert_fingerprints": []      ← VIDE
    }
  }
]
```

**Implications :**
- Google Play Asset Statements vérificateur (https://digitalassetlinks.googleapis.com/v1/statements:list) renverra `"matchingStatements":[]` → autoVerify=true côté APK ne validera **jamais** → le système Android **n'enregistrera pas** Sentinel comme handler des liens `astroscan.space/sentinel/*` → ouverture d'un chooser à chaque lien.
- Sécurité : n'importe quel APK rebadgé sous `package_name=space.astroscan.sentinel.driver` peut prétendre être l'app autorisée. Le fingerprint vide rend la vérification inopérante.

### 7.2 Code routes.py

```python
_ASSETLINKS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "static", ".well-known", "assetlinks.json",
)

@sentinel_bp.route("/.well-known/assetlinks.json", methods=["GET"])
def assetlinks():
    try:
        with open(_ASSETLINKS_PATH, "rb") as f:
            return Response(f.read(), mimetype="application/json")
    except FileNotFoundError:
        return Response(json.dumps([]), mimetype="application/json"), 404
```

Sain. Lecture binaire, pas d'interpolation, mimetype correct.

### 7.3 Localisation APK

```
/root/astro_scan/static/downloads/
├── sentinel-driver.apk    163 Mo (signé localement)
└── sentinel-parent.apk    150 Mo
```

Code source mobile : `/root/sentinel_mobile/` (projet Flutter/Melos avec 4 packages : `sentinel_core`, `sentinel_driver_android`, `sentinel_parent_android`, `sentinel_ui`).

### 7.4 Risques deep linking

- **Sans fingerprint :** un APK pirate avec le même `package_name` peut intercepter les liens et lire le `<token>` dans l'URL `/sentinel/driver/<token>`. Avec ce token, accès complet à la session pendant 90 min.
- **Avec fingerprint correct (prochaine étape requise) :** Android vérifie le certificat de signature de l'APK installée ; seule l'APK signée par ta clé prod peut intercepter le lien autoVerify.

### 7.5 Recommandations

1. **Avant rebranchement public :**
   - Signer les deux APK avec une clé de release dédiée (gardée hors repo, mode 0600).
   - Calculer le fingerprint : `keytool -list -v -keystore release.keystore | grep SHA256`.
   - Injecter le fingerprint dans `static/.well-known/assetlinks.json` pour les **deux** packages.
   - Re-tester via https://developers.google.com/digital-asset-links/tools/generator.
2. **Avant publication APK :**
   - Publier les checksums SHA-256 des deux APK sur la landing `/sentinel`.
   - Idéalement publier sur Play Store (verification managée par Google).
3. **Defense-in-depth :** ajouter dans le manifest Android `android:allowAutoVerify="true"` + tester avec `adb shell pm verify-app-links`.

---

## 8. COMPARAISON V1 vs V2 ARCHIVE

### 8.1 Ce que V2 avait de mieux (`.archive_sentinel_v2_squelette_20260515/`)

V2 était un squelette en cours de re-write avec une approche « bonnes pratiques » :

| Aspect | V2 |
|--------|-----|
| Layout | Application factory propre (`backend/app/__init__.py`), config.py séparé, blueprints/, extensions.py, error_handlers.py, db.py, utils/ |
| Env | `.env` isolé dans `backend/.env`, jamais en config Python |
| Systemd | `User=zakaria`, `NoNewPrivileges=true`, `ProtectSystem=strict`, `PrivateTmp=true`, `ProtectHome=read-only`, `ReadWritePaths=` explicites, `LimitNOFILE=4096`, `MemoryMax=512M`, port dédié `:5100` |
| Service worker | `--access-logfile -`, `--error-logfile -`, `--log-level info` |
| Périmètre | Isolé du monolithe, donc une RCE Sentinel ne touche pas le reste |

### 8.2 Ce que V1 a de mieux

| Aspect | V1 |
|--------|-----|
| Métier | **925 lignes V2 vs 2029 lignes V1.** Toute la logique vraie (FSM, anti-cut, alert, push, audit, telemetry, consent, batch, APK serving) est dans V1. V2 n'avait que des stubs. |
| FCM | V1 a un push_engine prêt à activer (250 lignes). V2 : 0 ligne push. |
| APK Android | V1 sert les APK + assetlinks.json. V2 : 0 ligne. |
| Templates UI | V1 a `landing.html` (132 lignes) + `driver.html` (119) + `parent.html` (108). V2 : stubs. |
| Audit trail | V1 a 14 events typés. V2 : pas d'audit logger. |
| FSM | V1 a la FSM dual-stop complète. V2 : pas de FSM cohérente. |
| Intégration monolithe | V1 est déjà branché, déjà servi, déjà sur :5003 derrière nginx. V2 était sur :5100, isolé, jamais branché publiquement. |

### 8.3 Quoi extraire de V2 pour réinjecter dans V1

**Recommandation : ne PAS recopier V2 en code, mais en INFRA.** Les fichiers V2 utiles à porter :

1. **`deploy/sentinel-prod.service` → fusionner dans `astroscan.service` :**
   - Ajouter `NoNewPrivileges=true`.
   - Ajouter `PrivateTmp=true`.
   - Ajouter `ProtectSystem=strict` + `ReadWritePaths=/root/astro_scan/data /root/astro_scan/static/downloads /root/astro_scan/logs /tmp`.
   - Ajouter `ProtectHome=read-only` (NB : `WorkingDirectory=/root/astro_scan` donc `/root` doit rester lisible — utiliser `ProtectHome=tmpfs` ou laisser de côté).
   - Ajouter `LimitNOFILE=4096`, `MemoryMax=2G` (le monolithe est plus gros que sentinel-prod seul).
   - Migrer vers `User=astroscan` non-root (chantier plus large, pas critique pour Sentinel seul).

2. **Pattern `.env` isolé pour Sentinel** : créer `/root/.config/sentinel/sentinel.env` (mode 0600 root) qui contient `FCM_PROJECT_ID=` et `FCM_SERVICE_ACCOUNT_PATH=` ; charger via `EnvironmentFile=` dans une unit override. Évite de polluer le `.env` global d'astroscan avec les credentials FCM.

3. **Ne rien recopier d'autre.** L'architecture monolithe + factory `create_app` de V1 est plus mature que celle de V2.

---

## 9. PLAN REBRANCHEMENT PUBLIC SÉCURISÉ

État de départ : nginx bloque `^/(sentinel|vehicle-secure-locator|vehicle|guardian-family|api/sentinel|modules/sentinel)` avec `return 404`. Code Flask tourne sain sur 127.0.0.1:5003.

### PASS 1 — Durcissement systemd (1h) — **BLOQUANT**

- Backup : `cp /etc/systemd/system/astroscan.service{,.bak_$(date +%Y%m%d_%H%M)}`.
- Ajouter au `[Service]` :
  ```
  NoNewPrivileges=true
  PrivateTmp=true
  ProtectSystem=strict
  ReadWritePaths=/root/astro_scan/data /root/astro_scan/static/downloads /root/astro_scan/logs /tmp
  ProtectHome=read-only
  LimitNOFILE=4096
  ```
- `systemctl daemon-reload && systemctl restart astroscan`.
- Vérif : `curl http://127.0.0.1:5003/api/sentinel/health` retourne 200.
- Vérif : `systemctl status astroscan` pas d'erreur démarrage.

### PASS 2 — Provisioning FCM ou désactivation explicite (1h) — **NON-BLOQUANT (peut désactiver)**

Option A (provisionner) :
- Ajouter `PyJWT==2.9.0` (ou compatible) à `requirements.txt`.
- `pip install -r requirements.txt`.
- Poser `firebase-sa.json` mode 0600 dans `/root/.config/sentinel/`.
- Exporter env `FCM_PROJECT_ID` + `FCM_SERVICE_ACCOUNT_PATH` via `EnvironmentFile` systemd.
- Restart, vérifier `push_enabled: true` sur `/health`.

Option B (couper explicitement) : laisser `push_enabled: false`, documenter sur la landing « notifications push réservées à l'app Android signée prochainement disponible ». Côté code, rien à changer (`is_configured()` retourne déjà false).

### PASS 3 — Signature APK + injection fingerprints (2h) — **BLOQUANT**

- Générer keystore prod (si pas déjà existant) : `keytool -genkeypair -alias sentinel-driver -keystore /root/.config/sentinel/release.keystore -keyalg RSA -keysize 4096 -validity 36500`.
- Re-builder + signer les deux APK avec `jarsigner` ou via Gradle `signingConfigs`.
- Calculer fingerprint : `keytool -list -v -keystore /root/.config/sentinel/release.keystore | grep SHA256`.
- Éditer `/root/astro_scan/static/.well-known/assetlinks.json` → insérer **le même** fingerprint dans les deux blocs `sha256_cert_fingerprints` (parent + driver).
- Tester via `curl https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://astroscan.space&relation=delegate_permission/common.handle_all_urls`.
- Republier les APK signés dans `/root/astro_scan/static/downloads/`.
- Publier SHA-256 des APK sur la landing.

### PASS 4 — Fix Permissions-Policy nginx (15 min) — **BLOQUANT**

Éditer `/etc/nginx/sites-enabled/astroscan.space:53` :
```
add_header Permissions-Policy "geolocation=(self), microphone=(), camera=(), payment=()" always;
```
Restreindre encore : seulement sur `/sentinel/*` si tu veux blocker geolocation ailleurs. `nginx -t && systemctl reload nginx`.

### PASS 5 — Tests fumée e2e (1h) — **BLOQUANT**

Scénario manuel ou script :
1. `POST /api/sentinel/session/create` → tokens.
2. `GET /sentinel/driver/<token>` → 200 HTML.
3. `POST /api/sentinel/session/accept` → ACTIVE.
4. `POST /api/sentinel/session/update` × 5 → telemetry persistée.
5. `POST /api/sentinel/session/sos` → sos_active=1, event en DB.
6. `POST /api/sentinel/session/sos_ack` → sos_ack_at posé.
7. `POST /api/sentinel/session/stop_request` (parent) → STOP_PENDING_PARENT.
8. `POST /api/sentinel/session/stop_approve` (driver) → ENDED.

Vérifier `sentinel_events` contient 8 events distincts.

### PASS 6 — Rebranchement nginx (5 min) — **ACTION FINALE**

- Backup nginx : `cp /etc/nginx/sites-enabled/astroscan.space{,.bak_$(date +%Y%m%d_%H%M)}`.
- Supprimer le bloc `# === SENTINEL TEMPORARILY HIDDEN ===` (lignes 35-44).
- `nginx -t && systemctl reload nginx`.
- Smoke : `curl -I https://astroscan.space/sentinel` → 200, `curl https://astroscan.space/.well-known/assetlinks.json` → 200 + JSON valide avec fingerprints.

### Sous-total bloquant : **6 h 15 min** (sans buffer)

### Post-rebranchement (non-bloquant)

| PASS | Durée | Description |
|------|-------|-------------|
| 7 | 4h | Écrire la suite de tests Pytest unitaires sur FSM + anti-cut + consent + audit-PII-strip. |
| 8 | 1h | Cron de backup quotidien SQLite (`sqlite3 archive_stellaire.db .backup` → `/root/backups/`). |
| 9 | 2h | Endpoint admin (`require_admin`) GET `/api/sentinel/admin/sessions` pour visualiser/purger manuellement. |
| 10 | 1h | Politique RGPD : doc rétention (90 jours max sur sentinel_sessions terminales), point de contact, lien sur landing. |
| 11 | 2h | Migrer SECRET_KEY Sentinel sur une clé dédiée (`SENTINEL_SECRET_KEY` env) au lieu du SECRET_KEY global. |
| 12 | 3h | Web Push (VAPID) pour usage navigateur sans APK. |

### Ce qui peut attendre

- Migration `User=root` → `User=astroscan` (chantier global monolithe).
- Migration rate-limit process-local → Redis (volume trop faible aujourd'hui).
- Logs persistants vers fichier + logrotate.
- Monitoring Prometheus.
- CI/CD avec déploiement automatique.

---

## 10. DETTE TECHNIQUE & BUGS

### 10.1 Bugs détectés (lecture statique, lecture seule)

| ID | Sévérité | Localisation | Description |
|----|----------|--------------|-------------|
| B-P0-01 | P0 | `requirements.txt` vs `push_engine.py:54,64` | `import jwt` requis mais **PyJWT absent du requirements**. Conséquence : sur déploiement neuf, `is_configured()` retourne `false` même si tout le reste est OK. Phase A push **inutilisable**. |
| B-P0-02 | P0 | `/etc/nginx/sites-enabled/astroscan.space:53` | `Permissions-Policy: geolocation=()` bloque `navigator.geolocation` côté navigateur. La page driver ne peut PAS demander la position GPS. |
| B-P1-01 | P1 | `app/__init__.py` (auto-purge) | `purge_old()` n'est appelée que sur `create_session`. Si pas de création, les sessions ENDED s'accumulent sans expiration de retention. Aucun worker périodique. |
| B-P1-02 | P1 | `assertlinks.json` | Fingerprints SHA-256 vides → App Links cassés (déjà couvert sécurité). |
| B-P2-01 | P2 | `routes.py:20-32` docstring | Liste 12 routes alors qu'il y en a 22 — drift documentaire. |
| B-P2-02 | P2 | `telemetry_engine.py:23-65` | Paramètre `role` accepté mais jamais utilisé pour différencier le payload. Parent et driver voient le même contenu. |
| B-P2-03 | P2 | `anti_cut_engine.py:39` | `assert_no_silent_deletion` jamais appelé — dead code (intention documentée mais inerte). |
| B-P2-04 | P2 | `session_manager.py:116` | Import cyclique différé `from app.blueprints.sentinel.routes import SIGNAL_LOSS_THRESHOLD` au runtime. Devrait vivre dans `state_machine.py` ou un `constants.py` dédié. |
| B-P3-01 | P3 | `routes.py:413-429` | `api_health()` try/except autour de TOUT. Si une seule colonne de health_counters échoue, on perd la visibilité de tout le reste. Préférable de scoper le try sur `store.health_counters()` seulement. |
| B-P3-02 | P3 | `push_engine.py:204` | `notify(target="both")` retourne `a or b` — si parent succeed et driver fail, on a `True` (= ok). Sémantique masquée d'un échec partiel. Devrait retourner un dict `{parent: bool, driver: bool}`. |
| B-P3-03 | P3 | `store.py:268-278` `mark_expired_if_due` | Ne notifie pas `push_engine` directement. La notification est dans `session_manager.public_state` mais pas dans `push_position`. Si l'expiry arrive pendant un update driver, le parent n'est notifié qu'à son prochain `state`. |
| B-P3-04 | P3 | `audit_logger.py:23` | `log.info("[SENTINEL] %s sid=%s", event_type, session_id)` — manque `[AUDIT]` ou similaire pour les filtres logfile. |

### 10.2 Dette technique

| Catégorie | État |
|-----------|------|
| **Tests** | ❌ Zéro test unitaire ni intégration Sentinel. Bloquant pour itérer en confiance. |
| **Git** | Le repo `/root/astro_scan` est un git repo (branche `main`), mais l'inventaire des `.bak_*` (5 backups manuels dans le dossier Sentinel + ~10 backups de `station_web.py`) suggère un workflow **fichier-bak** plutôt que git. Drift de discipline. |
| **CI/CD** | Non observé. Déploiement à la main. |
| **Documentation API** | Aucune doc OpenAPI/Swagger. La seule doc est le docstring d'en-tête de `routes.py` (qui drifte déjà). |
| **Runbook** | Inexistant. Pas de procédure « comment redémarrer Sentinel », « comment purger une session », « comment révoquer un token ». |
| **Monitoring** | Aucun. Pas d'alerting sur `sos_unack > 0`. Pas de SLO. |
| **Backups DB** | Aucun automatique. La base contient pourtant des PII. |
| **Logs persistants** | Aucun fichier log Sentinel dédié. Journalctl muet. |
| **Migrations DB** | Pas d'Alembic/équivalent. `init_schema()` fait du ALTER TABLE ADD COLUMN idempotent en code Python — fragile mais fonctionne. |
| **Secrets management** | `.env` global du monolithe. Pas de vault, pas de rotation, pas de séparation Sentinel. |
| **i18n** | Push notifications hard-codées en français. `_render` dans push_engine. Pas de fallback. |
| **Accessibility** | Templates HTML pas audités (hors scope rapport). |
| **Mobile parity** | Code mobile dans `/root/sentinel_mobile/` (Flutter/Melos) mais pas relié au backend par contrat versionné. |
| **Web Push** | Absent. Notifications uniquement Android natif via FCM. Aucun fallback navigateur. |
| **Rate-limit per session** | Absent. Seulement par IP. |

---

## 11. RECOMMANDATIONS STRATÉGIQUES POUR ZAKARIA

### 11.1 Sentinel V1 comme asset pour ESA / NASA / Spire / Planet Labs / CNES ?

**Réponse honnête : ni asset, ni distraction — ça dépend du pitch.**

ASTRO-SCAN se positionne devant ESA/NASA comme une **plate-forme d'observation et de service spatial citoyen**. Sentinel est un **vertical safety familial** qui n'a aucun rapport thématique avec l'observation spatiale, l'astronomie, le tracking satellite, ou la météo spatiale.

Trois scénarios :

| Scénario | Quand l'utiliser | Risque |
|----------|------------------|--------|
| **A. Le cacher complètement** | Si tu pitches « observatoire de Tlemcen + bulletin scientifique + radar satellite ». | Aucun. Cohérence du pitch. |
| **B. Le mentionner comme « platform extensibility »** | Si tu veux montrer que ASTRO-SCAN n'est pas qu'un site, mais un monolithe de blueprints modulaires capable d'héberger des verticals additionnels (incl. safety, IoT, etc.). | **Moyen.** Demande à l'évaluateur de croire qu'un cas safety familial démontre une capacité à porter un cas spatial. Pas faux, mais glissant. |
| **C. Le pitcher comme produit indépendant** | Si tu vises un investisseur business angel ou un programme deep-tech B2C — pas ESA/NASA. | **Élevé.** Tu noies ton pitch principal. ESA va se demander « il fait du space ou du family safety ? ». |

**Recommandation : scénario A, secondairement B en bullet « extensibility » s'il y a un slot.** Ne pas le mettre en headline.

### 11.2 Faut-il l'exposer publiquement avant le 31 mai ?

**Trois questions à te poser :**

1. **As-tu un beta-tester réel autre que toi-même ?** Si oui (famille, entourage Tlemcen), oui, expose-le après le PASS 1–6 (6 h de travail).
2. **As-tu le temps de superviser un incident SOS frauduleux dans les 2 prochaines semaines ?** Si non, repousse à fin mai.
3. **Est-ce que la candidature ESA/NASA va citer Sentinel ?** Si oui, expose-le **avant** la candidature pour que le lien `astroscan.space/sentinel` soit vivant. Si non, expose-le **après** mi-juin.

### 11.3 Risques réputationnels si exposé avec failles

Avec les 3 P0 actuels (systemd nu + assetlinks vides + PyJWT manquant) **exposé en l'état** :

| Risque | Probabilité | Impact |
|--------|-------------|--------|
| APK pirate intercepte les liens deep link et lit des tokens session | Faible (besoin d'installer un APK malveillant nommé pareil) | **Élevé** : fuite GPS temps-réel d'utilisateurs familles |
| Notification push promise mais ne marche jamais | Élevée si l'utilisateur installe l'APK | **Moyen** : crédibilité produit. Une app safety qui ne notifie pas est un bug fatal en perception. |
| RCE sur un autre BP du monolithe (32 BPs) compromet root → leak DB Sentinel (positions GPS) | Faible (32 BPs est large surface) | **Critique** : leak PII GPS familles → presse + CNIL |
| Permissions-Policy bloque navigator.geolocation → page driver inopérante en navigateur | Élevée (config nginx actuelle) | **Moyen** : « le site marche pas », abandon |

### 11.4 Recommandation finale

**Garder Sentinel caché jusqu'au 1er juin.** Concentrer le temps restant (15 jours) sur :
1. La candidature ESA / NASA / Spire / Planet Labs / CNES (priorité #1, deadline 31 mai).
2. Hardening minimal Sentinel en parallèle (6h, peut être étalé sur 3 sessions).
3. Rebranchement nginx **après** soumission candidatures, autour du **2-3 juin** → pas de pression, pas de surface d'incident sur le timing critique de la candidature.

Si pression interne (envie d'avoir Sentinel live pour rasure-toi), expose **uniquement** la landing `/sentinel` (page statique de présentation) sans les routes API, avec un CTA « beta privée — demandez l'accès ». Ça satisfait le besoin de présence sans exposer la surface critique.

---

## 12. ANNEXES

### A. requirements.txt — segment Sentinel-pertinent

```
Flask==3.1.3
itsdangerous==2.2.0          # tokens.py
requests==2.32.5             # push_engine.py
flask-sock==0.7.0            # non utilisé par Sentinel
sentry-sdk==2.58.0           # opt-in via SENTRY_DSN env
# MANQUANT : PyJWT (utilisé par push_engine.py)
```

### B. `__init__.py` reproduit

```python
# ASTROSCAN SENTINEL — Premium family safety + protected trip intelligence.
# Single flagship product; supersedes vehicle_locator + guardian prototypes.
# See routes.py for the complete legal / consent posture.
from app.blueprints.sentinel.routes import sentinel_bp  # noqa: F401
```

### C. Liste des @sentinel_bp.route avec auth status

```
# Pages HTML
GET   /sentinel                              public
GET   /sentinel/driver/<token>               token role=driver
GET   /sentinel/parent/<token>               token role=parent

# Deprecation 301
GET   /vehicle-secure-locator                public → 301 /sentinel
GET   /vehicle                               public → 301 /sentinel
GET   /guardian-family                       public → 301 /sentinel

# Asset distribution
GET   /.well-known/assetlinks.json           public
GET   /modules/sentinel/<filename>           public (whitelist 2 APK)

# API session lifecycle
POST  /api/sentinel/session/create           public        rl=6/min
POST  /api/sentinel/session/accept           token=driver  rl=12/min
POST  /api/sentinel/session/update           token=driver  rl=30/min
GET   /api/sentinel/session/<token>/state    token=any     rl=120/min
POST  /api/sentinel/session/sos              token=driver  rl=6/min
POST  /api/sentinel/session/sos_ack          token=parent  rl=12/min
POST  /api/sentinel/session/stop_request     token=any     rl=6/min
POST  /api/sentinel/session/stop_approve     token=any     rl=6/min
POST  /api/sentinel/session/push/register    token=any     rl=12/min
POST  /api/sentinel/session/push/unregister  token=any     rl=12/min
POST  /api/sentinel/session/update/batch     token=driver  rl=12/min

# Monitoring
GET   /api/sentinel/health                   public
```

Total : **22 routes effectives** (20 fonctions handler ; 3 alias `@route` sur `deprecated_redirect` ; soit 20+2 entrées supplémentaires d'URL = 22 enregistrements `url_map`).

### D. SHA-256 des fichiers critiques

```
06486246c38a84768473886a8d6f7203fe88083f6ee2cf09a202260f7ddcd521  app/blueprints/sentinel/routes.py
778575317bee8552e25fde9660f3aa3770a6e4b851cfb2f5df165fe95438e9d2  app/blueprints/sentinel/store.py
83cff4e01d6e1c39c6388b2defed1123c8bf8ec802eac6ac5a3e939c449e1cb6  app/blueprints/sentinel/session_manager.py
6aa5a4abd4824ae8296f8c7a77d0e23b8b58bbc5dd01a90cfa985f93f1cec414  app/blueprints/sentinel/tokens.py
```

---

## VALIDATION FINALE

- **Date :** 2026-05-15
- **Auditeur :** Claude Code Opus 4.7 (`claude-opus-4-7`)
- **Hash SHA-256 des 4 fichiers critiques :**
  - `routes.py` : `06486246c38a84768473886a8d6f7203fe88083f6ee2cf09a202260f7ddcd521`
  - `store.py` : `778575317bee8552e25fde9660f3aa3770a6e4b851cfb2f5df165fe95438e9d2`
  - `session_manager.py` : `83cff4e01d6e1c39c6388b2defed1123c8bf8ec802eac6ac5a3e939c449e1cb6`
  - `tokens.py` : `6aa5a4abd4824ae8296f8c7a77d0e23b8b58bbc5dd01a90cfa985f93f1cec414`

**Audit V1 terminé. Sentinel prêt pour décision Zakaria + Claude Web.**
