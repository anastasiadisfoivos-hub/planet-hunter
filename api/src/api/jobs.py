"""In-process Analyze queue: at most `workers` analyses at once, the rest wait in order.

One job per star: asking again for a star that is already queued or running returns that job.
A job is a full analysis, or (`lightcurve_only`) the re-read of a stored result's light curve
for a result stored before light curves were kept: no new search.
Storage calls block (network round trips on Postgres), so they run in threads, off the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from api import analysis
from api.models import JobRecord, JobStep
from api.timeutil import utcnow
from api.wiring import Services

log = logging.getLogger(__name__)


class QueueFull(Exception):
    pass


class AnalyzeQueue:
    def __init__(self, services: Services, workers: int, timeout_s: float, max_queued: int):
        self.services = services
        self.workers = workers
        self.timeout_s = timeout_s
        self.max_queued = max_queued
        self._queue: asyncio.Queue[str] | None = None
        self._tasks: list[asyncio.Task] = []
        self._lock: asyncio.Lock | None = None
        self._active: dict[int, JobRecord] = {}  # tic -> its queued or running job
        self._lightcurve_only: set[str] = set()  # job ids that only re-read a light curve

    async def start(self) -> None:
        self._queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._tasks = [asyncio.create_task(self._worker()) for _ in range(self.workers)]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def active(self, tic_id: int) -> JobRecord | None:
        return self._active.get(tic_id)

    def is_lightcurve_only(self, job_id: str) -> bool:
        return job_id in self._lightcurve_only

    async def submit(
        self, tic_id: int, marker: str | None, *, lightcurve_only: bool = False
    ) -> JobRecord:
        """Queue an analysis, or return the star's job already in the queue."""
        assert self._queue is not None and self._lock is not None, "start() was not called"
        async with self._lock:
            if (job := self._active.get(tic_id)) is not None:
                return job
            if len(self._active) >= self.max_queued:
                raise QueueFull
            now = utcnow()
            job = JobRecord(
                id=str(uuid.uuid4()),
                tic_id=tic_id,
                status="queued",
                data_marker=marker,
                steps=[JobStep(name="queued", at=now)],
                created_at=now,
            )
            await asyncio.to_thread(self.services.storage.create_job, job)
            if lightcurve_only:
                self._lightcurve_only.add(job.id)
            self._active[tic_id] = job
            await self._queue.put(job.id)
            return job

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            job_id = await self._queue.get()
            try:
                await self._run(job_id)
            except Exception:  # never let one job kill a worker
                log.exception("analyze job %s crashed", job_id)
            finally:
                self._queue.task_done()

    async def _run(self, job_id: str) -> None:
        storage, analyzer = self.services.storage, self.services.analyzer
        job = await asyncio.to_thread(storage.get_job, job_id)
        if job is None or job.status != "queued":
            return
        tic = job.tic_id

        def set_status(status, **kw) -> None:
            storage.set_job_status(job_id, status, at=utcnow(), **kw)

        def step(name: str) -> None:
            storage.append_job_step(job_id, JobStep(name=name, at=utcnow()))

        if job_id in self._lightcurve_only:
            try:
                await self._reread_lightcurve(job_id, tic, set_status, step)
            finally:
                self._lightcurve_only.discard(job_id)
                self._active.pop(tic, None)
            return

        try:
            await asyncio.to_thread(set_status, "running")
            await asyncio.to_thread(step, "started")
            # Someone (another instance, a precompute shard) may have stored this data meanwhile.
            rec = await asyncio.to_thread(analysis.reusable, storage, tic, job.data_marker)
            if rec is None:
                analyzed = await asyncio.wait_for(
                    asyncio.to_thread(analyzer.analyze, tic, step), self.timeout_s
                )
                marker = job.data_marker
                if marker is None:
                    marker = await asyncio.to_thread(analysis.marker_or_none, analyzer, tic)
                rec = await asyncio.to_thread(
                    analysis.store, storage, tic, marker, analyzed, utcnow()
                )
            await asyncio.to_thread(step, f"stored result (data {rec.data_marker or 'unknown'})")
            await asyncio.to_thread(set_status, "done")
        except TimeoutError:
            await asyncio.to_thread(set_status, "failed", error="analysis timed out")
        except LookupError as e:
            await asyncio.to_thread(analysis.record_no_data, storage, tic, utcnow())
            await asyncio.to_thread(set_status, "failed", error=str(e))
        except Exception as e:
            log.warning("analyze job %s failed: %s", job_id, e)
            await asyncio.to_thread(set_status, "failed", error=str(e) or type(e).__name__)
        finally:
            self._active.pop(tic, None)

    async def _reread_lightcurve(self, job_id: str, tic: int, set_status, step) -> None:
        storage, analyzer = self.services.storage, self.services.analyzer
        try:
            await asyncio.to_thread(set_status, "running")
            await asyncio.to_thread(step, "re-reading the light curve (no new search)")
            rec = await asyncio.to_thread(storage.get_star_analysis, tic)
            if rec is not None and await asyncio.to_thread(analysis.needs_lightcurve, storage, rec):
                lc = await asyncio.wait_for(
                    asyncio.to_thread(
                        analysis.backfill_lightcurve, storage, analyzer, rec, utcnow()
                    ),
                    self.timeout_s,
                )
                n = len(lc.curve.time_btjd) if lc.curve else 0
                await asyncio.to_thread(step, f"stored light curve ({n} points)")
            await asyncio.to_thread(set_status, "done")
        except TimeoutError:
            await asyncio.to_thread(set_status, "failed", error="light curve re-read timed out")
        except Exception as e:  # noqa: BLE001 - the stored result itself is untouched
            log.warning("light curve job %s failed: %s", job_id, e)
            error = f"could not re-read the light curve: {str(e) or type(e).__name__}"
            await asyncio.to_thread(set_status, "failed", error=error)
