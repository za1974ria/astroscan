#!/usr/bin/env bash
# AstroScan — contrôle Gunicorn (port 5003) sans modifier le code applicatif.
#
# IMPORTANT : une seule instance sur 5003.
#   Si « systemctl start astroscan » a réussi, NE PAS relancer python3 -m gunicorn …
#   à la main : vous obtiendrez « Connection in use » (port déjà pris par systemd).
#
# Usage :
#   ./deploy/astroscan_reload.sh start     # démarrer (ou signaler si déjà actif)
#   ./deploy/astroscan_reload.sh restart   # redémarrage via systemd (défaut)
#   ./deploy/astroscan_reload.sh inspect   # qui écoute sur 5003
#   ./deploy/astroscan_reload.sh free-port # libère 5003 (stop systemd + tue ce qui écoute encore)
#   ./deploy/astroscan_reload.sh check     # santé HTTP (health, ISS, sondes, live)
#   ./deploy/astroscan_reload.sh repair    # free-port + start systemd (orphelin 0.0.0.0:5003, etc.)
#
# Après chaque déploiement de code : ./deploy/astroscan_reload.sh restart

set -euo pipefail

ROOT="${ROOT:-/root/astro_scan}"
PORT="${PORT:-5003}"
UNIT="${UNIT:-astroscan}"

usage() {
  echo "Usage: $0 [start|restart|inspect|free-port|check|repair]" >&2
  exit 1
}

cmd_check() {
  local script="${ROOT}/deploy/astroscan_operational_check.sh"
  if [[ ! -x "$script" ]]; then
    chmod +x "$script" 2>/dev/null || true
  fi
  bash "$script" "http://127.0.0.1:${PORT}"
}

