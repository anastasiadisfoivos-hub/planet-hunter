"""Earth-frame events. No photographs exist for these, so none are made up.

- geomagnetic_storm: if the storm is ongoing or began within the last 24 h, NOAA SWPC's stable
  "latest" OVATION aurora forecast image for the matching hemisphere (the URL NOAA's product page
  uses; the picture behind it refreshes every few minutes). Older storms get nothing: the latest
  map would show a different time, and SWPC's time-stamped frames are deleted after ~24 h.
- fireball: CNEOS reports carry no imagery; returns [].
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from . import credits
from .models import Event, Image
from .sun import parse_time

LATEST = {
    "north": "https://services.swpc.noaa.gov/images/aurora-forecast-northern-hemisphere.jpg",
    "south": "https://services.swpc.noaa.gov/images/aurora-forecast-southern-hemisphere.jpg",
}
RECENT = timedelta(hours=24)


def _now() -> datetime:  # patched in tests
    return datetime.now(UTC)


def _hemispheres(event: Event) -> list[str]:
    lat = event["location"].get("lat_deg")  # type: ignore[union-attr]
    if isinstance(lat, (int, float)):
        return ["south"] if lat < 0 else ["north"]
    return ["north", "south"]


def is_current(event: Event, now: datetime | None = None) -> bool:
    """Ongoing or started within the last 24 h (a future start counts as ongoing)."""
    try:
        t = parse_time(event["observed_at"])
    except (KeyError, ValueError):
        return False
    return (now or _now()) - t <= RECENT


def earth_images(event: Event) -> list[Image]:
    if event.get("type") != "geomagnetic_storm" or not is_current(event):
        return []  # fireballs, anything else on Earth, and storms too old for "latest" to fit
    c = credits.NOAA_OVATION
    out: list[Image] = []
    for hemi in _hemispheres(event):
        caption = (f"NOAA aurora forecast, latest (model): {hemi}ern hemisphere. A model map of where "
                   "aurora is likely now (green to red = 10% to 90% chance), refreshed every few minutes; "
                   "not a photograph.")
        out.append(Image(url=LATEST[hemi], thumb_url=LATEST[hemi], kind="forecast_map", caption=caption,
                         credit=c.credit, license=c.license, width=None, height=None))
    return out
