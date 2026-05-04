"""Blueprint i18n — détection et switch de langue.

PASS 30 (2026-05-04) — Production-grade bilingual support:
  - get_lang() priority: ?lang= query > "lang" cookie > Accept-Language > default 'fr'
  - /set-lang/<lang> sets a 1-year cookie and redirects back to referrer
  - before_app_request: when ?lang= is present, stage the cookie renewal
    so subsequent requests honor the choice without keeping the query param
  - context_processor: exposes `lang` and `get_locale()` to every template
    (drop-in compatible with Flask-Babel idioms)
"""
from flask import Blueprint, request, redirect, make_response, g

bp = Blueprint("i18n", __name__)
SUPPORTED = {"fr", "en"}
COOKIE_NAME = "lang"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def get_lang() -> str:
    """Resolve current language. Priority:
    1) ?lang=fr|en query param
    2) "lang" cookie
    3) Accept-Language header
    4) default 'fr'
    """
    try:
        q = (request.args.get("lang") or "").lower()
        if q in SUPPORTED:
            return q
        cookie = request.cookies.get(COOKIE_NAME, "")
        if cookie in SUPPORTED:
            return cookie
        accept = request.headers.get("Accept-Language", "")
        return "en" if accept.lower().startswith("en") else "fr"
    except Exception:
        return "fr"


@bp.route("/set-lang/<lang>")
def set_lang(lang: str):
    if lang not in SUPPORTED:
        lang = "fr"
    resp = make_response(redirect(request.referrer or "/portail"))
    resp.set_cookie(
        COOKIE_NAME, lang,
        max_age=COOKIE_MAX_AGE,
        samesite="Lax",
        httponly=False,  # JS reads it for client-side i18n
    )
    return resp


# ── App-level hooks (registered by create_app via register_i18n_hooks) ──────
def _i18n_before_request():
    """If ?lang= was provided, stash it in g so after_request can renew the cookie."""
    try:
        q = (request.args.get("lang") or "").lower()
        if q in SUPPORTED:
            g._i18n_pending_lang = q
    except Exception:
        pass


def _i18n_after_request(response):
    """Renew the lang cookie if ?lang= was on the request."""
    try:
        pending = getattr(g, "_i18n_pending_lang", None)
        if pending in SUPPORTED:
            response.set_cookie(
                COOKIE_NAME, pending,
                max_age=COOKIE_MAX_AGE,
                samesite="Lax",
                httponly=False,
            )
    except Exception:
        pass
    return response


def _i18n_context():
    """Expose `lang` and `get_locale()` to every template."""
    try:
        lang = get_lang()
    except Exception:
        lang = "fr"
    return {
        "lang": lang,
        "get_locale": lambda: lang,
    }


def register_i18n_hooks(app) -> None:
    """Wire the i18n hooks into the Flask app (called from create_app)."""
    app.before_request(_i18n_before_request)
    app.after_request(_i18n_after_request)
    app.context_processor(_i18n_context)
