"""skypictures CLI: add real pictures to every event in an events.json.

    skypictures events.json -o events.with-pictures.json

Accepts a JSON list of events or an object with an "events" list (kept as is otherwise).
Every image links to its source (url + thumb_url); nothing is downloaded or re-hosted.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .core import Stats, order, pictures_for, validate
from .models import Event

log = logging.getLogger("skypictures")


def load_events(doc) -> list[Event]:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and isinstance(doc.get("events"), list):
        return doc["events"]
    raise SystemExit("input must be a JSON list of events or an object with an 'events' list")


def enrich_event(event: Event, *, check: bool, replace: bool, stats: Stats) -> Event:
    new = pictures_for(event, check=check, stats=stats)
    existing = [] if replace else list(event.get("images") or [])
    if existing and check:
        existing = validate(existing, stats)
    return {**event, "images": order(new + existing)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skypictures", description=__doc__.split("\n\n")[0])
    ap.add_argument("events", type=Path, help="input events.json")
    ap.add_argument("-o", "--out", type=Path, help="output file (default: overwrite input)")
    ap.add_argument("--no-check", action="store_true", help="do not fetch URLs to drop dead ones")
    ap.add_argument("--replace", action="store_true", help="drop images the events already had")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    out = args.out or args.events
    doc = json.loads(args.events.read_text())
    events = load_events(doc)
    stats = Stats()
    check = not args.no_check

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        enriched = list(pool.map(lambda e: enrich_event(e, check=check, replace=args.replace, stats=stats),
                                 events))

    if isinstance(doc, dict):
        doc = {**doc, "events": enriched}
    else:
        doc = enriched
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")

    kinds = Counter(img["kind"] for ev in enriched for img in ev["images"])
    with_pics = sum(1 for ev in enriched if ev["images"])
    print(f"{len(enriched)} events, {with_pics} with pictures; images by kind: {dict(kinds)}", file=sys.stderr)
    if check:
        rate = len(stats.dropped) / stats.candidates if stats.candidates else 0.0
        print(f"checked {stats.candidates} URLs, dropped {len(stats.dropped)} dead/blank ({rate:.1%})",
              file=sys.stderr)
        for url, reason in stats.dropped:
            print(f"  dropped {reason}: {url}", file=sys.stderr)
    for msg in stats.provider_errors:
        print(f"  source error {msg}", file=sys.stderr)
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
