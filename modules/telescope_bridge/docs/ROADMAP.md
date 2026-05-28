# Telescope Bridge — Roadmap (10 phases)

Chaque phase = livrable indépendant, déployable, **rollback en moins de 5 min**
par flag d'environnement ou suppression de fichier.

| # | Phase | Livrables | Flag activation | Production-visible ? |
|---|---|---|---|---|
| **1** | **Scaffolding architectural** (cet incrément) | `modules/telescope_bridge/` skeleton + 6 docs + `telescope_bridge_agent/` skeleton | aucun | non |
| 2 | Stockage + token service | `storage/schema.sql` exécuté en migration, `services/token_service.py`, `services/session_service.py`, tests unitaires (offline) | `FEATURE_TELESCOPE_BRIDGE=0` (toujours off) | non |
| 3 | Endpoints pair + auth | `api/routes_pair.py`, `api/auth.py`, `security/replay_cache.py` ; blueprint enregistré dans `app/__init__.py` derrière flag, **off par défaut** | `FEATURE_TELESCOPE_BRIDGE=1` en staging uniquement | dépend du flag |
| 4 | Agent skeleton + mock adapter | `astroscan_bridge/__main__.py`, `adapters/base.py`, `adapters/mock.py`, `service/pairing.py` ; CI lint + package wheel | n/a | non |
| 5 | Telemetry endpoint + uploader | `api/routes_telemetry.py`, `services/telemetry_store.py`, `service/uploader.py` ; pairing end-to-end staging avec mock adapter | staging only | non |
| 6 | Dashboard UI (page `/telescope`) | template + JS, consume `/devices`, `/telemetry/latest` ; granular consent UI | staging only | non |
| 7 | Adapter ASCOM Alpaca (Windows + Linux) | `adapters/alpaca.py` ; discovery UDP + property polling read-only ; tests contre ASCOM Remote en simulateur | staging only | non |
| 8 | Adapter INDI (Linux / Pi) | `adapters/indi.py` ; tests contre `indi_simulator_telescope` | staging only | non |
| 9 | Hardening + prod activation | TLS pinning, certificate update flow, audit log rotation, dashboard révocation session | **PROD** `FEATURE_TELESCOPE_BRIDGE=1` (beta privée 5 utilisateurs invités) | oui (beta) |
| 10 | GA + observabilité | Métriques Control Tower (lampes `tb_*`), alerting Sentry, doc utilisateur publique | PROD | oui (public) |

## Hors V1 (volontairement repoussés)

| Idée | Pourquoi pas en V1 |
|---|---|
| Slew / Park / Sync depuis dashboard | Hors périmètre par contrat utilisateur ; sera un module séparé `telescope_command/` avec consentement 2FA. |
| Partage communautaire | Risque vie privée non maîtrisé tant que pseudonymisation n'est pas validée juridiquement. |
| Preview image | Nécessite quota stockage, redimensionnement, modération ; déclencheur séparé. |
| Multi-tenant API publique | V2 : ouverture aux apps tierces avec OAuth2 scope `telescope:read`. |
| AI interpretation des images | Phase totalement séparée (`modules/digital_lab/`). |

## Critères "Definition of Done" par phase

- **Code** : 100 % typed (`mypy --strict` sur le module), tests unitaires ≥ 80 %, ruff sans warning.
- **Sécurité** : grep AST refuse `slew|park|abort|set_|sync|pulse_guide`.
- **Documentation** : tout nouveau endpoint dans `API_CONTRACT.md`.
- **Observabilité** : chaque ajout de table → 1 lampe Control Tower freshness.
- **Rollback** : test manuel de désactivation `FEATURE_TELESCOPE_BRIDGE=0` + restart → service nominal sans erreur.

## Métriques de succès V1

| Métrique | Cible 90 j post-GA |
|---|---|
| Agents installés | ≥ 50 |
| Sessions actives moyennes | ≥ 30 |
| Devices distincts | ≥ 80 |
| Taux d'erreur `/telemetry` | < 0,5 % |
| Latence upload p95 | < 800 ms |
| Incidents sécurité confirmés | 0 |
| Tickets support ouverts | < 15 |
