"""The search server's HTTP ingest, behind `Authorization: Bearer <PH_INGEST_TOKEN>` (off, 404,
unless set). With it the server needs no database URL: it sends each night's output in chunks
and runs the pixel checks itself (they need pixels/, which the API's deploy doesn't install).

- POST /finder/ingest: one chunk of candidates, monitor records, summary, sensitivity;
  `final: true` marks the run done (finder_ingest.ingest_chunk).
- GET /finder/pixel-queue: open candidates that need a pixel check for their current ephemeris.
- POST /finder/candidates/{id}/pixel-vet: the server's result (or failure) for one of them.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError

from api import monitor
from api.deps import ServicesDep, SettingsDep
from api.finder import CANDIDATE_ID, normalize_vet
from api.finder_ingest import ingest_chunk
from api.routes.monitor import require_ingest
from api.timeutil import utcnow

router = APIRouter(
    prefix="/finder",
    tags=["ingest"],
    include_in_schema=False,
    dependencies=[Depends(require_ingest)],
)

MAX_QUEUE = 100


class Chunk(BaseModel):
    run_id: str = Field(pattern=monitor.RUN_ID.pattern)
    run_started_at: datetime | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)
    monitor: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    summary: dict[str, Any] | None = None
    sensitivity: dict[str, Any] | None = None
    final: bool = False


@router.post("/ingest")
async def ingest(request: Request, services: ServicesDep, settings: SettingsDep) -> dict:
    """{run_id, run_started_at?, candidates: [{id, candidate}], monitor: [records], summary?,
    sensitivity?, final}. Answers the chunk's summary; invalid items are listed, not fatal."""
    size = request.headers.get("content-length")
    if size is None or not size.isdigit():
        raise HTTPException(411, "Content-Length is required.")
    if int(size) > settings.ingest_max_bytes:
        raise HTTPException(
            413, f"Chunk over {settings.ingest_max_bytes} bytes; send smaller chunks."
        )
    raw = await request.body()
    if len(raw) > settings.ingest_max_bytes:
        raise HTTPException(
            413, f"Chunk over {settings.ingest_max_bytes} bytes; send smaller chunks."
        )
    try:
        chunk = Chunk.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, f"Not a valid chunk: {str(exc)[:500]}") from None
    body = chunk.model_dump()
    started = body["run_started_at"]
    if started is not None and started.tzinfo is None:
        body["run_started_at"] = started.replace(tzinfo=UTC)
    return await run_in_threadpool(
        ingest_chunk, services.storage, body, keep_runs=settings.monitor_keep_runs
    )


@router.get("/pixel-queue")
def pixel_queue(
    services: ServicesDep,
    limit: Annotated[int, Query(ge=1, le=MAX_QUEUE)] = 20,
    max_attempts: Annotated[int, Query(ge=1, le=10)] = 3,
) -> dict:
    """{items: [{id, ephemeris_key, candidate}]}: never-vetted first, then by score; failed ones
    come back until `max_attempts`. Single dips never appear (no period to phase on)."""
    todo = services.storage.candidates_to_vet(limit, max_attempts)
    return {
        "items": [
            {"id": t.id, "ephemeris_key": t.ephemeris_key, "candidate": t.record} for t in todo
        ]
    }


class PixelVetIn(BaseModel):
    ephemeris_key: str = Field(min_length=1, max_length=200)
    vet: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=2000)


@router.post("/candidates/{candidate_id}/pixel-vet")
def pixel_vet(candidate_id: str, body: PixelVetIn, services: ServicesDep) -> dict:
    """Store the server's pixel check for the ephemeris it ran on: `vet` (a PixelVet) or `error`.
    409 when the candidate's ephemeris changed meanwhile (the new one is queued again)."""
    if not CANDIDATE_ID.match(candidate_id):
        raise HTTPException(404, f"No candidate {candidate_id}")
    storage = services.storage
    current = storage.candidate_ephemeris_key(candidate_id)
    if current is None:
        raise HTTPException(404, f"No candidate {candidate_id}")
    if current != body.ephemeris_key:
        raise HTTPException(409, "The candidate's ephemeris changed since it was queued.")
    if (body.vet is None) == (body.error is None):
        raise HTTPException(422, "Send exactly one of vet and error.")
    vet = None
    if body.vet is not None:
        try:
            vet = normalize_vet(body.vet)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, f"vet: {exc}") from None
    storage.put_pixel_vet(candidate_id, current, vet, body.error, utcnow())
    return {"id": candidate_id, "state": "done" if vet is not None else "failed"}
