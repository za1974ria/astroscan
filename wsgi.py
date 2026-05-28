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
# CHANTIER 2 (2026-05-23) : fallback monolithe désormais opt-in explicite.
# Par défaut, si create_app() échoue, l'exception est ré-élevée → systemd voit
# FAILED → restart loop visible. Cette variable permet la bascule legacy en
# secours manuel (debug, rollback contrôlé).
_ALLOW_MONOLITH_FALLBACK = os.environ.get(
    "ASTROSCAN_ALLOW_MONOLITH_FALLBACK", "0"
).strip() in ("1", "true", "yes", "on")


def _build_app():
    """Construit l'app Flask : factory en priorité, monolithe en repli.

    NOTE IMPORTANTE : station_web.py est TOUJOURS importé (avant ou après
    create_app), car il initialise des globals partagés (env vars, DB WAL,
    TLE_CACHE, threads collector) que les BPs utilisent via lazy-import
    (`from station_web import X`).
    """
    if _FORCE_MONOLITH:
        log.critical(
            "[WSGI][BOOT_MODE=monolith_forced] ASTROSCAN_FORCE_MONOLITH=1 — "
            "bypass create_app(). Production tourne sur le legacy station_web.app."
        )
        from station_web import app as _app
        _app.config["ASTROSCAN_BOOT_MODE"] = "monolith_forced"
        log.info("[WSGI][BOOT_MODE=monolith_forced] %d routes",
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
        _app.config["ASTROSCAN_BOOT_MODE"] = "factory"
        log.info(
            "[WSGI][BOOT_MODE=factory] create_app() loaded successfully — %d routes",
            len(list(_app.url_map.iter_rules())),
        )
        return _app
    except Exception as e:
        err = str(e).strip()
        # Trace systématique pour Sentry / journald avant toute décision.
        log.exception("[WSGI] create_app() exception trace:")

        # CHANTIER 2 (2026-05-23) : gated fallback. Sans opt-in explicite,
        # l'exception est ré-élevée → gunicorn refuse de démarrer → systemd
        # détecte FAILED → restart loop visible → opérateur alerté.
        if not _ALLOW_MONOLITH_FALLBACK:
            log.critical(
                "[WSGI][BOOT_MODE=hard_fail] create_app() FAILED and "
                "ASTROSCAN_ALLOW_MONOLITH_FALLBACK is OFF. "
                "Refusing to start on legacy monolith — fix the root cause: %s",
                err or repr(e)[:200],
            )
            # Sentry breadcrumb explicite si SDK chargé.
            try:
                import sentry_sdk
                sentry_sdk.capture_message(
                    f"AstroScan boot HARD FAIL (fallback disabled): {err or repr(e)[:200]}",
                    level="fatal",
                )
            except Exception:
                pass
            raise

        # Fallback explicitement autorisé par opérateur (mode secours).
        if err in ("SECRET_KEY", "NASA_API_KEY"):
            log.critical(
                "[WSGI][BOOT_MODE=monolith_fallback] create_app() aborted on env "
                "guard variable %s — fix .env immediately. Production runs in "
                "DEGRADED MODE on legacy station_web.app "
                "(ASTROSCAN_ALLOW_MONOLITH_FALLBACK=1).",
                err,
            )
        else:
            log.critical(
                "[WSGI][BOOT_MODE=monolith_fallback] create_app() FAILED at import "
                "— production runs on the LEGACY MONOLITH "
                "(ASTROSCAN_ALLOW_MONOLITH_FALLBACK=1). Investigate and fix: %s",
                e,
            )
        # Fallback intentionnel : si la factory casse, le monolithe charge
        # toujours ses 21 BPs via station_web.py L501+.
        from station_web import app as _app
        _app.config["ASTROSCAN_BOOT_MODE"] = "monolith_fallback"
        _app.config["ASTROSCAN_BOOT_FAILURE"] = err or repr(e)[:200]
        log.critical(
            "[WSGI][BOOT_MODE=monolith_fallback] Monolith loaded — %d routes. "
            "ALERT: this is NOT the standard boot path.",
            len(list(_app.url_map.iter_rules())),
        )
        try:
            import sentry_sdk
            sentry_sdk.capture_message(
                f"AstroScan boot fallback to monolith: {err or repr(e)[:200]}",
                level="error",
            )
        except Exception:
            pass
        return _app


app = _build_app()


if __name__ == "__main__":
    raise SystemExit(
        "Lancer via: gunicorn wsgi:app --workers 4 --threads 4 --bind 0.0.0.0:5003"
    )
