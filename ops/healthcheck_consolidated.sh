#!/usr/bin/env bash
# Healthcheck consolidé AstroScan — lecture seule, ne modifie pas l'application.
# Usage : bash /root/astro_scan/ops/healthcheck_consolidated.sh
set -euo pipefail
BASE="${ASTROSCAN_URL:-http://127.0.0.1:5003}"
echo "=== AstroScan healthcheck (base=$BASE) ==="
fail=0
check() {
  local path="$1"
  local code
  code=$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 5 "${BASE}${path}" || echo "000")
  if [[ "$code" =~ ^2 ]]; then
    echo "OK  $path  HTTP $code"
  else
    echo "BAD $path  HTTP $code"
    fail=1
  fi
}

check "/health"
check "/portail"
check "/dashboard-v2"
check "/api/system-status/cache"
check "/api/system-alerts"
check "/api/system-notifications"

echo "--- POST /api/system-heal (smoke) ---"
hcode=$(curl -sS -o /tmp/_heal_out.json -w "%{http_code}" --connect-timeout 15 \
  -X POST "${BASE}/api/system-heal" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{}' || echo "000")
if [[ "$hcode" =~ ^2 ]]; then
  echo "OK  /api/system-heal  HTTP $hcode"
else
  echo "BAD /api/system-heal  HTTP $hcode"
  fail=1
fi
head -c 300 /tmp/_heal_out.json 2>/dev/null; echo

echo "--- Port 5003 (doit être 127.0.0.1) ---"
ss -tlnp 2>/dev/null | grep 5003 || true

exit "$fail"
