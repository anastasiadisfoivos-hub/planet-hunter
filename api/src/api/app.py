"""FastAPI app factory. Run with: uv run uvicorn --factory api.app:create_app"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.jobs import HuntQueue
from api.ratelimit import RateLimiter
from api.routes import discoveries, forecast, hunt, traps
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
    queue = HuntQueue(services, settings.max_concurrent_hunts, settings.hunt_timeout_s)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Jobs don't survive a restart: mark them failed instead of leaving them hanging.
        services.storage.fail_unfinished_jobs("interrupted by a server restart", utcnow())
        await queue.start()
        yield
        await queue.stop()

    app = FastAPI(title="planet-hunter traps API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.services = services
    app.state.hunt_queue = queue
    app.state.limiter = limiter or RateLimiter()
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["X-Player-Id", "Content-Type"],
        )
    for module in (traps, forecast, hunt, discoveries):
        app.include_router(module.router)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict:
        return {"ok": True}

    return app
