from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    """Fixed-width UTC ISO string, so stored timestamps sort lexicographically."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


def parse(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None
