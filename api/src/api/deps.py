from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from api.jobs import HuntQueue
from api.ratelimit import RateLimiter
from api.settings import Settings
from api.wiring import Services


def services(request: Request) -> Services:
    return request.app.state.services


def settings(request: Request) -> Settings:
    return request.app.state.settings


def hunt_queue(request: Request) -> HuntQueue:
    return request.app.state.hunt_queue


def player_id(x_player_id: Annotated[str | None, Header()] = None) -> str:
    if not x_player_id:
        raise HTTPException(400, "Missing X-Player-Id header (a random UUID).")
    try:
        return str(uuid.UUID(x_player_id.strip()))
    except ValueError:
        raise HTTPException(400, "X-Player-Id must be a UUID.") from None


def _check(limiter: RateLimiter, bucket: str, key: str, per_minute: int) -> None:
    wait = limiter.hit(bucket, key, per_minute)
    if wait > 0:
        raise HTTPException(
            429,
            "Too many requests, slow down a little.",
            headers={"Retry-After": str(max(1, math.ceil(wait)))},
        )


def rate_limited(extra: str | None = None) -> Callable:
    """Per-player limit for every route, a per-IP backstop, and an optional per-route bucket."""

    def dep(
        request: Request,
        pid: Annotated[str, Depends(player_id)],
        cfg: Annotated[Settings, Depends(settings)],
    ) -> str:
        limiter: RateLimiter = request.app.state.limiter
        ip = request.client.host if request.client else "unknown"
        _check(limiter, "ip", ip, cfg.rate_ip_per_min)
        _check(limiter, "all", pid, cfg.rate_all_per_min)
        if extra == "trap_create":
            _check(limiter, extra, pid, cfg.rate_trap_create_per_min)
        elif extra == "hunt":
            _check(limiter, extra, pid, cfg.rate_hunt_per_min)
        return pid

    return dep


Player = Annotated[str, Depends(rate_limited())]
ServicesDep = Annotated[Services, Depends(services)]
SettingsDep = Annotated[Settings, Depends(settings)]
QueueDep = Annotated[HuntQueue, Depends(hunt_queue)]
