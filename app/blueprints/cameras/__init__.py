"""Blueprint Cameras — sky-camera, observatory status, skyview, telescope live img.

PASS 6 (2026-05-03) — Création :
  /sky-camera, /api/sky-camera/analyze,
  /observatory/status, /api/observatory/status,
  /api/skyview/{targets,fetch,multiwave/<id>,list},
  /telescope_live/<path:filename>, /visiteurs-live, /api/audio-proxy.

Différé : /api/sky-camera/simulate (deps _curl_get → PASS 13),
  /api/microobservatory/{images,preview} (deps lourdes → PASS 13).
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re

from flask import (
    Blueprint, render_template, request, jsonify, send_file, abort,
    Response, stream_with_context,
)
from werkzeug.utils import secure_filename

from app.config import STATION

log = logging.getLogger(__name__)

bp = Blueprint("cameras", __name__)


# ── Sky Camera page (Domaine E) ────────────────────────────────────────
@bp.route("/sky-camera")
def sky_camera():
    """Live Sky Camera — webcam + détection étoiles + Claude Vision."""
    return render_template("sky_camera.html")


@bp.route("/api/sky-camera/analyze", methods=["POST"])
def api_sky_camera_analyze():
    """Analyse d'image ciel nocturne via Claude Vision."""
    try:
        import requests
        from datetime import datetime, timezone

        data = request.get_json(force=True) or {}
        image_b64 = data.get("image_base64", "")
        datetime_str = data.get(
            "datetime",
            datetime.now(timezone.utc).strftime("%d/%m/%Y à %Hh%M"),
        )
        stars_detected = int(data.get("stars_detected", 0))
        sim_mode = bool(data.get("sim_mode", False))

        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            return jsonify({
                "ok": False,
                "error": "Clé API Anthropic non configurée",
                "analyse": "Clé API manquante.",
            }), 500

        mode_note = " (image de simulation)" if sim_mode else ""
        system_prompt = (
            "Tu es ORBITAL-CHOHRA, expert en astronomie et astrophysique. "
            "Tu analyses des images du ciel nocturne avec précision et poésie. "
            "Réponds toujours en français."
        )
        user_content = [
            {
                "type": "text",
                "text": (
                    f"Analyse cette image du ciel nocturne{mode_note} capturée le {datetime_str}. "
                    f"Mon algorithme de détection a identifié environ {stars_detected} points lumineux.\n\n"
                    "Identifie et liste :\n"
                    "1. Les étoiles visibles et leurs noms probables\n"
                    "2. Les constellations présentes ou suggérées\n"
                    "3. Les planètes si visibles\n"
                    "4. La magnitude approximative des objets les plus brillants\n"
                    "5. Un fait cosmique poétique sur l'objet le plus remarquable\n\n"
                    "Réponds de façon structurée mais avec un ton poétique et précis. "
                    "À la fin, fournis sur une ligne séparée au format JSON compact : "
                    '{"stars":N,"magnitude":"X.X","constellation":"Nom","planets":"Nom ou Aucune"}'
                ),
            }
        ]
        if image_b64:
            user_content.insert(0, {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64,
                },
            })

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": "claude-opus-4-5",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        }
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=body, timeout=60,
        )
        rdata = r.json()
        if r.status_code != 200:
            err = (rdata.get("error") or {}).get("message", r.text)[:300]
            return jsonify({
                "ok": False,
                "error": err,
                "analyse": f"Erreur API : {err}",
            }), 502

        text = rdata["content"][0]["text"].strip()

        stars_n, magnitude, constellation, planets = stars_detected, "—", "—", "—"
        m = re.search(r'\{[^{}]*"stars"[^{}]*\}', text)
        if m:
            try:
                meta = json.loads(m.group())
                stars_n = meta.get("stars", stars_n)
                magnitude = str(meta.get("magnitude", "—"))
                constellation = str(meta.get("constellation", "—"))
                planets = str(meta.get("planets", "—"))
                text = text[: m.start()].strip()
            except Exception:
                pass

        return jsonify({
            "ok": True,
            "analyse": text,
            "stars_count": stars_n,
            "magnitude": magnitude,
            "constellation": constellation,
            "planets": planets,
        })
    except Exception as e:
        log.warning("api_sky_camera_analyze: %s", e)
        return jsonify({
            "ok": False,
            "error": str(e),
            "analyse": f"Erreur serveur : {e}",
        }), 500


# ── Observatory status (Domaine K — camera control) ───────────────────
@bp.route("/api/observatory/status")
def api_observatory_status():
    """Read-only observatory connector status (JSON)."""
    try:
        from modules.observatory.real_telescope_connector import get_observatory_status
        return jsonify(get_observatory_status())
    except Exception as e:
        log.warning("api/observatory/status: %s", e)
        return jsonify({"providers": [], "summary": "Observatory status unavailable."})


