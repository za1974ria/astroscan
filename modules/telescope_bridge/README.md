# AstroScan Telescope Bridge — Module serveur

**État : Phase 1 — Scaffolding architectural uniquement. Aucun blueprint enregistré.**

Le module permet à l'agent local d'un utilisateur (sur son PC d'observatoire) de
publier de la **télémétrie en lecture seule** sur AstroScan. V1 n'autorise *aucune*
commande de mouvement. Cette propriété est garantie par construction côté agent
(allow-list de propriétés ASCOM/INDI) et côté serveur (aucun endpoint n'expose
de chemin "telescope → command").

## Garanties architecturales (V1)

1. **Read-only by construction** : ni le serveur ni l'agent n'implémentent de
   chemin pour Slew/Park/Sync/Abort/SetTracking. Voir
   `security/policy.py` (à créer en Phase 2) pour l'allow-list propriété par
   propriété.
2. **Outbound-only** : l'agent ouvre une connexion HTTPS vers AstroScan ; le
   serveur ne joint **jamais** l'agent. Aucun port à ouvrir sur le LAN
   utilisateur.
3. **Per-tenant isolation** : chaque session est liée à un user_id ; les
   endpoints serveur appliquent un filtre strict avant toute lecture du
   `telemetry_store`.
4. **Feature flag** : tant que `FEATURE_TELESCOPE_BRIDGE` n'est pas à `True`
   dans `app/__init__.py`, le blueprint n'est même pas importé. Toute Phase
   ≤ 5 reste donc invisible pour les utilisateurs.
5. **Storage isolé** : le module utilise sa propre base SQLite
   `/opt/astroscan/data/telescope_bridge.db`, jamais la base principale
   `archive_stellaire.db`. Toute corruption ou migration reste contenue.

## Documents

- `docs/ARCHITECTURE.md` — composants serveur et agent
- `docs/THREAT_MODEL.md` — 10 menaces inventoriées + mitigations
- `docs/API_CONTRACT.md` — endpoints REST + auth
- `docs/TELEMETRY_SCHEMA.md` — schéma des télémétries mount / camera / focuser / dome / weather
- `docs/ONBOARDING_UX.md` — flux pairing 6-digit + écrans
- `docs/ROADMAP.md` — plan 10 phases, prochaines actions
- `storage/schema.sql` — DDL pour les tables `tb_*` (Phase 2)

## Conventions de nommage

- Tables : préfixe `tb_` (telescope bridge), jamais de collision avec les
  tables existantes d'AstroScan.
- Endpoints : préfixe `/api/telescope-bridge/`, jamais d'overlap avec
  `/api/telescope/` (qui existe déjà pour `app/blueprints/telescope`).
- Variables d'environnement : préfixe `TB_` (ex. `TB_PAIR_TTL_SECONDS`).
- Identifiants ressources : UUID v4 partout (jamais d'auto-increment exposé).
