"""FastAPI app factory. Run with: uv run uvicorn --factory api.app:create_app"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.ratelimit import RateLimiter
from api.routes import admin, finder, monitor
from api.settings import Settings
from api.wiring import Services, build_services


def create_app(
    settings: Settings | None = None,
    services: Services | None = None,
    limiter: RateLimiter | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    services = services or build_services(settings)

    app = FastAPI(
        title="planet-hunter planet finder API",
        version="2.0.0",
        description="The Planet Finder's candidates, pixel checks, vetting and votes, and the"
        " live monitor of the nightly sweep (NASA TESS).",
    )
    app.state.settings = settings
    app.state.services = services
    app.state.limiter = limiter or RateLimiter()
    if settings.web_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.web_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Voter-Key", "Authorization"],
            expose_headers=["Retry-After"],
            max_age=3600,
        )
    app.include_router(finder.router)
    app.include_router(admin.router)
    app.include_router(monitor.router)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict:
        return {"ok": True}

    return app
