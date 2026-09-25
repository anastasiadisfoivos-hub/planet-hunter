"""Analyze a star (deploy/HOSTING.md R1-R5): one stored result per star, served until the star's
TESS data marker changes, and the marker itself asked for at most every PH_MARKER_TTL_S.

Shared by the API (routes/analyze.py + jobs.py) and `python -m api.precompute`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api import honesty
from api.known_systems import BY_KEY, name_key
from api.models import Analysis, Sector, Signal, StarInfo, StoredAnalysis
from api.ports import StarAnalyzer, Storage

log = logging.getLogger(__name__)

NOTE_UNAVAILABLE = "data check unavailable: showing stored result"
_TIC_RE = re.compile(r"^\s*TIC\s*(\d{1,10})\s*$", re.IGNORECASE)


@dataclass
class Freshness:
    stored: StoredAnalysis | None
    current: bool  # the stored result is good for the star's current data: serve it
    marker: str | None = None  # the star's current marker, when known
    no_data: bool = False  # MAST says the star has no usable TESS light curve
    note: str | None = None


def check(
    storage: Storage, analyzer: StarAnalyzer, tic_id: int, now: datetime, ttl_s: float
) -> Freshness:
    """Is the stored result current? Asks MAST only when the last check is older than ttl_s."""
    rec = storage.get_star_analysis(tic_id)
    if rec is not None and (now - rec.marker_checked_at).total_seconds() < ttl_s:
        return Freshness(rec, True, rec.data_marker)
    try:
        marker = analyzer.latest_data_marker(tic_id)
    except Exception as exc:  # noqa: BLE001 - MAST down: a stale result beats an error
        log.warning("data marker for TIC %s unavailable: %s", tic_id, exc)
        if rec is not None:
            return Freshness(rec, True, rec.data_marker, note=NOTE_UNAVAILABLE)
        return Freshness(None, False)
    if rec is not None and (marker is None or marker == rec.data_marker):
        # Same data (or the listing lost the star, which is no reason to drop a real result).
        storage.touch_star_analysis(tic_id, now)
        return Freshness(rec.model_copy(update={"marker_checked_at": now}), True, rec.data_marker)
    if marker is None:
        return Freshness(None, False, no_data=True)
    return Freshness(rec, False, marker)


def store(
    storage: Storage, tic_id: int, marker: str | None, analysis: Analysis, now: datetime
) -> StoredAnalysis:
    clean = Analysis.model_validate(honesty.clean(analysis.model_dump(mode="json")))
    rec = StoredAnalysis(
        tic_id=tic_id, data_marker=marker, analyzed_at=now, marker_checked_at=now, analysis=clean
    )
    storage.put_star_analysis(rec)
    return rec


def reusable(storage: Storage, tic_id: int, marker: str | None) -> StoredAnalysis | None:
    """A result someone else stored for exactly this data while we waited, if any."""
    if marker is None:
        return None
    rec = storage.get_star_analysis(tic_id)
    return rec if rec is not None and rec.data_marker == marker else None


def marker_or_none(analyzer: StarAnalyzer, tic_id: int) -> str | None:
    try:
        return analyzer.latest_data_marker(tic_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("data marker for TIC %s unavailable: %s", tic_id, exc)
        return None


def run(
    storage: Storage,
    analyzer: StarAnalyzer,
    tic_id: int,
    marker: str | None,
    progress: Callable[[str], None],
    now: Callable[[], datetime],
) -> StoredAnalysis:
    """Analyze and store (blocking). `marker` is the one checked before; None if unknown."""
    analysis = analyzer.analyze(tic_id, progress)
    if marker is None:  # the search just listed the star's data, so this is usually cached now
        marker = marker_or_none(analyzer, tic_id)
    return store(storage, tic_id, marker, analysis, now())


def lookup_name(storage: Storage, name: str) -> int | None:
    """TIC for a name without asking MAST: "TIC 123", a Known system, or a name seen before."""
    if m := _TIC_RE.match(name):
        return int(m.group(1))
    key = name_key(name)
    return BY_KEY.get(key) or storage.get_star_name(key)


def remember_name(storage: Storage, name: str, tic_id: int, now: datetime) -> None:
    storage.put_star_name(name_key(name), tic_id, now)


# plain-English summary ----------------------------------------------------------------


def _sectors(sectors: list[Sector]) -> str:
    nums = sorted({s.sector for s in sectors})
    if not nums:
        return "TESS data"
    if len(nums) == 1:
        return f"TESS sector {nums[0]}"
    return "TESS sectors " + ", ".join(map(str, nums[:-1])) + f" and {nums[-1]}"


def _signal(s: Signal) -> str:
    kind = {"planet_candidate": "a planet candidate", "eclipsing_binary": "an eclipsing binary"}
    text = (
        f"{kind.get(s.type, s.type.replace('_', ' '))} (best guess, confidence {s.confidence:.2f}):"
        f" a {s.depth_ppm / 1e4:.3f}% dip every {s.period_days:.4f} days"
    )
    if s.known_status == "known" and s.name_if_known:
        text += f", which matches the catalogued {s.name_if_known}"
    elif s.known_status == "not_on_lists":
        text += ", not on the catalogues we checked"
    return text


def describe(star: StarInfo, sectors: list[Sector], signals: list[Signal], flares: int) -> str:
    who = star.name or f"TIC {star.tic_id}"
    out = f"We searched {_sectors(sectors)} of {who} for repeating dips and flares. "
    if not signals:
        out += "No repeating dip stood out above the noise."
    elif len(signals) == 1:
        out += f"One repeating dip stood out: {_signal(signals[0])}."
    else:
        out += f"{len(signals)} repeating dips stood out: " + "; ".join(map(_signal, signals)) + "."
    if flares:
        out += f" The star also brightened suddenly {flares} time{'s' if flares != 1 else ''}"
        out += " (possible flares)."
    return out
