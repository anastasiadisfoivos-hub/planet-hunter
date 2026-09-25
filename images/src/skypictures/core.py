"""pictures_for(event): the real pictures for one event, checked and in display order."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import context, cutouts, earth, sun
from .models import Event, Image
from .net import get_net

log = logging.getLogger(__name__)

# Display order: the colour context picture is the hero; then before / after / what changed.
KIND_ORDER = ["sky_context", "solar", "cutout_reference", "cutout_new", "cutout_difference", "light_curve"]

PROVIDERS: dict[str, list[Callable[[Event], list[Image]]]] = {
    "sky": [context.sky_context, cutouts.survey_cutouts],
    "sun": [sun.solar_images],
    "earth": [earth.earth_images],
}


@dataclass
class Stats:
    """Counts across calls, for the CLI's dead-link report."""
    candidates: int = 0
    kept: int = 0
    dropped: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)
    provider_errors: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def checked(self, url: str, ok: bool, reason: str) -> None:
        with self._lock:
            self.candidates += 1
            if ok:
                self.kept += 1
            else:
                self.dropped.append((url, reason))

    def error(self, msg: str) -> None:
        with self._lock:
            self.provider_errors.append(msg)


def candidates_for(event: Event, stats: Stats | None = None) -> list[Image]:
    """Every picture we would offer, before checking the URLs work."""
    frame = (event.get("location") or {}).get("frame")
    out: list[Image] = []
    for provider in PROVIDERS.get(frame, []):  # type: ignore[arg-type]
        try:
            out += provider(event)
        except Exception as exc:  # noqa: BLE001 -- one broken source must not cost the event its other pictures
            msg = f"{event.get('id')}: {provider.__module__}.{provider.__name__}: {exc!r}"
            log.warning(msg)
            if stats:
                stats.error(msg)
    return out


def validate(images: list[Image], stats: Stats | None = None) -> list[Image]:
    """Keep images whose URL returns a real, non-blank picture; fill in true width/height."""
    kept: list[Image] = []
    for img in images:
        p = get_net().probe(img["url"])
        if stats:
            stats.checked(img["url"], p.ok, p.reason)
        if not p.ok:
            log.info("dropped %s: %s", img["url"], p.reason)
            continue
        kept.append({**img, "width": p.width, "height": p.height})
    return kept


def order(images: list[Image]) -> list[Image]:
    rank = {k: i for i, k in enumerate(KIND_ORDER)}
    seen: set[str] = set()
    out = []
    for img in sorted(images, key=lambda i: rank.get(i["kind"], len(rank))):  # stable within a kind
        if img["url"] not in seen:
            seen.add(img["url"])
            out.append(img)
    return out


def pictures_for(event: Event, *, check: bool = True, stats: Stats | None = None) -> list[Image]:
    """Real pictures for this event. With check=True (default) every URL is fetched once
    (cached) and dead, non-image or blank ones are dropped."""
    images = candidates_for(event, stats)
    if check:
        images = validate(images, stats)
    return order(images)


# -- thumbnails ---------------------------------------------------------------------------------

_SDO_SIZE = re.compile(r"_(\d+)_(\d{4})\.jpg$")


def thumbnail_url(url: str) -> str:
    """A smaller rendering of the same picture from the same source (same URL if there is none)."""
    parts = urlsplit(url)
    if url.startswith(context.HIPS2FITS):
        q = dict(parse_qsl(parts.query))
        q.update(width=str(context.THUMB_PX), height=str(context.THUMB_PX))
        return urlunsplit(parts._replace(query=urlencode(q)))
    if url.startswith(sun.HELIOVIEWER + "/downloadImage"):
        q = dict(parse_qsl(parts.query))
        q.update(width=str(context.THUMB_PX), height=str(context.THUMB_PX))
        return urlunsplit(parts._replace(query=urlencode(q)))
    if url.startswith(sun.SDO_BROWSE):
        return _SDO_SIZE.sub(lambda m: f"_{sun.THUMB_PX}_{m.group(2)}.jpg", url)
    return url  # Fink cutouts are already tiny; NOAA serves one size
