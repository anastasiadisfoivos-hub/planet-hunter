"""SQLite implementation of the Storage port (stdlib sqlite3, one connection, one lock).

Local dev and tests. Schema: migrations/sqlite/NNNN_*.sql, the twins of the Postgres files, applied
in order once each and recorded in schema_migrations.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from importlib import resources
from typing import Any

from api.storage.finder_sql import FinderSql
from api.storage.monitor_sql import MonitorSql
from api.timeutil import iso, parse


def migration_files() -> list[tuple[str, str]]:
    folder = resources.files("api.storage").joinpath("migrations").joinpath("sqlite")
    files = sorted(f for f in folder.iterdir() if f.name.endswith(".sql"))
    return [(f.name.removesuffix(".sql"), f.read_text()) for f in files]


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class SqliteStorage(FinderSql, MonitorSql):
    PH = "?"
    FOR_UPDATE = ""  # BEGIN IMMEDIATE already serializes writers

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = 0
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self.migrate()

    def migrate(self) -> list[str]:
        applied = []
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations"
                " (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            done = {r[0] for r in self._conn.execute("SELECT version FROM schema_migrations")}
            for version, sql in migration_files():
                if version in done:
                    continue
                self._conn.executescript(
                    f"BEGIN;\n{sql}\nINSERT INTO schema_migrations VALUES"
                    f" ('{version}', strftime('%Y-%m-%dT%H:%M:%fZ'));\nCOMMIT;"
                )
                applied.append(version)
        return applied

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def atomic(self) -> Iterator[None]:
        """One transaction; nested calls join the outer one."""
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if outer:
                    self._conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outer:
                    self._conn.execute("COMMIT")

    def _exec(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _all(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    # finder_sql / monitor_sql hooks
    def _j(self, obj: Any) -> str:
        return _dump(obj)

    def _jo(self, value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    def _t(self, dt: datetime | None) -> str | None:
        return iso(dt) if dt is not None else None

    def _to(self, value: Any) -> datetime | None:
        return parse(value)
