# Telescope Bridge — Threat Model

10 menaces inventoriées. Pour chaque : description, impact, surface,
mitigation V1, mitigation future.

## T1 — Commande de mouvement non-désirée sur le télescope physique

**Impact**: crash mécanique, blessure (contrepoids), perte de matériel.
**Surface**: agent qui exposerait une méthode write ASCOM/INDI.
**Mitigation V1**:
- `adapters/base.py` ne définit **que** `discover()` et `read_properties()`.
- Aucune méthode `slew`, `park`, `sync`, `abort`, `set_tracking`, `set_target` n'est
  importée ni exposée. Vérifié par grep AST dans le CI.
- `safety/readonly_filter.py` intercepte toute tentative de `getattr` sur
  un nom commençant par `set_`, `move_`, `slew_`, `abort_`, `park_`,
  `unpark_`, `sync_`, `pulse_guide` et lève `PermissionError`.
- Le serveur n'a aucun endpoint qui *demande* à l'agent d'agir.
**Mitigation future** (V2+): bridge bidirectionnel pour commandes sera un
module distinct `telescope_command/` avec consentement explicite par
session + 2FA + watchdog matériel.

## T2 — Vol du token de session (JWT agent)

**Impact**: usurpation d'agent, injection de fausse télémétrie.
**Surface**: filesystem utilisateur, sauvegardes, dump mémoire.
**Mitigation V1**:
- JWT stocké dans le **keychain OS** (DPAPI / Keychain / Secret Service),
  pas dans un fichier en clair.
- JWT scope = `agent_id` ; un token volé peut polluer la télémétrie d'**un seul agent**, jamais d'un autre utilisateur.
- Rotation : refresh JWT toutes les 24 h via `/session/heartbeat`.
- Révocation manuelle depuis le dashboard (Phase 6 UI).
**Mitigation future**: liaison cryptographique au matériel (TPM) si dispo.

## T3 — MITM / proxy malveillant sur le LAN utilisateur

**Impact**: lecture en clair de la position du télescope (= coordonnées domicile).
**Surface**: réseau local.
**Mitigation V1**:
- TLS 1.3 obligatoire (le client refuse < TLS 1.2).
- Le client refuse les certificats auto-signés.
- En Phase 3, certificate pinning : SHA-256 du leaf cert d'astroscan.space
  embarqué dans la build agent. Mise à jour via update agent signé.

## T4 — Fuite de coordonnées géographiques du site d'observation

**Impact**: divulgation de l'adresse physique du domicile de l'astronome.
**Surface**: champs `site_lat`/`site_lon` dans la télémétrie mount.
**Mitigation V1**:
- Ces champs sont **opt-in** dans l'agent (`config.send_site_location = false`
  par défaut). Sans opt-in, l'agent ne lit même pas la propriété.
- Côté serveur : si présents, ils sont chiffrés au repos avec une clé
  dérivée du user_id (jamais en clair dans la DB).
- Le dashboard ne réaffiche jamais les coordonnées brutes à un autre
  utilisateur (V2 community sharing devra arrondir au degré).

## T5 — Cross-tenant data access (utilisateur A lit le télescope de B)

**Impact**: divulgation, atteinte vie privée.
**Surface**: tout endpoint serveur qui prend un `device_id` en query string.
**Mitigation V1**:
- Tout endpoint `GET /devices`, `GET /telemetry/latest` applique un
  `WHERE user_id = current_user.id` côté SQL **avant** toute lecture.
- Test d'intégration obligatoire : utilisateur A requête le device_id
  d'un user B → doit retourner `404` (et pas `403`, pour ne pas révéler l'existence).

## T6 — Replay d'une requête télémétrie

**Impact**: injection de données obsolètes, manipulation graphes.
**Surface**: HTTP intercept + rejeu.
**Mitigation V1**:
- Chaque POST agent inclut `X-Bridge-Nonce: <128 bits>` + timestamp.
- `security/replay_cache.py` : LRU 5 min des nonces vus, rejet si déjà vu.
- Skew toléré : ±60 s entre `ts` payload et `Now()` serveur.

## T7 — DoS via inscription massive d'agents factices

**Impact**: épuisement DB, rate limit ailleurs, coûts.
**Surface**: `/pair/init`, `/pair/confirm`.
**Mitigation V1**:
- `/pair/init` requiert une session utilisateur authentifiée (cookie Flask).
- Quota par user : 5 agents max ; configurable.
- nginx `limit_req_zone` zone `tb_agent` : 10 r/s, burst 30.
- TTL pairing code : 10 min, single-use. Code consumé → DELETE row.

## T8 — Injection / corruption schéma télémétrie

**Impact**: panic dans le code de parsing, corruption DB, escalade RCE.
**Surface**: payload JSON inattendu de l'agent.
**Mitigation V1**:
- Validation stricte par dataclass + whitelist de champs (jamais d'`object.__dict__` brut).
- Tous les champs numériques bornés (`0 ≤ ra_hours < 24`, `-90 ≤ dec ≤ 90`).
- Limite de taille body POST : 16 KB.
- nginx body limit `client_max_body_size 32k` sur la zone telescope-bridge.

## T9 — Compromission du serveur AstroScan transformée en pivot vers télescope

**Impact**: si AstroScan était piraté, l'attaquant ne doit PAS pouvoir
piloter les télescopes des utilisateurs.
**Surface**: tout endpoint serveur qui parlerait à l'agent.
**Mitigation V1**: **Aucun endpoint serveur → agent**. La communication
est unidirectionnelle agent → serveur. Si AstroScan est compromis,
l'attaquant lit de la télémétrie passée et peut couper la session, mais
il ne peut **rien envoyer à l'agent**. C'est la propriété de sécurité la
plus importante du design V1.

## T10 — Supply chain (libpython, indilib, pywin32)

**Impact**: backdoor dans une dépendance = compromission directe agent.
**Surface**: PyPI, distros, ASCOM Remote builds.
**Mitigation V1**:
- Agent packagé avec `pip install --require-hashes` à partir d'un
  `requirements.txt` versionné + lockfile généré reproductible.
- Build agent reproductible (PyInstaller `--deterministic`).
- Signature des binaires Windows (Authenticode) et `.deb` (gpg).
- Audit annuel des dépendances directes (≤ 12).
