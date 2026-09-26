from __future__ import annotations

import math
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request

from api.ratelimit import RateLimiter
from api.settings import Settings
from api.wiring import Services


def services(request: Request) -> Services:
    return request.app.state.services


def settings(request: Request) -> Settings:
    return request.app.state.settings


def client_ip(request: Request, hops: int) -> str:
    """The caller's IP. Behind `hops` trusted proxies, each appends the address it saw to
    X-Forwarded-For, so the entry `hops` from the right is the one no client can forge."""
    if hops > 0:
        forwarded = [
            p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()
        ]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.client.host if request.client else "unknown"


def rate_limited(bucket: Literal["read", "vote", "admin", "ingest"]) -> Callable:
    """Per-IP token bucket; `vote`, `admin` and `ingest` each have their own (reads stay
    available)."""

    def dep(request: Request, cfg: Annotated[Settings, Depends(settings)]) -> str:
        limiter: RateLimiter = request.app.state.limiter
        ip = client_ip(request, cfg.trusted_proxy_hops)
        per_min = {
            "vote": cfg.rate_vote_per_min,
            "admin": cfg.rate_admin_per_min,
            "ingest": cfg.rate_ingest_per_min,
        }.get(bucket, cfg.rate_read_per_min)
        wait = limiter.hit(bucket, ip, per_min)
        if wait > 0:
            raise HTTPException(
                429,
                "Too many requests, slow down a little.",
                headers={"Retry-After": str(max(1, math.ceil(wait)))},
            )
        return ip

    return dep


Reader = Annotated[str, Depends(rate_limited("read"))]
Voter = Annotated[str, Depends(rate_limited("vote"))]
ServicesDep = Annotated[Services, Depends(services)]
SettingsDep = Annotated[Settings, Depends(settings)]
