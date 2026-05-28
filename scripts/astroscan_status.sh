#!/usr/bin/env bash
# astroscan_status.sh — Cockpit human-readable status snapshot.
#
# Affiche en sections lisibles :
#   - systemd state + workers
#   - disk (full + AstroScan paths)
#   - memory
#   - HTTP endpoints summary
#   - guardian agent
#   - boot mode
#   - last journal errors
#   - quick smoke check (12 endpoints)
#
# Usage:
#   scripts/astroscan_status.sh                       # tout
#   scripts/astroscan_status.sh --since "10 min ago"  # journal window
#   scripts/astroscan_status.sh --no-smoke            # skip smoke
#
# CHANTIER 4 (2026-05-23) — human dashboard, complément de post_deploy_check.sh.

set -uo pipefail

BASE_URL="${ASTROSCAN_BASE_URL:-http://127.0.0.1:5003}"
BASE_URL="${BASE_URL%/}"
SINCE="2 min ago"
RUN_SMOKE=1
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

while [ $# -gt 0 ]; do
    case "$1" in
        --since)    SINCE="${2:-2 min ago}"; shift 2 ;;
        --no-smoke) RUN_SMOKE=0; shift ;;
        *)          shift ;;
    esac
done

C_RED='\033[31m'; C_GRN='\033[32m'; C_YEL='\033[33m'; C_CYN='\033[36m'
C_BLD='\033[1m'; C_DIM='\033[2m'; C_OFF='\033[0m'
[ -t 1 ] || { C_RED=''; C_GRN=''; C_YEL=''; C_CYN=''; C_BLD=''; C_DIM=''; C_OFF=''; }

_h()  { echo -e "\n${C_CYN}${C_BLD}── $* ──${C_OFF}"; }
_kv() { printf "  %-22s %s\n" "$1" "$2"; }
_ok() { echo -e "  ${C_GRN}●${C_OFF} $*"; }
_warn(){ echo -e "  ${C_YEL}●${C_OFF} $*"; }
_ko() { echo -e "  ${C_RED}●${C_OFF} $*"; }

# ── Header ───────────────────────────────────────────────────────────────────
echo -e "${C_BLD}AstroScan Mission Control · $(date -Iseconds)${C_OFF}"
echo -e "${C_DIM}base=$BASE_URL  host=$(hostname)  user=$(whoami)${C_OFF}"

# ── 1. SYSTEMD ───────────────────────────────────────────────────────────────
_h "SYSTEMD"
SVC_STATE="$(systemctl is-active astroscan.service 2>/dev/null || echo unknown)"
SVC_ENABLED="$(systemctl is-enabled astroscan.service 2>/dev/null || echo unknown)"
SVC_UPTIME="$(systemctl show astroscan.service -p ActiveEnterTimestamp --value 2>/dev/null || true)"
case "$SVC_STATE" in
    active)   _ok   "astroscan.service: $SVC_STATE (enabled=$SVC_ENABLED)" ;;
    failed)   _ko   "astroscan.service: $SVC_STATE" ;;
    *)        _warn "astroscan.service: $SVC_STATE" ;;
esac
[ -n "$SVC_UPTIME" ] && _kv "ActiveEnter" "$SVC_UPTIME"
WORKERS="$(pgrep -fc 'gunicorn.*wsgi:app' 2>/dev/null || echo 0)"
_kv "gunicorn procs"  "$WORKERS  (1 master + N workers)"
RSS_TOTAL_KB=$(ps -C python3 -o rss= 2>/dev/null | awk '{s+=$1} END {print s+0}')
_kv "python3 RSS sum" "$((RSS_TOTAL_KB/1024)) MiB"

# ── 2. DISK ──────────────────────────────────────────────────────────────────
_h "DISK"
df -h / 2>/dev/null | awk 'NR==2 {printf "  / on %s   %s used / %s total   (%s used)   free %s\n", $1, $3, $2, $5, $4}'
for d in /root/astro_scan /root/astro_scan/data /root/astro_scan/logs /tmp; do
    sz="$(du -sh "$d" 2>/dev/null | awk '{print $1}')"
    [ -n "$sz" ] && _kv "$d" "$sz"
done

# ── 3. MEMORY ────────────────────────────────────────────────────────────────
_h "MEMORY"
free -h | awk 'NR==1{header=$0} NR==2{mem=$0} NR==3{swap=$0} END {print "  "header"\n  "mem"\n  "swap}'
LOAD="$(awk '{print $1, $2, $3}' /proc/loadavg 2>/dev/null)"
_kv "load avg 1/5/15"  "$LOAD"

# ── 4. HTTP ENDPOINTS ────────────────────────────────────────────────────────
_h "HTTP ENDPOINTS"
_probe() {
    local p="$1"
    local code
    code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 3 "$BASE_URL$p" 2>/dev/null || echo 000)"
    if [ "$code" = "200" ]; then
        _kv "$p" "${C_GRN}$code${C_OFF}"
    elif [ "$code" = "401" ] || [ "$code" = "503" ]; then
        _kv "$p" "${C_YEL}$code${C_OFF}  (auth-gated, expected)"
    else
        _kv "$p" "${C_RED}$code${C_OFF}"
    fi
}
_probe "/"
_probe "/portail"
_probe "/analytics"
_probe "/health"
_probe "/api/health"
_probe "/api/visits"
_probe "/api/admin/circuit-breakers"
_probe "/api/guardian/health"

