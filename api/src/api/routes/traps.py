from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from api import catalog
from api.deps import Player, QueueDep, ServicesDep, SettingsDep, rate_limited
from api.models import SweepInfo, Trap, TrapCreate, TrapCreated, TrapRecord
from api.timeutil import utcnow

log = logging.getLogger(__name__)
router = APIRouter(tags=["traps"])


@router.post("/traps", status_code=201, response_model=TrapCreated)
async def create_trap(
    body: TrapCreate,
    pid: Annotated[str, Depends(rate_limited("trap_create"))],
    svc: ServicesDep,
    cfg: SettingsDep,
    queue: QueueDep,
) -> TrapCreated:
    """Store a trap and sweep it right away: Rubin alerts from the last nights, or a TESS hunt."""
    storage = svc.storage
    if storage.count_traps(pid) >= cfg.max_traps_per_player:
        raise HTTPException(
            409, f"You already have {cfg.max_traps_per_player} traps. Remove one first."
        )
    now = utcnow()
    trap = TrapRecord(
        id=str(uuid.uuid4()),
        player_id=pid,
        kind="sky" if body.sphere else "star",
        sphere=body.sphere,
        star=body.star,
        created_at=now,
    )

    if body.star is not None:
        if storage.count_pending_jobs(pid) >= cfg.max_pending_jobs_per_player:
            raise HTTPException(
                429, "You have too many hunts waiting. Try again when one finishes."
            )
        storage.create_trap(trap)
        job = await queue.submit(pid, body.star.tic_id, trap_id=trap.id)
        return TrapCreated(
            trap=trap.public(), sweep=SweepInfo(status="queued"), catches=[], job_id=job.id
        )

    since, until = now - timedelta(days=cfg.sweep_nights), now
    status = "ok"
    found = []
    try:
        found = await asyncio.wait_for(
            asyncio.to_thread(svc.alerts.alerts_in_sphere, body.sphere, since, until),
            cfg.sweep_timeout_s,
        )
    except TimeoutError:
        status = "timeout"
    except Exception:
        log.exception("instant sweep failed")
        status = "error"

    # A failed sweep leaves last_checked_at at the window start, so the nightly check retries it.
    trap.last_checked_at = until if status == "ok" else since
    with storage.atomic():
        storage.create_trap(trap)
        result = catalog.ingest_rubin(storage, pid, trap.id, found, now)
    return TrapCreated(
        trap=trap.public(),
        sweep=SweepInfo(status=status, since=since, until=until, rejected=len(result.rejected)),
        catches=result.stored,
    )


@router.get("/traps", response_model=list[Trap])
def list_traps(pid: Player, svc: ServicesDep) -> list[Trap]:
    return [t.public() for t in svc.storage.list_traps(pid)]


@router.delete("/traps/{trap_id}", status_code=204)
def delete_trap(trap_id: str, pid: Player, svc: ServicesDep) -> Response:
    """Remove a trap. What it already caught stays in the player's collection."""
    if not svc.storage.delete_trap(pid, trap_id):
        raise HTTPException(404, "Trap not found.")
    return Response(status_code=204)
