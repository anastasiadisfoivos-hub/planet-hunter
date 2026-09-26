"""The only interfaces the API uses to reach pixels/, the known-planet lists and its database.

Real adapters live in api/adapters/finder_real.py; fakes in api/fakes/finder.py. Candidates and
the monitor's stars arrive through `python -m api.finder_ingest` (and, while a sweep runs, the
shards' POST /monitor/progress), never through a port.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

Upserted = Literal["created", "updated", "unchanged"]


# planet finder ---------------------------------------------------------------------------

CandidateStatus = Literal["new", "under review", "dismissed", "exported"]
Vote = Literal["planet", "fake", "unsure"]
CandidateSort = Literal["score", "newest", "votes"]


class PixelVetter(Protocol):
    """pixels/: is a candidate's dip on the target star or on a neighbour?"""

    def vet(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """The PixelVet dict ({verdict, reason, on_target_probability, ...}) for one candidate
        JSON. Raises on failure (no pixel data, MAST down, ...)."""
        ...


@dataclass
class KnownMatch:
    list_name: str  # "TOI" | "CTOI" | "confirmed" | "EB" | whatever the list calls itself
    name: str | None
    note: str | None = None  # e.g. "our period is twice the listed one"

    def reason(self) -> str:
        what = f"{self.list_name} {self.name}" if self.name else f"the {self.list_name} list"
        return f"matches {what}" + (f" ({self.note})" if self.note else "")


class KnownLists(Protocol):
    """Is a signal already on the TOI, CTOI, confirmed-planet or eclipsing-binary lists?"""

    def match(self, tic: int, period_d: float) -> KnownMatch | None:
        """None when it is on none of them. Raises when the lists can't be checked."""
        ...


@dataclass
class CandidateRow:
    id: str
    tic: int
    record: dict[str, Any]
    content_hash: str
    ephemeris_key: str
    score: float
    radius_rjup: float | None
    period_d: float | None  # None for a single dip (no period yet)
    vetting: dict[str, Any] | None  # VET's block, stored as JSON
    created_at: datetime
    updated_at: datetime


@dataclass
class CandidateQuery:
    min_radius: float | None = None  # Jupiter radii
    max_radius: float | None = None
    min_period: float | None = None  # days
    max_period: float | None = None
    pixel_verdicts: list[str] = field(default_factory=list)  # may include "unvetted"
    statuses: list[str] = field(default_factory=list)  # empty: all but dismissed
    needs_votes: int | None = None  # fewer votes than this, and still open (new/under review)
    sort: CandidateSort = "score"
    after: tuple[Any, str] | None = None  # cursor: (sort value, id) of the last row seen
    limit: int = 50


@dataclass
class VetTodo:
    id: str
    record: dict[str, Any]
    ephemeris_key: str


# monitor ---------------------------------------------------------------------------------


@dataclass
class MonitorStar:
    """One searched star (hunt's monitor/<tic>.json) plus the columns the monitor sorts and
    counts on."""

    tic: int
    record: dict[str, Any]
    searched_at: datetime
    outcome: str | None
    ra: float | None
    dec: float | None
    sectors: list[int]
    detections_count: int
    candidates_count: int
    rejected: dict[str, int]  # reason -> detections rejected for it


class Storage(Protocol):
    def atomic(self) -> AbstractContextManager[None]: ...
    def close(self) -> None: ...

    # planet finder
    def candidate_hashes(self, ids: list[str]) -> dict[str, str]: ...
    def upsert_candidate(self, row: CandidateRow) -> Upserted: ...
    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None: ...
    def query_candidates(self, q: CandidateQuery) -> list[dict[str, Any]]: ...
    def dismiss_candidate(self, candidate_id: str, reason: str, at: datetime) -> bool: ...
    def mark_known_checked(self, candidate_id: str, at: datetime) -> None: ...
    def candidates_to_recheck(self, limit: int) -> list[tuple[str, int, float]]: ...
    def candidates_to_vet(self, limit: int, max_attempts: int) -> list[VetTodo]: ...
    def put_pixel_vet(
        self, candidate_id: str, ephemeris_key: str, record: dict[str, Any] | None,
        error: str | None, at: datetime,
    ) -> None: ...  # fmt: skip
    def get_pixel_vet(self, candidate_id: str) -> dict[str, Any] | None: ...
    def put_vote(
        self, candidate_id: str, voter_key: str, vote: Vote | None, reason_chips: list[str],
        at: datetime,
    ) -> Vote | None: ...  # fmt: skip
    def get_vote(self, candidate_id: str, voter_key: str) -> dict[str, Any] | None: ...
    def vote_reasons(self, candidate_id: str) -> dict[str, dict[str, int]]: ...
    def mark_exported(self, ids: list[str], at: datetime) -> None: ...
    def finder_counts(self) -> dict[str, dict[str, int]]: ...
    def put_finder_doc(self, table: str, record: dict[str, Any], at: datetime) -> None: ...
    def get_finder_doc(self, table: str) -> tuple[dict[str, Any], datetime] | None: ...

    # monitor
    def put_monitor_run(
        self, run_id: str, started_at: datetime | None, state: str, at: datetime
    ) -> None: ...
    def put_monitor_progress(
        self, run_id: str, shard: int, done: int, total: int, at: datetime
    ) -> None: ...
    def put_monitor_star(self, run_id: str, star: MonitorStar) -> None: ...
    def get_monitor_run(self, run_id: str) -> dict[str, Any] | None: ...
    def latest_monitor_run(self, state: str | None = None) -> dict[str, Any] | None: ...
    def monitor_run_stars(self, run_id: str) -> list[tuple[int, datetime]]: ...
    def get_monitor_star(self, run_id: str, tic: int) -> dict[str, Any] | None: ...
    def latest_monitor_star(self, run_id: str) -> dict[str, Any] | None: ...
    def monitor_log(self, limit: int) -> list[dict[str, Any]]: ...
    def monitor_coverage(self) -> dict[str, Any]: ...
    def monitor_stats(self) -> dict[str, Any]: ...
    def prune_monitor_runs(self, keep: int) -> int: ...
