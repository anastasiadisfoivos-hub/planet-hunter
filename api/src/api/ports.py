"""The only interfaces the API uses to reach pipeline/, sources/ and forecast/, plus storage.

Real modules plug in through thin adapters (see api/adapters/real.py). Fakes live in api/fakes/.
All IDs must follow contracts/CONVENTIONS.md.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from api.contract import Discovery, Forecast, Sphere
from api.models import JobRecord, JobStatus, JobStep, TrapRecord


class AlertSource(Protocol):
    """sources/: Rubin alerts grouped per object.

    IDs: rubin:obj:<diaObjectId> or rubin:ss:<ssObjectId>.
    """

    def alerts_in_sphere(self, sphere: Sphere, since: datetime, until: datetime) -> list[Discovery]:
        """Objects with at least one alert in [since, until) inside the sphere."""
        ...


class StarHunter(Protocol):
    """pipeline/: TESS light-curve hunt for one star."""

    def latest_data_marker(self, tic_id: int) -> str | None:
        """Opaque marker (e.g. "sector-74") that changes when new TESS data exists.

        None means the star has no TESS data.
        """
        ...

    def hunt(self, tic_id: int, progress: Callable[[str], None]) -> list[Discovery]:
        """Run the hunt (20-60 s). Signals carry raw.period_days, flares raw.peak_btjd."""
        ...


class Forecaster(Protocol):
    """forecast/: what a sphere is likely to catch in a window."""

    def forecast(self, sphere: Sphere, start: datetime, end: datetime) -> Forecast: ...


class Storage(Protocol):
    def atomic(self) -> AbstractContextManager[None]: ...

    # traps
    def create_trap(self, trap: TrapRecord) -> None: ...
    def get_trap(self, trap_id: str) -> TrapRecord | None: ...
    def list_traps(self, player_id: str) -> list[TrapRecord]: ...
    def count_traps(self, player_id: str) -> int: ...
    def iter_traps(self) -> Iterator[TrapRecord]: ...
    def delete_trap(self, player_id: str, trap_id: str) -> bool: ...
    def set_trap_checked(
        self, trap_id: str, *, last_checked_at: datetime | None = None, marker: str | None = None
    ) -> None: ...

    # discoveries and catches
    def get_discovery(self, discovery_id: str) -> Discovery | None: ...
    def put_discovery(self, d: Discovery) -> None: ...
    def discoveries_with_prefix(self, prefix: str) -> list[Discovery]: ...
    def add_catch(
        self, player_id: str, discovery_id: str, trap_id: str | None, caught_at: datetime
    ) -> bool: ...
    def has_catch(self, player_id: str, discovery_id: str) -> bool: ...
    def list_catches(
        self, player_id: str, limit: int, before: tuple[str, str] | None
    ) -> list[tuple[Discovery, str]]: ...
    def count_catches(self) -> int: ...

    # jobs
    def create_job(self, job: JobRecord) -> None: ...
    def get_job(self, job_id: str) -> JobRecord | None: ...
    def set_job_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        at: datetime,
        result_ids: list[str] | None = None,
        error: str | None = None,
    ) -> None: ...
    def append_job_step(self, job_id: str, step: JobStep) -> None: ...
    def queue_position(self, job_id: str) -> int | None: ...
    def count_pending_jobs(self, player_id: str) -> int: ...
    def fail_unfinished_jobs(self, reason: str, at: datetime) -> int: ...
