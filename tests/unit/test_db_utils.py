"""Unit tests — app.utils.db (façade DB Blueprints)."""
from __future__ import annotations

import sqlite3

import pytest
from flask import Flask, g

from app.utils import db as db_mod


pytestmark = pytest.mark.unit


def _tmp_db(tmp_path) -> str:
    p = tmp_path / "test.db"
    conn = sqlite3.connect(str(p))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO t (name) VALUES ('a'), ('b'), ('c')")
    conn.commit()
    conn.close()
    return str(p)


# ── Constants exposed ───────────────────────────────────────────────────────


def test_db_constants_paths_strings():
    assert isinstance(db_mod.DB_MAIN, str)
    assert isinstance(db_mod.DB_VISITORS, str)
    assert isinstance(db_mod.DB_WEATHER, str)
    assert isinstance(db_mod.DB_PUSH, str)
    assert isinstance(db_mod.DB_ALERTS_SENT, str)


def test_db_main_path_ends_correctly():
    assert db_mod.DB_MAIN.endswith("archive_stellaire.db")


# ── db_session context manager ───────────────────────────────────────────────


def test_db_session_yields_connection(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM t")
        n = cur.fetchone()[0]
    assert n == 3


def test_db_session_row_factory_is_row(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        row = conn.execute("SELECT id, name FROM t LIMIT 1").fetchone()
        # services.db returns rows as Row objects with dict-like access
        assert row is not None
        assert row["name"] in ("a", "b", "c")


# ── get_db (Flask request scope) ─────────────────────────────────────────────


def test_get_db_requires_flask_context():
    with pytest.raises(RuntimeError):
        db_mod.get_db("/tmp/nope.db")


def test_get_db_caches_in_g(tmp_path):
    path = _tmp_db(tmp_path)
    app = Flask(__name__)
    with app.app_context():
        c1 = db_mod.get_db(path)
        c2 = db_mod.get_db(path)
        assert c1 is c2
        row = c1.execute("SELECT name FROM t LIMIT 1").fetchone()
        assert row is not None


def test_close_db_releases_connection(tmp_path):
    path = _tmp_db(tmp_path)
    app = Flask(__name__)
    with app.app_context():
        c = db_mod.get_db(path)
        assert c is not None
        db_mod.close_db(path=path)
        attr = f"_db_{path.replace('/', '_').replace('.', '_')}"
        assert getattr(g, attr, None) is None


def test_close_db_in_app_context_with_no_connection():
    """close_db must be a no-op when no connection was opened in g."""
    app = Flask(__name__)
    with app.app_context():
        db_mod.close_db(path="/tmp/nope.db")


def test_register_teardown_attaches(tmp_path):
    app = Flask(__name__)
    db_mod.register_teardown(app)
    path = _tmp_db(tmp_path)
    with app.test_request_context("/"):
        db_mod.get_db(path)


# ── fetch_all / fetch_one / execute_query ───────────────────────────────────


def test_fetch_all_returns_list_of_dicts(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        rows = db_mod.fetch_all(conn, "SELECT id, name FROM t ORDER BY id")
    assert isinstance(rows, list)
    assert len(rows) == 3
    assert all("name" in r for r in rows)


def test_fetch_all_with_params(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        rows = db_mod.fetch_all(conn, "SELECT * FROM t WHERE name = ?", ("a",))
    assert len(rows) == 1
    assert rows[0]["name"] == "a"


def test_fetch_all_on_bad_sql_returns_empty(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        rows = db_mod.fetch_all(conn, "SELECT * FROM no_such_table")
    assert rows == []


def test_fetch_one_returns_dict(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        row = db_mod.fetch_one(conn, "SELECT name FROM t LIMIT 1")
    assert isinstance(row, dict)
    assert row["name"] in ("a", "b", "c")


def test_fetch_one_empty_returns_none(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        row = db_mod.fetch_one(conn, "SELECT name FROM t WHERE name = 'zzz'")
    assert row is None


def test_fetch_one_bad_sql_returns_none(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        row = db_mod.fetch_one(conn, "SELECT * FROM no_table")
    assert row is None


def test_execute_query_insert(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        cur = db_mod.execute_query(
            conn, "INSERT INTO t (name) VALUES (?)", ("z",), commit=True
        )
        assert cur is not None
        assert cur.rowcount == 1
        rows = db_mod.fetch_all(conn, "SELECT name FROM t WHERE name = 'z'")
    assert len(rows) == 1


def test_execute_query_bad_sql_returns_none(tmp_path):
    path = _tmp_db(tmp_path)
    with db_mod.db_session(path) as conn:
        cur = db_mod.execute_query(conn, "DELETE FROM no_table")
    assert cur is None
