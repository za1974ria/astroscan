"""
app.utils.db — Façade DB centralisée pour les Blueprints AstroScan.

Deux modes d'accès :
  1. Flask request-scoped — get_db() stocke la connexion dans flask.g
     et la ferme automatiquement à la fin de la requête via teardown.
  2. Hors-Flask — db_session(path) context manager (re-export services.db).

Chemins DB disponibles :
    DB_MAIN    = archive_stellaire.db  (données scientifiques principales)
    DB_WEATHER = weather_bulletins.db  (météo)
    DB_VISITORS = visitors.db          (analytics visiteurs)
    DB_PUSH    = push_subscriptions.db
    DB_ALERTS  = alerts_sent.db

Usage dans les Blueprints :
    from app.utils.db import get_db, fetch_all, fetch_one, execute_query

    @bp.route('/api/example')
    def example():
        conn = get_db()
        rows = fetch_all(conn, 'SELECT * FROM visitor_log LIMIT 10')
        return jsonify(rows)

Usage hors-Flask (scripts, tests) :
    from app.utils.db import db_session, DB_WEATHER
    with db_session(DB_WEATHER) as conn:
        rows = conn.execute('SELECT * FROM weather_bulletins LIMIT 5').fetchall()
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Re-export des constantes et du context manager depuis services.db
# ---------------------------------------------------------------------------
try:
    from services.db import (  # noqa: F401
        DB_MAIN,
        DB_WEATHER,
        DB_VISITORS,
        DB_PUSH,
        DB_ALERTS_SENT,
        get_db as db_session,   # context manager pour usage hors-Flask
        init_wal,
        init_all_wal,
    )
    _SERVICES_DB_AVAILABLE = True
except ImportError:
    _SERVICES_DB_AVAILABLE = False
    log.warning("[db] services.db introuvable — fallback minimal")

    import os
    from contextlib import contextmanager

    _BASE = os.environ.get("STATION", "/root/astro_scan")
    DB_MAIN      = f"{_BASE}/data/archive_stellaire.db"     # type: ignore[assignment]
    DB_WEATHER   = f"{_BASE}/weather_bulletins.db"          # type: ignore[assignment]
    DB_VISITORS  = f"{_BASE}/data/visitors.db"              # type: ignore[assignment]
    DB_PUSH      = f"{_BASE}/data/push_subscriptions.db"    # type: ignore[assignment]
    DB_ALERTS_SENT = f"{_BASE}/data/alerts_sent.db"         # type: ignore[assignment]

    @contextmanager  # type: ignore[misc]
    def db_session(path: Optional[str] = None):
        conn = sqlite3.connect(path or DB_MAIN, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_wal(path: str) -> None:  # type: ignore[misc]
        pass

    def init_all_wal() -> None:  # type: ignore[misc]
        pass


# ---------------------------------------------------------------------------
# get_db() — connexion Flask request-scoped (stockée dans flask.g)
# ---------------------------------------------------------------------------

def get_db(path: Optional[str] = None) -> sqlite3.Connection:
    """Retourne une connexion SQLite liée au contexte Flask (flask.g).

    La connexion est ouverte une seule fois par requête et fermée
    automatiquement via le teardown enregistré dans le blueprint ou la factory.

    En dehors d'un contexte Flask, lève RuntimeError (utiliser db_session()).
    """
    try:
        from flask import g
    except RuntimeError as exc:
        raise RuntimeError(
            "get_db() nécessite un contexte Flask. "
            "Hors-Flask, utilisez: with db_session(path) as conn:"
        ) from exc

    db_path = path or DB_MAIN
    attr = f"_db_{db_path.replace('/', '_').replace('.', '_')}"

    conn: Optional[sqlite3.Connection] = getattr(g, attr, None)
    if conn is None:
        conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA cache_size=-32000")
        conn.row_factory = sqlite3.Row
        setattr(g, attr, conn)
    return conn


def close_db(path: Optional[str] = None, error: Any = None) -> None:
    """Teardown : ferme la connexion g-scoped. À appeler via app.teardown_appcontext."""
    try:
        from flask import g
    except RuntimeError:
        return
    db_path = path or DB_MAIN
    attr = f"_db_{db_path.replace('/', '_').replace('.', '_')}"
    conn = getattr(g, attr, None)
    if conn is not None:
        if error is None:
            try:
                conn.commit()
            except Exception:
                conn.rollback()
        conn.close()
        setattr(g, attr, None)


def register_teardown(app: Any) -> None:
    """Enregistre close_db sur l'app Flask pour fermeture automatique."""
    @app.teardown_appcontext
    def _teardown(error: Any = None) -> None:
        close_db(error=error)


# ---------------------------------------------------------------------------
# Helpers query — fetch_all, fetch_one, execute_query
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return row


def fetch_all(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
) -> list[dict]:
    """Exécute une SELECT et retourne une liste de dicts."""
    try:
        cur = conn.execute(sql, params)
        return [_row_to_dict(r) for r in cur.fetchall()]
    except Exception as exc:
        log.error("[db] fetch_all failed — %s | params=%s | err=%s", sql[:80], params, exc)
        return []


def fetch_one(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
) -> Optional[dict]:
    """Exécute une SELECT et retourne le premier résultat en dict, ou None."""
    try:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return _row_to_dict(row) if row else None
    except Exception as exc:
        log.error("[db] fetch_one failed — %s | params=%s | err=%s", sql[:80], params, exc)
        return None


def execute_query(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    commit: bool = False,
) -> Optional[sqlite3.Cursor]:
    """Exécute une requête INSERT/UPDATE/DELETE avec gestion d'erreur.

    Retourne le Cursor, ou None en cas d'erreur.
    """
    try:
        cur = conn.execute(sql, params)
        if commit:
            conn.commit()
        return cur
    except Exception as exc:
        log.error("[db] execute_query failed — %s | params=%s | err=%s", sql[:80], params, exc)
        return None
