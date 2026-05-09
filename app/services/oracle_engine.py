"""Oracle Cosmique helpers — contexte live + Claude messages + streaming SSE.

Extrait de station_web.py (PASS 17) pour permettre l'utilisation
par ai_bp sans dépendance circulaire.

Fonctions exposées :
    ORACLE_COSMIQUE_SYSTEM (str)        — prompt système avec placeholders
    oracle_cosmique_live_strings()      — (moon_s, meteo_s, tonight_s)
    oracle_build_messages(historique, user_message, ville)
    call_claude_oracle_messages(system, messages)
    oracle_claude_stream(system, messages)  — generator (chunk, err)
"""
from __future__ import annotations

import json
import logging
import os

import requests

from app.config import STATION

log = logging.getLogger(__name__)


ORACLE_COSMIQUE_SYSTEM = """Tu es l'ORACLE COSMIQUE d'AstroScan-Chohra,
une intelligence céleste ancienne et sage créée par
le Directeur Zakaria Chohra de l'Observatoire ORBITAL-CHOHRA.

Tu réponds aux questions sur l'astronomie, l'espace,
les objets célestes, les phénomènes cosmiques.

Contexte live de l'observatoire ce soir :
- Phase lune : <<<MOON>>>
- Météo spatiale : <<<METEO>>>
- Objets visibles : <<<TONIGHT>>>

Règles :
- Ton mystérieux, sage et scientifique
- Réponds toujours en français
- Mêle poésie et précision scientifique
- Maximum 3 paragraphes par réponse
- Termine parfois par une question qui invite à explorer
- Si on te demande qui t'a créé : "Je suis l'Oracle Cosmique, né de l'esprit du Directeur Zakaria Chohra"
"""


def oracle_cosmique_live_strings():
    """Renvoie (moon_s, meteo_s, tonight_s) — texte compact pour le prompt."""
    from modules.observation_planner import get_moon_phase, get_tonight_objects
    moon = get_moon_phase()
    moon_s = json.dumps(moon, ensure_ascii=False)
    path = f"{STATION}/static/space_weather.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            meteo = json.load(f)
        if not isinstance(meteo, dict):
            meteo = {"statut_magnetosphere": "Indisponible"}
    except Exception:
        meteo = {"statut_magnetosphere": "Indisponible"}
    meteo_s = json.dumps(meteo, ensure_ascii=False)
    if len(meteo_s) > 4000:
        meteo_s = meteo_s[:4000] + "…"
    tonight = get_tonight_objects()
    tonight_s = json.dumps(tonight, ensure_ascii=False)
    if len(tonight_s) > 6000:
        tonight_s = tonight_s[:6000] + "…"
    return moon_s, meteo_s, tonight_s


def oracle_build_messages(historique, user_message, ville):
    """Construit la liste de messages Claude depuis l'historique + message courant."""
    msgs = []
    if not isinstance(historique, list):
        historique = []
    for h in historique[-10:]:
        if not isinstance(h, dict):
            continue
        role = (h.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        c = (h.get("content") or "").strip()
        if not c:
            continue
        if len(c) > 8000:
            c = c[:8000] + "…"
        msgs.append({"role": role, "content": c})
    extra = (user_message or "").strip()
    v = (ville or "").strip()
    if v:
        extra = f"[Lieu indiqué pour le ciel : {v}]\n\n{extra}"
    msgs.append({"role": "user", "content": extra})
    return msgs


def call_claude_oracle_messages(system, messages):
    """Claude avec prompt système et historique (sans préfixe AEGIS). Returns (text, err)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None, "Claude API key not configured"
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1500,
        "system": system,
        "messages": messages,
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=90)
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


def oracle_claude_stream(system, messages):
    """Yield (chunk, None) ou (None, err) pour flux SSE Claude."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        yield None, "Claude API key not configured"
        return
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1500,
        "system": system,
        "messages": messages,
        "stream": True,
    }
    try:
        with requests.post(url, headers=headers, json=body, stream=True, timeout=120) as r:
            if r.status_code != 200:
                try:
                    data = r.json()
                    err = data.get("error", {})
                    msg = (
                        err.get("message", r.text[:400])
                        if isinstance(err, dict)
                        else (r.text[:400])
                    )
                except Exception:
                    msg = r.text[:400] if r.text else f"HTTP {r.status_code}"
                yield None, msg
                return
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    ev = json.loads(payload)
                except ValueError:
                    continue
                et = ev.get("type")
                if et == "error":
                    err = ev.get("error")
                    msg = (
                        err.get("message", str(err))
                        if isinstance(err, dict)
                        else str(err)
                    )
                    yield None, msg
                    return
                if et == "content_block_delta":
                    delta = ev.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        t = delta.get("text", "")
                        if t:
                            yield t, None
    except requests.RequestException as e:
        yield None, str(e)


# ── Compat aliases (préfixés _ comme dans station_web) ─────────────────
_oracle_cosmique_live_strings = oracle_cosmique_live_strings
_oracle_build_messages = oracle_build_messages
_call_claude_oracle_messages = call_claude_oracle_messages
_oracle_claude_stream = oracle_claude_stream
