"""FastAPI app factory. Run with: uv run uvicorn --factory api.app:create_app"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.jobs import AnalyzeQueue
from api.ratelimit import RateLimiter
from api.routes import admin, analyze, events, finder, stars
from api.settings import Settings
from api.timeutil import utcnow
from api.wiring import Services, build_services


def create_app(
    settings: Settings | None = None,
    services: Services | None = None,
    limiter: RateLimiter | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    services = services or build_services(settings)
    queue = AnalyzeQueue(
        services, settings.max_concurrent_hunts, settings.hunt_timeout_s, settings.max_queued_jobs
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Jobs don't survive a restart: mark them failed instead of leaving them hanging.
        await asyncio.to_thread(
            services.storage.fail_unfinished_jobs, "interrupted by a server restart", utcnow()
        )
        await queue.start()
        yield
        await queue.stop()

    app = FastAPI(
        title="planet-hunter phenomena spotter API",
        version="0.2.0",
        description="Live sky events with real pictures, Analyze a star (NASA TESS), each"
        " star's Lab data, and the Planet Finder's candidates.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.services = services
    app.state.analyze_queue = queue
    app.state.limiter = limiter or RateLimiter()
    if settings.web_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.web_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Voter-Key"],
            expose_headers=["Retry-After"],
            max_age=3600,
        )
    app.include_router(events.router)
    app.include_router(analyze.router)
    app.include_router(stars.router)
    app.include_router(finder.router)
    app.include_router(admin.router)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict:
        return {"ok": True}

    return app
