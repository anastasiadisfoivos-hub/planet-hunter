"""Fill the events table: `python -m api.ingest`.

skyevents fetches and de-duplicates every source; skypictures adds real pictures; the result is
upserted (an unchanged event is not rewritten), events observed more than --keep-days ago are
deleted, and each source's health plus Rubin's stream state are stored for GET /status.

    uv run python -m api.ingest                      # last 7 days, all sources, with pictures
    uv run python -m api.ingest --since 2d --sources donki,cneos --no-pictures
    uv run python -m api.ingest --from-file events.json --status-file status.json

Pictures are the slow part (every URL is checked), so an event keeps its stored pictures while
it hasn't changed and they were checked within --pictures-ttl-h.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from api import honesty
from api.ports import EventRow, Storage
from api.timeutil import iso, utcnow

log = logging.getLogger("api.ingest")

Enrich = Callable[[dict[str, Any]], list[dict[str, Any]]]


@dataclass
class IngestSummary:
    fetched: int = 0
    stored: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    pruned: int = 0
    too_old: int = 0
    rejected: list[str] = field(default_factory=list)
    pictures_checked: int = 0
    pictures_reused: int = 0


def digest(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def parse_time(value: str) -> datetime:
    from skyevents.util import as_utc

    return as_utc(value)


def category_of(event_type: str) -> str:
    from skyevents.models import CATEGORY_OF

    return CATEGORY_OF.get(event_type, "other")


def event_sources(event: dict[str, Any]) -> list[str]:
    members = (event.get("raw") or {}).get("sources") or []
    found = {event["source"], *(m.get("source") for m in members if isinstance(m, dict))}
    return sorted(s for s in found if isinstance(s, str) and s)


def _check(event: Any) -> str | None:
    """Why this event can't be stored, or None."""
    if not isinstance(event, dict):
        return "not an object"
    for key in ("id", "type", "source", "observed_at", "location", "confidence"):
        if key not in event:
            return f"missing {key}"
    loc = event["location"]
    if not isinstance(loc, dict) or loc.get("frame") not in ("sky", "sun", "earth"):
        return "bad location"
    coords = (loc.get("ra_deg"), loc.get("dec_deg"))
    if loc["frame"] == "sky" and not all(isinstance(c, int | float) for c in coords):
        return "sky location without ra/dec"
    try:
        parse_time(event["observed_at"])
    except (TypeError, ValueError):
        return "bad observed_at"
    return None


def to_row(
    record: dict[str, Any], *, source_hash: str, images_checked_at: datetime, now: datetime
) -> EventRow:
    loc = record["location"]
    sky = loc["frame"] == "sky"
    raw = record.get("raw") or {}
    return EventRow(
        id=record["id"],
        type=record["type"],
        category=category_of(record["type"]),
        frame=loc["frame"],
        observed_at=parse_time(record["observed_at"]),
        ra_deg=float(loc["ra_deg"]) if sky else None,
        dec_deg=float(loc["dec_deg"]) if sky else None,
        confidence=float(record["confidence"]),
        has_images=bool(record.get("images")),
        from_latest_observed_window=bool(raw.get("from_latest_observed_window")),
        sources=event_sources(record),
        record=record,
        source_hash=source_hash,
        content_hash=digest(record),
        images_checked_at=images_checked_at,
        updated_at=now,
    )


def pictures_enricher(check: bool = True) -> Enrich:
    """skypictures: the event's real pictures (its own ones too), checked and in display order."""
    from skypictures.cli import enrich_event
    from skypictures.core import Stats

    stats = Stats()

    def enrich(event: dict[str, Any]) -> list[dict[str, Any]]:
        return enrich_event(event, check=check, replace=False, stats=stats)["images"]

    return enrich


