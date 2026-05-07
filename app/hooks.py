"""
AstroScan — App-level hooks (factory-attached).

PASS 24 (2026-05-04) — Migration des 8 hooks app-level depuis station_web.py
vers le factory (`create_app()`).

Hooks migrés (copie verbatim, register_hooks(app) appelé après les BPs) :
  - 3 @before_request : timing_start, visitor_session_before, increment_visits
  - 2 @after_request  : struct_log_response, session_cookie_and_time_script
  - 2 @errorhandler   : 404, 500
  - 1 @context_processor : seo_site_description

Live path (CASE A — wsgi.py) : `gunicorn wsgi:app` retourne `create_app()`.
Les hooks `@app.X` toujours présents dans station_web.py sont attachés à
`station_web.app` (instance distincte, dead code sur le chemin live) ; ils
sont conservés intacts pour PASS 25 (cleanup).

Globals station_web référencés (lazy import dans le corps des fonctions
pour éviter l'import circulaire — station_web est pré-chargé par wsgi.py
AVANT create_app, donc les attributs sont toujours disponibles à l'appel) :
  SEO_HOME_DESCRIPTION, PAGE_PATHS, _SESSION_TIME_SNIPPET,
  _emit_diag_json, _register_unique_visit_from_request,
  _http_request_log_allow, metrics_record_request,
  struct_log, log
"""
from __future__ import annotations

import logging
import secrets
import time

from flask import Flask, g, jsonify, render_template, request


# ─── @context_processor ───────────────────────────────────────────────────────
def _inject_seo_site_description():
    """Expose la meta description globale (une seule source : SEO_HOME_DESCRIPTION)."""
    from station_web import SEO_HOME_DESCRIPTION
    return {'seo_site_description': SEO_HOME_DESCRIPTION}


# ─── @errorhandler(404) ───────────────────────────────────────────────────────
def _astroscan_404(e):
    if request.path.startswith('/api/'):
        return jsonify(error='not_found', path=request.path), 404
    try:
        return render_template('404.html', path=request.path), 404
    except Exception:
        return '<h1>404 — Page introuvable</h1>', 404


# ─── @errorhandler(500) ───────────────────────────────────────────────────────
def _astroscan_500(e):
    from station_web import log
    try:
        log.error("500 Internal Error on %s: %s", request.path, e, exc_info=True)
    except Exception:
        pass
    if request.path.startswith('/api/'):
        return jsonify(error='internal_error'), 500
    try:
        return render_template('500.html'), 500
    except Exception:
        return '<h1>500 — Erreur interne</h1>', 500


# ─── @before_request — timing start + heavy route trace ──────────────────────
def _astroscan_request_timing_start():
    """Timing start pour TOUTES les requêtes + trace route lourde (début)."""
    from station_web import _emit_diag_json
    try:
        g._astroscan_req_start = time.time()
        p = request.path or ""
        heavy_prefixes = (
            "/api/microobservatory/preview/",
            "/api/iss",
            "/api/tle",
            "/api/meteo",
            "/galerie",
            "/module/galerie",
        )
        if any(p.startswith(x) for x in heavy_prefixes):
            _emit_diag_json(
                {
                    "event": "route_trace_start",
                    "path": p,
                    "method": request.method,
                }
            )
    except Exception:
        pass


# ─── @before_request — visitor session cookie ────────────────────────────────
def _astroscan_visitor_session_before():
    """Cookie astroscan_sid (identifiant de session navigateur) pour corrélation visitor_log / session_time.
    DOIT s'exécuter AVANT _maybe_increment_visits pour que g._astroscan_sid soit disponible."""
    try:
        if (request.path or "").startswith("/static"):
            return
        sid = request.cookies.get("astroscan_sid")
        if sid:
            g._astroscan_sid = sid
            g._astroscan_sid_new = False
        else:
            g._astroscan_sid = secrets.token_urlsafe(24)
            g._astroscan_sid_new = True
    except Exception:
        try:
            g._astroscan_sid = secrets.token_urlsafe(24)
            g._astroscan_sid_new = True
        except Exception:
            pass


# ─── @before_request — page-view counter ─────────────────────────────────────
def _maybe_increment_visits():
    """
    Enregistre les visites de pages HTML (pas les API, static, etc.).
    - page_views : chaque chargement de page (toutes sessions)
    - visitor_log : une entrée par session (IP+session_id unique)
    S'exécute APRÈS _astroscan_visitor_session_before (g._astroscan_sid déjà défini).
    """
    from app.services.db_visitors import _register_unique_visit_from_request
    from station_web import PAGE_PATHS
    try:
        g._astroscan_req_start = time.time()
    except Exception:
        pass
    if request.path not in PAGE_PATHS:
        return
    _register_unique_visit_from_request(path_override=request.path)


