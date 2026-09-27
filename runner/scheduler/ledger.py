"""The search ledger: one row per (queue, star) ever started, so no night repeats another's work.

A star is eligible for a queue when it has no row there, or
- its row is `failed` with fewer than MAX_ATTEMPTS attempts (timeouts, crashes, network errors are retried), or
- its row is `done` but on a different `sectors_key` (a new sector of it became public: ROADMAP Phase 2,
  "re-search a star only when a new sector of it is public").
`claim` makes a star `running` in one SQL statement, so a star can never be started twice. After a crash or a
reboot, `recover` turns every `running` row back into a retryable `failed` one without charging it an attempt
(the star did nothing wrong), and the next run picks it up again.

Stars with no data (`outcome = no_data`) are `done`: there is nothing to search until a new sector appears.

Tables:
  stars(queue, tic) : status running|done|failed, attempts, sectors_key, run_id, times, outcome, counts,
                      best_snr / best_score / promising (the fast pass's hint for the deep queue), error
  vets(stem)        : one per candidate file: pending|running|done|failed, verdict, path of the vetted JSON
  runs(run_id)      : searching|wrapping|done, started_at, search_until, summary JSON
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path

MAX_ATTEMPTS = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS stars (
    queue        TEXT    NOT NULL,
    tic          INTEGER NOT NULL,
    status       TEXT    NOT NULL CHECK (status IN ('running', 'done', 'failed')),
    sectors_key  TEXT    NOT NULL DEFAULT '',
    attempts     INTEGER NOT NULL DEFAULT 0,
    run_id       TEXT,
    started_at   REAL,
    finished_at  REAL,
    elapsed_s    REAL,
    outcome      TEXT,
    n_sectors    INTEGER,
    n_signals    INTEGER,
    n_candidates INTEGER,
    best_snr     REAL,
    best_score   REAL,
    promising    INTEGER NOT NULL DEFAULT 0,
    pipeline     TEXT,
    error        TEXT,
    PRIMARY KEY (queue, tic)
);
CREATE INDEX IF NOT EXISTS stars_status ON stars (queue, status);
CREATE INDEX IF NOT EXISTS stars_run ON stars (run_id);
CREATE TABLE IF NOT EXISTS vets (
    stem        TEXT PRIMARY KEY,
    tic         INTEGER NOT NULL,
    run_id      TEXT NOT NULL,
    source      TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts    INTEGER NOT NULL DEFAULT 0,
    verdict     TEXT,
    vetted_path TEXT,
    elapsed_s   REAL,
    finished_at REAL,
    error       TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    state        TEXT NOT NULL CHECK (state IN ('searching', 'wrapping', 'done')),
    started_at   REAL NOT NULL,
    search_until REAL NOT NULL,
    finished_at  REAL,
    summary      TEXT
);
"""

RESULT_FIELDS = ("outcome", "n_sectors", "n_signals", "n_candidates", "best_snr", "best_score", "pipeline")
RETRYABLE_OUTCOMES = {"timeout", "crash", "error"}


