"""
apod_translator.py — Traducteur NASA APOD FR via Claude API

PASS 27.14 (2026-05-09) — Cascade graceful (latence /apod 3-10s → ~50ms cas nominal) :
- timeout NASA réduit 10s → 4s (fetch_apod)
- helper get_today_cached_entry() pour pré-check cache disque AVANT fetch HTTP
- cache négatif in-memory 5min (is_negative_cache_active / mark_negative_cache)
"""
import os
import json
import time
from datetime import datetime, timezone
import requests
import anthropic

NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CACHE_PATH = "/root/astro_scan/data/apod_cache.json"

# Cache négatif in-memory (par worker) — ttl 5 min après échec NASA.
# Volatil au restart worker, acceptable vu le ttl court.
_NEGATIVE_CACHE_FAILED_AT = 0.0
_NEGATIVE_CACHE_TTL = 300


def is_negative_cache_active():
    """True si NASA a échoué dans les 5 dernières minutes (skip fetch)."""
    return _NEGATIVE_CACHE_FAILED_AT > 0 and (time.time() - _NEGATIVE_CACHE_FAILED_AT) < _NEGATIVE_CACHE_TTL


def mark_negative_cache():
    """Marque NASA en échec — bloque les fetchs pendant 5 min."""
    global _NEGATIVE_CACHE_FAILED_AT
    _NEGATIVE_CACHE_FAILED_AT = time.time()


def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_latest_cached_entry():
    cache = load_cache()
    if not cache:
        return None
    keys = sorted(cache.keys(), reverse=True)
    for k in keys:
        v = cache.get(k)
        if isinstance(v, dict):
            return v
    return None


def get_today_cached_entry():
    """Retourne l'entrée cache disque pour la date UTC courante avec title_fr
    valide (non-translation_failed). Sinon None — l'appelant fera fallback."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache = load_cache()
    entry = cache.get(today)
    if not isinstance(entry, dict):
        return None
    if not entry.get("title_fr"):
        return None
    if entry.get("translation_failed"):
        return None
    return entry


def fetch_apod():
    r = requests.get(
        "https://api.nasa.gov/planetary/apod",
        params={"api_key": NASA_API_KEY},
        timeout=4,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("NASA APOD payload invalide")
    return data


def get_apod_fr():
    try:
        data = fetch_apod()
        title_en = data.get("title", "")
        explanation_en = data.get("explanation", "")

        # Traduction via Claude si clé disponible
        if ANTHROPIC_API_KEY:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": f"Traduis en français naturel et scientifique:\nTitre: {title_en}\nExplication: {explanation_en}\nRéponds UNIQUEMENT avec JSON: {{\"title_fr\": \"...\", \"explanation_fr\": \"...\"}}"
                }]
            )
            import json
            translated = json.loads(msg.content[0].text)
            data["title_fr"] = translated.get("title_fr", title_en)
            data["explanation_fr"] = translated.get("explanation_fr", explanation_en)
        else:
            data["title_fr"] = title_en
            data["explanation_fr"] = explanation_en

        data["status"] = "ok"
        return data

    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


def build_or_refresh_current_apod(apod_meta=None):
    data = apod_meta if isinstance(apod_meta, dict) else fetch_apod()
    title_en = data.get("title", "") or ""
    explanation_en = data.get("explanation", "") or ""
    day = (data.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()

    title_fr = title_en
    explanation_fr = explanation_en
    translation_failed = False
    translation_warn = ""

    if ANTHROPIC_API_KEY:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": (
                        "Traduis en français naturel et scientifique:\n"
                        f"Titre: {title_en}\n"
                        f"Explication: {explanation_en}\n"
                        "Réponds UNIQUEMENT avec JSON: "
                        "{\"title_fr\": \"...\", \"explanation_fr\": \"...\"}"
                    ),
                }],
            )
            translated = json.loads(msg.content[0].text)
            title_fr = translated.get("title_fr", title_en)
            explanation_fr = translated.get("explanation_fr", explanation_en)
        except Exception as e:
            translation_failed = True
            translation_warn = str(e)[:240]

    entry = dict(data)
    entry["title_fr"] = title_fr
    entry["explanation_fr"] = explanation_fr
    entry["translation_failed"] = translation_failed
    if translation_warn:
        entry["translation_warn"] = translation_warn
    entry["status"] = "ok"
    entry["date"] = day

    cache = load_cache()
    cache[day] = entry
    save_cache(cache)
    return entry
