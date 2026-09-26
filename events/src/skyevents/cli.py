"""events-ingest: fetch every source, de-duplicate, write events.json and status.json.

    uv run events-ingest --since 7d --out events.json
    uv run events-ingest --since 2026-09-01 --until 2026-09-08 --sources tns,ztf --out out/ev.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from .adapters import ADAPTERS
from .ingest import ingest
from .util import iso, parse_age


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="events-ingest", description=__doc__.splitlines()[0])
    p.add_argument("--since", default="7d", help="'7d', '12h', or an ISO date/time (default 7d)")
    p.add_argument("--until", default="now", help="'now' (default) or an ISO date/time")
    p.add_argument("--out", default="events.json", help="events file (default events.json)")
    p.add_argument("--status", default=None, help="status file (default: status.json next to --out)")
    p.add_argument("--sources", default=None, help=f"comma list, default all: {','.join(ADAPTERS)}")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    now = datetime.now(UTC)
    until = now if a.until == "now" else parse_age(a.until, now)
    since = parse_age(a.since, until)
    if since >= until:
        p.error("--since must be before --until")
    sources = [s.strip() for s in a.sources.split(",")] if a.sources else None

    events, status = ingest(since, until, sources, now=now)

    out = Path(a.out)
    status_path = Path(a.status) if a.status else out.with_name("status.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {"generated_at": iso(now), "since": iso(since), "until": iso(until), "count": len(events), "events": events}
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    status_path.write_text(json.dumps(status, indent=1))

    for name, st in status["sources"].items():
        flag = st["state"].upper()
        err = f"  ERROR {st['error']}" if st["error"] else ""
        print(
            f"{name:8s} {flag:8s} last={st['last_event_at'] or '-':25s} "
            f"in-window={st['events']} fetched={st['events_fetched']}{err}",
            file=sys.stderr,
        )
    print(f"{len(events)} events ({status['events_before_dedup']} before de-dup) -> {out}, {status_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
