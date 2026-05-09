"""Blueprint Telescope — flux télescope + mission control + Skyview NASA + Hubble.

PASS 9 (2026-05-03) — Création :
  /api/telescope-hub, /api/telescope/nightly,
  /mission-control, /api/mission-control,
  /telescopes (page),
  /telescope (page Skyview), /api/telescope/{image,catalogue,proxy-image},
  /api/telescope/{stream,status},
  /api/stellarium,
  /api/title, /api/image (avec helpers extraits → telescope_sources.py),
  /api/hubble/images (différé PASS 8 levé).

Différé : /api/telescope/live (deps _gemini_translate + _call_claude → PASS 11),
  /api/telescope/trigger-nightly (helper _telescope_nightly_tlemcen ~100 lignes
  + _mo_* helpers FITS+JPG → futur PASS 15),
  /api/jwst/{images,refresh} (deps _call_claude AI → PASS 11),
  /api/bepi/telemetry (gardé en monolithe, petit).
"""
from __future__ import annotations

import json
import logging
import os
import struct
import time
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

from flask import (
    Blueprint, render_template, request, jsonify, send_file,
    Response, stream_with_context,
)

from app.services.security import require_admin

from app.config import STATION, IMG_PATH, TITLE_F, HUB_F
from app.services.telescope_sources import (
    _IMAGE_CACHE_TTL, _source_path,
    _fetch_apod_live, _fetch_hubble_live, _fetch_apod_archive_live,
    fetch_hubble_images,
)

log = logging.getLogger(__name__)

bp = Blueprint("telescope", __name__)


# ── État cache mémoire (titre/label par source) ───────────────────────
_image_meta: dict = {}  # { source: (title, label) }


# ── Page principale Telescope (Skyview) ───────────────────────────────
try:
    from skyview import (
        OBJETS_TLEMCEN, SURVEYS, get_object_image,
        get_image_url as skyview_get_image_url,
    )
except ImportError:
    OBJETS_TLEMCEN = {}
    SURVEYS = {}

    def get_object_image(*a, **k):  # type: ignore[no-redef]
        return {"ok": False, "error": "skyview module non disponible"}


@bp.route("/telescopes")
def telescopes_page():
    return render_template("telescopes.html")


@bp.route("/telescope")
def telescope():
    return render_template("telescope.html", objets=OBJETS_TLEMCEN, surveys=SURVEYS)


# ── Mission Control (Domaine AO) ───────────────────────────────────────
@bp.route("/mission-control")
def mission_control():
    cesium_token = os.getenv("CESIUM_ION_TOKEN") or os.getenv("CESIUM_TOKEN", "")
    return render_template("mission_control.html", cesium_token=cesium_token)


@bp.route("/api/mission-control")
def api_mission_control():
    try:
        from modules.mission_control import get_global_mission_status
        return jsonify(get_global_mission_status())
    except Exception as e:
        log.warning("api/mission-control: %s", e)
        return jsonify({
            "error": str(e),
            "iss": {}, "mars": {}, "neo": {}, "voyager": {},
        }), 500


# ── Telescope hub + nightly (Domaine H) ───────────────────────────────
@bp.route("/api/telescope-hub")
def api_telescope_hub():
    if Path(HUB_F).exists():
        try:
            age = time.time() - Path(HUB_F).stat().st_mtime
            if age < 3600:
                with open(HUB_F) as f:
                    return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify({
        "ok": True,
        "telescopes": [
            {"name": "NASA SkyView", "status": "online", "latency": 210, "url": "https://skyview.gsfc.nasa.gov"},
            {"name": "SIMBAD/CDS", "status": "online", "latency": 380, "url": "http://simbad.u-strasbg.fr"},
            {"name": "ESA Hubble", "status": "online", "latency": 290, "url": "https://esahubble.org"},
            {"name": "Chandra X-Ray", "status": "online", "latency": 340, "url": "https://cxc.harvard.edu"},
            {"name": "IRSA/WISE", "status": "online", "latency": 260, "url": "https://irsa.ipac.caltech.edu"},
            {"name": "Minor Planet Center", "status": "online", "latency": 180, "url": "https://minorplanetcenter.net"},
        ],
        "online": 6, "total": 6,
    })


