"""Live monitor (the web's monitor page): the star being searched now, the log, sky coverage and
totals. While a sweep runs, its shards POST /monitor/progress with PH_INGEST_TOKEN; afterwards
`python -m api.finder_ingest` loads the run's monitor/*.json and marks it done."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api import monitor
from api.deps import Reader, ServicesDep, SettingsDep, rate_limited
from api.timeutil import utcnow

router = APIRouter(prefix="/monitor", tags=["monitor"])

MAX_LOG = 200
_limit = rate_limited("ingest")


def require_ingest(
    request: Request,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.ingest_token:
        raise HTTPException(404, "Not Found")
    _limit(request, settings)
    scheme, _, token = (authorization or "").partition(" ")
    given = token.strip().encode() if scheme.lower() == "bearer" else b""
    if not hmac.compare_digest(given, settings.ingest_token.encode()):
        raise HTTPException(403, "Wrong or missing ingest token (Authorization: Bearer ...).")


@router.get("/now")
def now(_: Reader, services: ServicesDep, settings: SettingsDep) -> dict:
    """{mode: "live"|"replay", run_id, run_started_at, progress: {done, total}, star, next_at}.
    `next_at` (replay only) is when the replay moves to the next star."""
    return monitor.now_view(
        services.storage,
        utcnow(),
        live_timeout_s=settings.monitor_live_timeout_s,
        step_s=settings.monitor_step_s,
    )


@router.get("/log")
def log(
    _: Reader,
    services: ServicesDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LOG)] = 50,
) -> dict:
    """The most recently searched stars, newest first (each star's latest search)."""
    return {"items": services.storage.monitor_log(limit)}


@router.get("/coverage")
def coverage(_: Reader, services: ServicesDep) -> dict:
    """Every star ever searched, by TESS sector and by 5-degree sky cell (ra/dec: the cell's
    centre, degrees)."""
    return services.storage.monitor_coverage()


@router.get("/stats")
def stats(_: Reader, services: ServicesDep) -> dict:
    """Totals over each star's latest search: signals = detections, candidates = detections
    whose outcome is "candidate", rejected_by_reason = the rest by reason."""
    return services.storage.monitor_stats()


class ProgressIn(BaseModel):
    run_id: str = Field(pattern=monitor.RUN_ID.pattern)
    run_started_at: datetime | None = None
    shard: int = Field(default=0, ge=0, le=10_000)
    done: int = Field(ge=0)
    total: int = Field(ge=0)
    star: dict[str, Any] | None = None  # the star this shard just finished (monitor shape)


@router.post("/progress", dependencies=[Depends(require_ingest)], include_in_schema=False)
def progress(body: ProgressIn, services: ServicesDep) -> dict:
    """A shard's progress (its own done/total; the run's is the sum), and optionally the star
    it just searched. Starts the run as "running"; a finished run stays finished."""
    if body.done > body.total:
        raise HTTPException(422, "done can't be more than total.")
    storage, at = services.storage, utcnow()
    started = body.run_started_at
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    star = None
    if body.star is not None:
        try:
            star = monitor.parse_star(body.star, at)
        except monitor.InvalidStar as exc:
            raise HTTPException(422, f"star: {exc}") from None
    with storage.atomic():
        storage.put_monitor_run(body.run_id, started, "running", at)
        storage.put_monitor_progress(body.run_id, body.shard, body.done, body.total, at)
        if star is not None:
            storage.put_monitor_star(body.run_id, star)
    run = storage.get_monitor_run(body.run_id)
    return {
        "run_id": body.run_id,
        "state": run["state"],
        "progress": {"done": run["done"], "total": run["total"]},
    }
