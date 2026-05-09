"""Utilitaires purs AstroScan — sans Flask, sans requests, testables isolément.

Extraits de station_web.py.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ── Détection bots ────────────────────────────────────────────────────────────

_VISITOR_BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|bingpreview|facebookexternal|semrush|ahrefs|"
    r"curl/|wget|python-requests|axios|go-http|http\.client|libwww|scrapy|"
    r"googlebot|bingbot|yandex|duckduck|baiduspider|petalbot|applebot|gptbot|"
    r"claudebot|anthropic|bytespider",
    re.I,
)


def _is_bot_user_agent(user_agent):
    """Retourne True si le User-Agent ressemble à un bot/crawler."""
    ua = (user_agent or "")[:400]
    return bool(_VISITOR_BOT_RE.search(ua))


# ── Dates / timestamps ────────────────────────────────────────────────────────

def _parse_iso_to_epoch_seconds(iso_str):
    """Convertit une chaîne ISO 8601 (ou timestamp numérique) en epoch secondes entier."""
    try:
        if not iso_str:
            return None
        if isinstance(iso_str, (int, float)):
            return int(iso_str)
        s = str(iso_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


# ── JSON sûr ──────────────────────────────────────────────────────────────────

def _safe_json_loads(raw, log_label=None):
    """Parse JSON sans lever d'exception. Ignore corps vide / HTML / non-JSON."""
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        try:
            s = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            return None
    else:
        s = (str(raw) or "").strip()
    if len(s) < 2 or s[0] not in "[{":
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        if log_label:
            log.debug("%s: corps non JSON ignoré", log_label)
        return None


# ── Système de fichiers ───────────────────────────────────────────────────────

def safe_ensure_dir(path: str) -> None:
    """Crée le dossier parent si nécessaire, sans lever si déjà présent."""
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    except Exception as e:
        log.warning("safe_ensure_dir(%s): %s", path, e)


# ── Détection langue ──────────────────────────────────────────────────────────

_EN_WORDS_RE = re.compile(
    r'\b(the|and|with|this|from|that|was|were|pictured|viewed|between|'
    r'captured|observed|known|bright|dark|light|shows|appear|near|across|'
    r'over|through|toward|within|during|before|after|above|below|along|'
    r'around|behind|beyond|despite|although|however|therefore|because|'
    r'while|where|which|whose|their|there|these|those|would|could|should|'
    r'might|shall|will|been|have|has|had|its|our|your|their)\b',
    re.I,
)


def _detect_lang(text):
    """Retourne True si le texte semble anglais (heuristique mots fréquents)."""
    if not text or len(text) < 10:
        return False
    return bool(_EN_WORDS_RE.search(text))
