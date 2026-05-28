# Telescope Bridge V1 — Architecture détaillée

## 1. Topologie

```
hardware → ASCOM/Alpaca | INDI → agent local → HTTPS outbound → AstroScan API → dashboard
```

L'agent local est **le seul composant** qui parle ASCOM/INDI. Le serveur ne
connaît aucun protocole astronomique de bas niveau ; il reçoit uniquement
des objets télémétrie normalisés (JSON).

## 2. Composants serveur

| Module | Rôle |
|---|---|
| `api/routes_pair.py` | `POST /pair/init` (dashboard), `POST /pair/confirm` (agent) |
| `api/routes_session.py` | `POST /session/heartbeat`, `DELETE /session/{id}` |
| `api/routes_devices.py` | `POST /devices/announce` (agent), `GET /devices` (dashboard) |
| `api/routes_telemetry.py` | `POST /telemetry` (agent), `GET /telemetry/latest` (dashboard) |
| `api/auth.py` | Décorateur `@require_agent_token`, `@require_user_session` |
| `services/token_service.py` | Génération pairing code, JWT de session, rotation |
| `services/session_service.py` | Cycle de vie session, heartbeat, expiration |
| `services/registry.py` | Catalogue des devices déclarés par un agent |
| `services/telemetry_store.py` | Append-only SQLite `tb_telemetry` + ring buffer mémoire pour latest |
| `services/agent_directory.py` | État live des agents (connecté/déconnecté/last_seen) |
| `schemas/device.py` | Dataclass `Device` (id, kind, name, capabilities) |
| `schemas/telemetry.py` | Dataclasses par device_kind (`MountTelemetry`, `CameraTelemetry`, …) |
| `schemas/session.py` | Dataclass `Session` (id, user_id, agent_id, issued_at, expires_at) |
| `security/token.py` | `compare_digest`, HMAC-SHA256 sur tokens, JWT |
| `security/replay_cache.py` | LRU des nonces vus dans les 5 dernières minutes |
| `security/audit.py` | Append-only TSV `tb_audit.log` (pair, session, telemetry rejected) |
| `security/policy.py` | Allow-list des propriétés que l'agent peut envoyer (refuse le reste) |

## 3. Composants agent

| Module | Rôle |
|---|---|
| `astroscan_bridge/__main__.py` | Entrée : `python -m astroscan_bridge` (systemd / service Windows) |
| `astroscan_bridge/config.py` | Charge `~/.astroscan/agent.toml` + variables d'env |
| `astroscan_bridge/client.py` | Client HTTPS avec retry exponentiel, TLS pinning optionnel |
| `astroscan_bridge/adapters/base.py` | `AbstractAdapter` : `discover()`, `read(device_id)` ; **pas de `write`**. |
| `astroscan_bridge/adapters/alpaca.py` | Discovery UDP Alpaca + GET sur `/management/v1/configureddevices`, `/api/v1/{type}/{n}/{property}` |
| `astroscan_bridge/adapters/ascom_com.py` | Bindings ASCOM COM via `pywin32` (Windows natif optionnel) |
| `astroscan_bridge/adapters/indi.py` | Client INDI raw socket / `pyindi-client`, abonnement `getProperties` |
| `astroscan_bridge/adapters/mock.py` | Données synthétiques pour dev / CI |
| `astroscan_bridge/safety/readonly_filter.py` | **Garde absolu** : intercepte toute tentative d'appel d'une méthode "write" |
| `astroscan_bridge/safety/audit.py` | Audit local `~/.astroscan/agent.log` |
| `astroscan_bridge/service/poller.py` | Boucle de polling (5 s default, ajustable par device) |
| `astroscan_bridge/service/uploader.py` | Batch + envoi HTTPS, file FIFO en cas de panne réseau (max 1 000 entrées) |
| `astroscan_bridge/service/pairing.py` | Flux pairing 6-digit, stockage JWT dans Keychain OS |
| `astroscan_bridge/install/systemd.service.template` | Template systemd user unit |
| `astroscan_bridge/install/windows_service.bat` | Installation NSSM / sc.exe |

