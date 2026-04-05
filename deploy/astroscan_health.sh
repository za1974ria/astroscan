#!/usr/bin/env bash
# Healthcheck AstroScan — ne doit jamais planter si le serveur est absent ou injoignable.
#
# IMPORTANT : ne collez pas de texte Markdown dans le terminal. Exemple sûr (une seule ligne) :
#   curl -sS -m 5 'http://127.0.0.1:5003/api/aegis/status' | grep -q claude_calls && echo OK || echo FAIL
#
# Si ce script n’affiche rien : vérifiez le fichier (wc -l, head) et qu’il n’est pas vide sur le serveur.

set +e
set +o pipefail 2>/dev/null || true

URL="http://127.0.0.1:5003/api/aegis/status"

# Toujours une trace sur stderr (même si stdout est redirigé ailleurs).
printf '%s\n' "astroscan_health.sh: GET ${URL}" >&2

response=""
response=$(curl -sS -m 10 --connect-timeout 5 "$URL" 2>/dev/null) || true

if [ -z "$response" ]; then
  printf '%s\n' "[ERROR] AstroScan unhealthy"
  printf '%s\n' "astroscan_health.sh: réponse vide (serveur arrêté, timeout ou curl absent ?)" >&2
  exit 1
fi

if printf '%s\n' "$response" | grep -q "claude_calls"; then
  printf '%s\n' "[OK] AstroScan is healthy"
  exit 0
fi

printf '%s\n' "[ERROR] AstroScan unhealthy"
printf '%s\n' "astroscan_health.sh: champ « claude_calls » absent (ancienne version station_web.py ?)" >&2
exit 1
