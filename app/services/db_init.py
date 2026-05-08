"""PASS 22.2 (2026-05-08) — DB initialization helpers + config constants.

Extrait depuis station_web.py lors de PASS 22.2 :
- 5 constantes config (timeouts requests + cache cap + Claude API budget)
- 2 chemins disque (DB principale + image télescope live)
- 3 fonctions d'init DB (WAL mode + visits table + session tracking)

Le shim ``station_web`` ré-exporte les 10 noms pour préserver la rétro-compat
des imports existants (``app/workers/translate_worker.py:37`` importe
``DB_PATH`` ; les usages internes au monolith continuent via la liaison
du shim au namespace de station_web).

``STATION`` est importé canonique depuis ``app.services.station_state``
(no cycle au load).

Constantes mutables NON migrées (cf. PASS 22.2 prompt) :
- ``STATION`` : path racine, conservé dans station_web (re-export depuis
  station_state à la ligne 190 — déjà l'origine canonique)
- ``START_TIME`` : timestamp boot, sémantique liée au boot du monolith
- ``CLAUDE_CALL_COUNT``, ``CLAUDE_80_WARNING_SENT`` : compteurs API mutables
  réassignés au runtime (sémantique de mutation top-level)
- ``GROQ_CALL_COUNT``, ``COLLECTOR_LAST_RUN`` : idem
- ``TRANSLATE_CACHE``, ``TRANSLATION_CACHE``, ``TRANSLATE_TTL_SECONDS``,
  ``TRANSLATE_LAST_REQUEST_TS`` : utilisés par translate_worker via lazy
  import — extraction casserait le contrat de mutation cross-module
- ``_REQ_ORIGINAL_REQUEST`` : référence du monkey-patch de requests
"""
from __future__ import annotations

import os
import sqlite3

from app.services.station_state import STATION

# ── Config HTTP timeouts (monkey-patch requests) ─────────────────────
_REQ_DEFAULT_TIMEOUT: int = 10        # secondes par défaut sur tout requests.get/post
_REQ_SLOW_MS: int = 1500              # seuil log "slow request"
_REQ_VERY_SLOW_MS: int = 5000         # seuil log "very slow request"

# ── Cache caps ───────────────────────────────────────────────────────
MAX_CACHE_SIZE: int = 500             # nombre max d'entrées dans le cache services
CLAUDE_MAX_CALLS: int = 100           # quota mensuel d'appels Claude API

# ── Chemins disque (calculés depuis STATION canonique) ───────────────
DB_PATH: str = f'{STATION}/data/archive_stellaire.db'
IMG_PATH: str = f'{STATION}/telescope_live/current_live.jpg'


def _init_sqlite_wal():
    """Active WAL mode sur toutes les DB SQLite au démarrage."""
    import sqlite3 as _sq
    for _db in [DB_PATH]:
        try:
            _c = _sq.connect(_db)
            _c.execute("PRAGMA journal_mode=WAL")
            _c.execute("PRAGMA synchronous=NORMAL")
            _c.execute("PRAGMA cache_size=10000")
            _c.commit()
            _c.close()
        except Exception as _e:
            print(f"[WAL] {_db}: {_e}")


def _init_visits_table():
    """Crée la table visits et insère la ligne initiale si besoin."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visits (id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0)
    """)
    conn.execute("INSERT OR IGNORE INTO visits (id, count) VALUES (1, 0)")
    conn.commit()
    conn.close()


def _init_session_tracking_db():
    """Colonne session_id sur visitor_log + table session_time (sans perte de données)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(visitor_log)").fetchall()]
        if cols and "session_id" not in cols:
            cur.execute("ALTER TABLE visitor_log ADD COLUMN session_id TEXT")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS session_time (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                path TEXT,
                duration INTEGER,
                created_at TEXT
            )
            """
        )
        # Index légers: accélère stats live, agrégations session et tri temporel.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_visitor_log_ip ON visitor_log(ip)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_visitor_log_session_id ON visitor_log(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_visitor_log_visited_at ON visitor_log(visited_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_visitor_log_country_code ON visitor_log(country_code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_session_time_session_id ON session_time(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_session_time_created_at ON session_time(created_at)")
        # Index UNIQUE sur (ip, session_id) : empêche les doublons entre workers Gunicorn.
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_visitor_log_ip_session "
            "ON visitor_log(ip, COALESCE(session_id, ''))"
        )
        # Nouvelles colonnes visitor_log (ajout sans perte si absentes)
        existing_cols = [r[1] for r in cur.execute("PRAGMA table_info(visitor_log)").fetchall()]
        for col, typedef in [
            ("isp", "TEXT DEFAULT ''"),
            ("human_score", "INTEGER DEFAULT -1"),
            ("is_owner", "INTEGER DEFAULT 0"),
        ]:
            if col not in existing_cols:
                cur.execute(f"ALTER TABLE visitor_log ADD COLUMN {col} {typedef}")
        # Table page_views : chaque vue de page (N par session)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS page_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                ip TEXT NOT NULL,
                path TEXT NOT NULL,
                visited_at TEXT NOT NULL DEFAULT (datetime('now')),
                referrer TEXT DEFAULT ''
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_page_views_session ON page_views(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_page_views_path ON page_views(path)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_page_views_visited_at ON page_views(visited_at)")
        # Table owner_ips : IPs du propriétaire
        cur.execute("""
            CREATE TABLE IF NOT EXISTS owner_ips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL UNIQUE,
                label TEXT DEFAULT '',
                added_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass


__all__ = [
    "_REQ_DEFAULT_TIMEOUT",
    "_REQ_SLOW_MS",
    "_REQ_VERY_SLOW_MS",
    "MAX_CACHE_SIZE",
    "CLAUDE_MAX_CALLS",
    "DB_PATH",
    "IMG_PATH",
    "_init_sqlite_wal",
    "_init_visits_table",
    "_init_session_tracking_db",
]
