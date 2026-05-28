#!/usr/bin/env bash
# post_deploy_check.sh — AstroScan post-deploy health verification.
#
# Run after any systemctl restart astroscan.service to confirm:
#   1. systemctl reports active
#   2. smoke endpoints return expected codes
#   3. journal has no errors in last 2 minutes
#   4. guardian agent is alive
#   5. boot mode is `factory` (not silent fallback)
#
# Exit codes:
#   0  all checks PASS
#   1  one or more checks FAIL
#   2  systemd reports service not active
#
# Usage:
#   scripts/post_deploy_check.sh
#   ASTROSCAN_BASE_URL=https://astroscan.space scripts/post_deploy_check.sh
#   scripts/post_deploy_check.sh --since "5 min ago"

set -uo pipefail

BASE_URL="${ASTROSCAN_BASE_URL:-http://127.0.0.1:5003}"
BASE_URL="${BASE_URL%/}"
SINCE="${1:---since}"; [ "$SINCE" = "--since" ] && SINCE="${2:-2 min ago}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

C_RED='\033[31m'; C_GRN='\033[32m'; C_YEL='\033[33m'; C_DIM='\033[2m'; C_BLD='\033[1m'; C_OFF='\033[0m'
[ -t 1 ] || { C_RED=''; C_GRN=''; C_YEL=''; C_DIM=''; C_BLD=''; C_OFF=''; }

FAIL=0
SECTION_RESULTS=()

_section()    { echo -e "\n${C_BLD}== $* ==${C_OFF}"; }
_ok()         { echo -e "  ${C_GRN}OK${C_OFF}     $*"; }
_warn()       { echo -e "  ${C_YEL}WARN${C_OFF}   $*"; }
_ko()         { echo -e "  ${C_RED}FAIL${C_OFF}   $*"; FAIL=$((FAIL+1)); }
_info()       { echo -e "  ${C_DIM}info${C_OFF}   $*"; }
_summary_add(){ SECTION_RESULTS+=("$*"); }

# ── 1. systemctl status ──────────────────────────────────────────────────────
_section "1/5 systemd service state"
SVC_STATE="$(systemctl is-active astroscan.service 2>/dev/null || echo unknown)"
if [ "$SVC_STATE" = "active" ]; then
    _ok "astroscan.service: active"
    _summary_add "systemd:PASS"
else
    _ko "astroscan.service: $SVC_STATE"
    _summary_add "systemd:FAIL($SVC_STATE)"
    echo -e "  ${C_DIM}--- last 10 lines ---${C_OFF}"
    systemctl status astroscan.service --no-pager -n 10 2>&1 | sed 's/^/  /'
    exit 2  # don't grade further when service is down
fi
WORKERS="$(pgrep -fc 'gunicorn.*wsgi:app' 2>/dev/null || echo 0)"
_info "gunicorn processes: $WORKERS  (1 master + N workers expected)"

# ── 2. smoke endpoints (delegate to smoke_tests.sh) ──────────────────────────
_section "2/5 smoke endpoints"
if [ -x "$SCRIPT_DIR/smoke_tests.sh" ]; then
    if ASTROSCAN_BASE_URL="$BASE_URL" "$SCRIPT_DIR/smoke_tests.sh" --quiet; then
        _ok "smoke suite: all PASS"
        _summary_add "smoke:PASS"
    else
        _ko "smoke suite: one or more failures"
        _summary_add "smoke:FAIL"
        echo -e "  ${C_DIM}--- rerun verbose for details: $SCRIPT_DIR/smoke_tests.sh${C_OFF}"
    fi
else
    _warn "smoke_tests.sh not executable — run: chmod +x $SCRIPT_DIR/smoke_tests.sh"
    _summary_add "smoke:SKIPPED"
fi

# ── 3. journal scan: ERROR / CRITICAL in last $SINCE ─────────────────────────
_section "3/5 journal errors since $SINCE"
JOURNAL_ERR="$(journalctl -u astroscan.service --since "$SINCE" --no-pager 2>/dev/null \
              | grep -iE 'ERROR|CRITICAL|Traceback|OperationalError|PermissionError' \
              | grep -viE 'OPENAI_API_KEY|ASTROSCAN_ADMIN_TOKEN|optional_missing' || true)"
if [ -z "$JOURNAL_ERR" ]; then
    _ok "no ERROR/CRITICAL in last $SINCE"
    _summary_add "journal:PASS"
