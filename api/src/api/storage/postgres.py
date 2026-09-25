"""Postgres implementation of the Storage port (psycopg 3 + a small connection pool).

Selected when PH_DATABASE_URL is set. Works with a direct connection or Supabase's pooled
connection strings (session or transaction mode): no server-side prepared statements, and every
transaction runs on one pooled connection that goes back to the pool when it ends.

Calls are blocking, like SqliteStorage's; async code runs them via asyncio.to_thread.
Unlike SQLite there is no global write lock: the API, `api.ingest` and the `api.precompute`
shards write concurrently under MVCC.
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

from api.models import JobRecord, JobStatus, JobStep, StoredAnalysis
from api.ports import EventMeta, EventQuery, EventRow, Upserted
from api.storage.events_sql import build_query

log = logging.getLogger(__name__)

# Held for the whole migration run, so an API instance and an ingest or precompute job starting
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

    # events ----------------------------------------------------------------------------

    def event_meta(self, ids: list[str]) -> dict[str, EventMeta]:
        if not ids:
            return {}
        rows = self._all(
            "SELECT id, source_hash, content_hash, images_checked_at,"
            " record->'images' AS images FROM events WHERE id = ANY(%s)",
            (list(ids),),
        )
        return {
            r["id"]: EventMeta(
                source_hash=r["source_hash"],
                content_hash=r["content_hash"],
                images_checked_at=_utc(r["images_checked_at"]),
                images=r["images"] or [],
            )
            for r in rows
        }

    def upsert_event(self, row: EventRow) -> Upserted:
        with self.atomic():
            old = self._one(
                "SELECT content_hash, images_checked_at FROM events WHERE id = %s FOR UPDATE",
                (row.id,),
            )
            if old is not None and old["content_hash"] == row.content_hash:
                if old["images_checked_at"] < row.images_checked_at:
                    self._exec(
                        "UPDATE events SET images_checked_at = %s WHERE id = %s",
                        (row.images_checked_at, row.id),
                    )
                return "unchanged"
            values = (
                row.type,
                row.category,
                row.frame,
                row.observed_at,
                row.ra_deg,
                row.dec_deg,
                row.confidence,
                row.has_images,
                row.from_latest_observed_window,
                Jsonb(row.record),
                row.source_hash,
                row.content_hash,
                row.images_checked_at,
                row.updated_at,
                row.id,
            )
            if old is None:
                self._exec(
                    "INSERT INTO events (type, category, frame, observed_at, ra_deg, dec_deg,"
                    " confidence, has_images, from_latest_observed_window, record, source_hash,"
                    " content_hash, images_checked_at, updated_at, id)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    values,
                )
            else:
                self._exec(
                    "UPDATE events SET type = %s, category = %s, frame = %s, observed_at = %s,"
                    " ra_deg = %s, dec_deg = %s, confidence = %s, has_images = %s,"
                    " from_latest_observed_window = %s, record = %s, source_hash = %s,"
                    " content_hash = %s, images_checked_at = %s, updated_at = %s WHERE id = %s",
                    values,
                )
                self._exec("DELETE FROM event_sources WHERE event_id = %s", (row.id,))
            for source in sorted(set(row.sources)):
                self._exec("INSERT INTO event_sources VALUES (%s, %s)", (row.id, source))
        return "created" if old is None else "updated"

    def prune_events(self, observed_before: datetime) -> int:
        return self._exec("DELETE FROM events WHERE observed_at < %s", (observed_before,))

    def query_events(self, q: EventQuery) -> list[tuple[dict[str, Any], datetime]]:
        sql, params = build_query(q, "%s", lambda dt: dt)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(r[0], _utc(r[1])) for r in rows]

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT record FROM events WHERE id = %s", (event_id,))
        return row["record"] if row else None

    def count_events(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM events")

    def put_status(self, key: str, record: dict[str, Any], at: datetime) -> None:
        self._exec(
            "INSERT INTO ingest_status (key, record, updated_at) VALUES (%s, %s, %s)"
            " ON CONFLICT (key) DO UPDATE SET record = excluded.record,"
            " updated_at = excluded.updated_at",
            (key, Jsonb(record), at),
        )

    def get_status(self) -> dict[str, dict[str, Any]]:
        return {r["key"]: r["record"] for r in self._all("SELECT key, record FROM ingest_status")}

    # analyze a star ----------------------------------------------------------------------

    def get_star_analysis(self, tic_id: int) -> StoredAnalysis | None:
        row = self._one("SELECT * FROM star_analyses WHERE tic_id = %s", (tic_id,))
        if row is None:
            return None
        return StoredAnalysis(
            tic_id=row["tic_id"],
            data_marker=row["data_marker"],
            analyzed_at=_utc(row["analyzed_at"]),
            marker_checked_at=_utc(row["marker_checked_at"]),
            analysis=row["result"],
        )

    def put_star_analysis(self, rec: StoredAnalysis) -> None:
        self._exec(
            "INSERT INTO star_analyses"
            " (tic_id, data_marker, analyzed_at, marker_checked_at, result)"
            " VALUES (%s,%s,%s,%s,%s::jsonb) ON CONFLICT (tic_id) DO UPDATE SET"
            " data_marker = excluded.data_marker, analyzed_at = excluded.analyzed_at,"
            " marker_checked_at = excluded.marker_checked_at, result = excluded.result",
            (
                rec.tic_id,
                rec.data_marker,
                rec.analyzed_at,
                rec.marker_checked_at,
                rec.analysis.model_dump_json(),
            ),
        )

    def touch_star_analysis(self, tic_id: int, at: datetime) -> None:
        self._exec(
            "UPDATE star_analyses SET marker_checked_at = %s WHERE tic_id = %s", (at, tic_id)
        )

    def get_star_name(self, key: str) -> int | None:
        row = self._one("SELECT tic_id FROM star_names WHERE name_key = %s", (key,))
        return row["tic_id"] if row else None

    def put_star_name(self, key: str, tic_id: int, at: datetime) -> None:
        self._exec(
            "INSERT INTO star_names VALUES (%s, %s, %s) ON CONFLICT (name_key) DO UPDATE SET"
            " tic_id = excluded.tic_id, resolved_at = excluded.resolved_at",
            (key, tic_id, at),
        )

    # jobs --------------------------------------------------------------------------------

    @staticmethod
    def _job(row: dict[str, Any]) -> JobRecord:
        return JobRecord(
            id=row["id"],
            tic_id=row["tic_id"],
            status=row["status"],
            data_marker=row["data_marker"],
            steps=row["steps"],
            error=row["error"],
            created_at=_utc(row["created_at"]),
            started_at=_utc(row["started_at"]),
            finished_at=_utc(row["finished_at"]),
        )

    def create_job(self, job: JobRecord) -> None:
        self._exec(
            "INSERT INTO analyze_jobs (id, tic_id, status, data_marker, steps, created_at)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (
                job.id,
                job.tic_id,
                job.status,
                job.data_marker,
                Jsonb([s.model_dump(mode="json") for s in job.steps]),
                job.created_at,
            ),
        )

    def get_job(self, job_id: str) -> JobRecord | None:
        row = self._one("SELECT * FROM analyze_jobs WHERE id = %s", (job_id,))
        return self._job(row) if row else None

    def set_job_status(
        self, job_id: str, status: JobStatus, *, at: datetime, error: str | None = None
    ) -> None:
        column = "started_at" if status == "running" else "finished_at"
        self._exec(
            f"UPDATE analyze_jobs SET status = %s, {column} = %s, error = COALESCE(%s, error)"
            " WHERE id = %s",
            (status, at, error, job_id),
        )

    def append_job_step(self, job_id: str, step: JobStep) -> None:
        self._exec(
            "UPDATE analyze_jobs SET steps = steps || jsonb_build_array(%s::jsonb) WHERE id = %s",
            (step.model_dump_json(), job_id),
        )

    def queue_position(self, job_id: str) -> int | None:
        return self._scalar(
            "SELECT CASE WHEN j.status = 'queued' THEN (SELECT COUNT(*) FROM analyze_jobs q"
            " WHERE q.status = 'queued' AND q.seq < j.seq) + 1 END"
            " FROM (SELECT 1) one LEFT JOIN analyze_jobs j ON j.id = %s",
            (job_id,),
        )

    def fail_unfinished_jobs(self, reason: str, at: datetime) -> int:
        return self._exec(
            "UPDATE analyze_jobs SET status = 'failed', error = %s, finished_at = %s"
            " WHERE status IN ('queued', 'running')",
            (reason, at),
        )