@bp.route("/observatory/status")
def observatory_status_page():
    """Read-only HTML view of observatory connector status."""
    try:
        from modules.observatory.real_telescope_connector import get_observatory_status
        data = get_observatory_status()
        return render_template("observatory_status.html", **data)
    except Exception as e:
        log.warning("observatory/status: %s", e)
        return render_template(
            "observatory_status.html",
            providers=[], summary="Observatory status unavailable.",
        )


# ── NASA SkyView (Domaine F — galerie images) ─────────────────────────
try:
    from skyview_module import (
        fetch_skyview_image, fetch_multiple_surveys,
        TARGETS as SKYVIEW_TARGETS, SURVEYS as SKYVIEW_SURVEYS,
    )
except ImportError:
    SKYVIEW_TARGETS = {}
    SKYVIEW_SURVEYS = {}

    def fetch_skyview_image(*a, **k):  # type: ignore[no-redef]
        return {"ok": False, "error": "skyview_module non disponible"}

    def fetch_multiple_surveys(*a, **k):  # type: ignore[no-redef]
        return []


@bp.route("/api/skyview/targets")
def skyview_targets():
    return jsonify({
        "targets": SKYVIEW_TARGETS,
        "surveys": SKYVIEW_SURVEYS,
        "total": len(SKYVIEW_TARGETS),
    })


@bp.route("/api/skyview/fetch", methods=["POST"])
def skyview_fetch():
    data = request.json or {}
    result = fetch_skyview_image(
        target_id=data.get("target", "M42"),
        survey=data.get("survey", "DSS2 Red"),
        size_deg=float(data.get("size", 0.5)),
        pixels=int(data.get("pixels", 512)),
    )
    return jsonify(result)


@bp.route("/api/skyview/multiwave/<target_id>")
def skyview_multiwave(target_id):
    results = fetch_multiple_surveys(target_id)
    return jsonify({"target": target_id, "images": results})


@bp.route("/api/skyview/list")
def skyview_list():
    files = glob.glob(f"{STATION}/static/img/skyview/*.gif")
    files.sort(key=os.path.getmtime, reverse=True)
    return jsonify({"images": [os.path.basename(f) for f in files[:20]]})


# ── Telescope live image (Domaine F) ──────────────────────────────────
@bp.route("/telescope_live/<path:filename>")
def serve_telescope_live_img(filename):
    """Sert les JPG nightly convertis depuis FITS Harvard."""
    safe = secure_filename(filename)
    path = os.path.join(STATION, "telescope_live", safe)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype="image/jpeg")


# ── Visiteurs live + Audio proxy (Domaine E) ──────────────────────────
@bp.route("/visiteurs-live")
def visiteurs_live_page():
    return render_template("visiteurs_live.html")


_ORBITAL_AUDIO_HOSTS = frozenset({"space.physics.uiowa.edu"})
_ORBITAL_AUDIO_EXT = frozenset({".mp3", ".mp4", ".webm", ".ogg", ".wav"})


@bp.route("/api/audio-proxy")
def api_audio_proxy():
    """Stream audio depuis URL en liste blanche (Iowa / plasma Voyager)."""
    import requests
    from urllib.parse import urlparse, unquote

    raw = (request.args.get("url") or "").strip()
    if not raw:
        abort(400)
    try:
        url = unquote(raw)
    except Exception:
        abort(400)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        abort(400)
    if parsed.hostname.lower() not in _ORBITAL_AUDIO_HOSTS:
        abort(403)
    path_lower = (parsed.path or "").lower()
    if ".." in parsed.path or not any(path_lower.endswith(ext) for ext in _ORBITAL_AUDIO_EXT):
        abort(400)

    ua = "ASTRO-SCAN/1.0 ORBITAL-CHOHRA (orbital-chohra@gmail.com)"
    try:
        up_headers = {"User-Agent": ua}
        rng = request.headers.get("Range")
        if rng:
            up_headers["Range"] = rng
        up = requests.get(url, headers=up_headers, stream=True, timeout=120)
        if up.status_code not in (200, 206):
            log.warning("audio-proxy upstream %s -> HTTP %s", url[:80], up.status_code)
            abort(502)
        skip = {"connection", "transfer-encoding", "content-encoding", "server"}
        out_headers = {
            k: v for k, v in up.headers.items() if k.lower() not in skip
        }
        out_headers.setdefault("Accept-Ranges", "bytes")
        out_headers.setdefault("Cache-Control", "public, max-age=86400")

        def gen():
            try:
                for chunk in up.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                up.close()

        return Response(
            stream_with_context(gen()),
            status=up.status_code, headers=out_headers,
        )
    except Exception as e:
        log.warning("audio-proxy: %s", e)
        abort(502)
