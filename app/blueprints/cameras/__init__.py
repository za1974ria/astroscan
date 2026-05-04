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
from app.utils.llm_errors import friendly_message

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
            raw = (rdata.get("error") or {}).get("message", r.text)[:300]
            log.warning("sky-camera/analyze provider err: %s", raw)
            safe = friendly_message(raw)
            return jsonify({
                "ok": False,
                "error": safe,
                "analyse": safe,
            }), 503

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
        safe = friendly_message(e)
        return jsonify({
            "ok": False,
            "error": safe,
            "analyse": safe,
        }), 503


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


# ── PASS 15 — Sky Camera simulate (différé PASS 6 levé) ───────────────
@bp.route("/api/sky-camera/simulate")
def api_sky_camera_simulate():
    """Retourne une image de ciel nocturne pour le mode simulation.
    Priorité : APOD NASA → image statique fallback.
    """
    from app.utils.cache import cache_get
    from app.services.http_client import _curl_get
    try:
        nasa_key = (os.environ.get("NASA_API_KEY") or "DEMO_KEY").strip()
        apod = cache_get("apod_hd", 3600)
        if not apod:
            raw = _curl_get(
                f"https://api.nasa.gov/planetary/apod?api_key={nasa_key}",
                timeout=12,
            )
            if raw:
                apod_data = json.loads(raw)
                if apod_data.get("media_type") == "image":
                    url = apod_data.get("hdurl") or apod_data.get("url", "")
                    return jsonify({
                        "ok": True, "url": url,
                        "title": apod_data.get("title", ""),
                        "source": "NASA APOD",
                    })
        if apod and isinstance(apod, dict):
            inner = apod.get("apod") or apod
            url = inner.get("hdurl") or inner.get("url", "")
            if url:
                return jsonify({
                    "ok": True, "url": url,
                    "source": "NASA APOD (cache)",
                })
    except Exception as e:
        log.warning("sky_simulate APOD: %s", e)
    return jsonify({
        "ok": True,
        "url": "https://apod.nasa.gov/apod/image/2401/OrionMolCloud_Addis_960.jpg",
        "title": "Orion Molecular Cloud",
        "source": "NASA APOD fallback",
    })


# ── PASS 15 — MicroObservatory images + preview FITS ──────────────────
@bp.route("/api/microobservatory/images")
def api_microobservatory_images():
    """Recent Harvard MicroObservatory images (cached 3600s)."""
    from app.utils.cache import get_cached
    from app.services.microobservatory import fetch_microobservatory_images
    try:
        data = get_cached("microobservatory_images", 3600, fetch_microobservatory_images)
        return jsonify(data if isinstance(data, dict) else {"ok": False, "images": []})
    except Exception as e:
        return jsonify({"ok": False, "images": [], "error": str(e)})


