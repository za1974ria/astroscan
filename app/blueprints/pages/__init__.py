"""Blueprint Pages — pages HTML simples sans logique complexe."""
from flask import Blueprint, render_template
from app.config import SEO_HOME_TITLE, SEO_HOME_DESCRIPTION

bp = Blueprint("pages", __name__)


@bp.route("/landing")
def landing():
    """Landing marketing AstroScan-Chohra."""
    return render_template(
        "landing.html",
        seo_title=SEO_HOME_TITLE,
        seo_description=SEO_HOME_DESCRIPTION,
    )

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
