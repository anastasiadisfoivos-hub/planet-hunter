"""API-level shapes (not part of the shared contract)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from api.contract import Discovery, Sphere, StarTarget

TrapKind = Literal["sky", "star"]
JobStatus = Literal["queued", "running", "done", "failed"]


class TrapCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sphere: Sphere | None = None
    star: StarTarget | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> TrapCreate:
        if (self.sphere is None) == (self.star is None):
            raise ValueError("send exactly one of 'sphere' or 'star'")
        return self


class Trap(BaseModel):
    id: str
    kind: TrapKind
    sphere: Sphere | None = None
    star: StarTarget | None = None
    created_at: datetime
    last_checked_at: datetime | None = None
    last_tess_marker: str | None = None


class TrapRecord(Trap):
    player_id: str

    def public(self) -> Trap:
        return Trap.model_validate(self.model_dump(exclude={"player_id"}))


class SweepInfo(BaseModel):
    status: Literal["ok", "timeout", "error", "queued"]
    since: datetime | None = None
    until: datetime | None = None
    rejected: int = 0


class TrapCreated(BaseModel):
    trap: Trap
    sweep: SweepInfo
    catches: list[Discovery]
    job_id: str | None = None


class HuntRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    star: StarTarget


class HuntAccepted(BaseModel):
    job_id: str
    status: JobStatus


class JobStep(BaseModel):
    name: str
    at: datetime


class JobRecord(BaseModel):
    id: str
    player_id: str
    trap_id: str | None = None
    tic_id: int
    status: JobStatus
    steps: list[JobStep] = []
    result_ids: list[str] = []
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobView(BaseModel):
    id: str
    status: JobStatus
    tic_id: int
    trap_id: str | None = None
    queue_position: int | None = None
    steps: list[JobStep]
    result: list[Discovery] | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DiscoveryPage(BaseModel):
    items: list[Discovery]
    next_cursor: str | None = None
