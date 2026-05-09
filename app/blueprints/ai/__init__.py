"""Blueprint AI — AEGIS chat, traduction, explications, JWST descriptions, telescope live.

PASS 10 (2026-05-03) — Création :
  /api/chat, /api/aegis/{chat,status,groq-ping,claude-test},
  /api/translate, /api/astro/explain,
  /api/telescope/live (différé PASS 9 levé),
  /api/jwst/{images,refresh} (différé PASS 8/9 levés),
  /guide-stellaire (page), /oracle-cosmique (page),
  /api/guide-geocode.

Différé : /api/oracle-cosmique POST (helpers _oracle_cosmique_live_strings,
  _oracle_build_messages, _oracle_claude_stream, _call_claude_oracle_messages
  ~200 lignes), /api/guide-stellaire POST (helpers weather/sunrise/planets
  ~80 lignes), /api/oracle alias (dépend de oracle-cosmique).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone

import requests

from flask import Blueprint, render_template, request, jsonify

from app.config import STATION
from app.services.ai_translate import (
    _call_claude, _call_groq, _call_ai, _enforce_french,
    _gemini_translate, _translate_to_french,
    get_ai_counters,
)
from app.services.observatory_feeds import (
    fetch_jwst_live_images, jwst_cache_file_path,
)
from app.services.http_client import _curl_get
from app.utils.llm_errors import friendly_message, llm_error_response

log = logging.getLogger(__name__)

bp = Blueprint("ai", __name__)


# Cache local AEGIS chat (5 min)
_chat_cache: dict = {}


# ── Pages (Domaine U) ──────────────────────────────────────────────────
@bp.route("/guide-stellaire")
def guide_stellaire_page():
    return render_template("guide_stellaire.html")


@bp.route("/oracle-cosmique")
def oracle_cosmique_page():
    return render_template("oracle_cosmique.html")


# ── AEGIS chat (Domaine N) ─────────────────────────────────────────────
@bp.route("/api/chat", methods=["POST"])
def api_chat():
    """Chat libre AEGIS — orchestrateur Claude/Groq + cache 5 min."""
    ua = (request.headers.get("User-Agent") or "").lower()
    bot_tokens = (
        "bot", "crawler", "spider", "curl", "wget", "python-requests",
        "go-http-client", "postman", "scanner", "headless", "puppeteer", "scrapy",
    )
    if (not ua) or any(tok in ua for tok in bot_tokens):
        return jsonify({
            "ok": False,
            "error": "AEGIS: acces automatise bloque",
            "status": "aegis_blocked",
            "tokens_consumed": 0,
        }), 403
    data = request.get_json(silent=True) or {}
    msg = data.get("message", "").strip()
    extra_ctx = (data.get("context") or "").strip()

    if not msg:
        return jsonify({"ok": False, "error": "message vide"})

    msg_hash = hashlib.md5(msg.lower().strip().encode()).hexdigest()
    if msg_hash in _chat_cache:
        ts, cached_resp = _chat_cache[msg_hash]
        if time.time() - ts < 300:
            return jsonify({"ok": True, "response": cached_resp, "cached": True})

    # Contexte station (DB)
    ctx = ""
    try:
        from app.utils.db import get_db
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anom = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE anomalie=1"
        ).fetchone()[0]
        last = conn.execute(
            "SELECT COALESCE(title, objets_detectes, '') as t, "
            "COALESCE(analyse_gemini,'') as r "
            "FROM observations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        ctx = (
            f"Station ORBITAL-CHOHRA à Tlemcen, Algérie (~34,9°N, 1,3°E). "
            f"Directeur : Zakaria Chohra. "
            f"Base de données : {total} observations, {anom} anomalies détectées. "
            f"Dernière observation : {last['t'] if last else 'inconnue'}. "
            f"Analyse AEGIS : {(last['r'] if last else '')[:200]}. "
            f"Sources actives : NASA APOD, ESA Hubble, SIMBAD, Chandra, IRSA/WISE, MPC. "
            f"Pipeline SDR NOAA actif. Répondre en français."
        )
    except Exception as e:
        log.warning("chat ctx: %s", e)
        ctx = "Station ORBITAL-CHOHRA — Tlemcen, Algérie."

    if extra_ctx:
        ctx = ctx + " " + extra_ctx

    prompt = (
        f"Tu es AEGIS — IA de la station astronomique ORBITAL-CHOHRA.\n"
        f"Directeur : Zakaria Chohra, Tlemcen, Algérie.\n"
        f"Contexte : {ctx}\n\n"
        "RÈGLES STRICTES :\n"
        "1. Réponds EXACTEMENT à la question posée — ni plus ni moins. Pas de digression.\n"
        "2. Si la question est factuelle (quoi, combien, où, quand) → une réponse courte et précise.\n"
        "3. Si la question est astronomique → ton savoir scientifique, concis et exact.\n"
        "4. Si la question concerne la station ou l'écran → utilise le contexte ci-dessus.\n"
        "5. Jamais de demande de précision. Toujours en français. Pas d'introduction ni de liste inutile.\n\n"
        f"Question : {msg}"
    )

    reply, err, model_used = _call_ai(prompt)
    if err:
        log.error("chat: %s", err)
        return jsonify({"ok": False, "response": err})

    _chat_cache[msg_hash] = (time.time(), reply)
    old_keys = [k for k, v in _chat_cache.items() if time.time() - v[0] > 300]
    for k in old_keys:
        del _chat_cache[k]

    return jsonify({"ok": True, "response": reply, "model": model_used})


@bp.route("/api/aegis/chat", methods=["POST"])
def api_aegis_chat():
    """AEGIS chatbot — Claude haiku avec historique multi-tours et contexte live."""
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not msg:
        return jsonify({"ok": False, "error": "message vide"})

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        prompt_fallback = (
            "Tu es AEGIS, assistant astronomique expert de l'Observatoire ORBITAL-CHOHRA "
            "dirigé par Zakaria Chohra à Tlemcen, Algérie. Réponds UNIQUEMENT en français, "
            "de façon experte et passionnée.\n\nQuestion : " + msg
        )
        reply, err = _call_groq(prompt_fallback)
        if reply:
            return jsonify({"ok": True, "response": _enforce_french(reply), "model": "groq"})
        if err:
            log.warning("aegis/chat groq fallback err: %s", str(err)[:300])
        return jsonify({"ok": False, "error": friendly_message(err)})

    # Contexte live (DB + station)
    live_ctx = ""
    try:
        from app.utils.db import get_db
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anom = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE anomalie=1"
        ).fetchone()[0]
        last = conn.execute(
            "SELECT COALESCE(title,'') as t, COALESCE(analyse_gemini,'') as r "
            "FROM observations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        live_ctx = (
            f"Données live station : {total} observations archivées, {anom} anomalies. "
            f"Dernière obs : {last['t'] if last else '?'}. "
        )
    except Exception:
        live_ctx = ""

    try:
        sw_path = os.path.join(STATION, "static", "space_weather.json")
        if os.path.isfile(sw_path):
            with open(sw_path) as f:
                sw = json.load(f)
            live_ctx += (
                f"Météo spatiale : Kp={sw.get('kp_index','?')}, "
                f"{sw.get('statut_magnetosphere','?')}. "
            )
    except Exception:
        pass

    system_prompt = (
        "Tu es AEGIS, assistant astronomique expert de l'Observatoire ORBITAL-CHOHRA "
        "dirigé par Zakaria Chohra à Tlemcen, Algérie (34.87°N, 1.32°E). "
        "Tu réponds UNIQUEMENT en français, de façon experte et passionnée. "
        "Tu connais parfaitement l'astronomie, l'astrophysique, l'ISS, les nébuleuses, "
        "les exoplanètes, la météo spatiale, les missions spatiales. "
        "Tu intègres les données live du site quand pertinent. "
        "Réponds de façon concise, précise et engageante. "
        "Pas de préambule inutile. " + live_ctx
    )

    messages = []
    for h in history[-6:]:
        role = h.get("role", "")
        content = h.get("content", "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": msg})

    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": messages,
    }
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body, timeout=30,
        )
        d = r.json()
        if r.status_code != 200:
            err_msg = (d.get("error") or {}).get("message", f"HTTP {r.status_code}")
            log.warning("aegis/chat Claude error raw=%s", str(err_msg)[:300])
            reply_g, err_g = _call_groq(system_prompt + "\n\nQuestion : " + msg)
            if reply_g:
                return jsonify({"ok": True, "response": _enforce_french(reply_g), "model": "groq"})
            return jsonify({"ok": False, "error": friendly_message(err_msg)})
        reply_text = d["content"][0]["text"].strip()
        return jsonify({"ok": True, "response": reply_text, "model": "claude"})
    except Exception as e:
        log.warning("aegis/chat exception: %s", e)
        reply_g, _ = _call_groq(system_prompt + "\n\nQuestion : " + msg)
        if reply_g:
            return jsonify({"ok": True, "response": _enforce_french(reply_g), "model": "groq"})
        return jsonify({"ok": False, "error": friendly_message(e)})


@bp.route("/api/aegis/status")
def api_aegis_status():
    """Statut AEGIS + métriques légères (lecture seule, sans appel API externe)."""
    try:
        groq_configured = bool(os.environ.get("GROQ_API_KEY", "").strip())
        ai_counters = get_ai_counters()
        return jsonify({
            "ok": True,
            "gemini_configured": False,
            "grok_configured": False,
            "grok_ok": False,
            "grok_error": None,
            "groq_configured": groq_configured,
            "groq_ok": groq_configured,
            "groq_error": None,
            "claude_calls": ai_counters["claude_calls"],
            "claude_limit": ai_counters["claude_limit"],
            "groq_calls": ai_counters["groq_calls"],
            "collector_last_run": 0,
            "timestamp": time.time(),
        })
    except Exception as e:
        log.exception("aegis/status")
        ai_counters = get_ai_counters()
        return jsonify({
            "ok": False,
            "gemini_configured": False,
            "grok_configured": False,
            "grok_ok": False,
            "grok_error": None,
            "groq_configured": bool(os.environ.get("GROQ_API_KEY", "").strip()),
            "groq_ok": False,
            "groq_error": str(e),
            "claude_calls": ai_counters["claude_calls"],
            "claude_limit": ai_counters["claude_limit"],
            "groq_calls": ai_counters["groq_calls"],
            "collector_last_run": 0,
            "timestamp": time.time(),
        })


@bp.route("/api/aegis/groq-ping")
def api_aegis_groq_ping():
    """Une requête Groq réelle (diagnostic) — à n'appeler que ponctuellement."""
    groq_configured = bool(os.environ.get("GROQ_API_KEY", "").strip())
    if not groq_configured:
        return jsonify({
            "ok": False,
            "groq_configured": False,
            "groq_ok": False,
            "groq_error": "GROQ_API_KEY non configurée",
            "timestamp": time.time(),
        })
    try:
        reply, err = _call_groq("Réponds uniquement par: OK")
        groq_ok = reply is not None and ("OK" in (reply or ""))
        return jsonify({
            "ok": True,
            "groq_configured": True,
            "groq_ok": groq_ok,
            "groq_error": err,
            "timestamp": time.time(),
        })
    except Exception as e:
        log.exception("aegis/groq-ping")
        return jsonify({
            "ok": False,
            "groq_configured": True,
            "groq_ok": False,
            "groq_error": str(e),
            "timestamp": time.time(),
        })


