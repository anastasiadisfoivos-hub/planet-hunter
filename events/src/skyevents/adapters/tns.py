"""Transient Name Server (TNS, IAU): spectroscopically classified supernovae and tidal
disruption events.

Uses the public search page's CSV export (https://www.wis-tns.org/search?format=csv&...), which
needs no account. TNS asks automated clients to be gentle, so this makes two small requests
per run (classified SNe, classified TDEs) at most one every 5 s. The TNS bot API
(https://www.wis-tns.org/content/tns-getting-started) needs a free bot account; it would add
exact classification dates, but it isn't needed for this feed.

Window: objects first reported within the last LOOKBACK_DAYS, because classification comes days
to weeks after first sighting and the CSV has no classification date. observed_at = TNS's first
detection date; the CSV gives no report time, so reported_at = observed_at
(raw.reported_at_known=False). Confidence 1.0 / official_report: a classification on TNS comes
from a spectrum and is the IAU's official record.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from ..models import Event
from ..util import as_utc, dms_to_deg, hms_to_deg, make_event, num, sky
from ._http import FRESH, client

NAME = "tns"
LIVE_WITHIN = timedelta(days=3)
SEARCH = "https://www.wis-tns.org/search"
LOOKBACK_DAYS = 30
MAX_ROWS = 500
POSITION_ERROR_DEG = 1.0 / 3600

TYPE_PREFIX = [
    ("SLSN", "supernova"), ("SN", "supernova"), ("TDE", "tidal_disruption_event"), ("Kilonova", "kilonova"),
    ("Nova", "nova"), ("AGN", "active_galaxy_flare"), ("QSO", "active_galaxy_flare"), ("M dwarf", "stellar_flare"),
    ("CV", "variable_star"), ("LBV", "variable_star"), ("Varstar", "variable_star"), ("Microlens", "microlensing"),
]


def fetch(since: datetime, until: datetime) -> list[Event]:
    start = min(since, until - timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    rows: dict[str, dict] = {}
    for flag in ("classified_sne", "classified_tde"):
        for r in search({flag: 1, "discovery_date_start": start}):
            rows[r["Name"]] = r
    return [e for r in rows.values() if (e := to_event(r)) and as_utc(e["observed_at"]) <= until]


def last_event_at(now: datetime) -> datetime | None:
    """Newest first-detection date among objects of any kind reported in the last 3 days
    (classifications lag by days, so they say little about whether TNS is flowing)."""
    rows = search({"reported_within_last_value": 3, "reported_within_last_units": "days", "num_page": 50})
    return max((as_utc(r["Discovery Date (UT)"]) for r in rows if r.get("Discovery Date (UT)")), default=None)


def search(params: dict) -> list[dict]:
    q = {"format": "csv", "num_page": MAX_ROWS, "page": 0, **params}
    text = client().request_text("GET", SEARCH, params=q, ttl=FRESH)
    return list(csv.DictReader(io.StringIO(text)))


def tns_type(label: str) -> str:
    return next((t for p, t in TYPE_PREFIX if label.startswith(p)), "unknown")


def to_event(r: dict) -> Event | None:
    name = r.get("Name", "").strip()
    if not name or not r.get("RA"):
        return None
    label = (r.get("Obj. Type") or "").strip()
    when = as_utc(r["Discovery Date (UT)"])
    short = name.split(" ", 1)[-1]
    internal = [s.strip() for s in (r.get("Disc. Internal Name") or "").split(",") if s.strip()]
    z = num(r.get("Redshift"))
    host = (r.get("Host Name") or "").strip()
    mag = num(r.get("Discovery Mag/Flux"))
    by = (r.get("Classifying Group/s") or "").strip()
    first_by = (r.get("Reporting Group/s") or r.get("Sender") or "").strip()
    where = f" in the galaxy {host}" if host else ""
    dist = f" at redshift {z:g}" if z else ""
    return make_event(
        source=NAME,
        source_id=short,
        type=tns_type(label),
        title=f"{name} ({label})" if label else name,
        summary=(
            f"The Transient Name Server lists {name}{where}{dist} as a {label}, classified from its spectrum"
            + (f" by {by}" if by else "")
            + f". It was first seen on {when:%d %b %Y}" + (f" by {first_by}" if first_by else "") + "."
        ),
        source_url=f"https://www.wis-tns.org/object/{short}",
        observed_at=when,
        reported_at=when,
        location=sky(hms_to_deg(r["RA"]), dms_to_deg(r["DEC"]), POSITION_ERROR_DEG),
        confidence=1.0,
        confidence_basis="official_report",
        brightness_mag=mag,
        raw={
            "names": [name, short, *internal],
            "tns_type": label,
            "redshift": z,
            "host": host or None,
            "first_mag": mag,
            "first_filter": r.get("Discovery Filter") or None,
            "reporting_groups": first_by or None,
            "classifying_groups": by or None,
            "reported_at_known": False,
        },
    )
