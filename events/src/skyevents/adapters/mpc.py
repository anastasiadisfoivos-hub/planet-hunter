"""Minor Planet Center confirmation pages: moving objects that observers reported and that still
need follow-up before they get an orbit and a designation.

- NEO Confirmation Page (NEOCP): possible near-Earth objects.
  https://www.minorplanetcenter.net/iau/NEO/toconfirm_tabular.html, JSON at
  /Extended_Files/neocp.json
- Possible Comet Confirmation Page (PCCP): objects reported to look cometary.
  https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html, text at /iau/NEO/pccp.txt

Both use the same temporary designations, and an object can move from one page to the other,
so the id is mpc:<temp designation> either way. RA on both pages is in hours.

Honesty: a NEOCP "score" is the MPC digest2 estimate (0-100) that the object is a NEO, a
machine estimate, so these events are machine_guess with confidence = score/100. A PCCP entry is
an observer's report of possible activity, not a confirmed comet: confidence 0.5.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from ..models import Event
from ..util import as_utc, make_event, num, sky
from ._http import FRESH, client

NAME = "mpc"
LIVE_WITHIN = timedelta(days=3)
NEOCP_JSON = "https://www.minorplanetcenter.net/Extended_Files/neocp.json"
NEOCP_PAGE = "https://www.minorplanetcenter.net/iau/NEO/toconfirm_tabular.html"
PCCP_TXT = "https://www.minorplanetcenter.net/iau/NEO/pccp.txt"
PCCP_PAGE = "https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html"
# Short arcs: positions are predictions good to a few arcminutes at best.
POSITION_ERROR_DEG = 0.05
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def fetch(since: datetime, until: datetime) -> list[Event]:
    """Everything currently on the two pages whose last sighting falls in [since, until]."""
    events = current()
    return [e for e in events if since <= as_utc(e["observed_at"]) <= until]


def last_event_at(now: datetime) -> datetime | None:
    return max((as_utc(e["observed_at"]) for e in current()), default=None)


def current() -> list[Event]:
    neocp = client().get_json(NEOCP_JSON, ttl=FRESH)
    pccp = client().request_text("GET", PCCP_TXT, ttl=FRESH)
    # An object can sit on both pages: reported as cometary, and scored as a possible NEO. It is
    # one Event, a possible comet, with the NEO score kept in raw.
    by_id = {e["id"]: e for e in (neocp_event(r) for r in neocp)}
    for r in parse_pccp(pccp):
        e = pccp_event(r)
        if e["id"] in by_id:
            e["raw"]["pages"] = ["NEOCP", "PCCP"]
        by_id[e["id"]] = e
    return list(by_id.values())


def parse_pccp(text: str) -> list[dict]:
    """Same columns as the NEOCP: desig score yyyy mm dd.d RA(h) Dec V 'Updated Mon. dd.dd UT'
    NObs Arc H NotSeen."""
    rows = []
    pat = re.compile(
        r"^(?P<desig>\S+)\s+(?P<score>\d+)\s+(?P<y>\d{4})\s+(?P<m>\d\d)\s+(?P<d>[\d.]+)\s+"
        r"(?P<ra>[\d.]+)\s+(?P<dec>[+-][\d.]+)\s+(?P<v>[\d.]+)?\s*(?P<upd>Updated .*? UT)\s+"
        r"(?P<nobs>\d+)\s+(?P<arc>[\d.]+)\s+(?P<h>[\d.]+)?\s+(?P<ns>[\d.]+)\s*$"
    )
    for line in text.splitlines():
        if m := pat.match(line.strip()):
            g = m.groupdict()
            rows.append({
                "Temp_Desig": g["desig"], "Score": int(g["score"]),
                "Discovery_year": int(g["y"]), "Discovery_month": int(g["m"]), "Discovery_day": float(g["d"]),
                "R.A.": float(g["ra"]), "Decl.": float(g["dec"]), "V": num(g["v"]), "Updated": g["upd"],
                "NObs": int(g["nobs"]), "Arc": float(g["arc"]), "H": num(g["h"]), "Not_Seen_dys": float(g["ns"]),
            })
    return rows


def _first_seen(r: dict) -> datetime:
    day = float(r["Discovery_day"])
    base = datetime(int(r["Discovery_year"]), int(r["Discovery_month"]), 1, tzinfo=UTC)
    return base + timedelta(days=day - 1)


def _updated(r: dict, first: datetime) -> datetime:
    """'Updated Sept. 25.64 UT' -> datetime (year from the first sighting, rolled over if needed)."""
    m = re.search(r"Updated\s+([A-Za-z]+)\.?\s+([\d.]+)", r.get("Updated") or "")
    if not m:
        return first
    month = MONTHS.get(m[1][:3].lower())
    if month is None:
        return first
    year = first.year + (1 if month < first.month else 0)
    return datetime(year, month, 1, tzinfo=UTC) + timedelta(days=float(m[2]) - 1)


def _common(r: dict) -> dict:
    """The arc can include observations from before the object was posted, so the last sighting
    is the page's update time minus "not seen for N days", not first sighting + arc."""
    first = _first_seen(r)
    updated = _updated(r, first)
    last = updated - timedelta(days=float(r.get("Not_Seen_dys") or 0.0))
    return {
        "first": first,
        "last": last,
        "updated": updated,
        "location": sky(float(r["R.A."]) * 15.0, float(r["Decl."]), POSITION_ERROR_DEG),
        "raw": {
            "names": [r["Temp_Desig"]],
            "temp_designation": r["Temp_Desig"],
            "first_seen": first.isoformat(timespec="minutes"),
            "observations": r.get("NObs"),
            "arc_days": r.get("Arc"),
            "absolute_mag_H": num(r.get("H")),
            "not_seen_days": r.get("Not_Seen_dys"),
            "neo_score": r.get("Score"),
        },
    }