else
    N=$(echo "$JOURNAL_ERR" | wc -l)
    _ko "$N error line(s) found"
    echo "$JOURNAL_ERR" | head -10 | sed 's/^/    /'
    [ "$N" -gt 10 ] && echo "    ... ($((N-10)) more)"
    _summary_add "journal:FAIL($N)"
fi

# ── 4. guardian agent ────────────────────────────────────────────────────────
_section "4/5 guardian agent"
GH="$(curl -sS --max-time 3 "$BASE_URL/api/guardian/health" 2>/dev/null || echo '')"
if [ -z "$GH" ]; then
    _warn "guardian endpoint unreachable"
    _summary_add "guardian:SKIPPED"
else
    SUMMARY="$(echo "$GH" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('parse-error'); sys.exit(1)
parts = []
parts.append(f\"module={d.get('module')}\")
parts.append(f\"v={d.get('version')}\")
parts.append(f\"enabled={d.get('enabled')}\")
parts.append(f\"started={d.get('started')}\")
parts.append(f\"thread_alive={d.get('thread_alive')}\")
parts.append(f\"ticks={d.get('ticks_total')}\")
parts.append(f\"is_leader={d.get('is_leader')}\")
parts.append(f\"leader_pid={d.get('leader_pid')}\")
parts.append(f\"in_grace={d.get('in_restart_grace')}\")
print('|'.join(parts))
" 2>/dev/null)"
    if echo "$SUMMARY" | grep -q "module=guardian"; then
        _ok "$SUMMARY"
        # singleton cross-worker check: 4 hits → leader_pid stable
        LEADERS=$(for i in 1 2 3 4 5 6; do
            curl -sS --max-time 2 "$BASE_URL/api/guardian/health" 2>/dev/null \
              | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('leader_pid'))" 2>/dev/null
        done | sort -u | grep -v '^$' | grep -v '^None$')
        N_LEADERS=$(echo "$LEADERS" | grep -c . || true)
        if [ "$N_LEADERS" = "1" ]; then
            _ok "singleton: 1 leader pid observed across workers ($LEADERS)"
            _summary_add "guardian:PASS"
        elif [ "$N_LEADERS" = "0" ]; then
            _warn "singleton: no leader pid observed (lockfile may not exist yet)"
            _summary_add "guardian:WARN"
        else
            _ko "singleton: multiple leader pids observed → race / regression"
            echo "$LEADERS" | sed 's/^/    /'
            _summary_add "guardian:FAIL"
        fi
    else
        _ko "guardian health invalid: $GH"
        _summary_add "guardian:FAIL"
    fi
fi

# ── 5. boot mode (factory vs fallback) ───────────────────────────────────────
_section "5/5 boot mode"
BOOT_LINE="$(journalctl -u astroscan.service --since "$SINCE" --no-pager 2>/dev/null \
              | grep -E 'BOOT_MODE=|create_app\(\) loaded' | tail -1)"
if echo "$BOOT_LINE" | grep -q "BOOT_MODE=factory"; then
    _ok "factory boot confirmed"
    _summary_add "boot:PASS"
    _info "$(echo "$BOOT_LINE" | sed 's/.*BOOT_MODE/BOOT_MODE/' | cut -c-120)"
elif echo "$BOOT_LINE" | grep -q "BOOT_MODE=monolith_fallback\|BOOT_MODE=hard_fail\|BOOT_MODE=monolith_forced"; then
    _ko "non-factory boot detected: $BOOT_LINE"
    _summary_add "boot:FAIL"
elif [ -z "$BOOT_LINE" ]; then
    _warn "no BOOT_MODE marker in journal (since $SINCE) — restart older than window?"
    _summary_add "boot:UNKNOWN"
else
    _warn "unexpected boot line: $BOOT_LINE"
    _summary_add "boot:UNKNOWN"
fi

# ── Final summary ────────────────────────────────────────────────────────────
echo
echo -e "${C_BLD}== SUMMARY ==${C_OFF}"
for s in "${SECTION_RESULTS[@]}"; do echo "  $s"; done
echo
if [ "$FAIL" -eq 0 ]; then
    echo -e "${C_GRN}${C_BLD}POST-DEPLOY OK${C_OFF}  base=$BASE_URL  workers=$WORKERS"
    exit 0
else
    echo -e "${C_RED}${C_BLD}POST-DEPLOY FAIL${C_OFF}  $FAIL section(s) failed  base=$BASE_URL"
    exit 1
fi
