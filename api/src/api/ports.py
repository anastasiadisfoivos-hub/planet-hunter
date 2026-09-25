"""The only interfaces the API uses to reach pipeline/ (Analyze a star), the NASA Exoplanet
Archive and its database.

Real modules plug in through api/adapters/real.py; fakes live in api/fakes/. Events arrive
through `python -m api.ingest`, not through a port: the web requests only ever read the table.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from api.models import (
    Analysis,
    HostSystem,
    JobRecord,
    JobStatus,
    JobStep,
    LightCurve,
    StarInfo,
    StoredAnalysis,
    StoredLightCurve,
)


class StarAnalyzer(Protocol):
    """pipeline/: TESS light-curve search for one star."""

    def resolve(self, name: str) -> StarInfo:
        """A star name to its TIC entry. Raises LookupError if no star has that name."""
        ...

    def latest_data_marker(self, tic_id: int) -> str | None:
        """Opaque marker (e.g. "sector-74") that changes when new TESS data exists.

        None means the star has no usable TESS light curve. Raises if MAST can't be reached.
        """
        ...

    def analyze(self, tic_id: int, progress: Callable[[str], None]) -> Analysis:
        """Run the search (20-60 s on a full CPU). Raises LookupError if there is no light curve.

        The result carries the unfolded light curve (Analysis.lightcurve), binned to <= 3000
        points, which storage keeps apart from the result."""
        ...

    def lightcurve(self, tic_id: int) -> LightCurve:
        """Just the unfolded, binned light curve (no search): the same data analyze() reads,
        for results stored before light curves were kept. Raises LookupError if there is none."""
        ...


class PlanetArchive(Protocol):
    """NASA Exoplanet Archive (pscomppars): the catalogued planets of one star."""

    def host_system(self, tic_id: int, now: datetime) -> HostSystem:
        """planets is empty when the star hosts none. Raises if the archive can't be reached."""
        ...


@dataclass
class EventRow:
    """One events-table row: the filter columns plus the stored Event itself."""

    id: str
    type: str
    category: str
    frame: str
    observed_at: datetime
    ra_deg: float | None
    dec_deg: float | None
    confidence: float
    has_images: bool
    from_latest_observed_window: bool
    sources: list[str]
    record: dict[str, Any]
    source_hash: str  # the event as fetched, before pictures
    content_hash: str  # the stored record
    images_checked_at: datetime
    updated_at: datetime


@dataclass
class EventMeta:
    source_hash: str
    content_hash: str
    images_checked_at: datetime
    images: list[dict[str, Any]]


@dataclass
class EventQuery:
    types: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    since: datetime | None = None
    until: datetime | None = None
    sources: list[str] = field(default_factory=list)
    frame: str | None = None
    region: tuple[float, float, float] | None = None  # ra, dec, radius (deg)
    min_confidence: float | None = None
    has_images: bool | None = None
    include_latest_window: bool = False
    before: tuple[datetime, str] | None = None  # cursor: (observed_at, id) of the last row seen
    limit: int = 50


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
    period_d: float | None
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


class Storage(Protocol):
    def atomic(self) -> AbstractContextManager[None]: ...
    def close(self) -> None: ...

    # events
    def event_meta(self, ids: list[str]) -> dict[str, EventMeta]: ...
    def upsert_event(self, row: EventRow) -> Upserted: ...
    def prune_events(self, observed_before: datetime) -> int: ...
    def query_events(self, q: EventQuery) -> list[tuple[dict[str, Any], datetime]]: ...
    def get_event(self, event_id: str) -> dict[str, Any] | None: ...
    def count_events(self) -> int: ...
    def put_status(self, key: str, record: dict[str, Any], at: datetime) -> None: ...
    def get_status(self) -> dict[str, dict[str, Any]]: ...

    # analyze a star
    def get_star_analysis(self, tic_id: int) -> StoredAnalysis | None: ...
    def put_star_analysis(self, rec: StoredAnalysis) -> None: ...
    def touch_star_analysis(self, tic_id: int, at: datetime) -> None: ...
    def get_star_name(self, key: str) -> int | None: ...
    def put_star_name(self, key: str, tic_id: int, at: datetime) -> None: ...

    # per-star lab
    def get_star_lightcurve(self, tic_id: int) -> StoredLightCurve | None: ...
    def put_star_lightcurve(self, rec: StoredLightCurve) -> None: ...
    def get_known_planets(self, tic_id: int) -> HostSystem | None: ...
    def put_known_planets(self, rec: HostSystem) -> None: ...

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
        self, candidate_id: str, voter_key: str, vote: Vote, reason_chips: list[str], at: datetime
    ) -> Vote | None: ...
    def get_vote(self, candidate_id: str, voter_key: str) -> dict[str, Any] | None: ...
    def vote_reasons(self, candidate_id: str) -> dict[str, dict[str, int]]: ...
    def mark_exported(self, ids: list[str], at: datetime) -> None: ...
    def finder_counts(self) -> dict[str, dict[str, int]]: ...
    def put_finder_doc(self, table: str, record: dict[str, Any], at: datetime) -> None: ...
    def get_finder_doc(self, table: str) -> tuple[dict[str, Any], datetime] | None: ...

    # jobs
    def create_job(self, job: JobRecord) -> None: ...
    def get_job(self, job_id: str) -> JobRecord | None: ...
    def set_job_status(
        self, job_id: str, status: JobStatus, *, at: datetime, error: str | None = None
    ) -> None: ...
    def append_job_step(self, job_id: str, step: JobStep) -> None: ...
    def queue_position(self, job_id: str) -> int | None: ...
    def fail_unfinished_jobs(self, reason: str, at: datetime) -> int: ...
