# Telescope Bridge — API contract (V1)

Préfixe : `/api/telescope-bridge/`
Auth : selon endpoint (session web, token agent, ou aucun).
Format : JSON, UTF-8. Tous les timestamps en ISO-8601 UTC.

## Auth headers

| Header | Origin | Forme |
|---|---|---|
| `Authorization: Bearer <jwt>` | agent | JWT HS256, claim `scope:"agent"`, `agent_id`, `user_id`, `exp` |
| `X-Bridge-Nonce: <hex>` | agent | 128 bits aléatoires, anti-replay |
| `X-Bridge-Agent-Version: <semver>` | agent | informationnel |
| Cookie `astroscan_sid` | dashboard | session web AstroScan existante |

## Endpoints

### POST /pair/init  (dashboard → serveur)

Crée un code pairing à 6 chiffres, single-use, TTL 10 min.

**Auth**: session utilisateur (cookie).
**Body**: vide ou `{"label":"Backyard PC"}` (libellé optionnel).
**Réponse 201**:
```json
{"pair_code":"479201","ttl_seconds":600,"label":"Backyard PC"}
```
**Rate limit**: 5 codes actifs max par user, 1 req/min.

### POST /pair/confirm  (agent → serveur)

Échange code pairing contre JWT de session.

**Auth**: aucune (le code EST l'authentification temporaire).
**Body**:
```json
{
  "pair_code":"479201",
  "agent_fingerprint":"<sha256 stable de hostname+install_id>",
  "agent_version":"0.1.0",
  "os":"linux|windows|macos"
}
```
**Réponse 200**:
```json
{
  "session_jwt":"eyJhbGc…",
  "agent_id":"uuid",
  "expires_at":"2026-05-25T20:00:00Z",
  "refresh_after":"2026-05-24T20:00:00Z"
}
```
**Erreurs**: `404 code_unknown_or_expired`, `409 code_already_consumed`.

### POST /session/heartbeat  (agent → serveur)

Maintient la session active, renouvelle JWT si proche expiration.

**Auth**: Bearer agent.
**Body**:
```json
{"agent_uptime_s":3600,"adapters_loaded":["alpaca","mock"]}
```
**Réponse 200**:
```json
{"renewed":false,"session_jwt":null,"valid_until":"2026-05-25T20:00:00Z"}
```
Si `renewed:true`, nouveau JWT à stocker.

### DELETE /session/{session_id}  (dashboard → serveur)

Révoque immédiatement. L'agent verra une `401` au prochain POST et
redemande pairing.

### POST /devices/announce  (agent → serveur)

L'agent déclare la liste de devices détectés.

**Auth**: Bearer agent.
**Body**:
```json
{
  "devices":[
    {
      "device_local_id":"alpaca:telescope:0",
      "kind":"mount",
      "name":"EQ6-R Pro",
      "driver":"alpaca",
      "capabilities":["ra_dec","alt_az","tracking_state","slewing_state"]
    },
    {
      "device_local_id":"alpaca:camera:0",
      "kind":"camera",
      "name":"ASI2600MM",
      "driver":"alpaca",
      "capabilities":["temperature","exposure_state","binning"]
    }
  ]
}
```
**Réponse 200**: `{"accepted": 2, "device_ids": ["uuid1","uuid2"]}`.

### POST /telemetry  (agent → serveur)

Batch de samples (max 50, body ≤ 16 KB).

**Auth**: Bearer agent.
**Body**:
```json
{
  "samples":[
    {"device_id":"uuid1","kind":"mount","ts":"…","ra_hours":5.12,…},
    {"device_id":"uuid2","kind":"camera","ts":"…","ccd_temp_c":-10.5,…}
  ]
}
```
**Réponse 202**: `{"ingested": 50, "rejected": 0}`.
**Réponse 400**: schema invalide ; `rejected` liste les indices fautifs.

### GET /devices  (dashboard → serveur)

Liste des devices de l'utilisateur courant.

**Auth**: session web.
**Réponse 200**:
```json
{
  "devices":[
    {"device_id":"uuid1","kind":"mount","name":"EQ6-R Pro","last_seen":"…","online":true}
  ]
}
```

### GET /telemetry/latest?device_id=…  (dashboard → serveur)

Dernier sample en cache mémoire (≤ 1 s de fraîcheur en cas de poll actif).

**Auth**: session web.
**Réponse 200**: payload télémétrie typé (cf. `TELEMETRY_SCHEMA.md`).
**Réponse 404**: device pas trouvé OU n'appartient pas à l'utilisateur.

## Codes d'erreur normalisés

| Code | Sens |
|---|---|
| 400 `schema_invalid` | payload non conforme |
| 401 `auth_required` | header manquant |
| 401 `auth_expired` | JWT expiré, redemander pairing |
| 401 `auth_revoked` | session révoquée par user |
| 403 `quota_exceeded` | trop d'agents pour ce user |
| 404 `not_found` | ressource inexistante OU pas autorisée (volontairement ambigu) |
| 409 `code_already_consumed` | pairing code déjà utilisé |
| 422 `replay_detected` | nonce déjà vu |
| 429 `rate_limited` | nginx ou app-level |
| 503 `feature_disabled` | `FEATURE_TELESCOPE_BRIDGE=0` |

## Tableau de versionnement

Tous les endpoints retournent header `X-TB-API-Version: 1`. Une bump
majeure casserait le contrat ; on préfèrerait coexistence `v2/`.
