# Phase 2 — Plan de consolidation SAFE

**Règle** : uniquement des **ajouts** sous `ops/` et documentation — **pas** de modification de `station_web.py`, engines, templates.

## NIVEAU A — zéro risque

| Action | Fichier | Rollback | Redémarrage |
|--------|---------|----------|-------------|
| Healthcheck HTTP consolidé | `ops/healthcheck_consolidated.sh` | Supprimer le fichier | Non |
| Validation JSON `data_core` (lecture seule) | `ops/verify_data_core_json.py` | Supprimer | Non |
| Scan doublons de routes (grep / script) | `ops/scan_flask_routes.sh` | Supprimer | Non |
| README exploitation | `ops/README_STABILITY.md` | Supprimer | Non |

## NIVEAU B — faible risque

| Action | Détail | Rollback |
|--------|--------|----------|
| Wrapper “restart sûr” | Appelle `deploy/astroscan_reload.sh restart` + healthcheck | Ne pas appeler le wrapper |

## NIVEAU C — non appliqué dans le code applicatif

- Aucun changement systemd/nginx dans ce lot (déjà traité en durcissement séparé si besoin).
- Aucun `chmod` sur `data_core` sans fenêtre maintenance.

## Actions volontairement non faites

- Refactor Flask, fusion de routes lab, modification des exceptions métier.
