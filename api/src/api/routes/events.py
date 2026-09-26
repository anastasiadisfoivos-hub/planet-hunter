from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from skyevents.adapters import ADAPTERS
from skyevents.models import CATEGORIES, EVENT_TYPES
from skyevents.util import as_utc, parse_age

from api.deps import Reader, ServicesDep
from api.models import Event, EventPage, SourceStatus, StatusView
from api.ports import EventQuery
from api.timeutil import iso, utcnow

router = APIRouter(tags=["events"])

MAX_LIMIT = 200
SOURCES = tuple(ADAPTERS)


def encode_cursor(observed_at: datetime, event_id: str) -> str:
    raw = json.dumps([iso(observed_at), event_id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        observed_at, event_id = json.loads(raw)
        if not isinstance(observed_at, str) or not isinstance(event_id, str):
            raise ValueError
        return as_utc(observed_at), event_id
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid cursor.") from None


def _list(values: list[str] | None, allowed: tuple[str, ...], what: str) -> list[str]:
    """Repeated (?types=a&types=b) or comma-separated (?types=a,b), checked against `allowed`."""
    out = [v.strip() for raw in values or [] for v in raw.split(",") if v.strip()]
    if bad := sorted(set(out) - set(allowed)):
        raise HTTPException(422, f"Unknown {what}: {', '.join(bad)}. Known: {', '.join(allowed)}.")
    return sorted(set(out))


def _time(value: str | None, what: str) -> datetime | None:
    if value is None:
        return None
    try:
        return parse_age(value, utcnow())
    except ValueError:
        raise HTTPException(
            422, f"{what} must be an ISO date/time or an age like '7d' or '12h'."
        ) from None


@router.get("/events", response_model=EventPage, response_model_exclude_unset=True)
def list_events(
    _: Reader,
    svc: ServicesDep,
    types: Annotated[list[str] | None, Query(description="e.g. supernova,comet")] = None,
    categories: Annotated[list[str] | None, Query(description=", ".join(CATEGORIES))] = None,
    since: Annotated[str | None, Query(description="observed_at >= this (ISO, or '7d')")] = None,
    until: Annotated[str | None, Query(description="observed_at <= this (ISO, or '1d')")] = None,
    sources: Annotated[list[str] | None, Query(description=", ".join(SOURCES))] = None,
    frame: Literal["sky", "sun", "earth"] | None = None,
    ra: Annotated[float | None, Query(ge=0, lt=360, description="region RA (deg)")] = None,
    dec: Annotated[float | None, Query(ge=-90, le=90, description="region Dec (deg)")] = None,
    radius: Annotated[float | None, Query(gt=0, le=180, description="region radius (deg)")] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    has_images: bool | None = None,
    include_latest_window: Annotated[
        bool, Query(description="include Rubin's latest nights while its stream is paused")
    ] = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> EventPage:
    """Sky events, newest observed first. Every filter is optional; they combine with AND."""
    region = None
    given = [x is not None for x in (ra, dec, radius)]
    if any(given):
        if not all(given):
            raise HTTPException(422, "A region needs all of ra, dec and radius.")
        if frame not in (None, "sky"):
            raise HTTPException(422, "A sky region only applies to frame 'sky'.")
        region = (ra, dec, radius)
    q = EventQuery(
        types=_list(types, EVENT_TYPES, "types"),
        categories=_list(categories, tuple(CATEGORIES), "categories"),
        since=_time(since, "since"),
        until=_time(until, "until"),
        sources=_list(sources, SOURCES, "sources"),
        frame=frame,
        region=region,
        min_confidence=min_confidence,
        has_images=has_images,
        include_latest_window=include_latest_window,
        before=decode_cursor(cursor) if cursor else None,
        limit=limit + 1,
    )
    if q.since and q.until and q.since > q.until:
        raise HTTPException(422, "since must be before until.")
    rows = svc.storage.query_events(q)
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last, observed_at = rows[-1]
        next_cursor = encode_cursor(observed_at, last["id"])
    return EventPage(items=[r for r, _ in rows], next_cursor=next_cursor)


@router.get("/events/{event_id:path}", response_model=Event, response_model_exclude_unset=True)
def get_event(event_id: str, _: Reader, svc: ServicesDep) -> Event:
    record = svc.storage.get_event(event_id)
    if record is None:
        raise HTTPException(404, "No such event (events older than 90 days are removed).")
    return record


@router.get("/status", response_model=StatusView, tags=["meta"])
def status(_: Reader, svc: ServicesDep) -> StatusView:
    """When events were last fetched, each source's health, and whether Rubin's stream is live."""
    stored = svc.storage.get_status()
    run = stored.get("run")
    sources = {k.removeprefix("source:"): v for k, v in stored.items() if k.startswith("source:")}
    return StatusView(
        ingested_at=run.get("ingested_at") if run else None,
        window=run.get("window") if run else None,
        events_stored=svc.storage.count_events(),
        ingest=run,
        sources={k: SourceStatus.model_validate(v) for k, v in sorted(sources.items())},
        rubin_stream=stored.get("rubin_stream"),
    )
