#!/usr/bin/env bash
# Sauvegarde lecture AstroScan — n’altère pas l’application en cours.
# Usage : sudo bash /root/astro_scan/ops/backup_astroscan_safe.sh
set -euo pipefail
ROOT="/root/astro_scan"
DEST="${BACKUP_ROOT:-/root/astro_scan/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${DEST}/astroscan_safe_${STAMP}.tar.gz"
mkdir -p "$DEST"
tar -czf "$OUT" \
  --exclude='./.git' \
  --exclude='./**/__pycache__' \
  --exclude='./**/*.pyc' \
  --exclude='./.venv' \
  --exclude='./venv' \
  -C "$(dirname "$ROOT")" "$(basename "$ROOT")"
echo "OK: $OUT ($(du -h "$OUT" | cut -f1))"
ls -la "$OUT"
