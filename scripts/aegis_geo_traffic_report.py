#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rapport géolocalisé des IP « humaines » (User-Agent filtré) depuis les logs nginx distants.

Variables d'environnement : voir scripts/aegis_ssh.py (SSH) et :
  NGINX_ACCESS_LOG    chemin distant (défaut /var/log/nginx/access.log)
  GEO_TAIL_LINES      lignes analysées (défaut 20000, max 500000)
  GEO_TOP_N           IP affichées (défaut 15, max 100)
  GEO_API_SLEEP       pause entre appels ip-api en secondes (défaut 0.25)
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from aegis_ssh import (  # noqa: E402
    build_ssh_command,
    env_int,
    hillsboro_host,
    is_bot_user_agent,
    is_private_or_reserved_ip,
    parse_nginx_combined_ip_ua,
)


def _fetch_log_tail(host: str, log_path: str, n_lines: int) -> str:
    remote = f"tail -n {int(n_lines)} {shlex.quote(log_path)} 2>/dev/null"
    r = subprocess.run(
        build_ssh_command(host, remote),
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        err = (r.stderr or "").strip() or f"code de sortie {r.returncode}"
        raise RuntimeError(err)
    return r.stdout or ""


def _count_human_ips(log_text: str) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    matched = 0
    for line in log_text.splitlines():
        parsed = parse_nginx_combined_ip_ua(line)
        if not parsed:
            continue
        matched += 1
        ip, ua = parsed
        if is_bot_user_agent(ua):
            continue
        counts[ip] = counts.get(ip, 0) + 1
    if matched == 0 and log_text.strip():
        print(
            "[AEGIS] Aucune ligne ne correspond au format « combined » (voir log_format nginx).",
            file=sys.stderr,
        )
    ranked = sorted(counts.items(), key=lambda x: -x[1])
    return ranked


def _geo_lookup(ip: str) -> tuple[str, str]:
    if is_private_or_reserved_ip(ip):
        return "Réseau privé / local", "—"
    try:
        req = urllib.request.Request(
            f"http://ip-api.com/json/{ip}?lang=fr&fields=status,country,city,message"
        )
        req.add_header("User-Agent", "Aegis-Geo-Tracker/1.0")
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode())
        if data.get("status") != "success":
            return "API", (data.get("message") or "échec")[:40]
        return data.get("country", "Inconnu"), data.get("city", "Inconnue")
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return "Erreur réseau API", "—"


def _col(text: str, width: int) -> str:
    """Texte sur largeur fixe (troncature propre, une seule ligne)."""
    s = " ".join((text or "").split())
    if len(s) <= width:
        return s.ljust(width)
    if width < 2:
        return s[:width]
    return s[: width - 1] + "…"


def generate_human_geo_report() -> None:
    host = hillsboro_host()
    log_path = os.environ.get("NGINX_ACCESS_LOG", "/var/log/nginx/access.log").strip() or "/var/log/nginx/access.log"
    tail_n = env_int("GEO_TAIL_LINES", 20_000, minimum=100, maximum=500_000)
    top_n = env_int("GEO_TOP_N", 15, minimum=1, maximum=100)
    api_sleep = float(os.environ.get("GEO_API_SLEEP", "0.25") or "0.25")
    if api_sleep < 0 or api_sleep > 5:
        api_sleep = 0.25

    print("=====================================================")
    print("--- [AEGIS : RAPPORT GÉOLOCALISÉ - TRAFIC HUMAIN] ---")
    print(f"Cible : {host}")
    print("Filtre : User-Agent (bots / scrapers / clients typiques exclus)")
    print("=====================================================\n")

    print("[*] Extraction des dernières lignes du journal nginx (SSH)…")
    try:
        raw = _fetch_log_tail(host, log_path, tail_n)
    except RuntimeError as e:
        print(f"\n[ERREUR] Liaison SSH ou lecture du journal : {e}", file=sys.stderr)
        sys.exit(1)

    ranked = _count_human_ips(raw)[:top_n]
    if not ranked:
        print("\n(Aucune ligne exploitable ou tout le trafic filtré comme bot.)")
        print("Vérifiez GEO_TAIL_LINES et le log_format nginx (combined ou équivalent).")
        return

    w_req, w_ip, w_country, w_city = 10, 45, 30, 26
    sep = " | "
    rule = "-" * (w_req + len(sep) + w_ip + len(sep) + w_country + len(sep) + w_city)

    print()
    print(_col("REQUÊTES", w_req) + sep + _col("ADRESSE IP", w_ip) + sep + _col("PAYS", w_country) + sep + _col("VILLE", w_city))
    print(rule)

    for i, (ip, count) in enumerate(ranked):
        country, city = _geo_lookup(ip)
        line = (
            _col(str(count), w_req)
            + sep
            + _col(ip, w_ip)
            + sep
            + _col(country, w_country)
            + sep
            + _col(city, w_city)
        )
        print(line)
        if i < len(ranked) - 1 and api_sleep > 0:
            time.sleep(api_sleep)


if __name__ == "__main__":
    generate_human_geo_report()
