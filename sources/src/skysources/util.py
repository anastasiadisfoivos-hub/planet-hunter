"""Small helpers shared by the clients."""

from __future__ import annotations

import math
from datetime import UTC, datetime


def as_utc(t: datetime | str) -> datetime:
    """Parse ISO strings (with or without Z) and make naive datetimes UTC."""
    if isinstance(t, str):
        t = datetime.fromisoformat(t.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle separation in degrees."""
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def float_or_none(v: object) -> float | None:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f
