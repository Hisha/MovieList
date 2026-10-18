"""Read-only enforcement: static analysis and connection behavior."""

from __future__ import annotations

import ast
import pathlib

import pytest

import movielist
from movielist import app as app_module
from movielist import artwork, config, db, kodi, ttlcache
from movielist.config import Settings
from movielist.db import Database, DatabaseUnavailable

APP_MODULES = [config, db, kodi, ttlcache, artwork, app_module]

SQL_KEYWORDS = {
    "select", "insert", "update", "delete", "replace", "alter", "drop",
    "create", "truncate", "grant", "revoke", "call", "load", "rename",
    "merge", "upsert", "set", "show", "describe", "desc", "explain",
}

ALLOWED_SQL_STARTS = ("select", "show", "describe", "desc", "explain")


def _sql_string_literals(module) -> list[str]:
    source = pathlib.Path(module.__file__).read_text()
    tree = ast.parse(source)
    literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.strip()
            first = text.split(None, 1)[0].lower().rstrip(";") if text else ""
            if first in SQL_KEYWORDS:
                literals.append(text)
    return literals


def test_no_write_sql_in_application_modules():
    for module in APP_MODULES:
        for literal in _sql_string_literals(module):
            first = literal.split(None, 1)[0].lower().rstrip(";")
            if first == "set":
                assert literal.upper().startswith("SET SESSION"), literal
                continue
            assert first in ALLOWED_SQL_STARTS, (
                f"{module.__name__} contains non-read SQL: {literal[:80]!r}"
            )


def test_pool_enforces_read_only_session(monkeypatch):
    executed = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            executed.append(sql)

        def fetchall(self):
            return [{"ok": 1}]

        def fetchone(self):
            return {"ok": 1}

    class FakeConnection:
        open = True

        def cursor(self):
            return FakeCursor()

        def ping(self, reconnect=False):
            pass

        def close(self):
            self.open = False

    monkeypatch.setattr(
        "pymysql.connect", lambda **kwargs: FakeConnection()
    )
    settings = Settings(kodi_db_password="secret")
    database = Database(settings)
    row = database.query_one("SELECT 1 AS ok")
    assert row == {"ok": 1}
    assert "SET SESSION TRANSACTION READ ONLY" in executed


def test_database_unavailable_wraps_connection_errors(monkeypatch):
    import pymysql

    def boom(**kwargs):
        raise pymysql.MySQLError("refused")

    monkeypatch.setattr("pymysql.connect", boom)
    database = Database(Settings())
    with pytest.raises(DatabaseUnavailable):
        database.query("SELECT 1")


def test_error_messages_do_not_include_password():
    exc = DatabaseUnavailable(
        "Cannot connect to Kodi database (h:3306/db) as user 'u': MySQLError"
    )
    assert "password" not in str(exc).lower()
    assert "secret" not in str(exc)


def test_main_module_has_no_sql():
    main_path = pathlib.Path(movielist.__file__).parent.parent / "main.py"
    source = main_path.read_text().lower()
    for verb in ("insert ", "update ", "delete ", "drop ", "truncate ",
                 "alter ", "replace "):
        assert verb not in source
