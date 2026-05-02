"""Blueprint i18n — détection et switch de langue."""
from flask import Blueprint, request, redirect, make_response

bp = Blueprint("i18n", __name__)
SUPPORTED = {"fr", "en"}


def get_lang() -> str:
    lang = request.cookies.get("lang", "")
    if lang in SUPPORTED:
        return lang
    accept = request.headers.get("Accept-Language", "")
    return "en" if accept.lower().startswith("en") else "fr"


@bp.route("/set-lang/<lang>")
def set_lang(lang: str):
    if lang not in SUPPORTED:
        lang = "fr"
    resp = make_response(redirect(request.referrer or "/portail"))
    resp.set_cookie("lang", lang, max_age=60*60*24*365, samesite="Lax")
    return resp
