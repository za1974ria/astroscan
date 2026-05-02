"""Blueprint Pages — pages HTML simples sans logique complexe."""
from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)

# DEFERRED B-RECYCLE — /landing reste dans station_web.py jusqu'à correction SEO
# Manque : seo_title=SEO_HOME_TITLE, seo_description=SEO_HOME_DESCRIPTION
# À activer lors de B-recycle-pages-fix — voir /tmp/pages_init_patched_TODO.md
# @bp.route("/landing")
# def landing():
#     return render_template("landing.html")

@bp.route("/vision")
def vision():
    try:
        return render_template("vision.html")
    except Exception:
        return render_template("portail.html")

@bp.route("/scientific")
def scientific():
    try:
        return render_template("scientific.html")
    except Exception:
        return render_template("portail.html")
