from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from api.contract import Forecast, Sphere
from api.deps import Player, ServicesDep
from api.timeutil import utcnow

router = APIRouter(tags=["forecast"])

MAX_WINDOW = timedelta(days=30)
_DURATION = re.compile(r"^(\d{1,4})([hd])$")


def parse_window(window: str, now: datetime) -> tuple[datetime, datetime]:
    """`12h` / `7d` from now, or an ISO-8601 interval `start/end` (naive times count as UTC)."""
    window = window.strip()
    m = _DURATION.match(window)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        span = timedelta(hours=n) if unit == "h" else timedelta(days=n)
        if not timedelta(hours=1) <= span <= MAX_WINDOW:
            raise ValueError("window must be between 1h and 30d")
        return now, now + span
    if "/" in window:
        a, b = window.split("/", 1)
        try:
            start, end = datetime.fromisoformat(a), datetime.fromisoformat(b)
        except ValueError:
            raise ValueError("window interval must be ISO-8601 'start/end'") from None
        start = start if start.tzinfo else start.replace(tzinfo=UTC)
        end = end if end.tzinfo else end.replace(tzinfo=UTC)
        if end <= start:
            raise ValueError("window end must be after its start")
        if end - start > MAX_WINDOW:
            raise ValueError("window can span at most 30 days")
        return start, end
    raise ValueError("window must look like '7d', '12h' or 'start/end'")


@router.get("/forecast", response_model=Forecast)
def get_forecast(
    pid: Player,
    svc: ServicesDep,
    ra: Annotated[float, Query(description="Right ascension, degrees [0, 360)")],
    dec: Annotated[float, Query(description="Declination, degrees [-90, 90]")],
    radius: Annotated[float, Query(description="Sphere radius, degrees [0.05, 10]")],
    window: Annotated[str, Query(description="'7d', '12h' or ISO 'start/end'")] = "7d",
) -> Forecast:
    try:
        sphere = Sphere(ra_deg=ra, dec_deg=dec, radius_deg=radius)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from None
    try:
        start, end = parse_window(window, utcnow())
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return svc.forecaster.forecast(sphere, start, end)
