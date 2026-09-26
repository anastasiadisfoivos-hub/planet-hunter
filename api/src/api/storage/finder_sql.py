"""Planet-finder storage, shared by both backends.

The backends differ only in the placeholder, how JSON and timestamps go in and come out, and
row locking; each supplies those through the hooks at the top of FinderSql.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any

from api.ports import CandidateQuery, CandidateRow, Upserted, VetTodo, Vote

OPEN = ("new", "under review")
SORT_COLUMNS = {"score": "c.score", "newest": "c.created_at", "votes": "c.votes_total"}
LIST_COLUMNS = (
    "c.id, c.tic, c.record, c.score, c.pixel_verdict, c.status, c.status_reason,"
    " c.votes_planet, c.votes_fake, c.votes_unsure, c.votes_total, c.exported_at,"
    " c.vetting, c.created_at, c.updated_at"
)
DOC_TABLES = ("sensitivity", "finder_sweep")


class FinderSql:
    # Hooks -------------------------------------------------------------------------------
    PH: str
    FOR_UPDATE: str

    def _j(self, obj: Any) -> Any: ...  # JSON in
    def _jo(self, value: Any) -> Any: ...  # JSON out
    def _t(self, dt: datetime | None) -> Any: ...  # timestamp in
    def _to(self, value: Any) -> datetime | None: ...  # timestamp out
    def atomic(self) -> AbstractContextManager[None]: ...
    def _exec(self, sql: str, params: tuple | list = ()) -> Any: ...
    def _all(self, sql: str, params: tuple | list = ()) -> list[Any]: ...
    def _one(self, sql: str, params: tuple | list = ()) -> Any: ...

    def _sql(self, sql: str) -> str:
        return sql.replace("?", self.PH)

    def _in(self, values: list[str] | tuple[str, ...]) -> str:
        return ", ".join([self.PH] * len(values))

    # Candidates --------------------------------------------------------------------------

    def candidate_hashes(self, ids: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for chunk in chunks(ids):
            rows = self._all(
                f"SELECT id, content_hash FROM candidates WHERE id IN ({self._in(chunk)})", chunk
            )
            out.update({r["id"]: r["content_hash"] for r in rows})
        return out

    def upsert_candidate(self, row: CandidateRow) -> Upserted:
        """Insert, or rewrite when content_hash changed. Status, votes and the first
        created_at are kept."""
        with self.atomic():
            old = self._one(
                self._sql(f"SELECT content_hash FROM candidates WHERE id = ?{self.FOR_UPDATE}"),
                (row.id,),
            )
            if old is not None and old["content_hash"] == row.content_hash:
                return "unchanged"
            values = (
                row.tic, self._j(row.record), row.content_hash, row.ephemeris_key, row.score,
                row.radius_rjup, row.period_d,
                self._j(row.vetting) if row.vetting is not None else None,
                self._t(row.updated_at),
            )  # fmt: skip
            if old is None:
                self._exec(
                    self._sql(
                        "INSERT INTO candidates (tic, record, content_hash, ephemeris_key, score,"
                        " radius_rjup, period_d, vetting, updated_at, created_at, id)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                    ),
                    (*values, self._t(row.created_at), row.id),
                )
                return "created"
            self._exec(
                self._sql(
                    "UPDATE candidates SET tic = ?, record = ?, content_hash = ?,"
                    " ephemeris_key = ?, score = ?, radius_rjup = ?, period_d = ?, vetting = ?,"
                    " updated_at = ? WHERE id = ?"
                ),
                (*values, row.id),
            )
            return "updated"

    def _candidate(self, r: Any) -> dict[str, Any]:
        return {
            "id": r["id"],
            "tic": r["tic"],
            "record": self._jo(r["record"]),
            "score": r["score"],
            "pixel_verdict": r["pixel_verdict"],
            "status": r["status"],
            "status_reason": r["status_reason"],
            "votes": {
                "planet": r["votes_planet"],
                "fake": r["votes_fake"],
                "unsure": r["votes_unsure"],
                "total": r["votes_total"],
            },
            "vetting": self._jo(r["vetting"]) if r["vetting"] is not None else None,
            "exported_at": self._to(r["exported_at"]),
            "created_at": self._to(r["created_at"]),
            "updated_at": self._to(r["updated_at"]),
        }

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        r = self._one(self._sql(f"SELECT {LIST_COLUMNS} FROM candidates c WHERE c.id = ?"),
                      (candidate_id,))  # fmt: skip
        return self._candidate(r) if r else None

    def query_candidates(self, q: CandidateQuery) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        for column, op, value in (
            ("c.radius_rjup", ">=", q.min_radius),
            ("c.radius_rjup", "<=", q.max_radius),
            ("c.period_d", ">=", q.min_period),
            ("c.period_d", "<=", q.max_period),
        ):
            if value is not None:
                where.append(f"{column} {op} {self.PH}")
                params.append(value)
        if q.pixel_verdicts:
            verdicts = [v for v in q.pixel_verdicts if v != "unvetted"]
            parts = [f"c.pixel_verdict IN ({self._in(verdicts)})"] if verdicts else []
            params.extend(verdicts)
            if "unvetted" in q.pixel_verdicts:
                parts.append("c.pixel_verdict IS NULL")
            where.append("(" + " OR ".join(parts) + ")")
        statuses = q.statuses or ["new", "under review", "exported"]
        where.append(f"c.status IN ({self._in(statuses)})")
        params.extend(statuses)
        if q.needs_votes is not None:
            where.append(f"c.votes_total < {self.PH} AND c.status IN ({self._in(OPEN)})")
            params += [q.needs_votes, *OPEN]
        column = SORT_COLUMNS[q.sort]
        if q.after is not None:
            value, last_id = q.after
            if q.sort == "newest":
                value = self._t(value)
            where.append(f"({column} < {self.PH} OR ({column} = {self.PH} AND c.id < {self.PH}))")
            params += [value, value, last_id]
        sql = (
            f"SELECT {LIST_COLUMNS} FROM candidates c WHERE {' AND '.join(where)}"
            f" ORDER BY {column} DESC, c.id DESC LIMIT {self.PH}"
        )
        params.append(q.limit)
        return [self._candidate(r) for r in self._all(sql, params)]

    def dismiss_candidate(self, candidate_id: str, reason: str, at: datetime) -> bool:
        """Dismiss an open candidate. False when it is already dismissed or exported."""
        with self.atomic():
            r = self._one(
                self._sql(f"SELECT status FROM candidates WHERE id = ?{self.FOR_UPDATE}"),
                (candidate_id,),
            )
            if r is None or r["status"] not in OPEN:
                return False
            self._exec(
                self._sql(
                    "UPDATE candidates SET status = 'dismissed', status_reason = ?,"
                    " known_checked_at = ?, updated_at = ? WHERE id = ?"
                ),
                (reason, self._t(at), self._t(at), candidate_id),
            )
            return True

    def mark_known_checked(self, candidate_id: str, at: datetime) -> None:
        self._exec(
            self._sql("UPDATE candidates SET known_checked_at = ? WHERE id = ?"),
            (self._t(at), candidate_id),
        )

    def candidates_to_recheck(self, limit: int) -> list[tuple[str, int, float]]:
        """Open candidates, the longest-unchecked first: (id, tic, period_d)."""
        rows = self._all(
            self._sql(
                f"SELECT id, tic, period_d FROM candidates WHERE status IN ({self._in(OPEN)})"
                " AND period_d IS NOT NULL ORDER BY known_checked_at IS NOT NULL,"
                " known_checked_at, score DESC, id LIMIT ?"
            ),
            (*OPEN, limit),
        )
        return [(r["id"], r["tic"], r["period_d"]) for r in rows]

    def mark_exported(self, ids: list[str], at: datetime) -> None:
        with self.atomic():
            for chunk in chunks(ids):
                self._exec(
                    f"UPDATE candidates SET status = 'exported', exported_at = {self.PH},"
                    f" status_reason = NULL WHERE id IN ({self._in(chunk)})",
                    (self._t(at), *chunk),
                )

    # Pixel vets --------------------------------------------------------------------------

    def candidates_to_vet(self, limit: int, max_attempts: int) -> list[VetTodo]:
        """Open candidates with no vet for their current ephemeris (never-vetted first, then by
        score), plus failed ones with attempts left. A single dip (no period yet) can't be
        pixel-checked: difference imaging needs every in-transit cadence."""
        rows = self._all(
            self._sql(
                "SELECT c.id, c.record, c.ephemeris_key FROM candidates c"
                " LEFT JOIN pixel_vets p ON p.candidate_id = c.id"
                f" WHERE c.status IN ({self._in(OPEN)}) AND c.period_d IS NOT NULL"
                " AND (p.candidate_id IS NULL"
                " OR p.ephemeris_key <> c.ephemeris_key"
                " OR (p.state = 'failed' AND p.attempts < ?))"
                " ORDER BY p.candidate_id IS NULL DESC, c.score DESC, c.id LIMIT ?"
            ),
            (*OPEN, max_attempts, limit),
        )
        return [VetTodo(r["id"], self._jo(r["record"]), r["ephemeris_key"]) for r in rows]

    def put_pixel_vet(
        self,
        candidate_id: str,
        ephemeris_key: str,
        record: dict[str, Any] | None,
        error: str | None,
        at: datetime,
    ) -> None:
        """Store a vet (record) or a failure (error). Failures on the same ephemeris count up."""
        state = "done" if record is not None else "failed"
        with self.atomic():
            old = self._one(
                self._sql(
                    "SELECT ephemeris_key, state, attempts FROM pixel_vets"
                    f" WHERE candidate_id = ?{self.FOR_UPDATE}"
                ),
                (candidate_id,),
            )
            same = old is not None and old["ephemeris_key"] == ephemeris_key
            attempts = old["attempts"] + 1 if same and old["state"] == "failed" else 1
            values = (
                self._j(record) if record is not None else None, ephemeris_key, state, error,
                attempts, self._t(at), candidate_id,
            )  # fmt: skip
            if old is None:
                self._exec(
                    self._sql(
                        "INSERT INTO pixel_vets (record, ephemeris_key, state, error, attempts,"
                        " vetted_at, candidate_id) VALUES (?,?,?,?,?,?,?)"
                    ),
                    values,
                )
            else:
                self._exec(
                    self._sql(
                        "UPDATE pixel_vets SET record = ?, ephemeris_key = ?, state = ?,"
                        " error = ?, attempts = ?, vetted_at = ? WHERE candidate_id = ?"
                    ),
                    values,
                )
            if record is not None:
                self._exec(
                    self._sql("UPDATE candidates SET pixel_verdict = ? WHERE id = ?"),
                    (record.get("verdict"), candidate_id),
                )

    def get_pixel_vet(self, candidate_id: str) -> dict[str, Any] | None:
        """The stored vet {record, vetted_at, current}, or None if it never succeeded.
        current is False when the candidate's ephemeris changed since (a new vet is due)."""
        r = self._one(
            self._sql(
                "SELECT p.record, p.vetted_at, p.ephemeris_key = c.ephemeris_key AS is_current"
                " FROM pixel_vets p JOIN candidates c ON c.id = p.candidate_id"
                " WHERE p.candidate_id = ? AND p.record IS NOT NULL"
            ),
            (candidate_id,),
        )
        if r is None:
            return None
        return {
            "record": self._jo(r["record"]),
            "vetted_at": self._to(r["vetted_at"]),
            "current": bool(r["is_current"]),
        }

    # Votes -------------------------------------------------------------------------------

    def put_vote(
        self,
        candidate_id: str,
        voter_key: str,
        vote: Vote | None,
        reason_chips: list[str],
        at: datetime,
    ) -> Vote | None:
        """Cast, change or (vote None) withdraw a vote. Returns the previous vote (None if there
        was none). Raises KeyError for an unknown candidate and PermissionError when casting on a
        dismissed one (withdrawing is always allowed). The candidate row is locked first, so
        concurrent votes can't lose a count. A candidate "under review" whose last vote is
        withdrawn goes back to "new"."""
        with self.atomic():
            c = self._one(
                self._sql(f"SELECT status FROM candidates WHERE id = ?{self.FOR_UPDATE}"),
                (candidate_id,),
            )
            if c is None:
                raise KeyError(candidate_id)
            if c["status"] == "dismissed" and vote is not None:
                raise PermissionError(candidate_id)
            old = self._one(
                self._sql("SELECT vote FROM votes WHERE candidate_id = ? AND voter_key = ?"),
                (candidate_id, voter_key),
            )
            if vote is None:
                if old is not None:
                    self._exec(
                        self._sql("DELETE FROM votes WHERE candidate_id = ? AND voter_key = ?"),
                        (candidate_id, voter_key),
                    )
            elif old is None:
                self._exec(
                    self._sql(
                        "INSERT INTO votes (candidate_id, voter_key, vote, reason_chips,"
                        " created_at, updated_at) VALUES (?,?,?,?,?,?)"
                    ),
                    (candidate_id, voter_key, vote, self._j(reason_chips), self._t(at),
                     self._t(at)),
                )  # fmt: skip
            else:
                self._exec(
                    self._sql(
                        "UPDATE votes SET vote = ?, reason_chips = ?, updated_at = ?"
                        " WHERE candidate_id = ? AND voter_key = ?"
                    ),
                    (vote, self._j(reason_chips), self._t(at), candidate_id, voter_key),
                )
            # Recounted, not incremented: a changed vote moves between columns.
            count = "(SELECT COUNT(*) FROM votes v WHERE v.candidate_id = candidates.id{})"
            total = count.format("")  # SET expressions see the old row: recount, don't reuse
            tallies = ", ".join(
                f"votes_{v} = " + count.format(f" AND v.vote = '{v}'")
                for v in ("planet", "fake", "unsure")
            )
            self._exec(
                self._sql(
                    f"UPDATE candidates SET {tallies}, votes_total = {total},"
                    f" status = CASE WHEN status = 'new' AND {total} > 0 THEN 'under review'"
                    f" WHEN status = 'under review' AND {total} = 0 THEN 'new'"
                    " ELSE status END WHERE id = ?"
                ),
                (candidate_id,),
            )
            return old["vote"] if old else None

    def get_vote(self, candidate_id: str, voter_key: str) -> dict[str, Any] | None:
        r = self._one(
            self._sql(
                "SELECT vote, reason_chips, created_at, updated_at FROM votes"
                " WHERE candidate_id = ? AND voter_key = ?"
            ),
            (candidate_id, voter_key),
        )
        if r is None:
            return None
        return {
            "vote": r["vote"],
            "reason_chips": self._jo(r["reason_chips"]),
            "created_at": self._to(r["created_at"]),
            "updated_at": self._to(r["updated_at"]),
        }

    def vote_reasons(self, candidate_id: str) -> dict[str, dict[str, int]]:
        """{vote: {chip: count}} over every vote on the candidate."""
        out: dict[str, dict[str, int]] = {}
        rows = self._all(
            self._sql("SELECT vote, reason_chips FROM votes WHERE candidate_id = ?"),
            (candidate_id,),
        )
        for r in rows:
            for chip in self._jo(r["reason_chips"]):
                chips = out.setdefault(r["vote"], {})
                chips[chip] = chips.get(chip, 0) + 1
        return out

    # Funnel, sensitivity -----------------------------------------------------------------

    def finder_counts(self) -> dict[str, dict[str, int]]:
        rows = self._all("SELECT status, COUNT(*) AS n FROM candidates GROUP BY status")
        status = {r["status"]: r["n"] for r in rows}
        verdicts = {
            r["pixel_verdict"]: r["n"]
            for r in self._all(
                "SELECT pixel_verdict, COUNT(*) AS n FROM candidates"
                " WHERE pixel_verdict IS NOT NULL GROUP BY pixel_verdict"
            )
        }
        return {"status": status, "pixel_verdict": verdicts}

    def put_finder_doc(self, table: str, record: dict[str, Any], at: datetime) -> None:
        """Replace the one row of `sensitivity` or `finder_sweep`."""
        if table not in DOC_TABLES:
            raise ValueError(table)
        self._exec(
            self._sql(
                f"INSERT INTO {table} (id, record, updated_at) VALUES (1, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET record = excluded.record,"
                " updated_at = excluded.updated_at"
            ),
            (self._j(record), self._t(at)),
        )

    def get_finder_doc(self, table: str) -> tuple[dict[str, Any], datetime] | None:
        if table not in DOC_TABLES:
            raise ValueError(table)
        r = self._one(f"SELECT record, updated_at FROM {table} WHERE id = 1")
        return (self._jo(r["record"]), self._to(r["updated_at"])) if r else None


def chunks(ids: list[str], size: int = 500) -> Iterator[list[str]]:
    for start in range(0, len(ids), size):
        yield ids[start : start + size]