def neocp_event(r: dict) -> Event:
    c = _common(r)
    score = int(r.get("Score") or 0)
    h = num(r.get("H"))
    size = f" Its brightness suggests it is roughly {_size_from_h(h)} across." if h is not None else ""
    return make_event(
        source=NAME,
        source_id=r["Temp_Desig"],
        type="near_earth_object",
        title=f"Possible near-Earth object {r['Temp_Desig']}",
        summary=(
            f"Observers reported this moving object and asked for follow-up; the MPC's automatic "
            f"score that it is a near-Earth object is {score} out of 100 (a machine estimate, no "
            f"orbit yet).{size}"
        ),
        source_url=NEOCP_PAGE,
        observed_at=c["last"],
        reported_at=c["updated"],
        location=c["location"],
        confidence=score / 100.0,
        confidence_basis="machine_guess",
        brightness_mag=num(r.get("V")),
        raw={**c["raw"], "pages": ["NEOCP"]},
    )


def pccp_event(r: dict) -> Event:
    c = _common(r)
    return make_event(
        source=NAME,
        source_id=r["Temp_Desig"],
        type="comet",
        title=f"Possible comet {r['Temp_Desig']}",
        summary=(
            "Observers reported that this moving object may look fuzzy or have a tail, and the MPC "
            "has asked for confirmation; it is not yet a confirmed comet."
        ),
        source_url=PCCP_PAGE,
        observed_at=c["last"],
        reported_at=c["updated"],
        location=c["location"],
        confidence=0.5,
        confidence_basis="official_report",
        brightness_mag=num(r.get("V")),
        raw={**c["raw"], "pages": ["PCCP"]},
    )


def _size_from_h(h: float) -> str:
    """Diameter range for albedo 0.25-0.05: D(km) = 1329 / sqrt(p) * 10^(-H/5)."""
    lo, hi = 1329 / 0.25**0.5 * 10 ** (-h / 5), 1329 / 0.05**0.5 * 10 ** (-h / 5)
    if hi < 1:
        return f"{lo * 1000:.0f}-{hi * 1000:.0f} m"
    return f"{lo:.1f}-{hi:.1f} km"
