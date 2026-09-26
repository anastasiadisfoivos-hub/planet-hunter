"""Postgres implementation of the Storage port (psycopg 3 + a small connection pool).

Selected when PH_DATABASE_URL is set. Works with a direct connection or Supabase's pooled
connection strings (session or transaction mode): no server-side prepared statements, and every
transaction runs on one pooled connection that goes back to the pool when it ends.

Calls are blocking, like SqliteStorage's; async code runs them via asyncio.to_thread.
Unlike SQLite there is no global write lock: the API and `api.finder_ingest` write concurrently
under MVCC.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from importlib import resources
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from api.storage.finder_sql import FinderSql
from api.storage.monitor_sql import MonitorSql

log = logging.getLogger(__name__)

# Held for the whole migration run, so an API instance and an ingest job starting
# at the same moment don't both apply the same file.
_MIGRATION_LOCK = 0x70685F6D6967  # "ph_mig"


def migration_files() -> list[tuple[str, str]]:
    """(version, sql) for every migrations/NNNN_*.sql, in order."""
    folder = resources.files("api.storage").joinpath("migrations")
    files = sorted(f for f in folder.iterdir() if f.name.endswith(".sql"))
    return [(f.name.removesuffix(".sql"), f.read_text()) for f in files]


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply pending migrations in one transaction. Idempotent; returns the versions applied."""
    applied_now = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for version, sql in migration_files():
            if version in done:
                continue
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied_now.append(version)
    if applied_now:
        log.info("applied migrations: %s", ", ".join(applied_now))
    return applied_now


def _utc(dt: datetime | None) -> datetime | None:
    return dt.astimezone(UTC) if dt is not None else None


class PostgresStorage(FinderSql, MonitorSql):
    PH = "%s"
    FOR_UPDATE = " FOR UPDATE"

    def __init__(
        self,
        url: str,
        *,
        pool_min: int = 1,
        pool_max: int = 5,
        timeout_s: float = 5.0,
        statement_timeout_ms: int = 15000,
    ) -> None:
        def configure(conn: psycopg.Connection) -> None:
            # Session-level: exact on direct/session-mode connections, best effort behind a
            # transaction-mode pooler (where the server role's own default applies).
            conn.execute(f"SET statement_timeout = {int(statement_timeout_ms)}")

        self._pool = ConnectionPool(
            url,
            min_size=pool_min,
            max_size=pool_max,
            timeout=timeout_s,  # wait for a free connection at most this long
            max_idle=300,  # hosted poolers drop idle clients; recycle before they do
            check=ConnectionPool.check_connection,
            configure=configure,
            kwargs={
                "autocommit": True,
                "prepare_threshold": None,  # transaction-mode poolers can't keep prepared stmts
                "connect_timeout": max(1, round(timeout_s)),
                "application_name": "planet-hunter-api",
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 3,
            },
            name="planet-hunter",
            open=False,
        )
        self._pool.open(wait=True, timeout=timeout_s * 2)
        # The connection this context's open atomic() block is using, if any.
        self._tx: ContextVar[psycopg.Connection | None] = ContextVar("ph_tx", default=None)
        with self._pool.connection() as conn:
            migrate(conn)

    def close(self) -> None:
        self._pool.close()

    @contextmanager
    def atomic(self) -> Iterator[None]:
        """One transaction; nested calls join the outer one."""
        if self._tx.get() is not None:
            yield
            return
        with self._pool.connection() as conn, conn.transaction():
            token = self._tx.set(conn)
            try:
                yield
            finally:
                self._tx.reset(token)

    @contextmanager
    def _conn(self) -> Iterator[psycopg.Connection]:
        """The open transaction's connection, or a pooled one in autocommit mode."""
        conn = self._tx.get()
        if conn is not None:
            yield conn
        else:
            with self._pool.connection() as conn:
                yield conn

    def _exec(self, sql: str, params: tuple = ()) -> int:
        with self._conn() as conn:
            return conn.execute(sql, params).rowcount

    def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._conn() as conn, conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        with self._conn() as conn, conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(sql, params).fetchone()

    def _scalar(self, sql: str, params: tuple = ()) -> Any:
        with self._conn() as conn:
            return conn.execute(sql, params).fetchone()[0]

    # finder_sql / monitor_sql hooks
    def _j(self, obj: Any) -> Jsonb:
        return Jsonb(obj)

    def _jo(self, value: Any) -> Any:
        return value

    def _t(self, dt: datetime | None) -> datetime | None:
        return dt

    def _to(self, value: Any) -> datetime | None:
        return _utc(value)
