"""The real queries behind the recorded fixtures. Shared by scripts/record_fixtures.py (live) and
the tests (replay), so both always run exactly the same calls."""

from __future__ import annotations

ECLIPTIC = {"ra_deg": 317.18, "dec_deg": -21.1, "radius_deg": 0.3}
ECLIPTIC_WINDOW = ("2026-07-10T00:00:00Z", "2026-07-11T12:00:00Z")
ECLIPTIC_CUTOUT_LOOKUPS = 3

DEEP_FIELD = {"ra_deg": 62.8786, "dec_deg": -48.4491, "radius_deg": 0.2}  # EDFS deep drilling field
DEEP_FIELD_WINDOW = ("2026-07-12T00:00:00Z", "2026-07-15T00:00:00Z")
LIGHT_CURVE_OBJECT = "313774269509664977"

SCHEDULE_SPHERE = {"ra_deg": 193.0, "dec_deg": 14.0, "radius_deg": 1.0}
SCHEDULE_PAST = ("2026-07-10T00:00:00Z", "2026-07-12T00:00:00Z")
SCHEDULE_FUTURE = ("2026-09-25T00:00:00Z", "2026-09-27T00:00:00Z")

SKYBOT_SPHERE = {"ra_deg": 10.0, "dec_deg": 5.0, "radius_deg": 0.5}
SKYBOT_TIME = "2026-09-25T04:00:00Z"

HEATMAP_NIGHTS = 1
HEATMAP_UNTIL = "2026-07-15T00:00:00Z"
HEATMAP_PAGE_SIZE = 50  # small real sample: first page(s) only
HEATMAP_MAX_PAGES = 1

WINDOW_NIGHTS = (1, 3, 7)
