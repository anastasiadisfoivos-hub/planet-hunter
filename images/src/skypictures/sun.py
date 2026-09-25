"""Sun-frame events: the real full-disk image nearest in time, in a wavelength that shows the event.

1. NASA SDO's own browse archive: static JPEGs every ~15 min at 512/1024/2048/4096 px,
   https://sdo.gsfc.nasa.gov/assets/img/browse/YYYY/MM/DD/YYYYMMDD_HHMMSS_<px>_<wl>.jpg
2. Fallback, and for SOHO/LASCO: Helioviewer.org's public API (getClosestImage + downloadImage).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from . import credits
from .models import Event, Image
from .net import FetchError, get_net

log = logging.getLogger(__name__)

SDO_BROWSE = "https://sdo.gsfc.nasa.gov/assets/img/browse"
HELIOVIEWER = "https://api.helioviewer.org/v2"
FULL_PX = 1024
THUMB_PX = 512
SDO_MAX_GAP = timedelta(hours=2)
HV_MAX_GAP = timedelta(hours=6)
LASCO_DELAY = timedelta(minutes=30)  # a CME needs ~30 min to climb into LASCO C2's field of view
LASCO_WINDOW = timedelta(hours=3)    # after that it has usually left C2 (out to ~6 solar radii)

# Helioviewer source IDs (from /v2/getDataSources/).
HV_SOURCE = {"94": 8, "131": 9, "171": 10, "193": 11, "211": 12, "304": 13, "335": 14, "1600": 15, "1700": 16,
             "LASCO C2": 4, "LASCO C3": 5}

WHY = {
    "131": "131 Å shows plasma near 10 million °C, where flares glow brightest",
    "193": "193 Å shows the 1.5-million-°C corona, where an erupting CME leaves a dark dimming",
    "304": "304 Å shows the chromosphere and prominences near 50,000 °C",
    "171": "171 Å shows coronal loops near 600,000 °C",
}
# Which SDO/AIA wavelength matches each event type.
WAVELENGTH = {"solar_flare": "131", "coronal_mass_ejection": "193"}

FILE_RE = re.compile(r'href="(\d{8})_(\d{6})_(\d+)_(\d{4})\.jpg"')
LOCATION_RE = re.compile(r"\b([NS])(\d{1,2})([EW])(\d{1,3})\b")


def parse_time(s: str) -> datetime:
    s = s.strip().replace("Z", "+00:00").replace(" ", "T")
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _fmt(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _gap(image_t: datetime, event_t: datetime, label: str) -> str:
    mins = round((image_t - event_t).total_seconds() / 60)
    if mins == 0:
        return f"at {label} ({event_t:%H:%M} UTC)"
    return f"{abs(mins)} min {'after' if mins > 0 else 'before'} {label} ({event_t:%H:%M} UTC)"


def sdo_nearest(t: datetime, wavelength: str) -> tuple[datetime, str] | None:
    """(time, file stem without size) of the nearest SDO browse JPEG, if within SDO_MAX_GAP."""
    days = {t.date()} | {(t + d).date() for d in (-SDO_MAX_GAP, SDO_MAX_GAP)}
    best: tuple[timedelta, datetime, str] | None = None
    for day in sorted(days):
        url = f"{SDO_BROWSE}/{day:%Y/%m/%d}/"
        try:
            html = get_net().text(url, ttl=1800.0)
        except FetchError as exc:
            log.info("SDO listing %s: %s", url, exc)
            continue
        for d, hms, px, wl in FILE_RE.findall(html):
            if px != str(FULL_PX) or wl != wavelength.zfill(4):
                continue
            it = datetime.strptime(d + hms, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            gap = abs(it - t)
            if best is None or gap < best[0]:
                best = (gap, it, f"{d}_{hms}")
    if best is None or best[0] > SDO_MAX_GAP:
        return None
    return best[1], best[2]


def sdo_url(stem: str, wavelength: str, px: int = FULL_PX) -> str:
    return f"{SDO_BROWSE}/{stem[:4]}/{stem[4:6]}/{stem[6:8]}/{stem}_{px}_{wavelength.zfill(4)}.jpg"


def helioviewer_nearest(t: datetime, source: str) -> tuple[datetime, str] | None:
    """(time, image id) of Helioviewer's closest image from `source`, if within HV_MAX_GAP."""
    q = {"date": t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "sourceId": HV_SOURCE[source]}
    try:
        d = get_net().json(f"{HELIOVIEWER}/getClosestImage/", q, ttl=86400.0)
    except (FetchError, ValueError) as exc:
        log.info("Helioviewer %s: %s", source, exc)
        return None
    if not isinstance(d, dict) or "id" not in d or "date" not in d:
        return None
    it = parse_time(d["date"])
    return (it, str(d["id"])) if abs(it - t) <= HV_MAX_GAP else None