# Après systemctl stop, un Gunicorn orphelin peut encore tenir 5003 → « Connection in use ».
cmd_free_port() {
  echo "=== systemctl stop ${UNIT} ==="
  systemctl stop "${UNIT}" 2>/dev/null || true
  sleep 2

  _pids_on_port() {
    if command -v lsof >/dev/null 2>&1; then
      lsof -t -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true
      return
    fi
    if command -v ss >/dev/null 2>&1; then
      ss -tlnp "sport = :${PORT}" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u
    fi
  }

  local pids
  pids="$(_pids_on_port | tr '\n' ' ')"
  if [ -n "${pids// }" ]; then
    echo "=== SIGTERM sur PID encore en écoute : ${pids} ==="
    for pid in ${pids}; do
      [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null || true
    done
    sleep 2
  fi

  pids="$(_pids_on_port | tr '\n' ' ')"
  if [ -n "${pids// }" ]; then
    echo "=== SIGKILL sur PID résiduels : ${pids} ==="
    for pid in ${pids}; do
      [ -n "$pid" ] && kill -KILL "$pid" 2>/dev/null || true
    done
    sleep 1
  fi

  echo "=== Gunicorn station_web (orphelins) ==="
  pkill -f 'gunicorn.*station_web:app' 2>/dev/null || true
  sleep 1
  echo "=== python station_web.py (mode dev sur :${PORT} — historiquement 0.0.0.0) ==="
  pkill -f 'python3.*station_web\.py' 2>/dev/null || true
  pkill -f 'python.*station_web\.py' 2>/dev/null || true
  sleep 1

  if command -v fuser >/dev/null 2>&1; then
    echo "=== fuser -k ${PORT}/tcp (dernier recours : tout ce qui tient encore le port) ==="
    fuser -k "${PORT}/tcp" 2>/dev/null || true
    sleep 1
  fi

  echo "=== État port :${PORT} ==="
  if command -v ss >/dev/null 2>&1; then
    ss -tlnp "sport = :${PORT}" 2>/dev/null || echo "(rien n’écoute)"
  else
    echo "(ss absent — installez iproute2)"
  fi
  echo "Si la ligne ci-dessus est vide, vous pouvez relancer : systemctl start ${UNIT} ou gunicorn …"
}

cmd_start() {
  if ! systemctl cat "${UNIT}.service" &>/dev/null; then
    echo "ERREUR: unité systemd « ${UNIT} » absente." >&2
    echo "Installer : sudo cp ${ROOT}/deploy/astroscan.service /etc/systemd/system/" >&2
    echo "            sudo systemctl daemon-reload && sudo systemctl enable ${UNIT}" >&2
    exit 1
  fi
  if systemctl is-active --quiet "${UNIT}" 2>/dev/null; then
    echo "astroscan est déjà actif (systemd). Le port ${PORT} est utilisé — ne lancez pas un second gunicorn."
    systemctl --no-pager -l status "${UNIT}" || true
    exit 0
  fi
  echo "=== systemctl start ${UNIT} ==="
  systemctl start "${UNIT}"
  sleep 2
  systemctl --no-pager -l status "${UNIT}" || true
}

cmd_inspect() {
  echo "========================================"
  echo "⚠️  WARNING: DO NOT RUN GUNICORN MANUALLY"
  echo "Only use: systemctl start astroscan"
  echo "========================================"
  echo "=== Écoute TCP :${PORT} ==="
  if command -v ss >/dev/null 2>&1; then
    ss -tlnp "sport = :${PORT}" 2>/dev/null || true
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -i ":${PORT}" 2>/dev/null || true
  fi
  echo "=== Processus gunicorn (aperçu) ==="
  ps aux 2>/dev/null | grep -E '[g]unicorn|[g]unicorn.*station_web' || true
  echo ""
  echo "Pour voir la ligne de commande du maître Gunicorn, repérer le PID parent"
  echo "(souvent celui lancé par systemd) puis :"
  echo "  tr '\\\\0' ' ' < /proc/PID/cmdline; echo"
}

cmd_restart() {
  if ! systemctl cat "${UNIT}.service" &>/dev/null; then
    echo "ERREUR: unité systemd « ${UNIT} » absente." >&2
    echo "Installer : sudo cp ${ROOT}/deploy/astroscan.service /etc/systemd/system/" >&2
    echo "            sudo systemctl daemon-reload && sudo systemctl enable --now ${UNIT}" >&2
    exit 1
  fi

  if pgrep -f "gunicorn.*5003" > /dev/null; then
    echo "⚠️ Existing Gunicorn detected on port 5003"
    echo "Make sure it is managed by systemd"
  fi

  echo "=== systemctl restart ${UNIT} ==="
  systemctl restart "${UNIT}"
  sleep 2
  systemctl --no-pager -l status "${UNIT}" || true

  echo ""
  echo "=== GET /api/aegis/status (extrait) ==="
  out="$(curl -sS -m 10 "http://127.0.0.1:${PORT}/api/aegis/status" || true)"
  echo "$out"
  if echo "$out" | grep -q 'claude_calls'; then
    echo ""
    echo "OK: réponse contient les champs métriques (code récent chargé)."
  else
    echo ""
    echo "ATTENTION: pas de « claude_calls » dans la réponse — ancien worker, mauvais répertoire," >&2
    echo "ou autre processus que systemd sur le port ${PORT}." >&2
    exit 1
  fi
}

cmd_repair() {
  echo "=== RÉPARATION ${UNIT} (orphelin sur 0.0.0.0:${PORT}, port bloqué, etc.) ==="
  cmd_free_port
  if ! systemctl cat "${UNIT}.service" &>/dev/null; then
    echo "ERREUR: unité systemd « ${UNIT} » absente." >&2
    exit 1
  fi
  echo "=== systemctl start ${UNIT} ==="
  systemctl start "${UNIT}"
  sleep 3
  systemctl --no-pager -l status "${UNIT}" || true
  echo ""
  echo "=== Port ${PORT} (service : 127.0.0.1:${PORT} selon astroscan.service) ==="
  ss -tlnp "sport = :${PORT}" 2>/dev/null || true
  echo ""
  local hc
  hc="$(curl -sS -o /dev/null -w "%{http_code}" -m 10 "http://127.0.0.1:${PORT}/health" 2>/dev/null || echo "000")"
  echo "=== GET /health → HTTP ${hc} ==="
  if [[ "${hc}" != "200" ]]; then
    echo "ATTENTION: /health anormal — voir journalctl -u ${UNIT} -n 50" >&2
    exit 1
  fi
}

main() {
  case "${1:-restart}" in
    start) cmd_start ;;
    inspect) cmd_inspect ;;
    free-port) cmd_free_port ;;
    check) cmd_check ;;
    repair) cmd_repair ;;
    restart) cmd_restart ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
}

main "$@"
