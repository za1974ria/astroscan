"""Validation stricte des variables d'environnement en production.

Ne journalise jamais les valeurs des secrets — noms de variables uniquement.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

log = logging.getLogger(__name__)

REQUIRED_ENV_PROD: List[str] = ["SECRET_KEY", "NASA_API_KEY"]

OPTIONAL_ENV_CHECKED: List[str] = [
    "ANTHROPIC_API_KEY",
    "CESIUM_TOKEN",
    "N2YO_API_KEY",
]

MIN_SECRET_KEY_LEN_PRODUCTION = 32


def _nonempty_str(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    s = raw.strip() if isinstance(raw, str) else str(raw).strip()
    return s or None


def validate_production_env() -> Dict[str, Any]:
    """Vérifie les variables requises pour la config production.

    Lève ``RuntimeError`` avec le *nom* de la variable uniquement si une
    exigence n'est pas satisfaite. Pour les clés optionnelles absentes,
    journalise un avertissement et les liste dans ``optional_missing``.

    Returns:
        {"required_ok": True, "optional_missing": [...]}
    """
    sk = _nonempty_str("SECRET_KEY")
    if sk is None or len(sk) < MIN_SECRET_KEY_LEN_PRODUCTION:
        raise RuntimeError("SECRET_KEY")

    if _nonempty_str("NASA_API_KEY") is None:
        raise RuntimeError("NASA_API_KEY")

    optional_missing: List[str] = []
    for name in OPTIONAL_ENV_CHECKED:
        if _nonempty_str(name) is None:
            optional_missing.append(name)
            log.warning("[ENV_GUARD] optional environment variable missing: %s", name)

    return {"required_ok": True, "optional_missing": optional_missing}