# ─── @after_request — struct_log + heavy route trace (end) ───────────────────
def _astroscan_struct_log_response(response):
    """Journalise les réponses HTTP (hors static) ; métriques légères + anti-spam logs 2xx/3xx."""
    from station_web import (
        _emit_diag_json,
        _http_request_log_allow,
        metrics_record_request,
        struct_log,
        log,
    )
    try:
        p = request.path or ""
        if p.startswith("/static"):
            return response
        # Comptage requêtes (fenêtre glissante) — hors /static pour ne pas polluer le throughput « API ».
        metrics_record_request()
        t0 = getattr(g, "_astroscan_req_start", None)
        dur_ms = None
        if t0 is not None:
            dur_ms = round((time.time() - t0) * 1000, 2)
        # 5xx → struct_log ERROR (alimente errors_last_5min) ; 4xx → WARNING ; 2xx/3xx via jeton (anti-spam).
        sc = response.status_code
        # Instrumentation demandée: timing JSON à partir de 1500 ms.
        if dur_ms is not None and dur_ms >= 1500:
            _emit_diag_json(
                {
                    "event": "request_timing",
                    "path": p,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": dur_ms,
                }
            )
        if dur_ms is not None and dur_ms >= 5000:
            _emit_diag_json(
                {
                    "event": "very_slow_request",
                    "path": p,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": dur_ms,
                }
            )
        # Trace routes lourdes ciblées (fin).
        heavy_prefixes = (
            "/api/microobservatory/preview/",
            "/api/iss",
            "/api/tle",
            "/api/meteo",
            "/galerie",
            "/module/galerie",
        )
        if dur_ms is not None and any((p or "").startswith(x) for x in heavy_prefixes):
            try:
                print(f"[DEBUG] route {p} took {dur_ms:.1f} ms", flush=True)
            except Exception:
                pass
            try:
                log.info("[DEBUG] route %s took %.1f ms", p, dur_ms)
            except Exception:
                pass

        # Signalement struct_log existant conservé (anti-régression).
        if dur_ms is not None and dur_ms >= 2500:
            struct_log(
                logging.WARNING,
                category="api",
                event="slow_request",
                method=request.method,
                path=p,
                status_code=sc,
                duration_ms=dur_ms,
            )
        if sc >= 500:
            struct_log(
                logging.ERROR,
                category="api",
                event="http_request",
                method=request.method,
                path=p,
                status_code=sc,
                duration_ms=dur_ms,
            )
        elif sc >= 400:
            struct_log(
                logging.WARNING,
                category="api",
                event="http_request",
                method=request.method,
                path=p,
                status_code=sc,
                duration_ms=dur_ms,
            )
        elif _http_request_log_allow():
            struct_log(
                logging.INFO,
                category="api",
                event="http_request",
                method=request.method,
                path=p,
                status_code=sc,
                duration_ms=dur_ms,
            )
    except Exception:
        pass
    return response


# ─── @after_request — session cookie + page-time script injection ────────────
def _astroscan_session_cookie_and_time_script(response):
    """Pose le cookie astroscan_sid + injecte le script de durée de page (HTML uniquement)."""
    from station_web import _SESSION_TIME_SNIPPET
    try:
        p = request.path or ""
        if p.startswith("/static"):
            return response
        secure = bool(request.is_secure) or (
            (request.headers.get("X-Forwarded-Proto") or "").lower() == "https"
        )
        # Rafraîchit le cookie à chaque page HTML : session = 30 min d'inactivité.
        # Si inactif > 30 min → cookie expire → prochaine visite = nouvelle session.
        if getattr(g, "_astroscan_sid", None):
            response.set_cookie(
                "astroscan_sid",
                g._astroscan_sid,
                max_age=60 * 30,  # 30 minutes d'inactivité = nouvelle session
                samesite="Lax",
                path="/",
                secure=secure,
            )
        ct = (response.headers.get("Content-Type") or "").lower()
        if response.status_code >= 400 or "text/html" not in ct:
            return response
        data = response.get_data(as_text=True)
        if "astroscan-session-time" in data or "</body>" not in data:
            return response
        data = data.replace("</body>", _SESSION_TIME_SNIPPET + "\n</body>", 1)
        response.set_data(data)
    except Exception:
        pass
    return response


# ─── Registration entry point ─────────────────────────────────────────────────
def register_hooks(app: Flask) -> None:
    """Attache les 8 hooks app-level au Flask `app` (factory)."""
    # Ordre des before_request : préserve la chaîne historique
    # (timing_start → visitor_session → increment_visits).
    app.before_request(_astroscan_request_timing_start)
    app.before_request(_astroscan_visitor_session_before)
    app.before_request(_maybe_increment_visits)

    app.after_request(_astroscan_struct_log_response)
    app.after_request(_astroscan_session_cookie_and_time_script)

    app.register_error_handler(404, _astroscan_404)
    app.register_error_handler(500, _astroscan_500)

    app.context_processor(_inject_seo_site_description)