def store_events(
    storage: Storage,
    events: list[dict[str, Any]],
    *,
    now: datetime,
    enrich: Enrich | None = None,
    keep_days: float = 90,
    pictures_ttl: timedelta = timedelta(hours=24),
    workers: int = 6,
) -> IngestSummary:
    summary = IngestSummary(fetched=len(events))
    cutoff = now - timedelta(days=keep_days)

    good: dict[str, dict[str, Any]] = {}
    for event in events:
        if (why := _check(event)) is not None:
            summary.rejected.append(f"{event.get('id') if isinstance(event, dict) else '?'}: {why}")
            continue
        if parse_time(event["observed_at"]) < cutoff:
            summary.too_old += 1
            continue
        good[event["id"]] = event  # skyevents already de-duplicates; last one wins otherwise

    meta = storage.event_meta(list(good))
    plan: dict[str, tuple[str, list[dict[str, Any]] | None, datetime]] = {}
    to_enrich: list[str] = []
    for eid, event in good.items():
        source_hash = digest(event)
        m = meta.get(eid)
        if (
            m is not None
            and m.source_hash == source_hash
            and (enrich is None or now - m.images_checked_at < pictures_ttl)
        ):
            plan[eid] = (source_hash, m.images, m.images_checked_at)
            summary.pictures_reused += 1
        elif enrich is None:
            plan[eid] = (source_hash, list(event.get("images") or []), now)
        else:
            plan[eid] = (source_hash, None, now)
            to_enrich.append(eid)

    def pictures(eid: str) -> list[dict[str, Any]]:
        try:
            return enrich(good[eid])  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001 - an event without pictures is still an event
            log.warning("pictures for %s failed: %s", eid, exc)
            return list(good[eid].get("images") or [])

    if to_enrich:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for eid, images in zip(to_enrich, pool.map(pictures, to_enrich), strict=True):
                source_hash, _, checked_at = plan[eid]
                plan[eid] = (source_hash, images, checked_at)
        summary.pictures_checked = len(to_enrich)

    with storage.atomic():
        for eid, event in good.items():
            source_hash, images, checked_at = plan[eid]
            record = honesty.clean({**event, "images": images or []})
            row = to_row(record, source_hash=source_hash, images_checked_at=checked_at, now=now)
            outcome = storage.upsert_event(row)
            setattr(summary, outcome, getattr(summary, outcome) + 1)
            summary.stored += 1
        summary.pruned = storage.prune_events(cutoff)
    return summary


def store_status(
    storage: Storage,
    status: dict[str, Any],
    summary: IngestSummary,
    *,
    now: datetime,
    rubin_stream: dict[str, Any] | None,
) -> None:
    run = {
        "ingested_at": iso(now),
        "window": status.get("window"),
        "events_before_dedup": status.get("events_before_dedup"),
        "events_in_window": status.get("events_in_window"),
        **{k: v for k, v in asdict(summary).items() if k != "rejected"},
        "rejected": len(summary.rejected),
    }
    with storage.atomic():
        storage.put_status("run", run, now)
        for name, st in (status.get("sources") or {}).items():
            storage.put_status(f"source:{name}", honesty.clean(st), now)
        if rubin_stream is not None:
            storage.put_status("rubin_stream", rubin_stream, now)


def rubin_stream_status() -> dict[str, Any] | None:
    try:
        from skysources import stream_status

        return stream_status()
    except Exception as exc:  # noqa: BLE001 - /status still works without it
        log.warning("Rubin stream status failed: %s", exc)
        return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m api.ingest", description=__doc__.splitlines()[0])
    p.add_argument("--since", default="7d", help="'7d', '12h' or an ISO time (default 7d)")
    p.add_argument("--until", default="now")
    p.add_argument("--sources", default=None, help="comma list (default: every skyevents source)")
    p.add_argument("--from-file", type=Path, help="read events.json instead of fetching")
    p.add_argument("--status-file", type=Path, help="with --from-file: its status.json")
    p.add_argument("--no-pictures", action="store_true", help="skip skypictures")
    p.add_argument("--no-check", action="store_true", help="don't fetch picture URLs to check them")
    p.add_argument("--keep-days", type=float, default=90, help="delete older events (default 90)")
    p.add_argument("--pictures-ttl-h", type=float, default=24)
    p.add_argument("--workers", type=int, default=6, help="parallel picture lookups")
    p.add_argument("--db", help="SQLite path (default: PH_DATABASE_URL, else PH_DB_PATH)")
    p.add_argument("--database-url", help="Postgres URL (default: PH_DATABASE_URL)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if a.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    from api.wiring import storage_from_cli

    started = time.monotonic()
    now = utcnow()
    if a.from_file:
        doc = json.loads(a.from_file.read_text())
        events = doc["events"] if isinstance(doc, dict) else doc
        status = json.loads(a.status_file.read_text()) if a.status_file else {}
        stream = status.get("rubin_stream")
    else:
        from skyevents.ingest import ingest
        from skyevents.util import parse_age

        until = now if a.until == "now" else parse_age(a.until, now)
        since = parse_age(a.since, until)
        if since >= until:
            p.error("--since must be before --until")
        sources = [s.strip() for s in a.sources.split(",")] if a.sources else None
        events, status = ingest(since, until, sources, now=now)
        stream = rubin_stream_status()

    enrich = None if a.no_pictures else pictures_enricher(check=not a.no_check)
    storage = storage_from_cli(a.db, a.database_url)
    try:
        summary = store_events(
            storage,
            events,
            now=now,
            enrich=enrich,
            keep_days=a.keep_days,
            pictures_ttl=timedelta(hours=a.pictures_ttl_h),
            workers=a.workers,
        )
        store_status(storage, status, summary, now=now, rubin_stream=stream)
    finally:
        storage.close()

    out = {
        **asdict(summary),
        "sources": {
            n: {"state": s.get("state"), "events": s.get("events"), "error": s.get("error")}
            for n, s in (status.get("sources") or {}).items()
        },
        "seconds": round(time.monotonic() - started, 1),
    }
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
