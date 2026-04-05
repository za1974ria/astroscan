"""
Accès local prioritaire : lecture JSON avec contrôle de fraîcheur, sans écraser l’existant.
À utiliser progressivement depuis les feeders ; aucun effet si non appelé.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def safe_read_json(path: str | Path) -> Optional[Dict[str, Any]]:
    try:
        p = Path(path)
        if not p.is_file():
            return None
        raw = p.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def file_age_seconds(path: str | Path) -> Optional[int]:
    try:
        p = Path(path)
        if not p.is_file():
            return None
        return max(0, int(time.time() - p.stat().st_mtime))
    except Exception:
        return None


def read_json_if_fresh(
    path: str | Path,
    max_age_seconds: float,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Retourne (données, raison) : données None si absentes / trop vieilles / invalides.
    """
    p = Path(path)
    if not p.is_file():
        return None, "missing"
    age = file_age_seconds(p)
    if age is None:
        return None, "unreadable"
    if age > max_age_seconds:
        return None, "stale"
    data = safe_read_json(p)
    if data is None:
        return None, "invalid_json"
    return data, "ok"


def data_core_path(station_root: str, *parts: str) -> str:
    base = Path(station_root) / "data_core"
    return str(base.joinpath(*parts))


def ensure_data_core_dirs(station_root: str) -> None:
    """Crée les répertoires data_core/* si absents (idempotent)."""
    sub = ("tle", "iss", "dsn", "weather", "skyview", "cache", "alerts", "notifications")
    root = Path(station_root) / "data_core"
    for s in sub:
        try:
            (root / s).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
