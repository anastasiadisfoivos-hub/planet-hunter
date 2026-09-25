"""query(filters) -> list[Event]: filter, sort newest first, page."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from .models import CATEGORIES, CATEGORY_OF, EVENT_TYPES, Event
from .util import as_utc, sep_deg

FRAMES = ("sky", "sun", "earth")
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


class Region(TypedDict):
    ra_deg: float
    dec_deg: float
    radius_deg: float


class Filters(TypedDict, total=False):
    types: list[str]  # any of EVENT_TYPES
    categories: list[str]  # any of CATEGORIES
    since: datetime | str  # observed_at >= since
    until: datetime | str  # observed_at <= until
    sources: list[str]  # event.source, or any member source of a merged event
    frame: str  # sky | sun | earth
    region: Region  # sky events within radius; implies frame "sky"
    min_confidence: float
    offset: int
    limit: int


def load(path: str | Path | None = None) -> list[Event]:
    """events.json as written by events-ingest (an object with "events", or a bare list)."""
    p = Path(path or os.environ.get("SKYEVENTS_FILE", "events.json"))
    doc = json.loads(p.read_text())
    return doc["events"] if isinstance(doc, dict) else doc


def query(filters: Filters | None = None, events: list[Event] | None = None) -> list[Event]:
    f = validate(filters or {})
    evs = load() if events is None else events
    out = [e for e in evs if matches(e, f)]
    out.sort(key=lambda e: (e["observed_at"], e["id"]), reverse=True)
    off = f.get("offset", 0)
    return out[off : off + f.get("limit", DEFAULT_LIMIT)]


def validate(f: Filters) -> dict[str, Any]:
    f = dict(f)
    if bad := set(f.get("types") or []) - set(EVENT_TYPES):
        raise ValueError(f"unknown types: {sorted(bad)}")
    if bad := set(f.get("categories") or []) - set(CATEGORIES):
        raise ValueError(f"unknown categories: {sorted(bad)} (known: {sorted(CATEGORIES)})")
    if f.get("frame") and f["frame"] not in FRAMES:
        raise ValueError(f"frame must be one of {FRAMES}")
    if r := f.get("region"):
        if not (0 <= float(r["ra_deg"]) < 360 and -90 <= float(r["dec_deg"]) <= 90 and 0 < float(r["radius_deg"]) <= 180):
            raise ValueError(f"bad region: {r}")
        if f.get("frame", "sky") != "sky":
            raise ValueError("a sky region only applies to frame 'sky'")
    for k in ("since", "until"):
        if f.get(k) is not None:
            f[k] = as_utc(f[k])
    if not 0.0 <= float(f.get("min_confidence", 0.0)) <= 1.0:
        raise ValueError("min_confidence must be in [0, 1]")
    f["offset"] = max(0, int(f.get("offset", 0)))
    f["limit"] = max(1, min(MAX_LIMIT, int(f.get("limit", DEFAULT_LIMIT))))
    return f


def matches(e: Event, f: dict[str, Any]) -> bool:
    if f.get("types") and e["type"] not in f["types"]:
        return False
    if f.get("categories") and CATEGORY_OF.get(e["type"]) not in f["categories"]:
        return False
    t = as_utc(e["observed_at"])
    if f.get("since") and t < f["since"]:
        return False
    if f.get("until") and t > f["until"]:
        return False
    if f.get("sources"):
        members = {e["source"], *(s["source"] for s in e.get("raw", {}).get("sources", []))}
        if not members & set(f["sources"]):
            return False
    loc = e["location"]
    if f.get("frame") and loc["frame"] != f["frame"]:
        return False
    if r := f.get("region"):
        if loc["frame"] != "sky":
            return False
        if sep_deg(r["ra_deg"], r["dec_deg"], loc["ra_deg"], loc["dec_deg"]) > r["radius_deg"]:
            return False
    return e["confidence"] >= float(f.get("min_confidence", 0.0))