## 4. Stockage serveur

Une base SQLite **séparée** de la base principale :
`/opt/astroscan/data/telescope_bridge.db`

Tables :
- `tb_pair_codes` : codes pairing 6-digit, TTL 10 min, single-use.
- `tb_sessions` : sessions JWT actives, lien `user_id ↔ agent_id`.
- `tb_agents` : agents enregistrés (un user peut en avoir plusieurs).
- `tb_devices` : devices déclarés par un agent (mount/camera/focuser/…).
- `tb_telemetry` : append-only, partitionnée par jour côté requête.
- `tb_audit` : journal sécurité.

Voir `storage/schema.sql` pour le DDL.

## 5. Stockage agent

`~/.astroscan/agent.toml` (lecture seule après pairing) :
```toml
[bridge]
server_url    = "https://astroscan.space"
agent_id      = "uuid-v4"
poll_interval = 5

[telemetry]
upload_batch_size = 50
upload_period_s   = 30
```

`~/.astroscan/agent.log` : append-only, rotation 10 MB.

Le **JWT n'est pas dans le fichier TOML**. Il est stocké dans :
- Windows : DPAPI (`win32crypt`)
- macOS  : Keychain (`keyring`)
- Linux  : Secret Service (`keyring` + libsecret)

## 6. Modèles de fil de données

### 6.1 Pairing (one-shot)

```
dashboard      server                          agent
   │  POST /pair/init                            │
   │ ────────────►   create pair_code (6 digits) │
   │ ◄────────────  {code:"479201", ttl:600}     │
   │                                             │
   │ user saisit code dans agent
   │                                             │
   │              POST /pair/confirm             │
   │              {code, agent_fingerprint}      │
   │              ◄──────────────────────────────│
   │              issue JWT scope=agent          │
   │              tb_sessions.row INSERT          │
   │              ──────────────────────────────►│
   │                                  {jwt, exp} │
```

### 6.2 Telemetry steady state

```
agent                                                server
 │   GET ASCOM/INDI properties (read-only)
 │   build batch (max 50 samples)
 │   POST /telemetry  Bearer <jwt>
 │ ───────────────────────────────────────────────► validate auth
 │                                                  validate schema (policy.py)
 │                                                  validate nonce (replay_cache)
 │                                                  INSERT tb_telemetry
 │                                                  push to in-mem latest
 │ ◄─────────────────────────────────────────────── 202 Accepted {ingested:50}
```

### 6.3 Dashboard read

```
browser                  server
   │  GET /api/telescope-bridge/devices
   │     (cookie session user)
   │ ─────────────────────────────────►  load tb_devices WHERE user_id=…
   │ ◄─────────────────────────────────  list[Device]
   │
   │  GET /api/telescope-bridge/telemetry/latest?device_id=…
   │ ─────────────────────────────────►  return latest in-mem snapshot
   │ ◄─────────────────────────────────  MountTelemetry | CameraTelemetry | …
```

## 7. Intégration au reste d'AstroScan

- **Aucune modification** de `app/__init__.py` en Phase 1.
- En Phase 2 : ajout d'un bloc derrière flag dans `_register_blueprints`,
  isolé en `try/except` (boot ne casse pas si import échoue) :
  ```python
  if os.environ.get("FEATURE_TELESCOPE_BRIDGE", "0") == "1":
      try:
          from modules.telescope_bridge.api import bp as tb_bp
          app.register_blueprint(tb_bp, url_prefix="/api/telescope-bridge")
      except Exception as e:
          log.warning("[telescope_bridge] disabled: %s", e)
  ```
- Pas de partage de SECRET_KEY : le JWT du bridge utilise sa propre clé
  `TB_JWT_SIGNING_KEY` (HS256), indépendante de Flask.
