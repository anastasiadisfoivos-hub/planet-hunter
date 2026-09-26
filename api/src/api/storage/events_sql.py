"""GET /events as one SQL query, shared by both backends (they differ only in placeholder and
how a timestamp is passed)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from api.ports import EventQuery


def build_query(q: EventQuery, ph: str, ts: Callable[[datetime], Any]) -> tuple[str, list[Any]]:
    """SQL selecting (record, observed_at) newest first, and its parameters."""
    where: list[str] = []
    params: list[Any] = []

    def any_of(column: str, values: list[str]) -> None:
        where.append(f"{column} IN ({', '.join([ph] * len(values))})")
        params.extend(values)

    if q.types:
        any_of("e.type", q.types)
    if q.categories:
        any_of("e.category", q.categories)
    if q.since is not None:
        where.append(f"e.observed_at >= {ph}")
        params.append(ts(q.since))
    if q.until is not None:
        where.append(f"e.observed_at <= {ph}")
        params.append(ts(q.until))
    if q.sources:
        where.append(
            "EXISTS (SELECT 1 FROM event_sources s WHERE s.event_id = e.id"
            f" AND s.source IN ({', '.join([ph] * len(q.sources))}))"
        )
        params.extend(q.sources)
    if q.frame is not None:
        where.append(f"e.frame = {ph}")
        params.append(q.frame)
    if q.region is not None:
        ra, dec, radius = q.region
        where.append("e.frame = 'sky'")
        # The declination band uses the index; the distance check is exact.
        where.append(f"e.dec_deg BETWEEN {ph} AND {ph}")
        params += [dec - radius, dec + radius]
        where.append(f"ph_sep_deg({ph}, {ph}, e.ra_deg, e.dec_deg) <= {ph}")
        params += [ra, dec, radius]
    if q.min_confidence is not None:
        where.append(f"e.confidence >= {ph}")
        params.append(q.min_confidence)
    if q.has_images is not None:
        where.append("e.has_images" if q.has_images else "NOT e.has_images")
    if not q.include_latest_window:
        where.append("NOT e.from_latest_observed_window")
    if q.before is not None:
        where.append(f"(e.observed_at, e.id) < ({ph}, {ph})")
        params += [ts(q.before[0]), q.before[1]]

    sql = "SELECT e.record, e.observed_at FROM events e"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY e.observed_at DESC, e.id DESC LIMIT {ph}"
    params.append(q.limit)
    return sql, params
