# -*- coding: utf-8 -*-
"""SSH et parsing nginx communs pour les outils Aegis (nœud Hillsboro).

Variables d'environnement (SSH) :
  HILLSBORO_SSH              user@host (défaut root@5.78.153.17)
  AEGIS_SSH_IDENTITY, SSH_IDENTITY_FILE   clé privée (-i)
  AEGIS_SSH_BATCH, WATCHER_SSH_BATCH      1/true/yes → BatchMode=yes
  AEGIS_SSH_CONNECT_TIMEOUT  secondes (défaut 20, plage 3–120)
  AEGIS_SSH_QUIET            0/false/no/off → sans option ssh -q
"""

from __future__ import annotations

import ipaddress
import os
import re
import sys
from typing import Optional, Tuple

DEFAULT_HILLSBORO_SSH = "root@5.78.153.17"

# Format combined nginx : … "$http_referer" "$http_user_agent"
NGINX_COMBINED_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[[^\]]+\] "[^"]*" \d+ \d+ "[^"]*" "(?P<ua>[^"]*)"\s*$'
)

_BOT_UA_RE = re.compile(
    r"bot|spider|crawler|curl|wget|python|Go-http|scrapy|java/|httpclient|axios|postman|"
    r"headless|phantom|selenium|lighthouse|pingdom|uptimerobot|monitoring|checker",
    re.IGNORECASE,
)


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def ssh_batch_mode() -> bool:
    return _truthy("AEGIS_SSH_BATCH") or _truthy("WATCHER_SSH_BATCH")


def env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 10_000_000) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return max(minimum, min(maximum, default))
    try:
        v = int(raw, 10)
    except ValueError:
        print(f"[AEGIS] Entier invalide {name}={raw!r} — repli {default}", file=sys.stderr)
        return max(minimum, min(maximum, default))
    if v < minimum or v > maximum:
        print(f"[AEGIS] {name}={v} hors [{minimum}, {maximum}] — repli {default}", file=sys.stderr)
        return max(minimum, min(maximum, default))
    return v


def hillsboro_host() -> str:
    h = os.environ.get("HILLSBORO_SSH", DEFAULT_HILLSBORO_SSH).strip()
    return h or DEFAULT_HILLSBORO_SSH


def build_ssh_command(host: str, remote_script: str) -> list[str]:
    timeout = env_int("AEGIS_SSH_CONNECT_TIMEOUT", 20, minimum=3, maximum=120)
    cmd: list[str] = ["ssh"]
    quiet = os.environ.get("AEGIS_SSH_QUIET", "1").strip().lower()
    if quiet not in ("0", "false", "no", "off"):
        cmd.append("-q")
    cmd.extend(
        [
            "-o",
            f"ConnectTimeout={timeout}",
            "-o",
            "BatchMode=yes" if ssh_batch_mode() else "BatchMode=no",
        ]
    )
    ident = os.environ.get("AEGIS_SSH_IDENTITY") or os.environ.get("SSH_IDENTITY_FILE", "").strip()
    if ident:
        if not os.path.isfile(ident) or not os.access(ident, os.R_OK):
            print(f"[ERREUR] Clé SSH illisible : {ident}", file=sys.stderr)
            sys.exit(1)
        cmd.extend(["-i", ident])
    cmd.extend([host, remote_script])
    return cmd


def is_private_or_reserved_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
        flags = [addr.is_private, addr.is_loopback, addr.is_link_local, addr.is_multicast]
        if hasattr(addr, "is_reserved"):
            flags.append(addr.is_reserved)
        return any(flags)
    except ValueError:
        return False


def parse_nginx_combined_ip_ua(line: str) -> Optional[Tuple[str, str]]:
    """Retourne (ip, user_agent) si la ligne ressemble au combined, sinon None."""
    line = line.strip()
    if not line:
        return None
    m = NGINX_COMBINED_RE.match(line)
    if m:
        return m.group("ip"), (m.group("ua") or "").strip()
    # Secours : première colonne = IP, dernière chaîne entre guillemets = UA (combined classique)
    parts_ip = line.split(None, 1)
    if not parts_ip:
        return None
    ip = parts_ip[0]
    try:
        ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return None
    quoted = re.findall(r'"([^"]*)"', line)
    if len(quoted) < 2:
        return None
    ua = quoted[-1].strip()
    return ip, ua


def is_bot_user_agent(ua: str) -> bool:
    if not ua or ua == "-":
        return True
    return bool(_BOT_UA_RE.search(ua))
