from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response

from api import analysis
from api.deps import Analyzer, QueueDep, Reader, ServicesDep, SettingsDep
from api.jobs import QueueFull
from api.models import MAX_TIC, AnalyzeRequest, AnalyzeResponse, JobView, StoredAnalysis
from api.timeutil import utcnow

router = APIRouter(tags=["analyze a star"])


async def _resolve(body: AnalyzeRequest, svc: ServicesDep, cfg: SettingsDep) -> int:
    if body.tic_id is not None:
        return body.tic_id
    name = body.name or ""
    tic = await asyncio.to_thread(analysis.lookup_name, svc.storage, name)
    if tic is not None:
        return tic
    try:
        star = await asyncio.wait_for(
            asyncio.to_thread(svc.analyzer.resolve, name), cfg.resolve_timeout_s
        )
    except LookupError:
        raise HTTPException(404, f"No star called {name!r} in the TESS Input Catalog.") from None
    except Exception:
        raise HTTPException(
            503, "The star catalogue (MAST) isn't answering. Try again, or use the TIC number."
        ) from None
    await asyncio.to_thread(analysis.remember_name, svc.storage, name, star.tic_id, utcnow())
    return star.tic_id


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={202: {"model": AnalyzeResponse, "description": "Queued: poll GET /jobs/{job_id}"}},
)
async def analyze(
    body: AnalyzeRequest,
    response: Response,
    _: Analyzer,
    svc: ServicesDep,
    cfg: SettingsDep,
    queue: QueueDep,
) -> AnalyzeResponse:
    """Check a star for planets in NASA TESS data.

    200 with the result when it's stored for the star's current TESS data; otherwise 202 with a
    job to poll. Only new TESS data makes a star get analyzed again.
    """
    tic = await _resolve(body, svc, cfg)

    if (job := queue.active(tic)) is not None:
        response.status_code = 202
        return AnalyzeResponse(status=job.status, tic_id=tic, job_id=job.id)

    try:
        fresh = await asyncio.wait_for(
            asyncio.to_thread(
                analysis.check, svc.storage, svc.analyzer, tic, utcnow(), cfg.marker_ttl_s
            ),
            cfg.marker_timeout_s,
        )
    except TimeoutError:  # MAST is slow: serve what is stored, or queue (the job checks again)
        rec = await asyncio.to_thread(svc.storage.get_star_analysis, tic)
        fresh = analysis.Freshness(
            rec, rec is not None, note=analysis.NOTE_UNAVAILABLE if rec else None
        )

    if fresh.current and fresh.stored is not None:
        return AnalyzeResponse(
            status="done", tic_id=tic, cached=True, note=fresh.note, result=fresh.stored
        )
    if fresh.no_data:
        raise HTTPException(
            404, f"TIC {tic} has no TESS light curve (SPOC, TESS-SPOC or QLP) to analyze."
        )
    try:
        job = await queue.submit(tic, fresh.marker)
    except QueueFull:
        raise HTTPException(
            503,
            "Lots of stars are being analyzed right now. Try again in a few minutes.",
            headers={"Retry-After": "120"},
        ) from None
    response.status_code = 202
    position = await asyncio.to_thread(svc.storage.queue_position, job.id)
    return AnalyzeResponse(status=job.status, tic_id=tic, job_id=job.id, queue_position=position)


@router.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: Annotated[str, Path(max_length=64)], _: Reader, svc: ServicesDep) -> JobView:
    job = svc.storage.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    result = svc.storage.get_star_analysis(job.tic_id) if job.status == "done" else None
    return JobView(
        id=job.id,
        status=job.status,
        tic_id=job.tic_id,
        queue_position=svc.storage.queue_position(job.id),
        steps=job.steps,
        error=job.error,
        result=result,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/stars/{tic_id}/analysis", response_model=StoredAnalysis)
def get_analysis(
    tic_id: Annotated[int, Path(gt=0, lt=MAX_TIC)], _: Reader, svc: ServicesDep
) -> StoredAnalysis:
    """The stored result for this star, however old; POST /analyze checks it's current."""
    rec = svc.storage.get_star_analysis(tic_id)
    if rec is None:
        raise HTTPException(404, f"TIC {tic_id} hasn't been analyzed yet. POST /analyze first.")
    return rec
