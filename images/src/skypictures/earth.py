"""Earth-frame events. No photographs exist for these, so none are made up.

- geomagnetic_storm: NOAA SWPC's OVATION aurora forecast map nearest the event time. SWPC keeps
  these time-stamped frames for only ~24 h, then deletes them, so the CLI re-hosts them
  (see EPHEMERAL_PREFIXES). An older storm gets no image: `latest.jpg` would show a different time.
- fireball: CNEOS reports carry no imagery; returns [].
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from . import credits
from .models import Event, Image
from .net import FetchError, get_net
from .sun import parse_time

log = logging.getLogger(__name__)

OVATION = "https://services.swpc.noaa.gov/images/animations/ovation"
MAX_GAP = timedelta(minutes=30)
# URLs under these prefixes disappear after about a day; the CLI copies them to a local folder.
EPHEMERAL_PREFIXES = (OVATION + "/",)

FILE_RE = re.compile(r'href="(aurora_([NS])_(\d{4}-\d{2}-\d{2})_(\d{4})\.jpg)"')


def _hemispheres(event: Event) -> list[str]:
    lat = event["location"].get("lat_deg")  # type: ignore[union-attr]
    if isinstance(lat, (int, float)):
        return ["south"] if lat < 0 else ["north"]
    return ["north", "south"]


def ovation_nearest(t: datetime, hemisphere: str) -> tuple[datetime, str] | None:
    try:
        html = get_net().text(f"{OVATION}/{hemisphere}/", ttl=300.0)
    except FetchError as exc:
        log.info("SWPC OVATION listing: %s", exc)
        return None
    best: tuple[timedelta, datetime, str] | None = None
    for name, _h, day, hhmm in FILE_RE.findall(html):
        it = datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H%M").replace(tzinfo=UTC)
        gap = abs(it - t)
        if best is None or gap < best[0]:
            best = (gap, it, name)
    if best is None or best[0] > MAX_GAP:
        return None
    return best[1], f"{OVATION}/{hemisphere}/{best[2]}"


def earth_images(event: Event) -> list[Image]:
    if event.get("type") != "geomagnetic_storm":
        return []  # fireballs and anything else on Earth: no real imagery to show
    try:
        t = parse_time(event["observed_at"])
    except (KeyError, ValueError):
        return []
    out: list[Image] = []
    for hemi in _hemispheres(event):
        hit = ovation_nearest(t, hemi)
        if not hit:
            continue
        it, url = hit
        caption = (f"NOAA OVATION aurora forecast for the {hemi}ern hemisphere, model run {it:%Y-%m-%d %H:%M} UTC "
                   "(the time it forecasts, printed on the map, is 30-90 min later): where aurora is likely, "
                   "green to red = 10% to 90% chance. A model map, not a photograph.")
        c = credits.NOAA_OVATION
        out.append(Image(url=url, kind="sky_context", caption=caption, credit=c.credit, license=c.license,
                         width=None, height=None))
    return out
