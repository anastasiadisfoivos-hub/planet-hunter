"""Re-record the test fixtures from the live services (network). Run from events/:

    uv run python scripts/record_fixtures.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

os.environ["SKYSOURCES_CACHE"] = tempfile.mkdtemp(prefix="skyevents-record-")

from recording import recording

from skyevents.adapters import cneos, donki, gracedb
from skyevents.ingest import ingest
from skyevents.util import iso


def main() -> None:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    since = now - timedelta(days=7)
    times = {"now": iso(now), "since": iso(since), "until": iso(now)}

    with recording("live_week", times):
        events, status = ingest(since, now, now=now)
    print(f"live_week: {len(events)} events", json.dumps({k: v["state"] for k, v in status["sources"].items()}))

    # Windows with events the live week may not have.
    w = {"since": "2025-11-17T00:00:00Z", "until": "2025-11-18T00:00:00Z"}
    with recording("gracedb_S251117dq", w):
        print("gracedb:", len(gracedb.fetch(datetime.fromisoformat(w["since"]), datetime.fromisoformat(w["until"]))))
    w = {"since": "2026-08-08T00:00:00Z", "until": "2026-08-10T00:00:00Z"}
    with recording("donki_storm_2026-08", w):
        print("donki:", len(donki.fetch(datetime.fromisoformat(w["since"]), datetime.fromisoformat(w["until"]))))
    w = {"since": "2026-09-01T00:00:00Z", "until": "2026-09-25T00:00:00Z"}
    with recording("cneos_2026-09", w):
        print("cneos:", len(cneos.fetch(datetime.fromisoformat(w["since"]), datetime.fromisoformat(w["until"]))))


if __name__ == "__main__":
    main()
