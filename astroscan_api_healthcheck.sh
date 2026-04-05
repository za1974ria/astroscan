#!/usr/bin/env bash
set -u

BASE_URL="${1:-http://127.0.0.1:5003}"
STATION_WEB="/root/astro_scan/station_web.py"
OUT_FILE="/root/astro_scan/logs/api_health_report.md"
TMP_ENDPOINTS="/tmp/astroscan_endpoints_$$.txt"

cleanup() {
  rm -f "$TMP_ENDPOINTS" 2>/dev/null || true
}
trap cleanup EXIT

if [ ! -f "$STATION_WEB" ]; then
  echo "Erreur: fichier introuvable: $STATION_WEB"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Erreur: curl est requis."
  exit 1
fi

# Extrait toutes les routes /api... (single quotes et double quotes) via Python.
python3 - "$STATION_WEB" "$TMP_ENDPOINTS" <<'PY'
import re, sys
src = open(sys.argv[1], "r", encoding="utf-8", errors="ignore").read()
routes = re.findall(r"@app\.route\((?:'|\")(/api[^'\"\)]*)(?:'|\")", src)
routes = sorted(set(routes))
with open(sys.argv[2], "w", encoding="utf-8") as f:
    for r in routes:
        f.write(r + "\n")
PY

if [ ! -s "$TMP_ENDPOINTS" ]; then
  echo "Aucun endpoint /api trouvé dans $STATION_WEB"
  exit 1
fi

{
  echo "# AstroScan API Health Report"
  echo
  echo "- Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
  echo "- Base URL: $BASE_URL"
  echo
  echo "| Endpoint | Statut HTTP | Latence (s) | Erreur |"
  echo "|---|---:|---:|---|"
} > "$OUT_FILE"

while IFS= read -r endpoint; do
  [ -z "$endpoint" ] && continue

  # Test minimal pour endpoints dynamiques paramétrés.
  test_endpoint="$endpoint"
  case "$endpoint" in
    */\<obj_id\>) test_endpoint="${endpoint%<obj_id>}25544" ;;
    */\<target_id\>) test_endpoint="${endpoint%<target_id>}M42" ;;
  esac

  # Pour endpoints POST seulement, on évite d'exécuter en GET (signalé explicitement).
  case "$endpoint" in
    "/api/visits/increment"|"/api/tle/refresh"|"/api/chat"|"/api/translate"|"/api/astro/explain"|"/api/skyview/fetch"|"/api/push/subscribe"|"/api/lab/upload"|"/api/lab/analyze"|"/api/analysis/run"|"/api/analysis/compare"|"/api/science/analyze-image")
      echo "| \`$endpoint\` | n/a | n/a | Endpoint POST (non testé en GET) |" >> "$OUT_FILE"
      continue
      ;;
  esac

  url="${BASE_URL}${test_endpoint}"
  # -m 8 timeout global, connect timeout court
  result="$(curl -sS -o /dev/null -w "%{http_code} %{time_total}" --connect-timeout 2 -m 8 "$url" 2>&1)"
  curl_rc=$?

  if [ $curl_rc -ne 0 ]; then
    # En cas d'erreur curl, inclure message court
    err="$(printf "%s" "$result" | tr '|' '/' | cut -c1-80)"
    echo "| \`$endpoint\` | timeout/error | n/a | ${err} |" >> "$OUT_FILE"
    continue
  fi

  code="$(printf "%s" "$result" | awk '{print $1}')"
  latency="$(printf "%s" "$result" | awk '{print $2}')"
  err="—"
  if [ "$code" -ge 500 ] 2>/dev/null; then
    err="Serveur 5xx"
  elif [ "$code" -ge 400 ] 2>/dev/null; then
    err="Client/route 4xx"
  fi

  echo "| \`$endpoint\` | $code | $latency | $err |" >> "$OUT_FILE"
done < "$TMP_ENDPOINTS"

echo "Rapport généré: $OUT_FILE"