def helioviewer_url(image_id: str, px: int = FULL_PX) -> str:
    return f"{HELIOVIEWER}/downloadImage/?" + urlencode({"id": image_id, "width": px, "height": px, "type": "jpg"})


def flare_region(event: Event) -> tuple[str | None, str | None]:
    """(heliographic location like 'N14E90', NOAA active-region number) if the source gave them."""
    raw = event.get("raw") or {}
    loc = raw.get("sourceLocation") or raw.get("source_location")
    if not (isinstance(loc, str) and LOCATION_RE.fullmatch(loc.strip())):
        m = LOCATION_RE.search(json.dumps(raw) + " " + event.get("summary", ""))
        loc = m.group(0) if m else None
    ar = raw.get("activeRegionNum") or raw.get("active_region")
    return (loc.strip() if loc else None), (str(ar) if ar else None)


def describe_location(loc: str) -> str:
    """'N14E90' -> 'on the left (east) edge of the disk, 14° north of the equator'."""
    m = LOCATION_RE.fullmatch(loc)
    if not m:
        return ""
    ns, lat, ew, lon = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
    side = "left (east)" if ew == "E" else "right (west)"
    if lon >= 75:
        where = f"on the {side} edge of the disk"
    elif lon >= 45:
        where = f"near the {side} edge of the disk"
    elif lon <= 10:
        where = "near the centre of the disk"
    else:
        where = f"{'left' if ew == 'E' else 'right'} of centre"
    if lat <= 5:
        return f"{where}, near the solar equator"
    return f"{where}, {lat}° {'north' if ns == 'N' else 'south'} of the equator"


def _event_time(event: Event) -> tuple[datetime, str] | None:
    """(time to match, how to name it in a caption)."""
    raw = event.get("raw") or {}
    for key in ("peakTime", "peak_time"):  # a flare is best seen at its peak
        if event.get("type") == "solar_flare" and isinstance(raw.get(key), str):
            try:
                return parse_time(raw[key]), "the flare peak"
            except ValueError:
                pass
    try:
        return parse_time(event["observed_at"]), "the reported time"
    except (KeyError, ValueError):
        return None


def solar_images(event: Event) -> list[Image]:
    when = _event_time(event)
    if when is None:
        return []
    t, label = when
    etype = event.get("type", "")
    wl = WAVELENGTH.get(etype, "171")
    loc, ar = flare_region(event)
    region = ""
    if loc:
        region = f" The source reports the {'flare' if etype == 'solar_flare' else 'eruption'} at {loc}"
        region += f" (NOAA active region {ar})" if ar else ""
        region += f": {describe_location(loc)}."
    what = {"solar_flare": "flare", "coronal_mass_ejection": "coronal mass ejection"}.get(etype, "event")

    out: list[Image] = []
    hit = sdo_nearest(t, wl)
    if hit:
        it, stem = hit
        url, c = sdo_url(stem, wl), credits.SDO
    else:
        hv = helioviewer_nearest(t, wl)
        it, url, c = (hv[0], helioviewer_url(hv[1]), credits.SDO_HELIOVIEWER) if hv else (None, "", None)
    if it is not None and c is not None:
        caption = (f"NASA SDO/AIA {wl} Å image of the whole Sun, {_fmt(it)}, {_gap(it, t, label)} "
                   f"of this {what}. {WHY.get(wl, '')}.{region}")
        out.append(Image(url=url, kind="solar", caption=caption.strip(), credit=c.credit, license=c.license,
                         width=FULL_PX, height=FULL_PX))

    if etype == "coronal_mass_ejection":
        for instrument, reach in (("LASCO C2", "about 6"), ("LASCO C3", "about 30")):
            lasco = helioviewer_nearest(t + LASCO_DELAY, instrument)
            if not lasco or not (t <= lasco[0] <= t + LASCO_WINDOW):
                continue  # a frame from before the CME, or long after, cannot show it
            it, image_id = lasco
            caption = (f"SOHO {instrument} coronagraph image, {_fmt(it)}, {_gap(it, t, label)} of this CME: the "
                       f"outer corona out to {reach} solar radii. The dark disk is the occulter blocking the "
                       "bright Sun; a CME seen by LASCO shows as a bright cloud moving outward.")
            out.append(Image(url=helioviewer_url(image_id), kind="solar", caption=caption,
                             credit=credits.LASCO.credit, license=credits.LASCO.license,
                             width=FULL_PX, height=FULL_PX))
            break
    return out
