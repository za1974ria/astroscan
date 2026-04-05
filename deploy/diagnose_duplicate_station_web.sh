#!/usr/bin/env bash
# Qui lance python3 …/station_web.py en plus de Gunicorn ?
# Usage : sudo bash deploy/diagnose_duplicate_station_web.sh

set -euo pipefail

echo "=== Processus station_web.py ==="
pgrep -af 'station_web\.py' || echo "(aucun)"

echo ""
echo "=== Arbre parent (chaque PID station_web.py encore vivant dans /proc) ==="
# pgrep puis pstree peuvent être séparés par quelques ms : le PID peut mourir (redémarrage, script court).
_any=0
for SPID in $(pgrep -f '/root/astro_scan/station_web\.py' 2>/dev/null || true); do
  if [[ ! -d "/proc/$SPID" ]]; then
    echo "--- PID $SPID : déjà terminé entre pgrep et l’inspection (course / restart) — réessayez tout de suite ---"
    continue
  fi
  _any=1
  echo ""
  echo "--- PID $SPID ---"
  ps -o pid,ppid,cmd -p "$SPID" 2>/dev/null || true
  echo ""
  echo "=== cgroup (slice systemd → nom du service) ==="
  tr '\0' '\n' < "/proc/$SPID/cgroup" 2>/dev/null || echo "(lecture cgroup impossible)"
  cur_pp="$(ps -o ppid= -p "$SPID" 2>/dev/null | tr -d ' ' || true)"
  while [[ -n "${cur_pp:-}" && "$cur_pp" != "0" && "$cur_pp" != "1" ]]; do
    ps -o pid,ppid,cmd -p "$cur_pp" 2>/dev/null || break
    cur_pp="$(ps -o ppid= -p "$cur_pp" 2>/dev/null | tr -d ' ' || true)"
  done
  if [[ "$(ps -o ppid= -p "$SPID" 2>/dev/null | tr -d ' ')" == "1" ]]; then
    echo ""
    echo "Note : PPID=1 = enfant direct de systemd (PID 1) OU orphelin réattribué à init."
    echo "      Voir cgroup et « systemctl status <PID> » ci-dessous."
  fi
  if command -v pstree >/dev/null 2>&1; then
    echo ""
    pstree -asp "$SPID" 2>/dev/null || echo "(pstree : impossible pour PID $SPID)"
  fi
done
[[ "$_any" -eq 0 ]] && echo "(aucun PID station_web.py vivant à cet instant — relancez si vous venez de redémarrer le service)"

echo ""
echo "=== Unité systemd propriétaire (systemctl status <pid>) ==="
if command -v systemctl >/dev/null 2>&1; then
  for SPID in $(pgrep -f '/root/astro_scan/station_web\.py' 2>/dev/null || true); do
    [[ -d "/proc/$SPID" ]] || continue
    echo "--- status $SPID ---"
    systemctl status "$SPID" 2>/dev/null || true
  done
fi

echo ""
echo "=== Unités systemd contenant « station_web » ==="
if [[ -d /etc/systemd/system ]]; then
  grep -rls 'station_web' /etc/systemd/system/*.service 2>/dev/null || echo "(aucun fichier .service)"
  grep -h 'ExecStart' /etc/systemd/system/*.service 2>/dev/null | grep -F station_web || true
fi

echo ""
echo "=== astroscan.service (extrait) ==="
systemctl cat astroscan.service 2>/dev/null | head -25 || echo "unité absente"

echo ""
echo "=== Services actifs (filtre astro / scan / gunicorn) ==="
systemctl list-units --type=service --no-pager 2>/dev/null | grep -iE 'astro|scan|gunicorn|flask' || true

echo ""
echo "=== Cron root (station_web) ==="
grep -n station_web /var/spool/cron/crontabs/root 2>/dev/null || crontab -l 2>/dev/null | grep -n station_web || echo "(rien dans crontab -l visible)"

echo ""
echo "=== Port 5003 ==="
ss -tlnp 2>/dev/null | grep 5003 || true

echo ""
echo "Si ExecStart d’astroscan pointe vers « python3 … station_web.py », remplacez par Gunicorn :"
echo "  sudo cp /root/astro_scan/deploy/astroscan.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload && sudo systemctl restart astroscan"
