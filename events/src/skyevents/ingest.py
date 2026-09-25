"""Run every adapter, de-duplicate, add distances, and describe each source's health for status.json."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from .adapters import ADAPTERS
from .dedup import dedup
from .distance import coverage_by_source, enrich
from .models import Event
from .util import as_utc, iso

log = logging.getLogger(__name__)


def ingest(
    since: datetime, until: datetime, sources: list[str] | None = None, *, now: datetime | None = None
) -> tuple[list[Event], dict[str, Any]]:
    """(events, status). A failing source is reported in status and skipped, never fatal."""
    now = now or datetime.now(UTC)
    names = sources or list(ADAPTERS)
    if bad := set(names) - set(ADAPTERS):
        raise ValueError(f"unknown sources: {sorted(bad)} (known: {sorted(ADAPTERS)})")

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        results = dict(zip(names, pool.map(lambda n: _run(n, since, until, now), names), strict=True))

    events = [e for r in results.values() for e in r[0]]
    merged = dedup(events)
    try:
        distances = enrich(merged)
    except Exception as exc:  # noqa: BLE001 - distances are extra; the feed still goes out
        log.warning("distance enrichment failed: %s", exc)
        distances = {"error": str(exc)[:300]}
    for name, cov in coverage_by_source(merged, names).items():
        results[name][1]["distance"] = cov
    status = {
        "generated_at": iso(now),
        "window": {"since": iso(since), "until": iso(until)},
        "events_before_dedup": len(events),
        "events": len(merged),
        "events_in_window": sum(since <= as_utc(e["observed_at"]) <= until for e in merged),
        "sources": {n: results[n][1] for n in names},
        "distances": distances,
    }
    return merged, status


def _run(name: str, since: datetime, until: datetime, now: datetime) -> tuple[list[Event], dict[str, Any]]:
    ad = ADAPTERS[name]
    st: dict[str, Any] = {"live": None, "last_event_at": None, "events": 0, "events_fetched": 0, "error": None}
    events: list[Event] = []
    try:
        events = ad.fetch(since, until)
        # "events" counts only what was observed inside the requested window; a paused source
        # (Rubin's latest nights) or a long lookback (TNS, JPL) can return older ones too.
        st["events"] = sum(since <= as_utc(e["observed_at"]) <= until for e in events)
        st["events_fetched"] = len(events)
    except Exception as exc:  # noqa: BLE001 - one broken source must not stop the feed
        log.warning("%s fetch failed: %s", name, exc)
        st["error"] = f"fetch: {exc}"[:300]
    try:
        last = ad.last_event_at(now)
        st["last_event_at"] = iso(last) if last else None
        st["live"] = bool(last and now - last <= ad.LIVE_WITHIN)
    except Exception as exc:  # noqa: BLE001
        log.warning("%s status failed: %s", name, exc)
        st["error"] = (st["error"] + "; " if st["error"] else "") + f"status: {exc}"[:300]
    if hasattr(ad, "status_extra"):
        try:
            st.update(ad.status_extra(since, until))
        except Exception as exc:  # noqa: BLE001
            log.warning("%s status_extra failed: %s", name, exc)
    st["live_within_hours"] = ad.LIVE_WITHIN.total_seconds() / 3600
    st["state"] = "live" if st["live"] else ("unknown" if st["live"] is None else "paused")
    return events, st
