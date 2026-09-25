"""API shapes. Events are the SHARED EVENT CONTRACT (events/src/skyevents/models.py), passed
through as stored; everything for "Analyze a star" is defined here."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JobStatus = Literal["queued", "running", "done", "failed"]

# Letters, digits, spaces and the punctuation real star names use ("HD 209458", "Kepler-10",
# "eps Eri", "Barnard's star", "2MASS J0523+2344", "LHS 1140").
_NAME_RE = re.compile(r"^[\w .'+\-*/()]{1,80}$")
MAX_TIC = 10_000_000_000


# events -------------------------------------------------------------------------------


class _Open(BaseModel):
    """Contract shapes: documented here, but new upstream fields pass through untouched."""

    model_config = ConfigDict(extra="allow")


class EventImage(_Open):
    url: str
    thumb_url: str | None = None
    kind: str
    caption: str
    credit: str
    license: str
    width: int | None = None
    height: int | None = None


class Event(_Open):
    id: str
    type: str
    title: str
    summary: str
    source: str
    source_url: str
    observed_at: str
    reported_at: str
    location: dict[str, Any]
    confidence: float
    confidence_basis: str
    brightness_mag: float | None = None
    images: list[EventImage] = []
    raw: dict[str, Any] = {}


class EventPage(BaseModel):
    items: list[Event]
    next_cursor: str | None = None


class SourceStatus(_Open):
    state: str | None = None
    live: bool | None = None
    last_event_at: str | None = None
    events: int | None = None
    events_fetched: int | None = None
    error: str | None = None


class StatusView(BaseModel):
    ingested_at: str | None = None
    window: dict[str, Any] | None = None
    events_stored: int
    ingest: dict[str, Any] | None = None
    sources: dict[str, SourceStatus]
    rubin_stream: dict[str, Any] | None = None


# analyze a star -----------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, description='A star name, e.g. "WASP-18" or "TIC 123"')
    tic_id: int | None = Field(default=None, gt=0, lt=MAX_TIC)

    @field_validator("tic_id", mode="before")
    @classmethod
    def _int_or_digits(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("tic_id must be an integer")
        if isinstance(v, str):
            if not re.fullmatch(r"\s*\d{1,10}\s*", v):
                raise ValueError("tic_id must be an integer or a string of digits")
            return int(v)
        return v

    @field_validator("name")
    @classmethod
    def _plain_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = " ".join(v.split())
        if not _NAME_RE.fullmatch(v):
            raise ValueError("name must be 1-80 letters, digits, spaces or . ' + - * / ( )")
        return v

    @model_validator(mode="after")
    def _exactly_one(self) -> AnalyzeRequest:
        if (self.name is None) == (self.tic_id is None):
            raise ValueError("send exactly one of 'name' or 'tic_id'")
        return self


class StarInfo(BaseModel):
    tic_id: int
    name: str | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    radius_rsun: float | None = None
    teff_k: float | None = None
    tmag: float | None = None


class FoldedCurve(BaseModel):
    """The light curve folded on the signal's period, binned: phase 0 is mid-dip."""

    phase: list[float] = Field(max_length=1000)
    flux: list[float] = Field(max_length=1000)

    @model_validator(mode="after")
    def _same_length(self) -> FoldedCurve:
        if len(self.phase) != len(self.flux):
            raise ValueError("phase and flux must have the same length")
        return self


class Check(BaseModel):
    name: str
    passed: bool | None = None
    reason: str


class Link(BaseModel):
    label: str
    url: str


class Signal(BaseModel):
    id: str
    type: str  # "planet_candidate" | "eclipsing_binary"
    confidence: float = Field(ge=0, le=1)
    period_days: float
    t0_btjd: float
    duration_hours: float
    depth_ppm: float
    snr: float
    n_transits: int
    radius_rjup: float | None = None
    radius_lower_rjup: float | None = None
    radius_upper_rjup: float | None = None
    known_status: Literal["known", "not_on_lists", "unchecked"]
    name_if_known: str | None = None
    explanation: str
    checks: list[Check] = []
    links: list[Link] = []
    folded: FoldedCurve


class Flare(BaseModel):
    id: str
    peak_btjd: float
    peak_at: str
    amplitude: float
    confidence: float = Field(ge=0, le=1)
    explanation: str


class Sector(BaseModel):
    sector: int
    author: str
    exptime: float


class Analysis(BaseModel):
    """One star's result, stored compactly and served as is."""

    star: StarInfo
    sectors: list[Sector]
    signals: list[Signal]
    flares: list[Flare] = Field(max_length=50)
    flares_found: int
    signals_examined: int
    summary: str
    links: list[Link] = []


class StoredAnalysis(BaseModel):
    tic_id: int
    data_marker: str | None
    analyzed_at: datetime
    marker_checked_at: datetime
    analysis: Analysis


class AnalyzeResponse(BaseModel):
    status: JobStatus
    tic_id: int
    job_id: str | None = None
    queue_position: int | None = None
    cached: bool = False
    note: str | None = None
    result: StoredAnalysis | None = None


class JobStep(BaseModel):
    name: str
    at: datetime


class JobRecord(BaseModel):
    id: str
    tic_id: int
    status: JobStatus
    data_marker: str | None = None
    steps: list[JobStep] = []
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobView(BaseModel):
    id: str
    status: JobStatus
    tic_id: int
    queue_position: int | None = None
    steps: list[JobStep]
    error: str | None = None
    result: StoredAnalysis | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
