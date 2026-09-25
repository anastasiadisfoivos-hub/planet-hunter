from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.deps import Player, QueueDep, ServicesDep, SettingsDep, rate_limited
from api.models import HuntAccepted, HuntRequest, JobView

router = APIRouter(tags=["hunt"])


@router.post("/hunt", status_code=202, response_model=HuntAccepted)
async def start_hunt(
    body: HuntRequest,
    pid: Annotated[str, Depends(rate_limited("hunt"))],
    svc: ServicesDep,
    cfg: SettingsDep,
    queue: QueueDep,
) -> HuntAccepted:
    """Queue a TESS hunt for one star. Poll GET /jobs/{id} for progress."""
    if svc.storage.count_pending_jobs(pid) >= cfg.max_pending_jobs_per_player:
        raise HTTPException(429, "You have too many hunts waiting. Try again when one finishes.")
    job = await queue.submit(pid, body.star.tic_id)
    return HuntAccepted(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str, pid: Player, svc: ServicesDep) -> JobView:
    job = svc.storage.get_job(job_id)
    if job is None or job.player_id != pid:
        raise HTTPException(404, "Job not found.")
    result = None
    if job.status == "done":
        result = [d for i in job.result_ids if (d := svc.storage.get_discovery(i)) is not None]
    return JobView(
        id=job.id,
        status=job.status,
        tic_id=job.tic_id,
        trap_id=job.trap_id,
        queue_position=svc.storage.queue_position(job.id),
        steps=job.steps,
        result=result,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