@bp.route("/api/microobservatory/preview/<nom_fichier>")
def api_microobservatory_preview(nom_fichier):
    """Download FITS from Harvard MicroObservatory, convert to JPG and return it."""
    try:
        safe_name = secure_filename(nom_fichier or "")
        if not safe_name:
            return jsonify({"ok": False, "error": "invalid filename"}), 400

        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in (".fits", ".fit"):
            return jsonify({"ok": False, "error": "preview supports FITS only"}), 400

        preview_dir = os.path.join(STATION, "data", "microobservatory_previews")
        fits_dir = os.path.join(preview_dir, "fits")
        jpg_dir = os.path.join(preview_dir, "jpg")
        os.makedirs(fits_dir, exist_ok=True)
        os.makedirs(jpg_dir, exist_ok=True)

        fits_path = os.path.join(fits_dir, safe_name)
        jpg_name = os.path.splitext(safe_name)[0] + ".jpg"
        jpg_path = os.path.join(jpg_dir, jpg_name)

        # Serve cached JPG when possible.
        if os.path.isfile(jpg_path) and os.path.getsize(jpg_path) > 0:
            return send_file(jpg_path, mimetype="image/jpeg")

        source_url = "https://mo-www.cfa.harvard.edu/ImageDirectory/" + safe_name

        # Download FITS.
        import urllib.request
        req = urllib.request.Request(source_url, headers={"User-Agent": "AstroScan/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if not data:
            return jsonify({"ok": False, "error": "empty FITS download"}), 502
        with open(fits_path, "wb") as f:
            f.write(data)

        # Convert FITS → JPG.
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from astropy.io import fits
        import numpy as np

        arr = fits.getdata(fits_path)
        if arr is None:
            return jsonify({"ok": False, "error": "invalid FITS data"}), 502

        while hasattr(arr, "ndim") and arr.ndim > 2:
            arr = arr[0]
        arr = np.asarray(arr, dtype=float)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        if arr.size == 0:
            return jsonify({"ok": False, "error": "empty FITS array"}), 502

        vmin = np.percentile(arr, 2)
        vmax = np.percentile(arr, 98)
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
            vmin = float(np.min(arr))
            vmax = float(np.max(arr)) if float(np.max(arr)) > float(np.min(arr)) else float(np.min(arr)) + 1.0

        plt.figure(figsize=(8, 8), dpi=120)
        plt.imshow(arr, cmap="gray", origin="lower", vmin=vmin, vmax=vmax)
        plt.axis("off")
        plt.tight_layout(pad=0)
        plt.savefig(jpg_path, format="jpg", bbox_inches="tight", pad_inches=0)
        plt.close()

        if not os.path.isfile(jpg_path) or os.path.getsize(jpg_path) == 0:
            return jsonify({"ok": False, "error": "jpg conversion failed"}), 502
        return send_file(jpg_path, mimetype="image/jpeg")
    except Exception as e:
        log.warning("microobservatory/preview: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── PASS 15 — Proxy-cam World Live (5 caméras + EPIC NASA dynamique) ──
import threading as _threading
import time as _time
import requests as _requests

_CAM_SOURCES = {
    "matterhorn": [
        "https://zermatt.roundshot.com/zermatt.jpg",
        "https://www.zermatt.ch/var/zermatt/storage/images/media/webcam/matterhorn.jpg",
    ],
    "aurora": [
        "https://nordlysobservatoriet.no/allsky/latest_small.jpg",
        "https://arcticspace.no/allsky_images/latest.jpg",
    ],
    "canyon": [
        "https://www.nps.gov/grca/planyourvisit/webcam-images/south-rim.jpg",
        "https://grandcanyonsunrise.org/livecam/latest.jpg",
    ],
    "fuji": [
        "https://livecam.fujigoko.tv/cameras/fujigoko6.jpg",
        "https://n-img00.tsite.jp/webcam/fujigoko/live.jpg",
    ],
    "iss": [
        "__epic__",
        "https://eol.jsc.nasa.gov/DatabaseImages/ESC/small/ISS070/ISS070-E-75001.JPG",
    ],
}
_CAM_ALLOWED = frozenset(_CAM_SOURCES)
_CAM_IMG_CACHE: dict = {}
_CAM_CACHE_TTL = 30
_CAM_FETCH_LOCKS = {city: _threading.Lock() for city in _CAM_SOURCES}
_CAM_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_CAM_FETCH_HEADERS = {
    "User-Agent": _CAM_UA,
    "Accept": "image/jpeg,image/*,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
_EPIC_URL_CACHE = {"url": None, "ts": 0.0}
_EPIC_URL_TTL = 3600


def _get_latest_epic_url():
    """Retourne l'URL JPEG de la dernière image naturelle DSCOVR/EPIC NASA."""
    now = _time.monotonic()
    if _EPIC_URL_CACHE["url"] and (now - _EPIC_URL_CACHE["ts"]) < _EPIC_URL_TTL:
        return _EPIC_URL_CACHE["url"]
    r = _requests.get(
        "https://epic.gsfc.nasa.gov/api/natural",
        timeout=(3, 8), headers={"User-Agent": _CAM_UA},
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        raise ValueError("EPIC API: aucune image disponible")
    img = data[0]
    date = img["date"][:10].replace("-", "/")
    url = f'https://epic.gsfc.nasa.gov/archive/natural/{date}/jpg/{img["image"]}.jpg'
    _EPIC_URL_CACHE["url"] = url
    _EPIC_URL_CACHE["ts"] = now
    log.info("[CAM EPIC] URL résolue : %s", url)
    return url


def _cam_resolve(raw_url):
    if raw_url == "__epic__":
        return _get_latest_epic_url()
    return raw_url


def _cam_fetch_url(url):
    kw = dict(
        timeout=(5, 12), headers=_CAM_FETCH_HEADERS,
        allow_redirects=True, stream=False,
    )
    try:
        r = _requests.get(url, verify=True, **kw)
    except _requests.exceptions.SSLError:
        r = _requests.get(url, verify=False, **kw)
    r.raise_for_status()
    data = r.content
    if not data:
        raise ValueError("réponse vide")
    ct = r.headers.get("content-type", "")
    if "image" not in ct and data[:3] != b"\xff\xd8\xff":
        raise ValueError(f"pas une image : content-type={ct!r}")
    return data


def _cam_response(data):
    resp = Response(data, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@bp.route("/proxy-cam/<city>.jpg")
def proxy_cam(city):
    if city not in _CAM_ALLOWED:
        abort(404)
    cached = _CAM_IMG_CACHE.get(city)
    now = _time.monotonic()
    if cached and (now - cached["ts"]) < _CAM_CACHE_TTL:
        return _cam_response(cached["data"])

    lock = _CAM_FETCH_LOCKS[city]
    if not lock.acquire(blocking=False):
        log.debug("[CAM SKIP] %s — fetch en cours, cache servi", city)
        if cached:
            return _cam_response(cached["data"])
        return Response("offline", status=503, mimetype="text/plain")

    try:
        cached = _CAM_IMG_CACHE.get(city)
        if cached and (_time.monotonic() - cached["ts"]) < _CAM_CACHE_TTL:
            return _cam_response(cached["data"])

        for raw_url in _CAM_SOURCES[city]:
            try:
                url = _cam_resolve(raw_url)
                data = _cam_fetch_url(url)
                _CAM_IMG_CACHE[city] = {"ts": _time.monotonic(), "data": data}
                log.info("[CAM OK] %s ← %s (%d B)", city, url, len(data))
                return _cam_response(data)
            except _requests.HTTPError as exc:
                st = exc.response.status_code if exc.response is not None else "?"
                log.warning("[CAM FAIL] %s ← %s  HTTP %s", city, raw_url, st)
            except _requests.RequestException as exc:
                log.warning("[CAM FAIL] %s ← %s  %s", city, raw_url, exc)
            except Exception as exc:
                log.warning("[CAM FAIL] %s ← %s  %s", city, raw_url, exc)

        if cached:
            age = _time.monotonic() - cached["ts"]
            log.info("[CAM CACHE SERVED] %s (périmé, age=%.0fs)", city, age)
            return _cam_response(cached["data"])

        log.warning("[CAM OFFLINE] %s — toutes sources échouées, aucun cache", city)
        return Response("offline", status=503, mimetype="text/plain")
    finally:
        lock.release()
