"""Blueprint Main — pages institutionnelles + PWA + assets statiques.

PASS 5 (2026-05-03) — Domaine Q (PWA) + AL (favicon) ajoutés :
  /sw.js, /manifest.json, /api/push/subscribe, /favicon.ico.
"""
import os
from pathlib import Path

from flask import (
    Blueprint, render_template, make_response, send_from_directory,
    send_file, jsonify, Response,
)

from app.config import STATION, SEO_HOME_DESCRIPTION

bp = Blueprint("main", __name__)


# ── Pages institutionnelles ────────────────────────────────────────────
@bp.route("/a-propos")
@bp.route("/about")
def a_propos():
    return render_template("a_propos.html")


@bp.route("/data")
def data_portal():
    return render_template("data_export.html")


@bp.route("/en/portail")
@bp.route("/en/")
@bp.route("/en")
def portail_en():
    resp = make_response(render_template("portail.html", lang="en"))
    resp.set_cookie("lang", "en", max_age=60 * 60 * 24 * 365, samesite="Lax")
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── PWA — Service Worker & Manifest (Domaine Q) ────────────────────────
@bp.route("/sw.js")
def sw_js():
    sw_path = f"{STATION}/static/sw.js"
    if Path(sw_path).exists():
        with open(sw_path) as f:
            content = f.read()
        resp = Response(content, mimetype="application/javascript")
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    return Response("// SW not found", mimetype="application/javascript")


@bp.route("/manifest.json")
def manifest_json():
    m_path = f"{STATION}/static/manifest.json"
    if Path(m_path).exists():
        return send_file(m_path, mimetype="application/json")
    return jsonify({
        "name": "AstroScan-Chohra",
        "short_name": "AstroScan",
        "description": SEO_HOME_DESCRIPTION,
        "start_url": "/observatoire",
        "display": "standalone",
        "background_color": "#010408",
        "theme_color": "#00d4ff",
        "icons": [
            {"src": "/static/img/pwa-icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/img/pwa-icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@bp.route("/api/push/subscribe", methods=["POST"])
def api_push_subscribe():
    return jsonify({"ok": True, "message": "Subscription enregistrée"})


# ── Favicon (Domaine AL) ────────────────────────────────────────────────
@bp.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(STATION, "static"), "favicon.ico"
    )
