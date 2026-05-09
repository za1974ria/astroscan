"""Integration tests — SQLite WAL accessor.

Uses a temporary on-disk SQLite file (not the production DB) to validate
that the ``get_db`` context manager correctly applies WAL pragmas, commits
on success, rolls back on exception, and supports concurrent reads.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    """Fresh on-disk SQLite DB initialised with WAL pragmas."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    conn.commit()
    conn.close()
    return str(db_file)


def test_get_db_applies_wal_mode(tmp_db):
    from services.db import get_db

    with get_db(tmp_db) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_get_db_commits_on_success(tmp_db):
    from services.db import get_db

    with get_db(tmp_db) as conn:
        conn.execute("INSERT INTO t (val) VALUES (?)", ("hello",))

    # Re-open with a fresh connection — committed value must be visible
    with get_db(tmp_db) as conn:
        rows = conn.execute("SELECT val FROM t").fetchall()
    assert [r["val"] for r in rows] == ["hello"]


def test_get_db_rolls_back_on_exception(tmp_db):
    from services.db import get_db

    with pytest.raises(RuntimeError):
        with get_db(tmp_db) as conn:
            conn.execute("INSERT INTO t (val) VALUES (?)", ("should-rollback",))
            raise RuntimeError("boom")

    with get_db(tmp_db) as conn:
        rows = conn.execute("SELECT val FROM t").fetchall()
    assert [r["val"] for r in rows] == []


def test_get_db_supports_concurrent_reads(tmp_db):
    """WAL mode allows readers in parallel without 'database is locked'."""
    from services.db import get_db

    # Seed a row
    with get_db(tmp_db) as conn:
        conn.execute("INSERT INTO t (val) VALUES (?)", ("concurrent",))

    results: list[str] = []
    errors: list[Exception] = []

    def reader():
        try:
            with get_db(tmp_db) as conn:
                rows = conn.execute("SELECT val FROM t").fetchall()
                time.sleep(0.05)  # hold the read briefly
                results.append(rows[0]["val"])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Concurrent readers raised: {errors}"
    assert results == ["concurrent"] * 4


def test_db_module_exposes_production_paths():
    from services import db

    assert hasattr(db, "DB_MAIN")
    assert hasattr(db, "_ALL_PRODUCTION_DBS")
    assert len(db._ALL_PRODUCTION_DBS) >= 3
    assert all(p.endswith(".db") for p in db._ALL_PRODUCTION_DBS)
