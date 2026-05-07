"""Blueprint Pages — pages HTML simples sans logique complexe.

PASS 5 (2026-05-03) — Domaines C, D, S, AG + redirects ajoutés :
  index/portail/technical/dashboard, overlord_live, galerie, observatoire,
  vision-2026, sondes, telemetrie-sondes, ce_soir,
  research, space, space-intelligence, module/<name>, demo,
  space-intelligence-page, aladin, carte-du-ciel,
  europe-live, flight-radar.
"""
import os

from flask import (
    Blueprint, render_template, make_response, redirect, abort,
)

from app.config import (
    SEO_HOME_TITLE, SEO_HOME_DESCRIPTION, STATION,
)
from app.blueprints.i18n import get_lang

bp = Blueprint("pages", __name__)


# ── Constantes locales ────────────────────────────────────────────────
FETES_ISLAMIQUES = [
    {
        "nom": "1er Mouharram",
        "nom_ar": "رأس السنة الهجرية",
        "description": "Nouvel An hégirien — début de l'année 1448",
        "date_2026": "2026-06-17",
        "hijri": "1 Mouharram 1448",
    },
    {
        "nom": "Achoura",
        "nom_ar": "عاشوراء",
        "description": "10ème jour de Mouharram — jour de jeûne recommandé",
        "date_2026": "2026-06-26",
        "hijri": "10 Mouharram 1448",
    },
    {
        "nom": "Mawlid Ennabawi",
        "nom_ar": "المولد النبوي الشريف",
        "description": "Naissance du Prophète Muhammad ﷺ",
        "date_2026": "2026-09-13",
        "hijri": "12 Rabi al-Awwal 1448",
    },
]


# ── Pages racine / portail (Domaine C) ────────────────────────────────
@bp.route("/")
def index():
    return render_template(
        "landing.html",
        seo_title=SEO_HOME_TITLE,
        seo_description=SEO_HOME_DESCRIPTION,
    )


@bp.route("/portail")
def portail():
    # PASS UI A FIX 4 (2026-05-07) : SSR du compteur visiteurs pour éviter
    # le flash "000 000" à l'arrivée. Le JS continue de rafraîchir la valeur
    # côté client après chargement.
    visitor_count = None
    try:
        from app.services.db_visitors import _get_visits_count
        visitor_count = _get_visits_count()
    except Exception:
        visitor_count = None
    response = make_response(render_template(
        "portail.html",
        lang=get_lang(),
        visitor_count=visitor_count,
    ))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    # Phase O-E (2026-05-07) : CSP préventif pour bloquer toute injection DOM
    # par extension de navigateur tierce (cause possible de sidebar fantôme).
    # 'unsafe-inline'/'unsafe-eval' conservés : le portail utilise du JS inline.
    # frame-ancestors 'self' empêche un éventuel embed cyclique.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' https: data: blob:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data: https:; "
        "connect-src 'self' https: wss:; "
        "frame-ancestors 'self'; "
        "base-uri 'self'"
    )
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@bp.route("/landing")
def landing():
    """Landing marketing AstroScan-Chohra."""
    return render_template(
        "landing.html",
        seo_title=SEO_HOME_TITLE,
        seo_description=SEO_HOME_DESCRIPTION,
    )


@bp.route("/technical")
def technical_page():
    return render_template("technical.html")


@bp.route("/dashboard")
def dashboard():
    return render_template("research_dashboard.html")


@bp.route("/overlord_live")
def overlord_live():
    return render_template("overlord_live.html")


