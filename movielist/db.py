"""Read-only MySQL/MariaDB connection pool for the Kodi video database.

Defense in depth: every connection is placed in READ ONLY transaction
mode so that even a buggy or malicious query cannot modify Kodi data.
The application is additionally expected to run with a SELECT-only
MySQL account (see scripts/setup_readonly_user.sql).
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any

import pymysql
from pymysql.connections import Connection

from .config import Settings

log = logging.getLogger(__name__)

_READ_ONLY_SESSION_SQL = "SET SESSION TRANSACTION READ ONLY"


class DatabaseUnavailable(RuntimeError):
    """Raised when the Kodi database cannot be reached or queried."""


class _Pool:
    """A minimal thread-safe connection pool with health checks."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._pool: queue.LifoQueue[Connection] = queue.LifoQueue(
            maxsize=settings.kodi_db_pool_size
        )
        self._lock = threading.Lock()

    def _new_connection(self) -> Connection:
        s = self._settings
        conn = pymysql.connect(
            host=s.kodi_db_host,
            port=s.kodi_db_port,
            user=s.kodi_db_user,
            password=s.kodi_db_password,
            database=s.kodi_db_name,
            connect_timeout=s.kodi_db_connect_timeout,
            read_timeout=s.kodi_db_read_timeout,
            write_timeout=s.kodi_db_read_timeout,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
        with conn.cursor() as cur:
            cur.execute(_READ_ONLY_SESSION_SQL)
        return conn

    def acquire(self) -> Connection:
        try:
            conn = self._pool.get_nowait()
        except queue.Empty:
            conn = None
        if conn is not None:
            try:
                conn.ping(reconnect=True)
                with conn.cursor() as cur:
                    cur.execute(_READ_ONLY_SESSION_SQL)
                return conn
            except Exception:
                log.warning("Discarding stale pooled connection", exc_info=True)
        try:
            return self._new_connection()
        except pymysql.MySQLError as exc:
            raise DatabaseUnavailable(
                f"Cannot connect to Kodi database "
                f"({self._settings.kodi_db_host}:{self._settings.kodi_db_port}/"
                f"{self._settings.kodi_db_name}) as user "
                f"{self._settings.kodi_db_user!r}: {type(exc).__name__}"
            ) from exc

    def release(self, conn: Connection) -> None:
        try:
            if not conn.open:
                return
            try:
                self._pool.put_nowait(conn)
            except queue.Full:
                conn.close()
        except Exception:
            log.warning("Error releasing connection", exc_info=True)

    def close_all(self) -> None:
        while True:
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                return
            try:
                conn.close()
            except Exception:
                pass


class Database:
    """Public facade: run parameterized read queries against Kodi."""

    def __init__(self, settings: Settings, pool: _Pool | None = None):
        self._settings = settings
        self._pool = pool if pool is not None else _Pool(settings)

    @property
    def pool(self) -> _Pool:
        return self._pool

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        """Execute a parameterized SELECT and return all rows."""
        conn = self._pool.acquire()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
        except pymysql.MySQLError as exc:
            raise DatabaseUnavailable(
                f"Kodi database query failed: {type(exc).__name__}"
            ) from exc
        finally:
            self._pool.release(conn)

    def query_one(
        self, sql: str, params: tuple | list = ()
    ) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def ping(self) -> bool:
        try:
            row = self.query_one("SELECT 1 AS ok")
            return bool(row)
        except DatabaseUnavailable:
            return False

    def close(self) -> None:
        self._pool.close_all()
