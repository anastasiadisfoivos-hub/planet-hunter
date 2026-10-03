"""Live monitor (the web's monitor page): the star being searched now, the log, sky coverage and
totals. While a sweep runs, its shards POST /monitor/progress with PH_INGEST_TOKEN; afterwards
`python -m api.finder_ingest` loads the run's monitor/*.json and marks it done."""

from __future__ import annotations

import hmac
import re
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field

from api import monitor
from api.deps import Reader, ServicesDep, SettingsDep, rate_limited
from api.timeutil import utcnow

router = APIRouter(prefix="/monitor", tags=["monitor"])

MAX_LOG = 200
LABEL = r"^[a-z][a-z0-9_-]{0,19}$"
RUNNER_STATES = ("searching", "vetting", "ingesting", "idle")
SPARK_NOTE = "each bin keeps its lowest point; sectors joined end to end"
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
def now(
    _: Reader,
    services: ServicesDep,
    settings: SettingsDep,
    after: Annotated[int | None, Query(ge=1)] = None,
) -> dict:
    """{mode: "live"|"replay", run_id, run_started_at, progress: {done, total}, star, next_at,
    next_tic, label, runner}. `next_at` (replay only) is when the replay moves to the next
    star. `after` (replay only; ignored live): return the star after this tic in the run's
    search order instead of the server-timed one. `next_tic` (replay only): the star after the
    returned one.
    `label`: which search found the star ("fast", "deep", "faint"), when the server said.
    `runner`: the search server's last heartbeat, {state, run_id, next_run_at, last_seen_at,
    responding}, or null if it never sent one."""
    at = utcnow()
    view = monitor.now_view(
        services.storage,
        at,
        live_timeout_s=settings.monitor_live_timeout_s,
        step_s=settings.monitor_step_s,
        after=after,
    )
    view["label"] = (view["star"] or {}).get("label")
    view["runner"] = monitor.runner_view(services.storage, at, stale_s=settings.runner_stale_s)
    return view


@router.get("/stars/{tic}")
def star(_: Reader, services: ServicesDep, tic: Annotated[int, Path(ge=1)]) -> dict:
    """The star's latest stored monitor record (full, light curve included). Only the last
    PH_MONITOR_KEEP_RUNS runs keep records: 404 otherwise."""
    record = services.storage.monitor_star_latest(tic)
    if record is None:
        raise HTTPException(404, f"No stored monitor record for TIC {tic}.")
    return record


@router.get("/log")
def log(
    _: Reader,
    services: ServicesDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LOG)] = 50,
    detail: bool = False,
) -> dict:
    """The most recently searched stars, newest first (each star's latest search). With
    detail=true each item also has `record`: that search's monitor record without `lightcurve`
    (null once its run is pruned)."""
    return {"items": services.storage.monitor_log(limit, detail=detail)}


@router.get("/coverage")
def coverage(_: Reader, services: ServicesDep) -> dict:
    """Every star ever searched, by TESS sector and by 5-degree sky cell (ra/dec: the cell's
    centre, degrees), and `stars`: each one's latest search {tic, ra, dec, outcome, sectors}
    (ra/dec in degrees, null when the record had none), by tic."""
    return services.storage.monitor_coverage()


@router.get("/stats")
def stats(_: Reader, services: ServicesDep) -> dict:
    """Totals over each star's latest search: signals = detections, candidates / known /
    rejected = detections whose outcome is "candidate" / "known" / "rejected",
    rejected_by_reason = the non-candidates by reason (known ones included, under their reason
    or "known"). `funnel` (only when a sweep summary is stored): its counts per step."""
    stats = services.storage.monitor_stats()
    doc = services.storage.get_finder_doc("finder_sweep")
    steps = monitor.funnel(doc[0] if doc else None)
    if steps is not None:
        stats["funnel"] = steps
    return stats


@router.get("/sparks")
def sparks(_: Reader, services: ServicesDep, response: Response) -> dict:
    """{unit: "ppm", bins, note, stars: {"<tic>": [ppm, ...]}}: every star whose latest search's
    record (light curve) is still kept, its whole curve in at most `bins` bins."""
    stars = {}
    for tic, f in services.storage.monitor_curves():
        if points := monitor.spark(f):
            stars[str(tic)] = points
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"unit": "ppm", "bins": monitor.SPARK_BINS, "note": SPARK_NOTE, "stars": stars}


class ProgressIn(BaseModel):
    run_id: str = Field(pattern=monitor.RUN_ID.pattern)
    run_started_at: datetime | None = None
    shard: int = Field(default=0, ge=0, le=10_000)
    done: int = Field(ge=0)
    total: int = Field(ge=0)
    star: dict[str, Any] | None = None  # the star this shard just finished (monitor shape)
    label: str | None = Field(default=None, pattern=LABEL)  # which search: fast, deep, faint


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
        record = dict(body.star)
        if body.label is not None:
            record["label"] = body.label
        try:
            star = monitor.parse_star(record, at)
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


class QueueCounts(BaseModel):
    done: int = Field(ge=0)
    listed: int | None = Field(default=None, ge=0)
    running: int = Field(default=0, ge=0)


class HeartbeatIn(BaseModel):
    runner_id: str | None = Field(default=None, pattern=monitor.RUN_ID.pattern)
    state: str = Field(pattern="^(" + "|".join(RUNNER_STATES) + ")$")
    run_id: str | None = Field(default=None, pattern=monitor.RUN_ID.pattern)
    next_run_at: datetime | None = None
    queues: dict[str, QueueCounts] | None = Field(default=None, max_length=20)


@router.post("/heartbeat", dependencies=[Depends(require_ingest)], include_in_schema=False)
def heartbeat(body: HeartbeatIn, services: ServicesDep) -> dict:
    """The search server says it is alive: what it is doing, when its next run starts, and its
    ledger's counts per queue. While it works on a run, that run stays "live" on the monitor."""
    for name in body.queues or {}:
        if not re.match(LABEL, name):
            raise HTTPException(422, f"queue name {name!r}: lower-case letters, digits, '_', '-'")
    at = utcnow()
    record = body.model_dump(mode="json")
    with services.storage.atomic():
        services.storage.put_finder_doc("monitor_heartbeat", record, at)
        if body.run_id and body.state != "idle":
            services.storage.put_monitor_run(body.run_id, None, "running", at)
    return {"ok": True, "received_at": at}


@router.get("/coverage/queues")
def coverage_queues(_: Reader, services: ServicesDep) -> dict:
    """The search ledger's counts per queue, as of the server's last heartbeat:
    {updated_at, queues: {name: {done, listed, running}}}; empty until one arrives."""
    doc = services.storage.get_finder_doc("monitor_heartbeat")
    if doc is None:
        return {"updated_at": None, "queues": {}}
    record, updated_at = doc
    return {"updated_at": updated_at, "queues": record.get("queues") or {}}
