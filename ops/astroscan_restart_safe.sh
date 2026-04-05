#!/usr/bin/env bash
# Redémarrage documenté — délègue à deploy/astroscan_reload.sh (ne duplique pas la logique métier).
set -euo pipefail
ROOT="${ROOT:-/root/astro_scan}"
exec bash "${ROOT}/deploy/astroscan_reload.sh" restart
