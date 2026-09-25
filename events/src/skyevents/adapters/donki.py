"""NASA DONKI (Space Weather Database Of Notifications, Knowledge, Information), CCMC Moon to
Mars Space Weather Analysis Office. Solar flares and CMEs (sun frame), geomagnetic storms (earth).

API: https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/{FLR,CME,GST} (no key; the api.nasa.gov
mirror needs one, DEMO_KEY is limited to 30 requests an hour). Entries are curated by the M2M
office, so confidence is 1.0 / official_report.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..models import Event
from ..util import as_utc, make_event, num
from ._http import FRESH, client

NAME = "donki"
LIVE_WITHIN = timedelta(days=7)
API = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get"

# A geomagnetic storm is global. The Earth-frame point is the geomagnetic north pole (IGRF
# 2025), around which the northern aurora ring is centred; raw.location_note says so.
GEOMAGNETIC_NORTH_POLE = (80.8, -72.7)
G_SCALE = [(9.0, "G5 (extreme)"), (8.0, "G4 (severe)"), (7.0, "G3 (strong)"), (6.0, "G2 (moderate)"), (5.0, "G1 (minor)")]


def fetch(since: datetime, until: datetime) -> list[Event]:
    out: list[Event] = []
    for kind, conv in (("FLR", flare_event), ("CME", cme_event), ("GST", storm_event)):
        for rec in _get(kind, since, until):
            if (e := conv(rec)) and since <= as_utc(e["observed_at"]) <= until:
                out.append(e)
    return out


def last_event_at(now: datetime) -> datetime | None:
    events = fetch(now - timedelta(days=30), now)
    return max((as_utc(e["observed_at"]) for e in events), default=None)


def _get(kind: str, since: datetime, until: datetime) -> list[dict]:
    params = {"startDate": since.date().isoformat(), "endDate": until.date().isoformat()}
    return client().get_json(f"{API}/{kind}", params=params, ttl=FRESH) or []


def _t(s: str | None) -> datetime | None:
    return as_utc(s) if s else None


def flare_event(r: dict) -> Event | None:
    peak = _t(r.get("peakTime")) or _t(r.get("beginTime"))
    if peak is None:
        return None
    cls = r.get("classType") or "unclassified"
    region = r.get("activeRegionNum")
    where = f" from active region {region}" if region else ""
    loc = f" at solar position {r['sourceLocation']}" if r.get("sourceLocation") else ""
    strength = {"X": "a major", "M": "a medium-sized", "C": "a small"}.get(cls[:1], "a")
    return make_event(
        source=NAME,
        source_id=r["flrID"],
        type="solar_flare",
        title=f"{cls} solar flare{where}",
        summary=(
            f"The Sun produced {strength} {cls}-class X-ray flare{where}{loc}, peaking at "
            f"{peak:%H:%M} UTC as measured by GOES."
        ),
        source_url=r.get("link") or "https://kauai.ccmc.gsfc.nasa.gov/DONKI/",
        observed_at=peak,
        reported_at=_t(r.get("submissionTime")) or peak,
        location={"frame": "sun"},
        confidence=1.0,
        confidence_basis="official_report",
        raw={
            "class": cls,
            "begin": r.get("beginTime"),
            "end": r.get("endTime"),
            "source_location": r.get("sourceLocation") or None,
            "active_region": region,
            "linked": [x["activityID"] for x in r.get("linkedEvents") or []],
        },
    )


def cme_event(r: dict) -> Event | None:
    start = _t(r.get("startTime"))
    if start is None:
        return None
    best = next((a for a in r.get("cmeAnalyses") or [] if a.get("isMostAccurate")), None) or {}
    speed = num(best.get("speed"))
    earth = _earth_arrival(best)
    speed_txt = f" at about {speed:.0f} km/s" if speed else ""
    if earth:
        tail = f" A model run predicts it could reach Earth around {earth:%d %b %H:%M} UTC."
    else:
        tail = " Model runs so far do not show it hitting Earth." if best.get("enlilList") else ""
    return make_event(
        source=NAME,
        source_id=r["activityID"],
        type="coronal_mass_ejection",
        title="Coronal mass ejection" + (f" ({speed:.0f} km/s)" if speed else ""),
        summary=f"A cloud of solar plasma left the Sun{speed_txt}, seen by coronagraphs from {start:%H:%M} UTC.{tail}",
        source_url=r.get("link") or "https://kauai.ccmc.gsfc.nasa.gov/DONKI/",
        observed_at=start,
        reported_at=_t(r.get("submissionTime")) or start,
        location={"frame": "sun"},
        confidence=1.0,
        confidence_basis="official_report",
        raw={
            "speed_km_s": speed,
            "half_angle_deg": num(best.get("halfAngle")),
            "analysis_type": best.get("type"),
            "source_location": r.get("sourceLocation") or None,
            "earth_arrival": earth.isoformat() if earth else None,
            "instruments": [i["displayName"] for i in r.get("instruments") or []],
        },
    )


def _earth_arrival(analysis: dict) -> datetime | None:
    for run in analysis.get("enlilList") or []:
        if run.get("estimatedShockArrivalTime"):
            return as_utc(run["estimatedShockArrivalTime"])
    return None


def storm_event(r: dict) -> Event | None:
    start = _t(r.get("startTime"))
    if start is None:
        return None
    kps = [k for k in r.get("allKpIndex") or [] if num(k.get("kpIndex")) is not None]
    kp = max((num(k["kpIndex"]) for k in kps), default=None)
    level = next((g for lim, g in G_SCALE if kp is not None and kp >= lim), None)
    lat, lon = GEOMAGNETIC_NORTH_POLE
    return make_event(
        source=NAME,
        source_id=r["gstID"],
        type="geomagnetic_storm",
        title=f"Geomagnetic storm{f' {level.split()[0]}' if level else ''}",
        summary=(
            f"Earth's magnetic field was disturbed from {start:%d %b %H:%M} UTC"
            + (f", reaching Kp {kp:g}, a {level} storm on NOAA's scale" if kp is not None and level else "")
            + ". Storms like this can bring aurora to lower latitudes than usual."
        ),
        source_url=r.get("link") or "https://kauai.ccmc.gsfc.nasa.gov/DONKI/",
        observed_at=start,
        reported_at=_t(r.get("submissionTime")) or start,
        location={"frame": "earth", "lat_deg": lat, "lon_deg": lon, "alt_km": None},
        confidence=1.0,
        confidence_basis="official_report",
        raw={
            "kp_max": kp,
            "noaa_g_scale": level,
            "location_note": "whole-Earth event; point is the geomagnetic north pole",
            "linked": [x["activityID"] for x in r.get("linkedEvents") or []],
        },
    )
