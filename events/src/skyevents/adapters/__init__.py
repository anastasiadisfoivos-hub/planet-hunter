"""Source adapters. Each module exposes:

    NAME: str                         the Event.source value and id prefix
    LIVE_WITHIN: timedelta            a source is "live" if its newest event is younger than this
    fetch(since, until) -> list[Event]
    last_event_at(now) -> datetime | None    newest event the source has, for status.json

All HTTP goes through skysources' CachedClient (disk cache, per-host rate limit, retries), so
the test recorder can replay every response offline.
"""

from __future__ import annotations

from types import ModuleType

from . import cneos, comets, donki, gcn, gracedb, icecube, mpc, rubin, tns, ztf

ADAPTERS: dict[str, ModuleType] = {
    m.NAME: m for m in (rubin, ztf, tns, mpc, comets, cneos, donki, gcn, icecube, gracedb)
}

__all__ = ["ADAPTERS"]
