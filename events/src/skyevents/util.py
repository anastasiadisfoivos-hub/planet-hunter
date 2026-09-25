"""Small helpers shared by the adapters: time parsing, sky geometry, event building."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from astropy.time import Time

from .models import Event, Image, Location


def as_utc(t: datetime | str) -> datetime:
    """datetime or ISO string (a trailing Z is fine) -> aware UTC datetime."""
    if isinstance(t, str):
        t = datetime.fromisoformat(t.strip().replace("Z", "+00:00").replace(" ", "T", 1))
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)


def iso(t: datetime) -> str:
    return as_utc(t).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_age(text: str, now: datetime) -> datetime:
    """'7d', '12h', '30m' -> now minus that; anything else is an ISO date/time."""
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)\s*([dhm])", text.strip()):
        n, unit = float(m[1]), m[2]
        return now - timedelta(**{{"d": "days", "h": "hours", "m": "minutes"}[unit]: n})
    return as_utc(text)


def mjd_utc_to_dt(mjd: float) -> datetime:
    return Time(float(mjd), format="mjd", scale="utc").to_datetime(UTC)


def mjd_tai_to_dt(mjd: float) -> datetime:
    return Time(float(mjd), format="mjd", scale="tai").utc.to_datetime(UTC)


def dt_to_mjd_utc(t: datetime) -> float:
    return float(Time(as_utc(t)).utc.mjd)


def sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle separation (haversine), degrees."""
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    h = math.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * math.cos(d2) * math.sin((r2 - r1) / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(h))))


def hms_to_deg(text: str) -> float:
    h, m, s = (float(x) for x in re.split(r"[:hms\s]+", text.strip()) if x)
    return (h + m / 60 + s / 3600) * 15.0


def dms_to_deg(text: str) -> float:
    t = text.strip()
    sign = -1.0 if t.startswith("-") else 1.0
    d, m, s = (float(x) for x in re.split(r"[:d'\"\s°′″]+", t.lstrip("+-")) if x)
    return sign * (d + m / 60 + s / 3600)


def num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def sky(ra: float, dec: float, error_deg: float) -> Location:
    return {"frame": "sky", "ra_deg": round(ra % 360.0, 6), "dec_deg": round(dec, 6), "error_deg": round(error_deg, 8)}


def make_event(
    *,
    source: str,
    source_id: str,
    type: str,
    title: str,
    summary: str,
    source_url: str,
    observed_at: datetime | str,
    reported_at: datetime | str,
    location: Location,
    confidence: float,
    confidence_basis: str,
    brightness_mag: float | None = None,
    images: list[Image] | None = None,
    raw: dict[str, Any] | None = None,
) -> Event:
    """One place that builds an Event, so every adapter emits the same keys in the same order."""
    return {
        "id": f"{source}:{source_id}",
        "type": type,  # type: ignore[typeddict-item]
        "title": title,
        "summary": summary,
        "source": source,
        "source_url": source_url,
        "observed_at": iso(as_utc(observed_at)),
        "reported_at": iso(as_utc(reported_at)),
        "location": location,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 4),
        "confidence_basis": confidence_basis,  # type: ignore[typeddict-item]
        "brightness_mag": None if brightness_mag is None else round(float(brightness_mag), 2),
        "images": images or [],
        "raw": raw or {},
    }
