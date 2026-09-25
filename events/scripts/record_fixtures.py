"""Re-record the test fixtures from the live services (network). Run from events/:

    uv run python scripts/record_fixtures.py              # everything
    uv run python scripts/record_fixtures.py distances    # only the distance lookups on top of live_week
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

from skyevents import ephemeris
from skyevents.adapters import cneos, donki, gcn, gracedb
from skyevents.ingest import ingest
from skyevents.util import as_utc, iso


def record_distances() -> None:
    """The distance/ephemeris lookups for the recorded week (the adapters' answers replay from
    live_week), plus a Horizons check of the Kepler and Earth-position code."""
    m = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/http/live_week.json").read_text())["meta"]
    with recording("distances_week", m, replay_from=("live_week",)):
        _, status = ingest(as_utc(m["since"]), as_utc(m["until"]), now=as_utc(m["now"]))
    print("distances_week:", json.dumps(status["distances"]["lookups"]))

    t0 = datetime(2026, 9, 16, tzinfo=UTC)
    w = {"pdes": "2026 R1", "t0": iso(t0), "later_days": [5, 30], "circulars": [45683]}
    with recording("distance_checks", w):
        p = ephemeris.horizons_params("DES=2026 R1;CAP;NOFRAG", t0)
        p.update(EPHEM_TYPE="ELEMENTS", TIME_TYPE="TDB")
        p.pop("VEC_TABLE")
        p.pop("VEC_CORR")
        ephemeris.client().get_json(ephemeris.HORIZONS, params=p)
        for d in w["later_days"]:
            ephemeris.horizons_xyz("DES=2026 R1;CAP;NOFRAG", t0 + timedelta(days=d))
        ephemeris.horizons_xyz("399", t0)
        for cid in w["circulars"]:  # a redshift only in the body (the subject has no value)
            gcn.circular(cid)
    print("distance_checks recorded")


def main() -> None:
    if sys.argv[1:] == ["distances"]:
        record_distances()
        return
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
    record_distances()


if __name__ == "__main__":
    main()
