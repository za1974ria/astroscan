#!/usr/bin/env bash
# Vérification rapide : app locale + routes « live » critiques (sans tout scanner).
# Usage :
#   ./deploy/astroscan_operational_check.sh
#   ./deploy/astroscan_operational_check.sh http://127.0.0.1:5003
#   ./deploy/astroscan_operational_check.sh --full   # inclut /api/health/full (plus lent, teste sources externes)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BASE_URL="${BASE_URL:-http://127.0.0.1:5003}"
FULL=0
if [[ "${1:-}" == "--full" ]]; then
  FULL=1
  shift || true
fi
[[ -n "${1:-}" ]] && BASE_URL="$1"

BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

fail=0
ok=0

# $1 libellé  $2 chemin  $3 code HTTP minimal acceptable (ex: 200)  $4 optionnel: sous-chaîne JSON
# $5 optionnel: délai max curl (secondes) — /api/iss peut dépasser 12 s (sources externes séquentielles).
check_http() {
  local label="$1" path="$2" min_ok="${3:-200}" need="${4:-}" maxt="${5:-25}"
  local raw digits code
  raw="$(curl -sS -o "$BODY" -w "%{http_code}" --connect-timeout 4 -m "$maxt" "${BASE_URL}${path}" 2>/dev/null || true)"
  digits="$(printf '%s' "$raw" | tr -cd '0-9')"
  if [[ ${#digits} -ge 3 ]]; then
    code="${digits: -3}"
  else
    code="000"
  fi
  if [[ "$code" -lt "$min_ok" ]] || [[ "$code" -ge 600 ]]; then
    echo "  [ÉCHEC] $label  → HTTP $code  ($path)  [max ${maxt}s — 000 = timeout / pas de réponse]"
    fail=$((fail + 1))
    return
  fi
  if [[ -n "$need" ]] && ! grep -q "$need" "$BODY" 2>/dev/null; then
    echo "  [ÉCHEC] $label  → HTTP $code mais corps sans « $need » ($path)"
    fail=$((fail + 1))
    return
  fi
  echo "  [OK]    $label  → HTTP $code"
  ok=$((ok + 1))
}

echo "=== AstroScan — contrôle opérationnel ==="
echo "Base: $BASE_URL"
echo ""

echo "— Cœur application (liveness / données locales) —"
check_http "GET /health" "/health" 200 '"status"'
check_http "GET /ready" "/ready" 200 '"ready"'
check_http "GET /api/tle/status" "/api/tle/status" 200 '"status"'
check_http "GET /api/aegis/status" "/api/aegis/status" 200 'claude_calls'

echo ""
echo "— ISS & agrégation sondes —"
check_http "GET /api/iss" "/api/iss" 200 '"lat"' 45
check_http "GET /api/sondes (clé iss)" "/api/sondes" 200 '"iss"'

echo ""
echo "— Flux « live » (JSON valide côté app) —"
# Format JSON variable (tableau ou objet) : réponse 200 suffit si l’app répond.
check_http "GET /api/live/news" "/api/live/news" 200 ""
check_http "GET /api/telescope/live" "/api/telescope/live" 200 '"title"'
check_http "GET /api/sondes/live" "/api/sondes/live" 200 '"voyager_1"'

if [[ "$FULL" -eq 1 ]]; then
  echo ""
  echo "— Santé étendue (sources externes, ~20–30 s) —"
  check_http "GET /api/health/full" "/api/health/full" 200 'reliability_score'
fi

echo ""
echo "=== Résumé : $ok OK, $fail échec(s) ==="
if [[ "$fail" -gt 0 ]]; then
  echo "Action : journalctl -u astroscan -n 80 --no-pager"
  echo "         sudo bash ${SCRIPT_DIR}/astroscan_reload.sh free-port && sudo systemctl start astroscan"
  exit 1
fi
exit 0
