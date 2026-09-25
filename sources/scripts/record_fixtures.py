"""Re-record the offline test fixtures from the live services.

    uv run python scripts/record_fixtures.py

Needs network; no logins. Overwrites tests/fixtures/. The Fink SSO bulk file (~40 MB) is cut
down to the real rows of the objects the scenarios touch.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from astropy.time import Time
from fixtures import scenarios as sc
from recording import SSO_BULK, recording

from skysources import fink, heatmap, sso
from skysources.alerts import alerts, light_curve
from skysources.schedule import schedule
from skysources.solar_system import known_solar_system


def main() -> None:
    designations: set[str] = set()

    with recording("alerts_ecliptic"):
        found = alerts(sc.ECLIPTIC, *sc.ECLIPTIC_WINDOW, max_cutout_lookups=sc.ECLIPTIC_CUTOUT_LOOKUPS)
    designations |= {d["name_if_known"] for d in found if d["id"].startswith("rubin:ss:")}
    print("alerts_ecliptic", len(found))

    with recording("alerts_deep_field"):
        found = alerts(sc.DEEP_FIELD, *sc.DEEP_FIELD_WINDOW)
        light_curve(sc.LIGHT_CURVE_OBJECT)
    print("alerts_deep_field", len(found))

    with recording("schedule"):
        print("schedule past", len(schedule(sc.SCHEDULE_SPHERE, *sc.SCHEDULE_PAST)))
        print("schedule future", len(schedule(sc.SCHEDULE_SPHERE, *sc.SCHEDULE_FUTURE)))

    with recording("skybot"):
        print("skybot", len(known_solar_system(sc.SKYBOT_SPHERE, sc.SKYBOT_TIME)))

    heatmap.PAGE_SIZE, heatmap.MAX_PAGES_PER_CLASS = sc.HEATMAP_PAGE_SIZE, sc.HEATMAP_MAX_PAGES
    with recording("heatmap"):
        heat = heatmap.build_heatmap(sc.HEATMAP_NIGHTS, until=sc.HEATMAP_UNTIL)
    print("heatmap cells", len(heat["cells"]))

    # The heatmap test reads the SSO subset too: keep a real sample of that night's objects.
    end = Time(sc.HEATMAP_UNTIL.replace("Z", ""), scale="utc")
    night = sso.sightings(float(end.tai.mjd) - 1.0, float(end.tai.mjd))
    designations |= {s.designation for s in night[:200]}

    table = pq.read_table(fink.sso_bulk())
    subset = table.filter(pc.is_in(table["designation"], value_set=pa.array(sorted(designations))))
    pq.write_table(subset, SSO_BULK, compression="zstd")
    print("sso subset rows", subset.num_rows, SSO_BULK.stat().st_size, "bytes")

if __name__ == "__main__":
    main()
