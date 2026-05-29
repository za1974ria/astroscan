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

import sqlite3

from app.services.station_state import STATION

# ── Config HTTP timeouts (monkey-patch requests) ─────────────────────
_REQ_DEFAULT_TIMEOUT: int = 10  # secondes par défaut sur tout requests.get/post
_REQ_SLOW_MS: int = 1500  # seuil log "slow request"
_REQ_VERY_SLOW_MS: int = 5000  # seuil log "very slow request"

# ── Cache caps ───────────────────────────────────────────────────────
MAX_CACHE_SIZE: int = 500  # nombre max d'entrées dans le cache services
CLAUDE_MAX_CALLS: int = 100  # quota mensuel d'appels Claude API


def _current_db_path() -> str:
    """Resolve the active SQLite path at call time, aligned with the canonical
    ``app.services.paths.DB_PATH``.

    Why dynamic resolution: ``paths.DB_PATH`` honours ``ASTROSCAN_DB_PATH`` /
    ``ASTROSCAN_DATA_DIR`` / ``ASTROSCAN_HOME`` at *paths* import time. The
    legacy literal here used to be ``f'{STATION}/data/archive_stellaire.db'``
    which ignored ``ASTROSCAN_DATA_DIR`` and therefore drifted away from the
    path actually queried by the export blueprint and other read-side
    callers (`app/blueprints/export/__init__.py`, `app/services/db_visitors.py`).
    Under a CI run setting ``ASTROSCAN_DATA_DIR=/tmp/dbvierge`` (or a shadow
    root from ``tests/conftest.py``), the init functions were creating
    ``visitor_log`` / ``observations`` in a DB that nobody read.

    By delegating to ``paths.DB_PATH`` at each call we guarantee that
    *creation* and *consumption* hit the same SQLite file. Import lives inside
    the function to avoid an import cycle at module load (paths is imported
    by app.__init__.py very early; db_init is pulled in by station_web).
    """
    try:
        from app.services.paths import DB_PATH as _PATHS_DB_PATH

        return _PATHS_DB_PATH
    except Exception:
        # Defensive only — should never happen in tree, but keeps the helper
        # callable in stripped-down environments.
        return f"{STATION}/data/archive_stellaire.db"


# ── Chemins disque ───────────────────────────────────────────────────
# Symbole module conservé pour rétro-compat (station_web ré-exporte ``DB_PATH``
# qui est ensuite lu par ``app/workers/translate_worker.py:40``). Sa valeur
# est désormais alignée sur la source canonique ``app.services.paths.DB_PATH``
# au lieu du legacy figé ``f'{STATION}/data/archive_stellaire.db'``.
DB_PATH: str = _current_db_path()
IMG_PATH: str = f"{STATION}/telescope_live/current_live.jpg"


def _init_sqlite_wal():
    """Active WAL mode sur toutes les DB SQLite au démarrage."""
    import sqlite3 as _sq

    for _db in [_current_db_path()]:
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
    conn = sqlite3.connect(_current_db_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visits (id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0)
    """)
    conn.execute("INSERT OR IGNORE INTO visits (id, count) VALUES (1, 0)")
    conn.commit()
    conn.close()


def _init_session_tracking_db():
    """Colonne session_id sur visitor_log + table session_time (sans perte de données)."""
    try:
        conn = sqlite3.connect(_current_db_path())
        cur = conn.cursor()
        # ── Bootstrap base vierge (fix_dbinit 2026-05-29) ───────────────
        # Sur une CI / DB fraîchement créée, `visitor_log` et `observations`
        # n'existaient pas, ce qui faisait planter en 500 les endpoints
        # /api/export/{visitors.csv,visitors.json,observations.json} et les
        # tests smoke associés (test_legacy_critiques + test_legacy_api_json).
        # En prod la table préexiste : les ALTER TABLE plus bas l'ont
        # progressivement enrichie. On reproduit ici la forme finale, en
        # IDEMPOTENT (CREATE TABLE IF NOT EXISTS) : aucune table existante
        # n'est touchée, on ne crée que ce qui manque.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS visitor_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT,
                country TEXT DEFAULT 'Unknown',
                country_code TEXT DEFAULT 'XX',
                city TEXT DEFAULT 'Unknown',
                region TEXT DEFAULT 'Unknown',
                flag TEXT DEFAULT 'XX',
                user_agent TEXT,
                path TEXT,
                visited_at TEXT DEFAULT (datetime('now')),
                session_id TEXT,
                ip_hash TEXT,
                lat REAL,
                lon REAL,
                continent TEXT DEFAULT 'Unknown',
                is_bot INTEGER DEFAULT 0,
                isp TEXT DEFAULT '',
                human_score INTEGER DEFAULT -1,
                is_owner INTEGER DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                image_path TEXT,
                source TEXT DEFAULT 'NASA_APOD',
                analyse_gemini TEXT,
                objets_detectes TEXT,
                anomalie INTEGER DEFAULT 0,
                score_confiance REAL DEFAULT 0.0,
                title TEXT DEFAULT '',
                rapport_fr TEXT DEFAULT ''
            )
            """
        )
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
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_visitor_log_session_id ON visitor_log(session_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_visitor_log_visited_at ON visitor_log(visited_at)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_visitor_log_country_code ON visitor_log(country_code)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_time_session_id ON session_time(session_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_time_created_at ON session_time(created_at)"
        )
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
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_page_views_visited_at ON page_views(visited_at)"
        )
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
