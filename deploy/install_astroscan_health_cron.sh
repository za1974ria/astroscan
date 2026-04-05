#!/usr/bin/env bash
# Installe (ou laisse en place) la tâche cron healthcheck AstroScan — idempotent.
# Exécuter en root : sudo ./deploy/install_astroscan_health_cron.sh

set -euo pipefail

CRON_LINE='*/5 * * * * /root/astro_scan/deploy/astroscan_health.sh >> /var/log/astroscan_health.log 2>&1'
SCRIPT='/root/astro_scan/deploy/astroscan_health.sh'
LOG='/var/log/astroscan_health.log'

if [ "$(id -u)" -ne 0 ]; then
  echo "Lancer en root : sudo $0" >&2
  exit 1
fi

if [ ! -x "$SCRIPT" ]; then
  echo "Rendre le script exécutable : chmod +x $SCRIPT" >&2
  exit 1
fi

touch "$LOG"
chmod 644 "$LOG" 2>/dev/null || true

if crontab -l 2>/dev/null | grep -Fq 'astroscan_health.sh'; then
  echo "Cron healthcheck déjà présent (astroscan_health.sh)."
  crontab -l 2>/dev/null | grep -F 'astroscan_health.sh' || true
  exit 0
fi

(crontab -l 2>/dev/null || true; echo "$CRON_LINE") | crontab -
echo "Cron ajouté :"
echo "  $CRON_LINE"
echo "Journal : $LOG"
