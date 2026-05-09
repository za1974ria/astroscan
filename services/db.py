"""Context manager SQLite centralisé — WAL, busy_timeout, row_factory.

Extrait et renforcé depuis station_web.py.
Usage :
    from services.db import get_db
    with get_db('/path/to/db') as conn:
        rows = conn.execute('SELECT ...').fetchall()
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager

log = logging.getLogger(__name__)

# Verrou global léger : évite les "database is locked" sur connexions concurrentes
# Chaque worker gunicorn a son propre verrou (mémoire séparée par process).
_lock = threading.Lock()

# Chemins principaux — importer si besoin depuis config
DB_MAIN          = "/root/astro_scan/data/archive_stellaire.db"
DB_WEATHER       = "/root/astro_scan/weather_bulletins.db"
DB_VISITORS      = "/root/astro_scan/data/visitors.db"
DB_PUSH          = "/root/astro_scan/data/push_subscriptions.db"
DB_ALERTS_SENT   = "/root/astro_scan/data/alerts_sent.db"

_ALL_PRODUCTION_DBS = [DB_MAIN, DB_WEATHER, DB_VISITORS, DB_PUSH, DB_ALERTS_SENT]


@contextmanager
def get_db(path=None):
    """Connexion SQLite avec WAL, busy_timeout et commit/rollback automatique.

    Example:
        with get_db() as conn:
            rows = conn.execute('SELECT * FROM visitor_log LIMIT 10').fetchall()
    """
    db_path = path or DB_MAIN
    with _lock:
        conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA cache_size=-32000")
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_wal(path):
    """Active WAL mode sur une base SQLite (idempotent, sans transaction)."""
    try:
        conn = sqlite3.connect(path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA cache_size=-32000")
        conn.close()
        log.info("WAL activé : %s", path)
    except Exception as e:
        log.warning("init_wal(%s) : %s", path, e)


def init_all_wal():
    """Active WAL sur toutes les bases de production au démarrage."""
    import os
    for path in _ALL_PRODUCTION_DBS:
        if os.path.exists(path):
            init_wal(path)