class Ledger:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # One connection, used from the scheduler's main thread only; autocommit, explicit transactions.
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    # ---- stars ----------------------------------------------------------------------------------------------

    def claim(self, queue: str, tic: int, sectors_key: str, run_id: str) -> bool:
        """Mark the star running for this queue if it is eligible (see module doc). True if claimed."""
        now = time.time()
        cur = self.db.execute(
            """
            INSERT INTO stars (queue, tic, status, sectors_key, attempts, run_id, started_at)
            VALUES (?, ?, 'running', ?, 1, ?, ?)
            ON CONFLICT (queue, tic) DO UPDATE SET
                status = 'running',
                attempts = CASE WHEN stars.status = 'done' THEN 1 ELSE stars.attempts + 1 END,
                sectors_key = excluded.sectors_key, run_id = excluded.run_id,
                started_at = excluded.started_at, finished_at = NULL, error = NULL
            WHERE (stars.status = 'failed' AND stars.attempts < ?)
               OR (stars.status = 'done' AND stars.sectors_key != excluded.sectors_key)
            """,
            (queue, tic, sectors_key, run_id, now, MAX_ATTEMPTS),
        )
        return cur.rowcount == 1

    def finish(self, queue: str, tic: int, result: dict) -> str:
        """Record a finished star. Timeouts, crashes and errors are `failed` (retried up to MAX_ATTEMPTS times);
        everything else, including no_data, is `done`. Returns the status written."""
        outcome = result.get("outcome") or "error"
        status = "failed" if outcome in RETRYABLE_OUTCOMES else "done"
        now = time.time()
        row = self.db.execute("SELECT started_at FROM stars WHERE queue = ? AND tic = ?", (queue, tic)).fetchone()
        elapsed = result.get("elapsed_s")
        if elapsed is None and row is not None and row["started_at"]:
            elapsed = now - row["started_at"]
        self.db.execute(
            f"""UPDATE stars SET status = ?, finished_at = ?, elapsed_s = ?, error = ?, promising = ?,
                {", ".join(f"{f} = ?" for f in RESULT_FIELDS)}
                WHERE queue = ? AND tic = ?""",
            (status, now, elapsed, (result.get("error") or None) and str(result["error"])[:500],
             1 if result.get("promising") else 0, *(result.get(f) for f in RESULT_FIELDS), queue, tic),
        )
        return status

    def recover(self) -> int:
        """Rows left `running` by a crash or reboot become retryable again, without costing an attempt."""
        cur = self.db.execute(
            """UPDATE stars SET status = 'failed', attempts = MAX(attempts - 1, 0),
                   error = 'interrupted (scheduler stopped mid-star)'
               WHERE status = 'running'"""
        )
        self.db.execute("UPDATE vets SET status = 'pending', attempts = MAX(attempts - 1, 0) WHERE status = 'running'")
        return cur.rowcount

    def blocked(self, queue: str) -> dict[int, str | None]:
        """Stars a queue must not start now: tic -> sectors_key for `done` rows (eligible again only on a new
        sectors_key), None for rows that are running or out of attempts."""
        out: dict[int, str | None] = {}
        for r in self.db.execute(
            "SELECT tic, status, sectors_key, attempts FROM stars WHERE queue = ?", (queue,)
        ):
            if r["status"] == "done":
                out[r["tic"]] = r["sectors_key"]
            elif r["status"] == "running" or r["attempts"] >= MAX_ATTEMPTS:
                out[r["tic"]] = None
        return out

    def get(self, queue: str, tic: int) -> dict | None:
        r = self.db.execute("SELECT * FROM stars WHERE queue = ? AND tic = ?", (queue, tic)).fetchone()
        return dict(r) if r else None

    def promising(self, queue: str = "fast") -> list[dict]:
        """Stars the fast pass flagged for the deep pass, best first."""
        return [dict(r) for r in self.db.execute(
            """SELECT tic, sectors_key, best_score, best_snr, n_candidates FROM stars
               WHERE queue = ? AND status = 'done' AND promising = 1
               ORDER BY n_candidates DESC, COALESCE(best_score, 0) DESC, COALESCE(best_snr, 0) DESC, tic""",
            (queue,),
        )]

    def mean_elapsed(self, queue: str, last: int = 200) -> float | None:
        r = self.db.execute(
            """SELECT AVG(elapsed_s) AS m, COUNT(*) AS n FROM (
                   SELECT elapsed_s FROM stars WHERE queue = ? AND status = 'done' AND elapsed_s IS NOT NULL
                   AND outcome != 'no_data' ORDER BY finished_at DESC LIMIT ?)""",
            (queue, last),
        ).fetchone()
        return float(r["m"]) if r["n"] else None

    def counts(self, run_id: str | None = None) -> dict[str, dict[str, int]]:
        q = "SELECT queue, status, COUNT(*) AS n FROM stars"
        args: tuple = ()
        if run_id:
            q += " WHERE run_id = ?"
            args = (run_id,)
        out: dict[str, dict[str, int]] = {}
        for r in self.db.execute(q + " GROUP BY queue, status", args):
            out.setdefault(r["queue"], {})[r["status"]] = r["n"]
        return out

    def run_rows(self, run_id: str) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM stars WHERE run_id = ? ORDER BY finished_at", (run_id,))]

    # ---- vets -----------------------------------------------------------------------------------------------

    def add_vets(self, run_id: str, items: Iterable[tuple[str, int, str]]) -> int:
        """(stem, tic, candidate path). A stem already known keeps its state unless its source changed (the same
        candidate found again on a later night: vet the new file)."""
        n = 0
        for stem, tic, source in items:
            cur = self.db.execute(
                """INSERT INTO vets (stem, tic, run_id, source, status) VALUES (?, ?, ?, ?, 'pending')
                   ON CONFLICT (stem) DO UPDATE SET run_id = excluded.run_id, source = excluded.source,
                       status = 'pending', attempts = 0, verdict = NULL, vetted_path = NULL, error = NULL
                   WHERE vets.source != excluded.source""",
                (stem, tic, run_id, source),
            )
            n += cur.rowcount
        return n

    def next_vet(self) -> dict | None:
        r = self.db.execute(
            """SELECT * FROM vets WHERE status = 'pending' OR (status = 'failed' AND attempts < ?)
               ORDER BY run_id DESC, stem LIMIT 1""",
            (MAX_ATTEMPTS,),
        ).fetchone()
        if r is None:
            return None
        self.db.execute("UPDATE vets SET status = 'running', attempts = attempts + 1 WHERE stem = ?", (r["stem"],))
        return dict(r)

    def finish_vet(self, stem: str, *, ok: bool, verdict: str | None = None, vetted_path: str | None = None,
                   elapsed_s: float | None = None, error: str | None = None) -> None:
        self.db.execute(
            """UPDATE vets SET status = ?, verdict = ?, vetted_path = ?, elapsed_s = ?, finished_at = ?, error = ?
               WHERE stem = ?""",
            ("done" if ok else "failed", verdict, vetted_path, elapsed_s, time.time(),
             (error or None) and error[:500], stem),
        )

    def get_vet(self, stem: str) -> dict | None:
        r = self.db.execute("SELECT * FROM vets WHERE stem = ?", (stem,)).fetchone()
        return dict(r) if r else None

    def vetted(self) -> dict[str, dict]:
        return {r["stem"]: dict(r) for r in self.db.execute("SELECT * FROM vets WHERE status = 'done'")}

    def pending_vets(self) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM vets WHERE status = 'pending' OR (status = 'failed' AND attempts < ?)",
            (MAX_ATTEMPTS,)).fetchone()[0]

    # ---- runs -----------------------------------------------------------------------------------------------

    def get_run(self, run_id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if r is None:
            return None
        out = dict(r)
        out["summary"] = json.loads(out["summary"]) if out["summary"] else None
        return out

    def start_run(self, run_id: str, started_at: float, search_until: float) -> dict:
        """Create the run, or return it unchanged when it exists (a resumed run keeps its start and deadline)."""
        self.db.execute(
            "INSERT OR IGNORE INTO runs (run_id, state, started_at, search_until) VALUES (?, 'searching', ?, ?)",
            (run_id, started_at, search_until),
        )
        return self.get_run(run_id)  # type: ignore[return-value]

    def set_run(self, run_id: str, state: str, summary: dict | None = None) -> None:
        self.db.execute(
            "UPDATE runs SET state = ?, finished_at = ?, summary = COALESCE(?, summary) WHERE run_id = ?",
            (state, time.time() if state == "done" else None, json.dumps(summary) if summary else None, run_id),
        )

    def last_run(self) -> dict | None:
        r = self.db.execute("SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        return self.get_run(r["run_id"]) if r else None
