# Exploitation — stabilité AstroScan (outils additifs)

Tous les scripts sous `ops/` sont **additifs** : ils ne modifient pas `station_web.py` ni les templates.

| Script | Rôle |
|--------|------|
| `healthcheck_consolidated.sh` | Vérifie HTTP health, pages clés, APIs système, POST heal, affiche `ss` sur 5003. |
| `verify_data_core_json.py` | Parse tous les `*.json` sous `data_core/` (détecte corruption). |
| `scan_duplicate_routes.py` | Signale les chemins `@app.route` dupliqués dans `station_web.py`. |
| `scan_flask_routes.sh` | Aperçu `uniq -c` des lignes `@app.route` (complément). |
| `astroscan_restart_safe.sh` | Appelle `deploy/astroscan_reload.sh restart`. |
| `backup_astroscan_safe.sh` | Archive du dépôt (voir `README_RESTORE.md`). |

## Redémarrage propre (port bloqué)

1. `sudo bash /root/astro_scan/deploy/astroscan_reload.sh inspect`
2. Si besoin : `sudo bash /root/astro_scan/deploy/astroscan_reload.sh repair`

## Vérifications rapides

```bash
bash /root/astro_scan/ops/healthcheck_consolidated.sh
python3 /root/astro_scan/ops/verify_data_core_json.py
python3 /root/astro_scan/ops/scan_duplicate_routes.py
```
