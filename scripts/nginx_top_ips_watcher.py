#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Surveille le top des IP (access.log nginx) sur le nœud distant via SSH.

Variables : scripts/aegis_ssh.py + NGINX_ACCESS_LOG, WATCHER_TAIL, WATCHER_INTERVAL.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from aegis_ssh import build_ssh_command, env_int, hillsboro_host  # noqa: E402
import shlex


def run_report(host: str, log_path: str, tail_n: int) -> int:
    remote = (
        f"tail -n {tail_n} {shlex.quote(log_path)} 2>/dev/null | "
        "awk '{print $1}' | sort | uniq -c | sort -nr | head -n 5"
    )
    return subprocess.call(build_ssh_command(host, remote))


def monitor_traffic() -> None:
    host = hillsboro_host()
    log_path = os.environ.get("NGINX_ACCESS_LOG", "/var/log/nginx/access.log").strip() or "/var/log/nginx/access.log"
    tail_n = env_int("WATCHER_TAIL", 100, minimum=10, maximum=500_000)
    interval = env_int("WATCHER_INTERVAL", 60, minimum=5, maximum=86_400)

    print("--- [AstroScan-Chohra — nginx top IPs] ---", flush=True)
    try:
        while True:
            print(f"\n[REPORT {time.strftime('%H:%M:%S')}] Top trafic (dernières {tail_n} lignes) :", flush=True)
            run_report(host, log_path, tail_n)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[STOP] Interruption clavier.", flush=True)


if __name__ == "__main__":
    monitor_traffic()
