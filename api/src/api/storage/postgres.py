"""Postgres implementation of the Storage port (psycopg 3 + a small connection pool).

Selected when PH_DATABASE_URL is set. Works with a direct connection or Supabase's pooled
connection strings (session or transaction mode): no server-side prepared statements, and every
transaction runs on one pooled connection that goes back to the pool when it ends.

Calls are blocking, like SqliteStorage's; async code runs them via asyncio.to_thread.
Unlike SQLite there is no global write lock: the API and the nightly checker write concurrently
under MVCC. The one read-then-write that needs serialising (TESS signal-ID assignment for a star)
takes a per-star advisory lock, see discoveries_with_prefix().
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from importlib import resources
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from api.contract import Discovery, Sphere, StarTarget
from api.models import JobRecord, JobStatus, JobStep, TrapRecord
from api.timeutil import iso, parse

log = logging.getLogger(__name__)

# Held for the whole migration run, so an API instance and the nightly checker starting at the
# same moment don't both apply the same file.
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


class PostgresStorage:
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

    # traps ---------------------------------------------------------------

    @staticmethod
    def _trap(row: dict[str, Any]) -> TrapRecord:
        sphere = star = None
        if row["kind"] == "sky":
            sphere = Sphere(
                ra_deg=row["ra_deg"], dec_deg=row["dec_deg"], radius_deg=row["radius_deg"]
            )
        else:
            star = StarTarget(tic_id=row["tic_id"])
        return TrapRecord(
            id=row["id"],
            player_id=row["player_id"],
            kind=row["kind"],
            sphere=sphere,
            star=star,
            created_at=_utc(row["created_at"]),
            last_checked_at=_utc(row["last_checked_at"]),
            last_tess_marker=row["last_tess_marker"],
        )

    def create_trap(self, trap: TrapRecord) -> None:
        s, t = trap.sphere, trap.star
        self._exec(
            "INSERT INTO traps (id, player_id, kind, ra_deg, dec_deg, radius_deg, tic_id,"
            " created_at, last_checked_at, last_tess_marker)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                trap.id,
                trap.player_id,
                trap.kind,
                s.ra_deg if s else None,
                s.dec_deg if s else None,
                s.radius_deg if s else None,
                t.tic_id if t else None,
                trap.created_at,
                trap.last_checked_at,
                trap.last_tess_marker,
            ),
        )

    def get_trap(self, trap_id: str) -> TrapRecord | None:
        row = self._one("SELECT * FROM traps WHERE id = %s", (trap_id,))
        return self._trap(row) if row else None

    def list_traps(self, player_id: str) -> list[TrapRecord]:
        rows = self._all(
            "SELECT * FROM traps WHERE player_id = %s ORDER BY created_at DESC, id", (player_id,)
        )
        return [self._trap(r) for r in rows]

    def count_traps(self, player_id: str) -> int:
        return self._scalar("SELECT COUNT(*) FROM traps WHERE player_id = %s", (player_id,))

    def iter_traps(self) -> Iterator[TrapRecord]:
        rows = self._all("SELECT * FROM traps ORDER BY created_at, id")
        return iter([self._trap(r) for r in rows])

    def delete_trap(self, player_id: str, trap_id: str) -> bool:
        n = self._exec("DELETE FROM traps WHERE id = %s AND player_id = %s", (trap_id, player_id))
        return n > 0

    def set_trap_checked(
        self, trap_id: str, *, last_checked_at: datetime | None = None, marker: str | None = None
    ) -> None:
        if last_checked_at is not None:
            self._exec(
                "UPDATE traps SET last_checked_at = %s WHERE id = %s", (last_checked_at, trap_id)
            )
        if marker is not None:
            self._exec("UPDATE traps SET last_tess_marker = %s WHERE id = %s", (marker, trap_id))

    # discoveries and catches ----------------------------------------------

    def get_discovery(self, discovery_id: str) -> Discovery | None:
        row = self._one(
            "SELECT record::text AS record FROM discoveries WHERE id = %s", (discovery_id,)
        )
        return Discovery.model_validate_json(row["record"]) if row else None

    def put_discovery(self, d: Discovery) -> None:
        self._exec(
            "INSERT INTO discoveries (id, source, type, detected_at, record)"
            " VALUES (%s,%s,%s,%s,%s::jsonb)"
            " ON CONFLICT (id) DO UPDATE SET source = excluded.source, type = excluded.type,"
            " detected_at = excluded.detected_at, record = excluded.record",
            (d.id, d.source, d.type.value, d.detected_at, d.model_dump_json()),
        )

    def discoveries_with_prefix(self, prefix: str) -> list[Discovery]:
        """Inside atomic() this also locks the prefix until commit.

        catalog.ingest_hunt reads a star's stored signals here, then assigns IDs and writes. An API
        hunt and the nightly re-hunt of the same star must not interleave that, or both could
        assign the same new ID to different signals. SQLite gets this from its single writer.
        """
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._conn() as conn:
            if self._tx.get() is not None:
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (prefix,))
            rows = conn.execute(
                "SELECT record::text FROM discoveries WHERE id LIKE %s ESCAPE '\\' ORDER BY id",
                (escaped + "%",),
            ).fetchall()
        return [Discovery.model_validate_json(r[0]) for r in rows]

    def add_catch(
        self, player_id: str, discovery_id: str, trap_id: str | None, caught_at: datetime
    ) -> bool:
        n = self._exec(
            "INSERT INTO catches (player_id, discovery_id, trap_id, caught_at)"
            " VALUES (%s,%s,%s,%s) ON CONFLICT (player_id, discovery_id) DO NOTHING",
            (player_id, discovery_id, trap_id, caught_at),
        )
        return n > 0

    def has_catch(self, player_id: str, discovery_id: str) -> bool:
        row = self._one(
            "SELECT 1 FROM catches WHERE player_id = %s AND discovery_id = %s",
            (player_id, discovery_id),
        )
        return row is not None

    def list_catches(
        self, player_id: str, limit: int, before: tuple[str, str] | None
    ) -> list[tuple[Discovery, str]]:
        sql = (
            "SELECT d.record::text AS record, c.caught_at FROM catches c JOIN discoveries d"
            " ON d.id = c.discovery_id WHERE c.player_id = %s"
        )
        params: list = [player_id]
        if before is not None:
            try:
                before_at = parse(before[0])
            except ValueError:
                return []  # a forged cursor: nothing sorts before it
            if before_at is None:
                return []
            if before_at.tzinfo is None:
                before_at = before_at.replace(tzinfo=UTC)
            sql += " AND (c.caught_at, c.discovery_id) < (%s, %s)"
            params += [before_at, before[1]]
        sql += " ORDER BY c.caught_at DESC, c.discovery_id DESC LIMIT %s"
        params.append(limit)
        rows = self._all(sql, tuple(params))
        return [(Discovery.model_validate_json(r["record"]), iso(r["caught_at"])) for r in rows]

    def count_catches(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM catches")

    # jobs -------------------------------------------------------------------

    @staticmethod
    def _job(row: dict[str, Any]) -> JobRecord:
        return JobRecord(
            id=row["id"],
            player_id=row["player_id"],
            trap_id=row["trap_id"],
            tic_id=row["tic_id"],
            status=row["status"],
            steps=row["steps"],
            result_ids=row["result_ids"],
            error=row["error"],
            created_at=_utc(row["created_at"]),
            started_at=_utc(row["started_at"]),
            finished_at=_utc(row["finished_at"]),
        )

    def create_job(self, job: JobRecord) -> None:
        self._exec(
            "INSERT INTO jobs (id, player_id, trap_id, tic_id, status, steps, created_at)"
            " VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)",
            (
                job.id,
                job.player_id,
                job.trap_id,
                job.tic_id,
                job.status,
                json.dumps([s.model_dump(mode="json") for s in job.steps]),
                job.created_at,
            ),
        )

    def get_job(self, job_id: str) -> JobRecord | None:
        row = self._one("SELECT * FROM jobs WHERE id = %s", (job_id,))
        return self._job(row) if row else None

    def set_job_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        at: datetime,
        result_ids: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        column = "started_at" if status == "running" else "finished_at"
        self._exec(
            f"UPDATE jobs SET status = %s, {column} = %s, error = COALESCE(%s, error),"
            " result_ids = COALESCE(%s::jsonb, result_ids) WHERE id = %s",
            (status, at, error, json.dumps(result_ids) if result_ids is not None else None, job_id),
        )

    def append_job_step(self, job_id: str, step: JobStep) -> None:
        self._exec(
            "UPDATE jobs SET steps = steps || jsonb_build_array(%s::jsonb) WHERE id = %s",
            (step.model_dump_json(), job_id),
        )

    def queue_position(self, job_id: str) -> int | None:
        return self._scalar(
            "SELECT CASE WHEN j.status = 'queued' THEN"
            " (SELECT COUNT(*) FROM jobs q WHERE q.status = 'queued' AND q.seq < j.seq) + 1 END"
            " FROM (SELECT 1) one LEFT JOIN jobs j ON j.id = %s",
            (job_id,),
        )

    def count_pending_jobs(self, player_id: str) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM jobs WHERE player_id = %s AND status IN ('queued', 'running')",
            (player_id,),
        )

    def fail_unfinished_jobs(self, reason: str, at: datetime) -> int:
        return self._exec(
            "UPDATE jobs SET status = 'failed', error = %s, finished_at = %s"
            " WHERE status IN ('queued', 'running')",
            (reason, at),
        )
