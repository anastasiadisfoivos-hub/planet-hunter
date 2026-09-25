"""SQLite implementation of the Storage port (stdlib sqlite3, one connection, one lock)."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from api.contract import Discovery, Sphere, StarTarget
from api.models import JobRecord, JobStatus, JobStep, TrapRecord
from api.timeutil import iso, parse

SCHEMA = """
CREATE TABLE IF NOT EXISTS traps (
    id TEXT PRIMARY KEY,
    player_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('sky', 'star')),
    ra_deg REAL, dec_deg REAL, radius_deg REAL,
    tic_id INTEGER,
    created_at TEXT NOT NULL,
    last_checked_at TEXT,
    last_tess_marker TEXT
);
CREATE INDEX IF NOT EXISTS traps_player ON traps (player_id, created_at);

CREATE TABLE IF NOT EXISTS discoveries (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    type TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    record TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catches (
    player_id TEXT NOT NULL,
    discovery_id TEXT NOT NULL REFERENCES discoveries (id),
    trap_id TEXT,
    caught_at TEXT NOT NULL,
    PRIMARY KEY (player_id, discovery_id)
);
CREATE INDEX IF NOT EXISTS catches_newest ON catches (player_id, caught_at DESC, discovery_id DESC);

CREATE TABLE IF NOT EXISTS jobs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    player_id TEXT NOT NULL,
    trap_id TEXT,
    tic_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    steps TEXT NOT NULL DEFAULT '[]',
    result_ids TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status, seq);
