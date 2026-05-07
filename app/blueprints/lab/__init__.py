"""Blueprint Lab — Digital Lab + Space Analysis Engine.

PASS 13 (2026-05-03) — Création :
  /lab (page), /lab/upload, /lab/images, /api/lab/images,
  /lab/raw/<path:filename>, /api/lab/metadata/<path:filename>,
  /lab/analyze, /lab/dashboard, /api/lab/run_analysis,
  /api/lab/skyview/sync, /api/lab/upload, /api/lab/analyze,
  /api/lab/report, /api/analysis/{run,compare,discoveries}.

Pattern : lazy-import des helpers monolithe via `from station_web import`.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime

from flask import (
    Blueprint, render_template, request, jsonify, send_from_directory,
)
from werkzeug.utils import secure_filename

log = logging.getLogger(__name__)

bp = Blueprint("lab", __name__)


def _to_native(obj):
    """Convertit numpy scalars en types natifs Python."""
    if hasattr(obj, "item"):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_native(x) for x in obj]
    return obj


# ── Page principale Lab ────────────────────────────────────────────────
@bp.route("/lab")
def digital_lab():
    return render_template("lab.html")


# ── Upload simple (multipart) ──────────────────────────────────────────
@bp.route("/lab/upload", methods=["POST"])
def lab_upload():
    from station_web import SPACE_IMAGE_DB, METADATA_DB, MAX_LAB_IMAGE_BYTES

    if "image" not in request.files:
        return jsonify({"error": "no image"}), 400
    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "no image"}), 400
    allowed = (".jpg", ".jpeg", ".png", ".fits", ".fit")
    filename = secure_filename(file.filename)
    req_len = request.content_length or 0
    if req_len and req_len > MAX_LAB_IMAGE_BYTES:
        return jsonify({"error": "image too large"}), 413
    if not filename.lower().endswith(allowed):
        return jsonify({"error": "invalid format"}), 400
    path = os.path.join(SPACE_IMAGE_DB, filename)
    if os.path.exists(path):
        filename = str(int(time.time())) + "_" + filename
        path = os.path.join(SPACE_IMAGE_DB, filename)
    try:
        file.save(path)
        meta = {
            "source": "UPLOAD",
            "filename": filename,
            "date": datetime.utcnow().isoformat() + "Z",
            "telescope": "unknown",
            "object_name": "unknown",
            "instrument": "unknown",
        }
        meta_path = os.path.join(METADATA_DB, filename + ".json")
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception as e:
            log.warning("lab/upload metadata: %s", e)
        return jsonify({"status": "saved", "file": filename, "path": path})
    except Exception as e:
        log.warning("lab/upload: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/lab/images")
def lab_images():
    from station_web import SPACE_IMAGE_DB
    try:
        files = [
            f for f in os.listdir(SPACE_IMAGE_DB)
            if os.path.isfile(os.path.join(SPACE_IMAGE_DB, f))
            and not f.endswith(".json")
        ]
        return jsonify({"images": files})
    except Exception as e:
        log.warning("lab/images: %s", e)
        return jsonify({"images": []})


@bp.route("/api/lab/images")
def api_lab_images():
    """Liste les images brutes disponibles pour le Digital Lab (PNG/JPG)."""
    from station_web import RAW_IMAGES
    try:
        exts = (".png", ".jpg", ".jpeg")
        entries = []
        for name in os.listdir(RAW_IMAGES):
            if not name.lower().endswith(exts):
                continue
            path = os.path.join(RAW_IMAGES, name)
            if not os.path.isfile(path):
                continue
            entries.append({"file": name, "mtime": os.path.getmtime(path)})
        entries.sort(key=lambda x: x["mtime"], reverse=True)
        images = [{"file": e["file"], "url": f"/lab/raw/{e['file']}"} for e in entries]
        return jsonify({"images": images})
    except Exception as e:
        log.warning("api/lab/images: %s", e)
        return jsonify({"images": []})


@bp.route("/lab/raw/<path:filename>")
def lab_raw_file(filename):
    """Sert les fichiers bruts du laboratoire (images) depuis RAW_IMAGES."""
    from station_web import RAW_IMAGES
    return send_from_directory(RAW_IMAGES, filename, as_attachment=False)


@bp.route("/api/lab/metadata/<path:filename>")
def api_lab_metadata(filename):
    """Return normalized metadata JSON for a lab image file, if present."""
    from station_web import METADATA_DB
    try:
        safe = secure_filename(os.path.basename(filename)) or filename
        meta_path = os.path.join(METADATA_DB, safe + ".json")
        if not os.path.isfile(meta_path):
            return jsonify({})
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        log.warning("api/lab/metadata: %s", e)
        return jsonify({})


# ── Analyses ──────────────────────────────────────────────────────────
@bp.route("/lab/analyze", methods=["POST"])
def lab_analyze():
    from station_web import ANALYSED_IMAGES
    if "image" not in request.files:
        return jsonify({
            "error": "no image", "stars_detected": 0,
            "objects_detected": 0, "brightness_mean": 0, "report": {},
        }), 400
    file = request.files["image"]
    if not file.filename:
        return jsonify({
            "error": "no image", "stars_detected": 0,
            "objects_detected": 0, "brightness_mean": 0, "report": {},
        }), 400
    try:
        from modules.digital_lab import run_pipeline
        filename = secure_filename(file.filename) or "analyzed.png"
        data_bytes = file.read()
        try:
            os.makedirs(ANALYSED_IMAGES, exist_ok=True)
            analysed_path = os.path.join(ANALYSED_IMAGES, filename)
            with open(analysed_path, "wb") as out_f:
                out_f.write(data_bytes)
        except Exception as e:
            log.warning("lab/analyze save analysed: %s", e)
        result = run_pipeline(data_bytes)
        stars_detected = len(result.get("stars") or [])
        objects_detected = len(result.get("objects") or [])
        brightness = result.get("brightness") or {}
        brightness_mean = float(brightness.get("global_mean", 0.0))
        report = result.get("report") or {}
        return jsonify({
            "stars_detected": stars_detected,
            "objects_detected": objects_detected,
            "brightness_mean": _to_native(brightness_mean),
            "report": _to_native(report),
        })
    except Exception as e:
        log.warning("lab/analyze: %s", e)
        return jsonify({
            "error": str(e),
            "stars_detected": 0,
            "objects_detected": 0,
            "brightness_mean": 0,
            "report": {},
        }), 500


@bp.route("/lab/dashboard")
def lab_dashboard():
    """Dashboard: number_of_images, latest_images, sources (from metadata)."""
    from station_web import SPACE_IMAGE_DB, METADATA_DB
    try:
        files = [
            f for f in os.listdir(SPACE_IMAGE_DB)
            if os.path.isfile(os.path.join(SPACE_IMAGE_DB, f))
            and not f.endswith(".json")
        ]
        latest = sorted(
            files,
            key=lambda f: os.path.getmtime(os.path.join(SPACE_IMAGE_DB, f)),
            reverse=True,
        )[:10]
        sources = set()
        for f in files:
            meta_path = os.path.join(METADATA_DB, f + ".json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as fp:
                        m = json.load(fp)
                        sources.add(m.get("source", "unknown"))
                except Exception:
                    pass
        return jsonify({
            "number_of_images": len(files),
            "latest_images": latest,
            "sources": list(sources) if sources else [
                "NASA APOD", "HUBBLE", "JWST", "ESA", "UPLOAD",
            ],
        })
    except Exception as e:
        log.warning("lab/dashboard: %s", e)
        return jsonify({"number_of_images": 0, "latest_images": [], "sources": []})


@bp.route("/api/lab/run_analysis", methods=["POST"])
def api_lab_run_analysis():
    """Analyze the newest image in RAW_IMAGES using the Digital Lab pipeline."""
    from station_web import RAW_IMAGES
    from modules.digital_lab import run_pipeline

    exts = (".png", ".jpg", ".jpeg", ".fits", ".fit")
    candidates = []
    for name in os.listdir(RAW_IMAGES):
        if name.lower().endswith(exts):
            path = os.path.join(RAW_IMAGES, name)
            if os.path.isfile(path):
                candidates.append((os.path.getmtime(path), name))

    if not candidates:
        return jsonify({"error": "no images available"}), 400

    candidates.sort(reverse=True)
    filename = candidates[0][1]
    path = os.path.join(RAW_IMAGES, filename)
    result = run_pipeline(path)
    return jsonify({
        "status": "ok",
        "filename": filename,
        "report": result,
    })


@bp.route("/api/lab/skyview/sync")
def force_skyview_sync():
    """Force une synchronisation immédiate SkyView → Lab."""
    from station_web import _sync_skyview_to_lab
    _sync_skyview_to_lab()
    return jsonify({"status": "skyview_sync_ok"})


# ── Upload + analyse via JSON (pipeline complet) ─────────────────────
@bp.route("/api/lab/upload", methods=["POST"])
def api_lab_upload():
    from app.services.security import _api_rate_limit_allow
    from station_web import LAB_UPLOADS, MAX_LAB_IMAGE_BYTES
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        ip = ip.split(",")[0].strip()
        allowed, retry = _api_rate_limit_allow(f"lab_upload:{ip}", limit=30, window_sec=60)
        if not allowed:
            return jsonify({
                "error": f"Trop de televersements. Reessayez dans {retry}s.",
                "retry_after": retry,
            }), 429
        os.makedirs(LAB_UPLOADS, exist_ok=True)
        f = request.files.get("image")
        if not f or not f.filename:
            return jsonify({"error": "No image file provided"}), 400
        req_len = request.content_length or 0
        if req_len and req_len > MAX_LAB_IMAGE_BYTES:
            return jsonify({"error": "Image trop volumineuse (max 25 MB)"}), 413
        ext = os.path.splitext(f.filename)[1] or ".png"
        name = str(uuid.uuid4()) + ext
        path = os.path.join(LAB_UPLOADS, name)
        f.save(path)
        return jsonify({"id": name, "path": name, "uploaded": True})
    except Exception as e:
        log.warning("api/lab/upload: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/lab/analyze", methods=["POST"])
def api_lab_analyze():
    from app.services.security import _api_rate_limit_allow
    from station_web import (
        LAB_UPLOADS,
        RAW_IMAGES,
        MAX_LAB_IMAGE_BYTES,
        _lab_last_report,
    )
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        ip = ip.split(",")[0].strip()
        allowed, retry = _api_rate_limit_allow(f"lab_analyze:{ip}", limit=20, window_sec=60)
        if not allowed:
            return jsonify({
                "error": f"Trop d analyses. Reessayez dans {retry}s.",
                "retry_after": retry,
            }), 429
        from modules.digital_lab import run_pipeline
        source = None
        payload = request.get_json(silent=True) or {}
        if request.files.get("image"):
            f = request.files["image"]
            req_len = request.content_length or 0
            if req_len and req_len > MAX_LAB_IMAGE_BYTES:
                return jsonify({
                    "error": "Image trop volumineuse pour analyse (max 25 MB)",
                    "report": {},
                }), 413
            source = f.read()
        elif payload.get("upload_id"):
            path = os.path.join(LAB_UPLOADS, payload["upload_id"])
            if os.path.isfile(path):
                source = path
        elif payload.get("raw_file"):
            raw_name = secure_filename(os.path.basename(str(payload.get("raw_file"))))
            raw_path = os.path.join(RAW_IMAGES, raw_name)
            if os.path.isfile(raw_path):
                source = raw_path
        if source is None:
            return jsonify({
                "error": "Provide image file, upload_id or raw_file in JSON",
            }), 400
        result = run_pipeline(source)
        result = _to_native(result)
        _lab_last_report["report"] = result.get("report", {})
        _lab_last_report["full"] = {
            k: v for k, v in result.items()
            if k != "report"
            and not (isinstance(v, (list, dict)) and len(str(v)) > 2000)
        }
        return jsonify(result)
    except Exception as e:
        log.warning("api/lab/analyze: %s", e)
        return jsonify({"error": str(e), "report": {}}), 500


@bp.route("/api/lab/report", methods=["GET"])
def api_lab_report():
    from station_web import _lab_last_report
    try:
        report = _lab_last_report.get("report", {})
        if not report:
            return jsonify({"report": {}, "message": "Run /api/lab/analyze first"})
        return jsonify({"report": report})
    except Exception as e:
        return jsonify({"error": str(e), "report": {}}), 500


# ── Space Analysis Engine (Domaine AB) ────────────────────────────────
@bp.route("/api/analysis/run", methods=["POST"])
def api_analysis_run():
    try:
        from modules.space_analysis_engine import run_analysis
        data = request.get_json(silent=True) or {}
        pipeline_result = data.get("pipeline_result")
        source = data.get("source", "upload")
        if not pipeline_result:
            return jsonify({
                "error": "Provide pipeline_result (output of digital_lab run_pipeline)",
            }), 400
        result = run_analysis(pipeline_result, source=source)
        return jsonify(result)
    except Exception as e:
        log.warning("api/analysis/run: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/analysis/compare", methods=["POST"])
def api_analysis_compare():
    try:
        from modules.space_analysis_engine import compare_results_from_sources
        data = request.get_json(silent=True) or {}
        result_a = data.get("result_a")
        result_b = data.get("result_b")
        source_a = data.get("source_a", "source_a")
        source_b = data.get("source_b", "source_b")
        if not result_a or not result_b:
            return jsonify({
                "error": "Provide result_a and result_b (pipeline results)",
            }), 400
        out = compare_results_from_sources(
            result_a, result_b,
            source_a=source_a, source_b=source_b,
        )
        return jsonify(out)
    except Exception as e:
        log.warning("api/analysis/compare: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/analysis/discoveries", methods=["GET"])
def api_analysis_discoveries():
    try:
        from modules.space_analysis_engine import get_discoveries
        limit = request.args.get("limit", 100, type=int)
        discoveries = get_discoveries(limit=min(limit, 500))
        return jsonify({"discoveries": discoveries, "count": len(discoveries)})
    except Exception as e:
        log.warning("api/analysis/discoveries: %s", e)
        return jsonify({"error": str(e), "discoveries": []}), 500
