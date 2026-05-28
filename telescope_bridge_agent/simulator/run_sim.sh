#!/usr/bin/env bash
# Launch the Alpaca simulator in background. PID file at /tmp/alpaca_sim.pid.
set -euo pipefail

SIM_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/alpaca_sim.pid"
LOG_FILE="/tmp/alpaca_sim.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "alpaca_sim already running (pid $(cat "$PID_FILE"))" >&2
    exit 1
fi

nohup python3 "$SIM_DIR/alpaca_sim.py" >"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
sleep 0.4

if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "alpaca_sim failed to start; check $LOG_FILE" >&2
    exit 1
fi

echo "alpaca_sim started pid=$(cat "$PID_FILE") log=$LOG_FILE"
