#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Veille SSH sur le nœud Hillsboro : top IP nginx + compteurs iptables DROP.

Variables : scripts/aegis_ssh.py + NGINX_ACCESS_LOG, WATCHER_TAIL, WATCHER_INTERVAL.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from aegis_ssh import build_ssh_command, env_int, hillsboro_host  # noqa: E402
import shlex


def run_traffic(host: str, log_path: str, tail_n: int) -> None:
    remote = (
        f"tail -n {tail_n} {shlex.quote(log_path)} 2>/dev/null | "
        "awk '{print $1}' | sort | uniq -c | sort -nr | head -n 5"
    )
    subprocess.run(build_ssh_command(host, remote), check=False)


def run_aegis_counters(host: str) -> None:
    # Exclure les lignes « Chain » ; $(NF-1) = source IPv4/IPv6 dans la sortie -L standard.
    remote = (
        "iptables -L INPUT -v -n 2>/dev/null | "
        "awk '!/^Chain/ && /DROP/ && $1 ~ /^[0-9]+$/ "
        "{print \"Bloqué:\", $1, \"paquets — source\", $(NF-1)}'"
    )
    r = subprocess.run(
        build_ssh_command(host, remote),
        capture_output=True,
        text=True,
        check=False,
    )
    out = (r.stdout or "").strip()
    if out:
        print(out)
    else:
        print("(aucune règle DROP avec compteur — ou chaîne INPUT vide / nftables)")


def monitor_astroscan_node() -> None:
    host = hillsboro_host()
    log_path = os.environ.get("NGINX_ACCESS_LOG", "/var/log/nginx/access.log").strip() or "/var/log/nginx/access.log"
    tail_n = env_int("WATCHER_TAIL", 100, minimum=10, maximum=500_000)
    interval = env_int("WATCHER_INTERVAL", 30, minimum=5, maximum=86_400)

    print("==================================================")
    print("--- [AstroScan-Chohra — tactical watcher] ---")
    print(f"Cible : {host}")
    print("Liaison : voir AEGIS_SSH_BATCH / WATCHER_SSH_BATCH (cron) dans aegis_ssh.py")
    print("==================================================\n")

    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n[SCAN {now}] --- Trafic web (requêtes | IP) :")
            run_traffic(host, log_path, tail_n)

            print(f"[SCAN {now}] --- Bouclier (iptables DROP, INPUT) :")
            run_aegis_counters(host)

            print("-" * 50)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[AstroScan-Chohra] Interruption manuelle. Veille suspendue.")


if __name__ == "__main__":
    monitor_astroscan_node()
