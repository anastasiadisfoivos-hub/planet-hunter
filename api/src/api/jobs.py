"""In-process TESS hunt queue: at most `max_concurrent_hunts` running, the rest wait in order.

Storage calls block (network round trips on Postgres), so they run in threads, off the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from api import catalog
from api.models import JobRecord, JobStep
from api.timeutil import utcnow
from api.wiring import Services

log = logging.getLogger(__name__)


class HuntQueue:
    def __init__(self, services: Services, workers: int, timeout_s: float):
        self.services = services
        self.workers = workers
        self.timeout_s = timeout_s
        self._queue: asyncio.Queue[str] | None = None
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self._queue = asyncio.Queue()
        self._tasks = [asyncio.create_task(self._worker()) for _ in range(self.workers)]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def submit(self, player_id: str, tic_id: int, trap_id: str | None = None) -> JobRecord:
        assert self._queue is not None, "HuntQueue.start() was not called"
        now = utcnow()
        job = JobRecord(
            id=str(uuid.uuid4()),
            player_id=player_id,
            trap_id=trap_id,
            tic_id=tic_id,
            status="queued",
            steps=[JobStep(name="queued", at=now)],
            created_at=now,
        )
        await asyncio.to_thread(self.services.storage.create_job, job)
        await self._queue.put(job.id)
        return job

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            job_id = await self._queue.get()
            try:
                await self._run(job_id)
            except Exception:  # never let one job kill a worker
                log.exception("hunt job %s crashed", job_id)
            finally:
                self._queue.task_done()

    async def _run(self, job_id: str) -> None:
        storage = self.services.storage
        job = await asyncio.to_thread(storage.get_job, job_id)
        if job is None or job.status != "queued":
            return

        def set_status(status, **kw) -> None:
            storage.set_job_status(job_id, status, at=utcnow(), **kw)

        def step(name: str) -> None:
            storage.append_job_step(job_id, JobStep(name=name, at=utcnow()))

        def store(found, marker) -> catalog.IngestResult:
            now = utcnow()
            with storage.atomic():
                result = catalog.ingest_hunt(
                    storage, job.player_id, job.trap_id, job.tic_id, found, now
                )
                if job.trap_id and marker is not None and storage.get_trap(job.trap_id):
                    storage.set_trap_checked(job.trap_id, last_checked_at=now, marker=marker)
            return result

        await asyncio.to_thread(set_status, "running")
        await asyncio.to_thread(step, "started")
        try:
            marker = await asyncio.to_thread(self.services.hunter.latest_data_marker, job.tic_id)
            found = await asyncio.wait_for(
                asyncio.to_thread(self.services.hunter.hunt, job.tic_id, step), self.timeout_s
            )
            result = await asyncio.to_thread(store, found, marker)
            await asyncio.to_thread(step, f"stored {len(result.stored)} catches")
            await asyncio.to_thread(set_status, "done", result_ids=[d.id for d in result.stored])
        except TimeoutError:
            await asyncio.to_thread(set_status, "failed", error="hunt timed out")
        except Exception as e:
            log.warning("hunt job %s failed: %s", job_id, e)
            await asyncio.to_thread(set_status, "failed", error=str(e) or type(e).__name__)
