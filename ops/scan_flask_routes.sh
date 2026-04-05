#!/usr/bin/env bash
# Aperçu des routes Flask (lignes @app.route) — complément à scan_duplicate_routes.py
set -euo pipefail
STATION="${1:-/root/astro_scan/station_web.py}"
grep -n "@app.route(" "$STATION" | head -60
