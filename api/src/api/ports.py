"""The only interfaces the API uses to reach pipeline/ (Analyze a star) and its database.

Real modules plug in through api/adapters/real.py; fakes live in api/fakes/. Events arrive
through `python -m api.ingest`, not through a port: the web requests only ever read the table.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from api.models import Analysis, JobRecord, JobStatus, JobStep, StarInfo, StoredAnalysis


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
        """Run the search (20-60 s on a full CPU). Raises LookupError if there is no light curve."""
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

    # jobs
    def create_job(self, job: JobRecord) -> None: ...
    def get_job(self, job_id: str) -> JobRecord | None: ...
    def set_job_status(
        self, job_id: str, status: JobStatus, *, at: datetime, error: str | None = None
    ) -> None: ...
    def append_job_step(self, job_id: str, step: JobStep) -> None: ...
    def queue_position(self, job_id: str) -> int | None: ...
    def fail_unfinished_jobs(self, reason: str, at: datetime) -> int: ...
