"""Blueprint Main — pages HTML institutionnelles."""
from flask import Blueprint, render_template, make_response
from app.blueprints.i18n import get_lang

bp = Blueprint("main", __name__)


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
    resp.set_cookie("lang", "en", max_age=60*60*24*365, samesite="Lax")
    resp.headers["Cache-Control"] = "no-store"
    return resp
