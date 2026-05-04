#!/usr/bin/env python3
"""Vérifie l'environnement production (sans afficher de secrets).

Charge le même `.env` que `station_web` (dotenv + setdefault), exécute
``validate_production_env``, affiche uniquement un statut sûr, code 0/1.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _station_root() -> str:
    return os.environ.get("STATION", "/root/astro_scan")


def load_env_like_station_web() -> None:
    """Aligné sur station_web.py : dotenv puis setdefault depuis .env."""
    station = _station_root()
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(station, ".env"))
    except Exception:
        pass

    env_file = os.path.join(station, ".env")
    p = Path(env_file)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    load_env_like_station_web()
    from app.services.env_guard import validate_production_env

    try:
        report = validate_production_env()
    except RuntimeError as exc:
        name = str(exc)
        print(f"env_check: FAIL required variable missing or invalid: {name}")
        return 1

    missing = report.get("optional_missing") or []
    if missing:
        print(
            "env_check: OK required; optional_missing:",
            ",".join(missing),
        )
    else:
        print("env_check: OK required; optional_missing: (none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