# ── 5. /health summary (parsed) ──────────────────────────────────────────────
_h "HEALTH SUMMARY  (from /health)"
HEALTH_JSON="$(curl -sS --max-time 3 "$BASE_URL/health" 2>/dev/null || echo '')"
if [ -n "$HEALTH_JSON" ]; then
    echo "$HEALTH_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
def kv(k, v):
    print(f'  {k:<22} {v}')
kv('status',         d.get('status'))
kv('mode',           d.get('mode'))
kv('boot_mode',      d.get('boot_mode'))
if d.get('boot_failure'):
    kv('boot_failure',   d.get('boot_failure'))
kv('uptime_s',       d.get('uptime_sec'))
kv('tle_count',      d.get('tle_count'))
disk = d.get('disk_usage', {})
if disk:
    kv('disk', f\"{disk.get('pct','?')}% used · free {disk.get('free_gb','?')} GB / {disk.get('total_gb','?')} GB\")
mem = d.get('memory_usage', {})
if mem:
    kv('memory', f\"process {mem.get('process_mb','?')} MB · system {mem.get('system_pct','?')}%\")
sq = d.get('sqlite') or {}
if sq:
    kv('sqlite', f\"ok={sq.get('ok')} writable={sq.get('writable')} db={sq.get('db_path')}\")
g = d.get('gunicorn') or {}
if g:
    kv('gunicorn', f\"master={g.get('master_pid')} worker_pid={g.get('worker_pid')} workers={g.get('worker_count')}\")
cb = d.get('circuit_breakers') or {}
if cb:
    kv('circuit_breakers', f\"total={cb.get('total')} open={cb.get('open')} half_open={cb.get('half_open')} closed={cb.get('closed')}\")
gd = d.get('guardian') or {}
if gd:
    kv('guardian.enabled',   gd.get('enabled'))
    kv('guardian.version',   gd.get('version'))
    kv('guardian.leader_pid',gd.get('leader_pid'))
    kv('guardian.is_leader', gd.get('is_leader'))
    kv('guardian.ticks',     gd.get('ticks_total'))
    kv('guardian.in_grace',  gd.get('in_restart_grace'))
" 2>/dev/null || echo -e "  ${C_RED}health JSON parse failed${C_OFF}"
else
    _ko "/health unreachable"
fi

# ── 6. GUARDIAN cross-worker leader scan ─────────────────────────────────────
_h "GUARDIAN  (cross-worker leader scan)"
LEADERS=$(for i in 1 2 3 4 5 6; do
    curl -sS --max-time 2 "$BASE_URL/api/guardian/health" 2>/dev/null \
      | python3 -c "import json,sys;
try: d=json.load(sys.stdin); print(d.get('leader_pid'))
except: pass" 2>/dev/null
done | sort -u | grep -v '^$' | grep -v '^None$')
N_LEADERS=$(echo "$LEADERS" | grep -c . || echo 0)
case "$N_LEADERS" in
    1)  _ok   "1 leader pid observed across 6 calls: $LEADERS" ;;
    0)  _warn "no leader pid (lockfile not created yet?)" ;;
    *)  _ko   "multiple leaders observed (singleton broken): $LEADERS" ;;
esac
[ -r /tmp/astroscan_guardian.lock ] && _kv "lockfile content" "$(cat /tmp/astroscan_guardian.lock)" || _kv "lockfile" "(unreadable as $(whoami))"

# ── 7. JOURNAL ERRORS ────────────────────────────────────────────────────────
_h "JOURNAL ERRORS  (since $SINCE)"
JOURNAL_ERR="$(journalctl -u astroscan.service --since "$SINCE" --no-pager 2>/dev/null \
              | grep -iE 'ERROR|CRITICAL|Traceback|OperationalError|PermissionError' \
              | grep -viE 'OPENAI_API_KEY|ASTROSCAN_ADMIN_TOKEN|optional_missing' || true)"
if [ -z "$JOURNAL_ERR" ]; then
    _ok "no ERROR/CRITICAL"
else
    N=$(echo "$JOURNAL_ERR" | wc -l)
    _ko "$N error line(s) — last 5:"
    echo "$JOURNAL_ERR" | tail -5 | sed 's/^/    /'
fi

# ── 8. SMOKE QUICK CHECK ─────────────────────────────────────────────────────
if [ "$RUN_SMOKE" -eq 1 ] && [ -x "$SCRIPT_DIR/smoke_tests.sh" ]; then
    _h "SMOKE QUICK CHECK"
    if ASTROSCAN_BASE_URL="$BASE_URL" "$SCRIPT_DIR/smoke_tests.sh" --quiet; then
        _ok "smoke 12/12 PASS"
    else
        _ko "smoke FAIL — rerun: $SCRIPT_DIR/smoke_tests.sh"
    fi
fi

echo