@bp.route("/observatoire")
def observatoire():
    # PASS 26.B — nasa_key no longer passed to template (proxy via /api/nasa/*)
    response = make_response(render_template("observatoire.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ── Pages thématiques (Domaine D + AG) ────────────────────────────────
@bp.route("/vision")
def vision():
    try:
        return render_template("vision.html")
    except Exception:
        return render_template("portail.html")


@bp.route("/vision-2026")
def vision_2026():
    return render_template("vision_2026.html")


@bp.route("/scientific")
def scientific():
    try:
        return render_template("scientific.html")
    except Exception:
        return render_template("portail.html")


@bp.route("/sondes")
def sondes():
    """Page SONDES SPATIALES — Voyager, Mars, ISS, JWST, Hubble, Parker."""
    return render_template("sondes.html")


@bp.route("/telemetrie-sondes")
def telemetrie_sondes():
    """Télémétrie live Voyager 1&2, James Webb, New Horizons."""
    return render_template("telemetrie_sondes.html")


# ── Ce soir (Domaine S) ────────────────────────────────────────────────
@bp.route("/ce_soir")
def ce_soir_page():
    return render_template("ce_soir.html", fetes_islamiques=FETES_ISLAMIQUES)


# ── Pages supplémentaires (Domaine AG) ─────────────────────────────────
@bp.route("/research")
def research():
    """Scientific research dashboard — Digital Lab, anomaly detector, NEO, discoveries."""
    return render_template("research.html")


@bp.route("/space")
def space():
    return render_template("space.html")


@bp.route("/space-intelligence")
def space_intelligence():
    return redirect("/space")


@bp.route("/space-intelligence-page")
def space_intelligence_page():
    """Page Intelligence spatiale (éviter conflit avec /space)."""
    return render_template("space_intelligence.html")


@bp.route("/demo")
def astroscan_demo_page():
    """Page produit : liens MASTER / VIEWER et test WS pour démo client."""
    return render_template("demo.html")


@bp.route("/aladin")
@bp.route("/carte-du-ciel")
def aladin_page():
    return render_template("aladin.html")


@bp.route("/module/<name>")
def module(name):
    """Route legacy : redirige vers route officielle, ou rend <name>.html si présent."""
    module_routes = {
        "galerie": "/galerie",
        "observatoire": "/observatoire",
        "portail": "/portail",
        "dashboard": "/dashboard",
        "ce_soir": "/ce_soir",
    }
    target = module_routes.get((name or "").strip().lower())
    if target:
        return redirect(target)

    template = f"{name}.html"
    template_path = os.path.join(STATION, "templates", template)
    if os.path.exists(template_path):
        try:
            return render_template(template)
        except Exception:
            return redirect("/portail")

    safe_name = (name or "").upper()
    return f"""
<html>
<head>
<title>Orbital-Chohra</title>
<style>
body {{
    background:#020b14;
    color:#00eaff;
    font-family:monospace;
    text-align:center;
    padding-top:120px;
}}
a {{
    color:#00ffaa;
    text-decoration:none;
    font-size:18px;
}}
</style>
</head>

<body>
    <h1>MODULE {safe_name}</h1>
    <p>Module actif – contenu en cours de chargement</p>
    <br>
    <a href="/portail">⬅ Retour portail</a>
</body>
</html>
"""


# ── Pages géo / live (Domaine AL léger) ────────────────────────────────
@bp.route("/europe-live")
def europe_live():
    return render_template("europe_live.html")


# /flight-radar moved to app/blueprints/flight_radar (premium ATC tower).


# ── Galerie (Domaine C, accès DB léger) ────────────────────────────────
@bp.route("/galerie")
def galerie():
    """Galerie d'observations stellaires (lecture archive_stellaire.db)."""
    observations = []
    stats = {"total": 0, "anomalies": 0}
    classification_stats = []
    try:
        from app.utils.db import get_db
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        anomalies = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE anomalie=1"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT id, timestamp, source, objets_detectes, "
            "analyse_gemini as rapport_gemini, COALESCE(title,'') as title, anomalie "
            "FROM observations ORDER BY id DESC LIMIT 200"
        ).fetchall()
        class_rows = conn.execute(
            "SELECT COALESCE(objets_detectes,'inconnu') as type, COUNT(*) as n "
            "FROM observations GROUP BY objets_detectes ORDER BY n DESC"
        ).fetchall()
        observations = [dict(r) for r in rows]
        stats = {"total": total, "anomalies": anomalies}
        classification_stats = [dict(r) for r in class_rows]
    except Exception:
        pass
    return render_template(
        "galerie.html",
        stats=stats,
        observations=observations,
        classification_stats=classification_stats,
    )


# ── PASS 11 — Globe Mission Control 3D ────────────────────────────────
@bp.route("/globe")
def globe():
    """Mission Control 3D plein écran — token Cesium depuis .env uniquement."""
    cesium_token = os.environ.get("CESIUM_ION_TOKEN", "")
    return render_template("globe.html", cesium_token=cesium_token)
