"""Is Rubin's data flowing? stream_status() and latest_observed_window().

- last_alert_at: newest LSST detection in ALeRCE's object list (exact time). If ALeRCE is down,
  the start of the newest night with alerts in Fink's statistics (date precision only).
- last_scheduled_visit_at: newest exposure start (t_min) in Rubin's ObsLocTAP table, any status.
- Nights: Fink /api/v1/statistics per-night alert counts. Fink's "night" is the UTC date of the
  alerts (its newest night 20260714 holds the 2026-07-14 10:03 UTC alert), so a night here is
  [date 00:00 UTC, date+1 00:00 UTC).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, date, datetime, timedelta

from astropy.time import Time

from . import fink
from .http import UpstreamError, cache_dir, get_client

log = logging.getLogger(__name__)

ALERCE_OBJECTS = "https://api-lsst.alerce.online/object_api/list_objects"
OBSLOCTAP_URL = "https://usdf-rsp.slac.stanford.edu/obsloctap/schedule"
LIVE_WITHIN = timedelta(hours=72)
STATUS_TTL_S = 3600.0


def stream_status(*, max_age_s: float = STATUS_TTL_S) -> dict:
    """{last_alert_at, last_scheduled_visit_at, is_live, checked_at}. Cached on disk ~1 h, and
    checked_at is when the upstream services were actually asked."""
    path = cache_dir() / "stream_status.json"
    try:
        cached = json.loads(path.read_text())
        age = time.time() - datetime.fromisoformat(cached["checked_at"]).timestamp()
        if 0 <= age < max_age_s:
            return cached
    except (OSError, ValueError, KeyError):
        pass

    now = datetime.now(UTC)
    last_alert = _safe(last_alert_at)
    last_visit = _safe(last_scheduled_visit_at)
    status = {
        "last_alert_at": _iso(last_alert),
        "last_scheduled_visit_at": _iso(last_visit),
        "is_live": bool(last_alert and now - last_alert <= LIVE_WITHIN),
        "checked_at": _iso(now),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status))
    return status


def last_alert_at() -> datetime:
    try:
        data = get_client().get_json(
            ALERCE_OBJECTS,
            params={"survey": "lsst", "page_size": 1, "order_by": "lastmjd", "order_mode": "DESC"},
            ttl=0,
        )
        return _from_mjd_tai(data["items"][0]["lastmjd"])
    except (UpstreamError, KeyError, IndexError) as exc:
        log.warning("ALeRCE latest-object lookup failed (%s); using Fink night statistics", exc)
        nights = observed_nights(ttl=0)
        if not nights:
            raise UpstreamError("no broker reports any LSST alerts") from exc
        return datetime.combine(nights[-1], datetime.min.time(), UTC)


def last_scheduled_visit_at() -> datetime:
    """Newest exposure start in ObsLocTAP (planned, performed or aborted)."""
    rows = get_client().get_json(
        OBSLOCTAP_URL,
        params={"time": 0, "RESPONSEFORMAT": "json", "columns": "t_min"},
        ttl=0,
    )
    if not rows:
        raise UpstreamError("ObsLocTAP returned no rows")
    return _from_mjd_utc(max(r["t_min"] for r in rows))


def observed_nights(ttl: float = STATUS_TTL_S) -> list[date]:
    """UTC dates with at least one LSST alert at Fink, oldest first."""
    rows = fink.statistics("", ttl=ttl)
    nights = {
        date.fromisoformat(r["f:night"])  # YYYYMMDD
        for r in rows
        if int(r.get("f:alerts") or 0) > 0
    }
    return sorted(nights)


def latest_observed_window(nights: int = 7) -> tuple[datetime, datetime]:
    """(start, end) covering the most recent `nights` nights that actually have alerts.

    Nights without alerts in between are inside the window but don't count toward `nights`.
    """
    if nights < 1:
        raise ValueError("nights must be >= 1")
    have = observed_nights()
    if not have:
        raise UpstreamError("Fink reports no nights with LSST alerts")
    chosen = have[-nights:]
    start = datetime.combine(chosen[0], datetime.min.time(), UTC)
    end = datetime.combine(chosen[-1] + timedelta(days=1), datetime.min.time(), UTC)
    return start, end


def _safe(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a banner must render even if one service is down
        log.warning("%s failed: %s", fn.__name__, exc)
        return None


def _from_mjd_tai(mjd: float) -> datetime:
    return Time(mjd, format="mjd", scale="tai").utc.to_datetime(UTC)


def _from_mjd_utc(mjd: float) -> datetime:
    return Time(mjd, format="mjd", scale="utc").to_datetime(UTC)


def _iso(t: datetime | None) -> str | None:
    return t.isoformat(timespec="seconds") if t else None
