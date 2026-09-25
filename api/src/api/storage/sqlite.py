"""SQLite implementation of the Storage port (stdlib sqlite3, one connection, one lock).

Local dev and tests. Schema: migrations/sqlite/NNNN_*.sql, the twins of the Postgres files, applied
in order once each and recorded in schema_migrations.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from importlib import resources
from typing import Any

from api.models import (
    HostSystem,
    JobRecord,
    JobStatus,
    JobStep,
    StoredAnalysis,
    StoredLightCurve,
)
from api.ports import EventMeta, EventQuery, EventRow, Upserted
from api.storage.events_sql import build_query
from api.timeutil import iso, parse


def sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float | None:
    """Great-circle distance in degrees (haversine); same formula as Postgres' ph_sep_deg."""
    if None in (ra1, dec1, ra2, dec2):
        return None
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    h = math.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * math.cos(d2) * math.sin((r2 - r1) / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(h))))


def migration_files() -> list[tuple[str, str]]:
    folder = resources.files("api.storage").joinpath("migrations").joinpath("sqlite")
    files = sorted(f for f in folder.iterdir() if f.name.endswith(".sql"))
    return [(f.name.removesuffix(".sql"), f.read_text()) for f in files]


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class SqliteStorage:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = 0
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.create_function("ph_sep_deg", 4, sep_deg, deterministic=True)
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

    # events ----------------------------------------------------------------------------

    def event_meta(self, ids: list[str]) -> dict[str, EventMeta]:
        out: dict[str, EventMeta] = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            rows = self._all(
                "SELECT id, source_hash, content_hash, images_checked_at,"
                " json_extract(record, '$.images') AS images FROM events"
                f" WHERE id IN ({', '.join('?' * len(chunk))})",
                chunk,
            )
            for r in rows:
                out[r["id"]] = EventMeta(
                    source_hash=r["source_hash"],
                    content_hash=r["content_hash"],
                    images_checked_at=parse(r["images_checked_at"]),
                    images=json.loads(r["images"] or "[]"),
                )
        return out

    def upsert_event(self, row: EventRow) -> Upserted:
        with self.atomic():
            old = self._one(
                "SELECT content_hash, images_checked_at FROM events WHERE id = ?", (row.id,)
            )
            if old is not None and old["content_hash"] == row.content_hash:
                if parse(old["images_checked_at"]) < row.images_checked_at:
                    self._exec(
                        "UPDATE events SET images_checked_at = ? WHERE id = ?",
                        (iso(row.images_checked_at), row.id),
                    )
                return "unchanged"
            values = (
                row.type,
                row.category,
                row.frame,
                iso(row.observed_at),
                row.ra_deg,
                row.dec_deg,
                row.confidence,
                int(row.has_images),
                int(row.from_latest_observed_window),
                _dump(row.record),
                row.source_hash,
                row.content_hash,
                iso(row.images_checked_at),
                iso(row.updated_at),
            )
            if old is None:
                self._exec(
                    "INSERT INTO events (type, category, frame, observed_at, ra_deg, dec_deg,"
                    " confidence, has_images, from_latest_observed_window, record, source_hash,"
                    " content_hash, images_checked_at, updated_at, id)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*values, row.id),
                )
            else:
                self._exec(
                    "UPDATE events SET type = ?, category = ?, frame = ?, observed_at = ?,"
                    " ra_deg = ?, dec_deg = ?, confidence = ?, has_images = ?,"
                    " from_latest_observed_window = ?, record = ?, source_hash = ?,"
                    " content_hash = ?, images_checked_at = ?, updated_at = ? WHERE id = ?",
                    (*values, row.id),
                )
                self._exec("DELETE FROM event_sources WHERE event_id = ?", (row.id,))
            for source in sorted(set(row.sources)):
                self._exec("INSERT INTO event_sources VALUES (?, ?)", (row.id, source))
        return "created" if old is None else "updated"

    def prune_events(self, observed_before: datetime) -> int:
        cur = self._exec("DELETE FROM events WHERE observed_at < ?", (iso(observed_before),))
        return cur.rowcount

    def query_events(self, q: EventQuery) -> list[tuple[dict[str, Any], datetime]]:
        sql, params = build_query(q, "?", iso)
        return [(json.loads(r[0]), parse(r[1])) for r in self._all(sql, params)]

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT record FROM events WHERE id = ?", (event_id,))
        return json.loads(row[0]) if row else None

    def count_events(self) -> int:
        return self._one("SELECT COUNT(*) FROM events")[0]

    def put_status(self, key: str, record: dict[str, Any], at: datetime) -> None:
        self._exec(
            "INSERT INTO ingest_status (key, record, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT (key) DO UPDATE SET record = excluded.record,"
            " updated_at = excluded.updated_at",
            (key, _dump(record), iso(at)),
        )

    def get_status(self) -> dict[str, dict[str, Any]]:
        return {r[0]: json.loads(r[1]) for r in self._all("SELECT key, record FROM ingest_status")}

    # analyze a star ----------------------------------------------------------------------

    def get_star_analysis(self, tic_id: int) -> StoredAnalysis | None:
        row = self._one("SELECT * FROM star_analyses WHERE tic_id = ?", (tic_id,))
        if row is None:
            return None
        return StoredAnalysis(
            tic_id=row["tic_id"],
            data_marker=row["data_marker"],
            analyzed_at=parse(row["analyzed_at"]),
            marker_checked_at=parse(row["marker_checked_at"]),
            analysis=json.loads(row["result"]),
        )

    def put_star_analysis(self, rec: StoredAnalysis) -> None:
        self._exec(
            "INSERT INTO star_analyses"
            " (tic_id, data_marker, analyzed_at, marker_checked_at, result)"
            " VALUES (?,?,?,?,?) ON CONFLICT (tic_id) DO UPDATE SET"
            " data_marker = excluded.data_marker, analyzed_at = excluded.analyzed_at,"
            " marker_checked_at = excluded.marker_checked_at, result = excluded.result",
            (
                rec.tic_id,
                rec.data_marker,
                iso(rec.analyzed_at),
                iso(rec.marker_checked_at),
                rec.analysis.model_dump_json(),
            ),
        )

    def touch_star_analysis(self, tic_id: int, at: datetime) -> None:
        self._exec(
            "UPDATE star_analyses SET marker_checked_at = ? WHERE tic_id = ?", (iso(at), tic_id)
        )

    def get_star_name(self, key: str) -> int | None:
        row = self._one("SELECT tic_id FROM star_names WHERE name_key = ?", (key,))
        return row[0] if row else None

    def put_star_name(self, key: str, tic_id: int, at: datetime) -> None:
        self._exec(
            "INSERT INTO star_names VALUES (?, ?, ?) ON CONFLICT (name_key) DO UPDATE SET"
            " tic_id = excluded.tic_id, resolved_at = excluded.resolved_at",
            (key, tic_id, iso(at)),
        )

    # per-star lab ------------------------------------------------------------------------

    def get_star_lightcurve(self, tic_id: int) -> StoredLightCurve | None:
        row = self._one("SELECT * FROM star_lightcurves WHERE tic_id = ?", (tic_id,))
        if row is None:
            return None
        return StoredLightCurve(
            tic_id=row["tic_id"],
            status=row["status"],
            data_marker=row["data_marker"],
            stored_at=parse(row["stored_at"]),
            curve=json.loads(row["curve"]) if row["curve"] else None,
        )

    def put_star_lightcurve(self, rec: StoredLightCurve) -> None:
        self._exec(
            "INSERT INTO star_lightcurves (tic_id, status, data_marker, stored_at, curve)"
            " VALUES (?,?,?,?,?) ON CONFLICT (tic_id) DO UPDATE SET status = excluded.status,"
            " data_marker = excluded.data_marker, stored_at = excluded.stored_at,"
            " curve = excluded.curve",
            (
                rec.tic_id,
                rec.status,
                rec.data_marker,
                iso(rec.stored_at),
                rec.curve.model_dump_json() if rec.curve else None,
            ),
        )

    def get_known_planets(self, tic_id: int) -> HostSystem | None:
        row = self._one("SELECT * FROM known_planets WHERE tic_id = ?", (tic_id,))
        if row is None:
            return None
        return HostSystem(
            tic_id=row["tic_id"],
            host_name=row["host_name"],
            star=json.loads(row["star"]),
            planets=json.loads(row["planets"]),
            fetched_at=parse(row["fetched_at"]),
        )

    def put_known_planets(self, rec: HostSystem) -> None:
        doc = rec.model_dump(mode="json")
        self._exec(
            "INSERT INTO known_planets (tic_id, host_name, star, planets, fetched_at)"
            " VALUES (?,?,?,?,?) ON CONFLICT (tic_id) DO UPDATE SET"
            " host_name = excluded.host_name, star = excluded.star,"
            " planets = excluded.planets, fetched_at = excluded.fetched_at",
            (rec.tic_id, rec.host_name, _dump(doc["star"]), _dump(doc["planets"]),
             iso(rec.fetched_at)),
        )  # fmt: skip

    # jobs --------------------------------------------------------------------------------

    @staticmethod
    def _job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            tic_id=row["tic_id"],
            status=row["status"],
            data_marker=row["data_marker"],
            steps=json.loads(row["steps"]),
            error=row["error"],
            created_at=parse(row["created_at"]),
            started_at=parse(row["started_at"]),
            finished_at=parse(row["finished_at"]),
        )

    def create_job(self, job: JobRecord) -> None:
        self._exec(
            "INSERT INTO analyze_jobs (id, tic_id, status, data_marker, steps, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (
                job.id,
                job.tic_id,
                job.status,
                job.data_marker,
                _dump([s.model_dump(mode="json") for s in job.steps]),
                iso(job.created_at),
            ),
        )

    def get_job(self, job_id: str) -> JobRecord | None:
        row = self._one("SELECT * FROM analyze_jobs WHERE id = ?", (job_id,))
        return self._job(row) if row else None

    def set_job_status(
        self, job_id: str, status: JobStatus, *, at: datetime, error: str | None = None
    ) -> None:
        column = "started_at" if status == "running" else "finished_at"
        self._exec(
            f"UPDATE analyze_jobs SET status = ?, {column} = ?, error = COALESCE(?, error)"
            " WHERE id = ?",
            (status, iso(at), error, job_id),
        )

    def append_job_step(self, job_id: str, step: JobStep) -> None:
        self._exec(
            "UPDATE analyze_jobs SET steps = json_insert(steps, '$[#]', json(?)) WHERE id = ?",
            (step.model_dump_json(), job_id),
        )

    def queue_position(self, job_id: str) -> int | None:
        row = self._one("SELECT seq, status FROM analyze_jobs WHERE id = ?", (job_id,))
        if row is None or row["status"] != "queued":
            return None
        ahead = self._one(
            "SELECT COUNT(*) FROM analyze_jobs WHERE status = 'queued' AND seq < ?", (row["seq"],)
        )[0]
        return ahead + 1

    def fail_unfinished_jobs(self, reason: str, at: datetime) -> int:
        cur = self._exec(
            "UPDATE analyze_jobs SET status = 'failed', error = ?, finished_at = ?"
            " WHERE status IN ('queued', 'running')",
            (reason, iso(at)),
        )
        return cur.rowcount
