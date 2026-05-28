#!/usr/bin/env bash
# smoke_tests.sh — AstroScan production smoke suite (CI/cron-friendly).
#
# Exit codes:
#   0  all smoke tests passed
#   1  one or more endpoint failures
#   2  service unreachable (refuse to grade if not running)
#
# Usage:
#   scripts/smoke_tests.sh                       # default 127.0.0.1:5003
#   ASTROSCAN_BASE_URL=https://astroscan.space scripts/smoke_tests.sh
#   scripts/smoke_tests.sh --quiet               # only PASS/FAIL summary
#
# CHANTIER 3 (2026-05-23) — see also tests/test_smoke_prod.py for pytest variant.

set -uo pipefail  # do NOT set -e: we want to run all tests then aggregate.

BASE_URL="${ASTROSCAN_BASE_URL:-http://127.0.0.1:5003}"
BASE_URL="${BASE_URL%/}"
TIMEOUT="${ASTROSCAN_SMOKE_TIMEOUT:-3}"
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

PASS=0
FAIL=0
FAILED_TESTS=()

C_RED='\033[31m'; C_GRN='\033[32m'; C_YEL='\033[33m'; C_DIM='\033[2m'; C_OFF='\033[0m'
[ -t 1 ] || { C_RED=''; C_GRN=''; C_YEL=''; C_DIM=''; C_OFF=''; }

_log()  { [ "$QUIET" -eq 0 ] && echo -e "$*"; }
_pass() { PASS=$((PASS+1)); _log "  ${C_GRN}PASS${C_OFF}  $*"; }
_fail() { FAIL=$((FAIL+1)); FAILED_TESTS+=("$*"); _log "  ${C_RED}FAIL${C_OFF}  $*"; }

# ── Service reachability check ───────────────────────────────────────────────
_check_alive() {
    local host_port="${BASE_URL#*://}"
    host_port="${host_port%%/*}"
    local host="${host_port%%:*}"
    local port
    case "$BASE_URL" in
        https://*) port="${host_port##*:}"; [ "$port" = "$host" ] && port=443 ;;
        *)         port="${host_port##*:}"; [ "$port" = "$host" ] && port=80 ;;
    esac
    if ! (echo > "/dev/tcp/$host/$port") 2>/dev/null; then
        echo -e "${C_RED}UNREACHABLE${C_OFF}  $BASE_URL  (host=$host port=$port)"
        exit 2
    fi
}

# ── Single HTTP probe: returns "status|body" on stdout ───────────────────────
_probe() {
    local path="$1"
    shift
    curl -sS -o /tmp/_smoke_body.$$ -w "%{http_code}" \
        --max-time "$TIMEOUT" "$@" "$BASE_URL$path"
    local code=$?
    if [ "$code" -ne 0 ]; then
        echo "000"
        return
    fi
}

_body() { cat /tmp/_smoke_body.$$ 2>/dev/null; }

# ── Individual tests ─────────────────────────────────────────────────────────

t_status_eq() {
    # t_status_eq NAME PATH EXPECTED_STATUS [curl args...]
    local name="$1" path="$2" expected="$3"; shift 3
    local got
    got="$(_probe "$path" "$@")"
    if [ "$got" = "$expected" ]; then _pass "$name  [$path → $got]"
    else _fail "$name  [$path → $got, expected $expected]"; fi
}

t_status_in() {
    # t_status_in NAME PATH "401 503" [curl args...]
    local name="$1" path="$2" expected_set="$3"; shift 3
    local got
    got="$(_probe "$path" "$@")"
    if echo " $expected_set " | grep -q " $got "; then _pass "$name  [$path → $got]"
    else _fail "$name  [$path → $got, expected one of: $expected_set]"; fi
}

t_json_field() {
    # t_json_field NAME PATH PYTHON_EXPR_RETURNING_BOOL
    # Expression lue via env SMOKE_EXPR + body via fichier → zero quote conflict.
    local name="$1" path="$2" expr="$3"
    local got
    got="$(_probe "$path")"
    if [ "$got" != "200" ]; then _fail "$name  [$path → $got, expected 200]"; return; fi
    local out rc
    out="$(SMOKE_EXPR="$expr" SMOKE_BODY_FILE="/tmp/_smoke_body.$$" python3 - <<'PYEOF' 2>&1
import json, os, sys
try:
    with open(os.environ["SMOKE_BODY_FILE"]) as fh:
        d = json.load(fh)
except Exception as e:
    print("not-json:", e); sys.exit(1)
expr = os.environ["SMOKE_EXPR"]
try:
    ok = bool(eval(expr, {"__builtins__": __builtins__}, {"d": d}))
except Exception as e:
    print("eval-error:", e); sys.exit(3)
if not ok:
    print("expr-false ->", d); sys.exit(2)
PYEOF
)"
    rc=$?
    if [ "$rc" -eq 0 ]; then _pass "$name  [$path]"; else _fail "$name  [$path: $out]"; fi
}

t_header_contains() {
    # t_header_contains NAME PATH HEADER_LOWER NEEDLE
    local name="$1" path="$2" header="$3" needle="$4"
    local headers
    headers="$(curl -sSI --max-time "$TIMEOUT" "$BASE_URL$path" 2>/dev/null)"
    if echo "$headers" | grep -i "^$header:" | grep -qi "$needle"; then
        _pass "$name  [$path: $header contains '$needle']"
    else
        _fail "$name  [$path: $header missing '$needle']"
    fi
}

# ── Suite ────────────────────────────────────────────────────────────────────
_log "${C_DIM}AstroScan smoke suite — base=$BASE_URL timeout=${TIMEOUT}s${C_OFF}"
_check_alive

t_status_eq    "root_200"           /                              200
t_status_eq    "portail_200"        /portail                       200
t_status_eq    "analytics_200"      /analytics                     200
t_json_field   "health_ok"          /health                        "d.get('status')=='ok' or d.get('ok') is True"
t_json_field   "api_health_ok"      /api/health                    "(d.get('operational',{}).get('status')=='ok') or (d.get('ok') is True)"
t_json_field   "api_visits_count"   /api/visits                    "isinstance(d.get('count'),int) and d['count']>=0"
t_status_in    "admin_cb_unauth"    /api/admin/circuit-breakers    "401 503"
t_status_in    "admin_cb_bad_token" /api/admin/circuit-breakers    "401 503" -H "Authorization: Bearer wrong-x"
t_json_field   "guardian_health"    /api/guardian/health           "d.get('module')=='guardian' and d.get('ok') is True"
t_header_contains "csp_present"     /analytics                     "Content-Security-Policy" "default-src"
t_header_contains "nosniff_present" /analytics                     "X-Content-Type-Options"  "nosniff"
t_header_contains "cookie_httponly" /                              "Set-Cookie"              "HttpOnly"

# ── Summary ──────────────────────────────────────────────────────────────────
rm -f /tmp/_smoke_body.$$
TOTAL=$((PASS+FAIL))
if [ "$FAIL" -eq 0 ]; then
    [ "$QUIET" -eq 0 ] && echo -e "${C_GRN}SMOKE PASS${C_OFF}  $PASS/$TOTAL  ($BASE_URL)"
    exit 0
else
    echo -e "${C_RED}SMOKE FAIL${C_OFF}  $FAIL/$TOTAL failed  ($BASE_URL)"
    for t in "${FAILED_TESTS[@]}"; do echo "  - $t"; done
    exit 1
fi