@bp.route("/api/telescope/nightly")
def api_telescope_nightly():
    """Images nocturnes Harvard MicroObservatory — sélection Tlemcen."""
    meta_path = os.path.join(STATION, "telescope_live", "nightly_meta.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                data = json.load(f)
            data["ok"] = True
            return jsonify(data)
        except Exception:
            pass
    return jsonify({
        "ok": False, "images": [],
        "message": "Aucune collecte nocturne disponible",
    })


# ── Telescope image API (Skyview) ─────────────────────────────────────
@bp.route("/api/telescope/image")
def api_telescope_image():
    """GET /api/telescope/image?objet=M42&survey=DSS2+Red — URL image NASA SkyView."""
    objet = request.args.get("objet", "M42")
    survey = request.args.get("survey", "DSS2 Red")
    data = get_object_image(objet, survey)
    return jsonify(data)


@bp.route("/api/telescope/catalogue")
def api_telescope_catalogue():
    """Liste tous les objets du catalogue Tlemcen."""
    return jsonify({
        "objets": OBJETS_TLEMCEN,
        "surveys": SURVEYS,
        "source": "NASA SkyView",
        "observatoire": "Tlemcen 34.87°N 1.32°E 816m",
    })


@bp.route("/api/telescope/proxy-image")
def api_telescope_proxy_image():
    """Proxy NASA SkyView — télécharge l'image côté serveur, évite CORS."""
    objet = request.args.get("objet", "M42")
    survey = request.args.get("survey", "DSS2 Red")
    pixels = request.args.get("pixels", "600")
    size = request.args.get("size", "0.5")
    params = urllib.parse.urlencode({
        "Position": objet,
        "Survey": survey,
        "Coordinates": "J2000",
        "Return": "GIF",
        "Size": size,
        "Pixels": pixels,
        "Scaling": "Log",
        "resolver": "SIMBAD-NED",
        "Sampler": "LI",
        "imscale": "",
        "skyview": "query",
    })
    url = f"https://skyview.gsfc.nasa.gov/current/cgi/runquery.pl?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AstroScan/2.0 astroscan.space"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
            content_type = resp.headers.get_content_type()
        return Response(
            data,
            mimetype=content_type or "image/gif",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        log.warning("SkyView proxy error: %s", e)
        return Response(status=502)


# ── Telescope MJPEG stream + status ───────────────────────────────────
@bp.route("/api/telescope/stream")
def telescope_stream():
    """Stream MJPEG depuis fichier live ou APOD fallback."""
    import requests

    LIVE_PATH = "/root/astro_scan/telescope_live/current_live.jpg"

    def frames():
        while True:
            try:
                if os.path.exists(LIVE_PATH):
                    mtime = os.path.getmtime(LIVE_PATH)
                    age = time.time() - mtime
                    if age < 300:
                        with open(LIVE_PATH, "rb") as f:
                            img = f.read()
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + img + b"\r\n")
                        time.sleep(2)
                        continue
                key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
                r = requests.get(f"https://api.nasa.gov/planetary/apod?api_key={key}", timeout=6)
                d = r.json()
                img_url = d.get("url", "")
                if img_url and img_url.endswith((".jpg", ".png", ".jpeg")):
                    img_data = requests.get(img_url, timeout=8).content
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + img_data + b"\r\n")
            except Exception:
                pass
            time.sleep(30)

    return Response(
        stream_with_context(frames()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@bp.route("/api/telescope/status")
def telescope_status():
    """Statut réel du feed télescope."""
    LIVE_PATH = "/root/astro_scan/telescope_live/current_live.jpg"
    if os.path.exists(LIVE_PATH):
        age = time.time() - os.path.getmtime(LIVE_PATH)
        mode = "LIVE" if age < 300 else "STALE"
        return jsonify({"mode": mode, "age_sec": int(age), "source": "telescope_live"})
    return jsonify({
        "mode": "APOD_FALLBACK",
        "source": "NASA APOD",
        "note": "Aucune image locale détectée",
    })


# ── Stellarium fusion ─────────────────────────────────────────────────
@bp.route("/api/stellarium")
def api_stellarium():
    from modules.stellarium_fusion import get_stellarium_data, get_priority_object
    data = get_stellarium_data()
    data["priority_object"] = get_priority_object(data)
    return jsonify(data)


# ── Image multi-source + title (Domaine H) ────────────────────────────
def _png_1x1():
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr)
    ihdr_chunk = struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", ihdr_crc)
    idat_data = zlib.compress(b"\x00\x00\x00\x00")
    idat_crc = zlib.crc32(b"IDAT" + idat_data)
    idat_chunk = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + struct.pack(">I", idat_crc)
    iend_crc = zlib.crc32(b"IEND")
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    return sig + ihdr_chunk + idat_chunk + iend_chunk


@bp.route("/api/image")
def api_image():
    source = (request.args.get("source") or "live").strip().lower()
    fresh = request.args.get("fresh", "").strip().lower() in ("1", "true", "yes")
    if source not in ("apod", "hubble", "apod_archive"):
        source = "live"

    if source == "live":
        if Path(IMG_PATH).exists():
            return send_file(IMG_PATH, mimetype="image/jpeg")
    else:
        path = _source_path(source)
        now = time.time()
        if not fresh and path.exists():
            age = now - path.stat().st_mtime
            if age < _IMAGE_CACHE_TTL:
                return send_file(path, mimetype="image/jpeg")
        if source == "apod":
            data, title, label = _fetch_apod_live()
        elif source == "hubble":
            data, title, label = _fetch_hubble_live()
        elif source == "apod_archive":
            data, title, label = _fetch_apod_archive_live()
        else:
            data, title, label = None, None, None
        if data:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                _image_meta[source] = (title, label)
            except Exception as e:
                log.warning("write source image: %s", e)
            return Response(
                data,
                mimetype="image/jpeg",
                headers={"Cache-Control": "no-cache, max-age=0"},
            )
        if path.exists():
            return send_file(str(path), mimetype="image/jpeg")

    return Response(
        _png_1x1(),
        mimetype="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@bp.route("/api/title")
def api_title():
    src_param = (request.args.get("source") or "live").strip().lower()
    if src_param in _image_meta:
        title, source = _image_meta[src_param]
        if title and source:
            return jsonify({"title": title, "source": source})
    title = "ORBITAL-CHOHRA Observatory"
    if Path(TITLE_F).exists():
        try:
            with open(TITLE_F) as f:
                title = f.read().strip() or title
        except Exception:
            pass
    source = "NASA APOD"
    try:
        from app.utils.db import get_db
        conn = get_db()
        row = conn.execute(
            "SELECT COALESCE(title, objets_detectes, 'Observation') as t, source "
            "FROM observations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            title = row["t"] or title
            source = row["source"] or source
    except Exception:
        pass
    return jsonify({"title": title, "source": source})


# ── Hubble images (différé PASS 8 levé) ───────────────────────────────
@bp.route("/api/hubble/images")
def api_hubble_images():
    """Proxy Hubble images — NASA APOD count=6 ou fallback statique."""
    try:
        return jsonify(fetch_hubble_images())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── PASS 16 — /api/telescope/trigger-nightly POST (différé PASS 9 levé) ──
@bp.route("/api/telescope/trigger-nightly", methods=["POST"])
@require_admin
def api_telescope_trigger_nightly():
    """Déclenche manuellement le pipeline nocturne Harvard MO (thread daemon)."""
    import threading
    from station_web import _telescope_nightly_tlemcen
    t = threading.Thread(target=_telescope_nightly_tlemcen, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Pipeline nocturne démarré en arrière-plan"})
