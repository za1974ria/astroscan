"""AI translation + chat helpers — Claude / Gemini / Groq / xAI Grok.

Extrait de station_web.py (PASS 10) pour permettre l'utilisation
par ai_bp et autres BPs sans dépendance circulaire.

Toutes les API keys lues depuis os.environ :
    ANTHROPIC_API_KEY, GEMINI_API_KEY (+ BACKUP, _3),
    GROQ_API_KEY, XAI_API_KEY.

Caches in-memory (par worker Gunicorn) :
    TRANSLATION_CACHE, _chat_cache, _key_usage,
    TRANSLATE_CACHE (gemini_translate).

Compteurs globaux :
    CLAUDE_CALL_COUNT, GROQ_CALL_COUNT, CLAUDE_MAX_CALLS,
    CLAUDE_80_WARNING_SENT.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Optional, Tuple

import requests

from app.config import DB_PATH

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State / globals
# ---------------------------------------------------------------------------
TRANSLATION_CACHE: dict = {}
MAX_CACHE_SIZE = 500

TRANSLATE_CACHE: dict = {}
TRANSLATE_TTL_SECONDS = 3600
TRANSLATE_LAST_REQUEST_TS = 0.0

_chat_cache: dict = {}   # {hash_msg: (timestamp, response)}
_key_usage: dict = {}    # {key: last_used_timestamp}

CLAUDE_CALL_COUNT = 0
CLAUDE_MAX_CALLS = 100
CLAUDE_80_WARNING_SENT = False
GROQ_CALL_COUNT = 0


# ---------------------------------------------------------------------------
# Language detection helper (lightweight wrapper)
# ---------------------------------------------------------------------------
def _detect_lang(text: str) -> bool:
    """Returns True if text looks English (needs translation), False if French."""
    try:
        from services.utils import _detect_lang as _detect
        return _detect(text)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Gemini — rotation de clés + curl
# ---------------------------------------------------------------------------
def _get_best_key() -> Optional[str]:
    """Retourne la clé Gemini la moins récemment utilisée (rotation)."""
    keys = []
    for k in ("GEMINI_API_KEY", "GEMINI_API_KEY_BACKUP", "GEMINI_API_KEY_3"):
        v = os.environ.get(k, "").strip()
        if v:
            keys.append(v)
    if not keys:
        return None
    keys.sort(key=lambda k: _key_usage.get(k, 0))
    return keys[0]


def _call_gemini(prompt: str, model: str = "gemini-2.0-flash") -> Tuple[Optional[str], Optional[str]]:
    """Appel Gemini avec rotation de clés + curl (contourne blocage urllib) + délai 4s."""
    api_key = _get_best_key()
    if not api_key:
        return None, "Clé API Gemini non configurée."

    last = _key_usage.get(api_key, 0)
    wait = 4.0 - (time.time() - last)
    if wait > 0:
        time.sleep(wait)

    _key_usage[api_key] = time.time()
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]})
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )

    try:
        proc = subprocess.run(
            ["curl", "-s", "-X", "POST", url,
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=25,
        )
        result = json.loads(proc.stdout)
        if "error" in result:
            code = result["error"].get("code", 0)
            msg_err = (result["error"].get("message") or "").strip()
            if code == 429:
                backup = os.environ.get("GEMINI_API_KEY_BACKUP", "").strip()
                if backup and backup != api_key:
                    _key_usage[backup] = 0
                    return _call_gemini(prompt, model)
                return None, "Quota dépassé — réessayez dans 1 minute."
            if code in (400, 401, 403) and (
                "invalid" in msg_err.lower()
                or "api key" in msg_err.lower()
                or "apikey" in msg_err.lower()
            ):
                return None, (
                    "Clé Gemini invalide. Vérifiez GEMINI_API_KEY et "
                    "GEMINI_API_KEY_BACKUP dans .env (Google AI Studio)."
                )
            return None, msg_err if msg_err else f"Erreur API ({code})."
        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text, None
    except subprocess.TimeoutExpired:
        return None, "Délai dépassé. Réessayez."
    except Exception as e:
        return None, f"Erreur connexion : {e}"


def _gemini_translate(text: str, obs_id: Optional[int] = None) -> str:
    """Traduit EN→FR via Gemini. Cache mémoire + DB observations."""
    global TRANSLATE_LAST_REQUEST_TS
    if not text or len(text) < 15:
        return text
    if not _detect_lang(text):
        return text  # Déjà en français
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return text
    try:
        lang = "fr"
        raw_key = (text[:1500] + "|" + lang).encode("utf-8", errors="ignore")
        cache_key = hashlib.sha256(raw_key).hexdigest()
        now_ts = time.time()
        item = TRANSLATE_CACHE.get(cache_key)
        if item and (now_ts - item.get("ts", 0) < TRANSLATE_TTL_SECONDS):
            return item.get("value", text)

        if now_ts - TRANSLATE_LAST_REQUEST_TS < 1.0:
            return text

        payload = json.dumps({"contents": [{"parts": [{"text":
            "Traduis ce texte astronomique en français fluide et naturel. "
            "Réponds UNIQUEMENT avec la traduction, sans guillemets ni commentaires.\n\n"
            + text[:1500]
        }]}]}).encode()
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}",
            data=payload, headers={"Content-Type": "application/json"},
        )
        TRANSLATE_LAST_REQUEST_TS = time.time()
        with urllib.request.urlopen(req, timeout=12) as r:
            result = json.loads(r.read())
        translated = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        try:
            TRANSLATE_CACHE[cache_key] = {"value": translated or text, "ts": time.time()}
        except Exception:
            pass
        if obs_id and translated:
            try:
                c = sqlite3.connect(DB_PATH)
                c.execute(
                    "UPDATE observations SET rapport_fr=? WHERE id=?",
                    (translated, obs_id),
                )
                c.commit()
                c.close()
            except Exception:
                pass
        return translated
    except urllib.error.HTTPError as e:
        if getattr(e, "code", None) == 429:
            prompt_tr = (
                "Traduis ce texte astronomique en français fluide et naturel. "
                "Réponds UNIQUEMENT avec la traduction, sans guillemets ni commentaires.\n\n"
                + text[:1500]
            )
            try:
                result, err = _call_gemini(prompt_tr)
                if result and result != text:
                    TRANSLATE_CACHE[cache_key] = {"value": result, "ts": time.time()}
                    return result
            except Exception:
                pass
            try:
                groq_result, groq_err = _call_groq(
                    "Traduis en français astronomique naturel. Réponds UNIQUEMENT avec la traduction.\n\n"
                    + text[:1500]
                )
                if groq_result and groq_result != text:
                    TRANSLATE_CACHE[cache_key] = {"value": groq_result, "ts": time.time()}
                    return groq_result
            except Exception:
                pass
        return text
    except Exception:
        return text


def _gemini_translate_no_throttle(text: str) -> str:
    """
    Version sans throttle de _gemini_translate, dédiée au batch endpoint.

    Le batch endpoint est lui-même rate-limité à 10/min/IP, donc le throttle
    global de 1s n'a pas lieu d'être ici (il casserait toute boucle batch).

    Réutilise TRANSLATE_CACHE partagé. NE met PAS à jour la DB observations
    (pas d'obs_id en batch).
    """
    if not text or len(text) < 15:
        return text
    if not _detect_lang(text):
        return text  # déjà en français
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return text
    cache_key = None
    try:
        lang = "fr"
        raw_key = (text[:1500] + "|" + lang).encode("utf-8", errors="ignore")
        cache_key = hashlib.sha256(raw_key).hexdigest()
        now_ts = time.time()
        item = TRANSLATE_CACHE.get(cache_key)
        if item and (now_ts - item.get("ts", 0) < TRANSLATE_TTL_SECONDS):
            return item.get("value", text)
        # PAS de check TRANSLATE_LAST_REQUEST_TS ici (volontaire pour batch)
        payload = json.dumps({"contents": [{"parts": [{"text":
            "Traduis ce texte astronomique en français fluide et naturel. "
            "Réponds UNIQUEMENT avec la traduction, sans guillemets ni commentaires.\n\n"
            + text[:1500]
        }]}]}).encode()
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}",
            data=payload, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
        translated = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        try:
            TRANSLATE_CACHE[cache_key] = {"value": translated or text, "ts": time.time()}
        except Exception:
            pass
        return translated or text
    except urllib.error.HTTPError as e:
        if getattr(e, "code", None) == 429:
            try:
                prompt_tr = (
                    "Traduis ce texte astronomique en français fluide et naturel. "
                    "Réponds UNIQUEMENT avec la traduction, sans guillemets ni commentaires.\n\n"
                    + text[:1500]
                )
                result, err = _call_gemini(prompt_tr)
                if result and result != text and cache_key:
                    TRANSLATE_CACHE[cache_key] = {"value": result, "ts": time.time()}
                    return result
            except Exception:
                pass
        return text
    except Exception:
        return text


# ---------------------------------------------------------------------------
# Claude (Anthropic) — requests wrapper
# ---------------------------------------------------------------------------
def _call_claude(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None, "Claude API key not configured"
    final_prompt = (
        "You are AEGIS, a professional assistant.\n"
        "You must ALWAYS respond in French.\n"
        "Never use English.\n"
        "Use clear, natural and professional French.\n\n"
        "User: " + prompt
    )
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": final_prompt}],
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=45)
        try:
            data = r.json()
        except ValueError:
            return None, (r.text or "Invalid JSON response")[:500]
        if r.status_code != 200:
            err_obj = data.get("error") if isinstance(data, dict) else None
            if isinstance(err_obj, dict):
                msg = (err_obj.get("message") or str(err_obj))[:500]
            elif isinstance(err_obj, str):
                msg = err_obj[:500]
            else:
                msg = (r.text or f"HTTP {r.status_code}")[:500]
            return None, msg
        text = data["content"][0]["text"].strip()
        return text, None
    except (KeyError, IndexError, TypeError) as e:
        return None, f"Réponse Claude invalide: {e}"
    except requests.RequestException as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# Groq (llama-3.3-70b) — fallback rapide via curl
# ---------------------------------------------------------------------------
def _call_groq(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Fallback Groq API — llama-3.3-70b — gratuit, zéro quota."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None, "GROQ_API_KEY non configurée"
    system_message = (
        "You are AEGIS, an intelligent and composed assistant.\n"
        "You speak like a real human expert, not like an AI.\n\n"
        "Your communication style is:\n"
        "- natural and fluid\n- calm and confident\n- clear and easy to follow\n\n"
        "You avoid:\n- robotic or generic phrases\n- unnecessary formatting\n- over-explaining\n\n"
        "You prefer:\n- short and clear paragraphs\n"
        "- simple but precise explanations\n- a conversational tone\n\n"
        "When answering:\n- go straight to the point\n"
        "- sound helpful and professional\n- make the user feel guided, not lectured\n"
        "Always prioritize clarity, relevance, and usefulness over verbosity.\n"
    )
    final_prompt = system_message + "\n\nUser: " + prompt
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": final_prompt}],
        "max_tokens": 1024,
        "temperature": 0.7,
    })

    try:
        from services.circuit_breaker import CB_GROQ
    except ImportError:
        CB_GROQ = None

    def _do_groq():
        proc = subprocess.run(
            ["curl", "-s", "-X", "POST",
             "https://api.groq.com/openai/v1/chat/completions",
             "-H", f"Authorization: Bearer {api_key}",
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=20,
        )
        result = json.loads(proc.stdout)
        if "error" in result:
            msg = (result["error"].get("message") or "Erreur Groq").strip()
            if "invalid" in msg.lower() or "api key" in msg.lower() or "apikey" in msg.lower():
                msg = (
                    "Clé Groq invalide. Vérifiez GROQ_API_KEY dans .env "
                    "(clé gsk_xxx sur console.groq.com)."
                )
            raise Exception(msg)
        return result["choices"][0]["message"]["content"].strip()

    if CB_GROQ is not None:
        text = CB_GROQ.call(_do_groq, fallback=None)
    else:
        try:
            text = _do_groq()
        except Exception as e:
            return None, str(e)
    if text is None:
        return None, "Groq indisponible (circuit ouvert)"
    return text, None


# ---------------------------------------------------------------------------
# xAI Grok — API compatible OpenAI
# ---------------------------------------------------------------------------
def _call_xai_grok(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    api_key = os.environ.get("XAI_API_KEY", "").strip()
    if not api_key:
        return None, "XAI_API_KEY non configurée"
    model = (os.environ.get("XAI_MODEL") or "grok-3").strip() or "grok-3"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.7,
    })
    url = (os.environ.get("XAI_CHAT_COMPLETIONS_URL") or "").strip() or "https://api.x.ai/v1/chat/completions"
    try:
        proc = subprocess.run(
            ["curl", "-s", "-X", "POST", url,
             "-H", f"Authorization: Bearer {api_key}",
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=45,
        )
        result = json.loads(proc.stdout)
        if "error" in result:
            msg = (result["error"].get("message") or "Erreur xAI Grok").strip()
            low = msg.lower()
            if "invalid" in low or "api key" in low or "unauthor" in low:
                msg = "Clé xAI invalide. Vérifiez XAI_API_KEY dans .env (console.x.ai)."
            return None, msg
        text = result["choices"][0]["message"]["content"].strip()
        return text, None
    except Exception as e:
        return None, f"Erreur xAI Grok : {e}"


# ---------------------------------------------------------------------------
# Translation EN→FR via Groq + cache
# ---------------------------------------------------------------------------
_EN_WORD_RE = re.compile(
    r"(?<!\w)(the|and|is|are|you|your|this|that|with|for|error)(?!\w)",
    re.IGNORECASE,
)


def _translate_to_french(text: str, max_chars: int = 800) -> str:
    """Traduit EN→FR via Groq avec cache mémoire."""
    if not text:
        return text
    text_to_translate = text[:max_chars] if max_chars else text
    if text_to_translate in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[text_to_translate]
    try:
        translated, err = _call_groq(
            "Traduis en français de manière naturelle et fluide :\n\n" + text_to_translate
        )
        if translated:
            if len(TRANSLATION_CACHE) > MAX_CACHE_SIZE:
                TRANSLATION_CACHE.clear()
            TRANSLATION_CACHE[text_to_translate] = translated
            return translated
    except Exception:
        pass
    return text


def _english_score(text: str) -> float:
    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return 0.0
    en_words = [w for w in words if _EN_WORD_RE.search(w)]
    return len(en_words) / len(words)


def _enforce_french(text: str) -> str:
    if not text:
        return text
    if _EN_WORD_RE.search(text):
        score = _english_score(text)
        if score > 0.2:
            log.info("English detected → auto translation (score: %.2f)", score)
            return _translate_to_french(text)
    return text


# ---------------------------------------------------------------------------
# Orchestrator : Claude pour prompts complexes, Groq sinon
# ---------------------------------------------------------------------------
def _is_complex_prompt(p: str) -> bool:
    if not p:
        return False
    p = p.lower()
    keywords = [
        "analyse", "analysis", "explain", "why", "compare",
        "financial", "architecture", "strategy",
        "detailed", "deep", "technical", "complex",
    ]
    return len(p) > 120 or any(k in p for k in keywords)


def _call_ai(prompt: str) -> Tuple[Optional[str], Optional[str], str]:
    """Sélection automatique Claude/Groq selon complexité + quotas."""
    global CLAUDE_CALL_COUNT, GROQ_CALL_COUNT, CLAUDE_80_WARNING_SENT

    claude_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    is_complex = _is_complex_prompt(prompt)
    if (
        CLAUDE_CALL_COUNT > 0.8 * CLAUDE_MAX_CALLS
        and not CLAUDE_80_WARNING_SENT
    ):
        log.warning("Claude usage above 80%%")
        CLAUDE_80_WARNING_SENT = True
    use_claude = CLAUDE_CALL_COUNT < CLAUDE_MAX_CALLS

    if claude_key and is_complex and use_claude:
        try:
            log.info("Using Claude (complex task)")
            reply, err = _call_claude(prompt)
            if reply:
                CLAUDE_CALL_COUNT += 1
                log.info("Claude usage: %s/%s", CLAUDE_CALL_COUNT, CLAUDE_MAX_CALLS)
                reply = _enforce_french(reply)
                return reply, err, "claude"
            else:
                log.warning("Claude failed, fallback to Groq")
        except Exception as e:
            log.warning("Claude error: %s", e)

    if not os.environ.get("GROQ_API_KEY", "").strip():
        return None, "Service IA temporairement indisponible. Réessayez plus tard.", "none"

    log.info("Using Groq (simple or fallback)")
    reply, err = _call_groq(prompt)
    if reply:
        GROQ_CALL_COUNT += 1
        reply = _enforce_french(reply)
        return reply, err, "groq"
    if err:
        log.warning("_call_ai Groq indisponible: %s", err)
    return None, err or "Service IA temporairement indisponible. Réessayez plus tard.", "groq"


def get_ai_counters() -> dict:
    """Snapshot des compteurs Claude/Groq pour /api/aegis/status."""
    return {
        "claude_calls": CLAUDE_CALL_COUNT,
        "claude_limit": CLAUDE_MAX_CALLS,
        "groq_calls": GROQ_CALL_COUNT,
    }
