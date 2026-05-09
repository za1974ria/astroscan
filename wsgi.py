"""
AstroScan-Chohra — WSGI Production Entry Point (PASS 18 bascule)

Standard Gunicorn entry: gunicorn wsgi:app

PASS 18 (2026-05-03) — BASCULE create_app
=========================================
Cible : `app.create_app()` (factory) — 21 blueprints + 13 services extraits.
Fallback : `station_web:app` (monolithe legacy) si la factory échoue à
l'import.

Le fallback est volontaire : si une régression silencieuse rend
`create_app()` non-importable au boot (import error, config manquante,
DB indisponible…), l'app retombe sur le monolithe et le service reste
servi. Une seule régression critique = rollback automatique.

Pour forcer l'utilisation du monolithe (debug / rollback explicite) :
    ASTROSCAN_FORCE_MONOLITH=1

Production deployment :
    gunicorn wsgi:app --workers 4 --threads 4 --bind 127.0.0.1:5003
"""
from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger("astroscan.wsgi")

_FORCE_MONOLITH = os.environ.get("ASTROSCAN_FORCE_MONOLITH", "").strip() in (
    "1", "true", "yes", "on",
)


def _build_app():
    """Construit l'app Flask : factory en priorité, monolithe en repli.

    NOTE IMPORTANTE : station_web.py est TOUJOURS importé (avant ou après
    create_app), car il initialise des globals partagés (env vars, DB WAL,
    TLE_CACHE, threads collector) que les BPs utilisent via lazy-import
    (`from station_web import X`).
    """
    if _FORCE_MONOLITH:
        log.warning("[WSGI] ASTROSCAN_FORCE_MONOLITH=1 — bypass create_app()")
        from station_web import app as _app
        log.info("[WSGI] Monolith loaded (forced) — %d routes",
                 len(list(_app.url_map.iter_rules())))
        return _app

    try:
        # 1. Pré-chargement station_web AVANT factory : initialise globals
        #    (env, DB, TLE collector) nécessaires aux lazy-imports BPs.
        import station_web  # noqa: F401 — side effects required
        log.info("[WSGI] station_web pré-chargé (init globals)")

        # 2. Factory : crée l'app propre avec 21 BPs registered.
        from app import create_app
        _app = create_app("production")
        log.info(
            "[WSGI] create_app() loaded successfully — %d routes",
            len(list(_app.url_map.iter_rules())),
        )
        return _app
    except Exception as e:
        err = str(e).strip()
        if err in ("SECRET_KEY", "NASA_API_KEY"):
            log.error(
                "[WSGI] create_app() aborted on env guard variable %s — "
                "fix .env before relying on monolith fallback (degraded routes).",
                err,
            )
        log.exception(
            "[WSGI] create_app() FAILED at import — fallback to monolith: %s", e,
        )
        # Fallback intentionnel : si la factory casse, le monolithe charge
        # toujours ses 21 BPs via station_web.py L501+.
        from station_web import app as _app
        log.warning(
            "[WSGI] Monolith fallback loaded — %d routes",
            len(list(_app.url_map.iter_rules())),
        )
        return _app


app = _build_app()


if __name__ == "__main__":
    raise SystemExit(
        "Lancer via: gunicorn wsgi:app --workers 4 --threads 4 --bind 0.0.0.0:5003"
    )