"""


class SqliteStorage:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = 0
        self._conn.execute("PRAGMA busy_timeout = 5000")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)

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

    def _exec(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _all(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    # traps ---------------------------------------------------------------

    @staticmethod
    def _trap(row: sqlite3.Row) -> TrapRecord:
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
            created_at=parse(row["created_at"]),
            last_checked_at=parse(row["last_checked_at"]),
            last_tess_marker=row["last_tess_marker"],
        )

    def create_trap(self, trap: TrapRecord) -> None:
        s, t = trap.sphere, trap.star
        self._exec(
            "INSERT INTO traps (id, player_id, kind, ra_deg, dec_deg, radius_deg, tic_id,"
            " created_at, last_checked_at, last_tess_marker) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                trap.id,
                trap.player_id,
                trap.kind,
                s.ra_deg if s else None,
                s.dec_deg if s else None,
                s.radius_deg if s else None,
                t.tic_id if t else None,
                iso(trap.created_at),
                iso(trap.last_checked_at) if trap.last_checked_at else None,
                trap.last_tess_marker,
            ),
        )

    def get_trap(self, trap_id: str) -> TrapRecord | None:
        row = self._one("SELECT * FROM traps WHERE id = ?", (trap_id,))
        return self._trap(row) if row else None

    def list_traps(self, player_id: str) -> list[TrapRecord]:
        rows = self._all(
            "SELECT * FROM traps WHERE player_id = ? ORDER BY created_at DESC, id", (player_id,)
        )
        return [self._trap(r) for r in rows]

    def count_traps(self, player_id: str) -> int:
        return self._one("SELECT COUNT(*) FROM traps WHERE player_id = ?", (player_id,))[0]

    def iter_traps(self) -> Iterator[TrapRecord]:
        rows = self._all("SELECT * FROM traps ORDER BY created_at, id")
        return iter([self._trap(r) for r in rows])

    def delete_trap(self, player_id: str, trap_id: str) -> bool:
        cur = self._exec("DELETE FROM traps WHERE id = ? AND player_id = ?", (trap_id, player_id))
        return cur.rowcount > 0

    def set_trap_checked(
        self, trap_id: str, *, last_checked_at: datetime | None = None, marker: str | None = None
    ) -> None:
        if last_checked_at is not None:
            self._exec(
                "UPDATE traps SET last_checked_at = ? WHERE id = ?", (iso(last_checked_at), trap_id)
            )
        if marker is not None:
            self._exec("UPDATE traps SET last_tess_marker = ? WHERE id = ?", (marker, trap_id))

    # discoveries and catches ----------------------------------------------

    def get_discovery(self, discovery_id: str) -> Discovery | None:
        row = self._one("SELECT record FROM discoveries WHERE id = ?", (discovery_id,))
        return Discovery.model_validate_json(row["record"]) if row else None

    def put_discovery(self, d: Discovery) -> None:
        self._exec(
            "INSERT INTO discoveries (id, source, type, detected_at, record) VALUES (?,?,?,?,?)"
            " ON CONFLICT (id) DO UPDATE SET source = excluded.source, type = excluded.type,"
            " detected_at = excluded.detected_at, record = excluded.record",
            (d.id, d.source, d.type.value, iso(d.detected_at), d.model_dump_json()),
        )

    def discoveries_with_prefix(self, prefix: str) -> list[Discovery]:
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self._all(
            "SELECT record FROM discoveries WHERE id LIKE ? ESCAPE '\\' ORDER BY id",
            (escaped + "%",),
        )
        return [Discovery.model_validate_json(r["record"]) for r in rows]

    def add_catch(
        self, player_id: str, discovery_id: str, trap_id: str | None, caught_at: datetime
    ) -> bool:
        cur = self._exec(
            "INSERT OR IGNORE INTO catches (player_id, discovery_id, trap_id, caught_at)"
            " VALUES (?,?,?,?)",
            (player_id, discovery_id, trap_id, iso(caught_at)),
        )
        return cur.rowcount > 0

    def has_catch(self, player_id: str, discovery_id: str) -> bool:
        row = self._one(
            "SELECT 1 FROM catches WHERE player_id = ? AND discovery_id = ?",
            (player_id, discovery_id),
        )
        return row is not None

    def list_catches(
        self, player_id: str, limit: int, before: tuple[str, str] | None
    ) -> list[tuple[Discovery, str]]:
        sql = (
            "SELECT d.record, c.caught_at FROM catches c JOIN discoveries d"
            " ON d.id = c.discovery_id WHERE c.player_id = ?"
        )
        params: list = [player_id]
        if before is not None:
            sql += " AND (c.caught_at < ? OR (c.caught_at = ? AND c.discovery_id < ?))"
            params += [before[0], before[0], before[1]]
        sql += " ORDER BY c.caught_at DESC, c.discovery_id DESC LIMIT ?"
        params.append(limit)
        rows = self._all(sql, tuple(params))
        return [(Discovery.model_validate_json(r["record"]), r["caught_at"]) for r in rows]

    def count_catches(self) -> int:
        return self._one("SELECT COUNT(*) FROM catches")[0]

    # jobs -------------------------------------------------------------------

    @staticmethod
    def _job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            player_id=row["player_id"],
            trap_id=row["trap_id"],
            tic_id=row["tic_id"],
            status=row["status"],
            steps=json.loads(row["steps"]),
            result_ids=json.loads(row["result_ids"]),
            error=row["error"],
            created_at=parse(row["created_at"]),
            started_at=parse(row["started_at"]),
            finished_at=parse(row["finished_at"]),
        )

    def create_job(self, job: JobRecord) -> None:
        self._exec(
            "INSERT INTO jobs (id, player_id, trap_id, tic_id, status, steps, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                job.id,
                job.player_id,
                job.trap_id,
                job.tic_id,
                job.status,
                json.dumps([s.model_dump(mode="json") for s in job.steps]),
                iso(job.created_at),
            ),
        )

    def get_job(self, job_id: str) -> JobRecord | None:
        row = self._one("SELECT * FROM jobs WHERE id = ?", (job_id,))
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
        with self.atomic():
            self._exec(
                f"UPDATE jobs SET status = ?, {column} = ?, error = COALESCE(?, error)"
                " WHERE id = ?",
                (status, iso(at), error, job_id),
            )
            if result_ids is not None:
                self._exec(
                    "UPDATE jobs SET result_ids = ? WHERE id = ?", (json.dumps(result_ids), job_id)
                )

    def append_job_step(self, job_id: str, step: JobStep) -> None:
        self._exec(
            "UPDATE jobs SET steps = json_insert(steps, '$[#]', json(?)) WHERE id = ?",
            (step.model_dump_json(), job_id),
        )

    def queue_position(self, job_id: str) -> int | None:
        row = self._one("SELECT seq, status FROM jobs WHERE id = ?", (job_id,))
        if row is None or row["status"] != "queued":
            return None
        ahead = self._one(
            "SELECT COUNT(*) FROM jobs WHERE status = 'queued' AND seq < ?", (row["seq"],)
        )[0]
        return ahead + 1

    def count_pending_jobs(self, player_id: str) -> int:
        return self._one(
            "SELECT COUNT(*) FROM jobs WHERE player_id = ? AND status IN ('queued', 'running')",
            (player_id,),
        )[0]

    def fail_unfinished_jobs(self, reason: str, at: datetime) -> int:
        cur = self._exec(
            "UPDATE jobs SET status = 'failed', error = ?, finished_at = ?"
            " WHERE status IN ('queued', 'running')",
            (reason, iso(at)),
        )
        return cur.rowcount