@bp.route("/api/aegis/claude-test")
def api_aegis_claude_test():
    """Diagnostic Claude (Anthropic) — n'affecte pas les autres routes."""
    configured = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    reply, err = _call_claude("Reply only with OK")
    if err:
        log.warning("aegis/claude-test provider err: %s", str(err)[:300])
    return jsonify({
        "claude_configured": configured,
        "claude_ok": reply is not None,
        "error": friendly_message(err) if err else None,
    })


# ── Translation (Domaine N) ────────────────────────────────────────────
@bp.route("/api/translate", methods=["POST"])
def api_translate():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    translated = _gemini_translate(text)
    return jsonify({"ok": True, "translated": translated})


@bp.route("/api/astro/explain", methods=["POST"])
def api_astro_explain():
    """Traduction EN→FR d'un texte (ex. analyse Gemini)."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "translated": ""})
    translated = _translate_to_french(text, max_chars=2000)
    return jsonify({"ok": True, "translated": translated})


# ── Guide geocode (light helper) ──────────────────────────────────────
@bp.route("/api/guide-geocode", methods=["GET", "POST"])
def api_guide_geocode():
    from modules.guide_stellaire import geocode_search
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        q = (body.get("q") or body.get("query") or "").strip()
    else:
        q = (request.args.get("q") or "").strip()
    return jsonify({"ok": True, "results": geocode_search(q, limit=8)})


# ── Telescope APOD live (différé PASS 9 levé) ─────────────────────────
@bp.route("/api/telescope/live")
def api_telescope_live():
    """APOD du jour NASA : titre + description traduits FR via Gemini, analyse Claude."""
    try:
        meta_path = os.path.join(STATION, "telescope_live", "apod_meta.json")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("date") == today or meta.get("fetched_at", "").startswith(today):
                    analyse_claude = meta.get("analyse_claude", "")
                    if not analyse_claude:
                        title_en = meta.get("title_original") or meta.get("title", "")
                        expl_en = meta.get("explanation_original") or meta.get("explanation", "")
                        if title_en and expl_en:
                            apod_date = meta.get("date") or "aujourd'hui"
                            prompt_analyse = (
                                f"Image astronomique NASA APOD du {apod_date}.\n"
                                f"Titre : {title_en}\n"
                                f"Description : {expl_en[:800]}\n\n"
                                "Rédige en 3 à 4 phrases une analyse scientifique approfondie de cette image : "
                                "type d'objet céleste, phénomènes physiques visibles, intérêt astronomique, "
                                "contexte dans l'univers observable. Style expert, en français."
                            )
                            analyse_claude, err_c = _call_claude(prompt_analyse)
                            if analyse_claude:
                                log.info("api/telescope/live: analyse Claude générée (%d car)", len(analyse_claude))
                                try:
                                    meta["analyse_claude"] = analyse_claude
                                    with open(meta_path, "w", encoding="utf-8") as fout:
                                        json.dump(meta, fout, ensure_ascii=False, indent=2)
                                except Exception:
                                    pass
                            else:
                                log.warning("api/telescope/live: Claude analyse: %s", err_c)
                    return jsonify({
                        "title": meta.get("title", ""),
                        "title_original": meta.get("title_original", ""),
                        "date": meta.get("date", ""),
                        "explanation": meta.get("explanation", ""),
                        "url": meta.get("url", ""),
                        "source": "NASA APOD",
                        "media_type": "image",
                        "translated": meta.get("translated", False),
                        "analyse_claude": analyse_claude or "",
                        "from_cache": True,
                    })
            except Exception:
                pass

        # Fallback : fetch NASA + traduction Gemini en ligne
        nasa_key = (os.environ.get("NASA_API_KEY") or "DEMO_KEY").strip()
        raw = _curl_get(f"https://api.nasa.gov/planetary/apod?api_key={nasa_key}", timeout=14)
        if not raw:
            return jsonify({"error": "Indisponible"}), 503
        data = json.loads(raw)
        title_en = data.get("title", "")
        expl_en = data.get("explanation", "")
        title_fr = _gemini_translate(title_en) if title_en else title_en
        expl_fr = _gemini_translate(expl_en) if expl_en else expl_en
        analyse_claude = ""
        if title_en and expl_en:
            apod_date_live = data.get("date") or "aujourd'hui"
            prompt_analyse = (
                f"Image astronomique NASA APOD du {apod_date_live}.\n"
                f"Titre : {title_en}\n"
                f"Description : {expl_en[:800]}\n\n"
                "Rédige en 3 à 4 phrases une analyse scientifique approfondie de cette image : "
                "type d'objet céleste, phénomènes physiques visibles, intérêt astronomique, "
                "contexte dans l'univers observable. Style expert, en français."
            )
            analyse_claude, _ = _call_claude(prompt_analyse)
        return jsonify({
            "title": title_fr or title_en,
            "title_original": title_en,
            "date": data.get("date", ""),
            "explanation": expl_fr or expl_en,
            "url": data.get("hdurl") or data.get("url", ""),
            "source": "NASA APOD",
            "media_type": data.get("media_type", "image"),
            "translated": bool(expl_fr and expl_fr != expl_en),
            "analyse_claude": analyse_claude or "",
            "from_cache": False,
        })
    except Exception as e:
        log.warning("api/telescope/live: %s", e)
        return jsonify({"error": "Indisponible"}), 503


# ── JWST images (différé PASS 8/9 levé) ───────────────────────────────
@bp.route("/api/jwst/images")
def api_jwst_images():
    """Images JWST — NASA Images API + Claude AI descriptions + fallback statique."""
    try:
        data = fetch_jwst_live_images()
        if not data:
            return jsonify({"error": "no data"}), 502
        return jsonify(data)
    except Exception as e:
        log.warning("jwst/images: %s", e)
        return jsonify({"error": friendly_message(e)}), 503


@bp.route("/api/jwst/refresh", methods=["POST"])
def api_jwst_refresh():
    """Force le rechargement du cache JWST."""
    try:
        cache_file = jwst_cache_file_path()
        if os.path.exists(cache_file):
            os.remove(cache_file)
        data = fetch_jwst_live_images()
        return jsonify({"ok": True, "count": len(data)})
    except Exception as e:
        log.warning("jwst/refresh: %s", e)
        return jsonify({"error": friendly_message(e)}), 503


# ── PASS 17 — Oracle Cosmique POST (différé PASS 10 levé) ────────────
@bp.route("/api/oracle-cosmique", methods=["POST"])
def api_oracle_cosmique():
    """Chat Oracle Cosmique : contexte live (lune, météo spatiale, ce soir) + Claude."""
    from flask import Response, stream_with_context
    from app.services.oracle_engine import (
        ORACLE_COSMIQUE_SYSTEM,
        oracle_cosmique_live_strings,
        oracle_build_messages,
        call_claude_oracle_messages,
        oracle_claude_stream,
    )
    if not request.is_json:
        return jsonify({"ok": False, "error": "Corps JSON requis"}), 400
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "Message vide"}), 400
    ville = (body.get("ville") or "").strip()
    historique = body.get("historique")
    if not isinstance(historique, list):
        historique = []
    want_stream = body.get("stream", True)

    moon_s, meteo_s, tonight_s = oracle_cosmique_live_strings()
    system = (
        ORACLE_COSMIQUE_SYSTEM
        .replace("<<<MOON>>>", moon_s)
        .replace("<<<METEO>>>", meteo_s)
        .replace("<<<TONIGHT>>>", tonight_s)
    )
    msgs = oracle_build_messages(historique, message, ville)

    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return jsonify({
            "ok": False,
            "error": "Oracle momentanément muet (ANTHROPIC_API_KEY non configurée).",
        }), 503

    if want_stream:
        def sse_gen():
            try:
                for chunk, err in oracle_claude_stream(system, msgs):
                    if err:
                        log.warning("oracle-cosmique stream provider err: %s", str(err)[:300])
                        safe = friendly_message(err)
                        yield f"data: {json.dumps({'error': safe}, ensure_ascii=False)}\n\n"
                        return
                    if chunk:
                        yield f"data: {json.dumps({'t': chunk}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                log.warning("oracle-cosmique stream: %s", e)
                yield f"data: {json.dumps({'error': friendly_message(e)}, ensure_ascii=False)}\n\n"

        return Response(
            stream_with_context(sse_gen()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    reply, err = call_claude_oracle_messages(system, msgs)
    if err:
        log.warning("oracle-cosmique provider err: %s", str(err)[:300])
        return llm_error_response(err, provider='Anthropic')
    return jsonify({"ok": True, "response": reply})


@bp.route("/api/oracle", methods=["POST"])
def api_oracle_alias():
    """Alias /api/oracle → /api/oracle-cosmique (POST). Délégation interne."""
    try:
        return api_oracle_cosmique()
    except Exception as e:
        return llm_error_response(e, provider='Anthropic', http_status=500)


# ── PASS 17 — Guide Stellaire POST (différé PASS 10 levé) ────────────
@bp.route("/api/guide-stellaire", methods=["POST"])
def api_guide_stellaire():
    """Génère un guide d'observation orbital pour ville/lat/lon/date."""
    from app.services.guide_engine import build_orbital_guide

    data = request.get_json(silent=True) or {}
    ville = (data.get("ville") or data.get("city") or "").strip() or "Lieu inconnu"
    try:
        lat = float(data.get("latitude", data.get("lat")))
        lon = float(data.get("longitude", data.get("lon")))
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "latitude et longitude numériques requises",
        }), 400
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"ok": False, "error": "coordonnées hors limites"}), 400
    date_iso = (data.get("date") or "").strip()
    if not date_iso:
        date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "error": "date invalide (YYYY-MM-DD)"}), 400

    result = build_orbital_guide(ville, lat, lon, date_iso)
    if not result.get("ok"):
        # Status 502 if context present (Claude error), else 500
        status = 502 if "context" in result else 500
        return jsonify(result), status
    return jsonify(result)
