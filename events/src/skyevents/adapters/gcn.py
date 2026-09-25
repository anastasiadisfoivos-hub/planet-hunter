"""Gamma-ray bursts and Einstein Probe X-ray transients, from NASA GCN Circulars.

GCN Circulars (https://gcn.nasa.gov/circulars) are the community's official, human-written
reports. Public, no login: the archive index is the page's JSON loader
(`?_data=routes/circulars._archive._index`, subjects only) and each circular is
`/circulars/<id>.json`. GCN's machine Notices need a (free) Kafka account, so they are not used.

One Event per named burst: "GRB 260925A" -> gcn:GRB_260925A, "EP260924a" -> gcn:EP260924a.
A circular naming both ("GRB 260920B/EP260920b") joins them. The position comes from the circular
bodies: the first report plus up to MAX_BODIES_PER_EVENT position reports, chosen by subject
(Swift-XRT > Swift-BAT > Fermi GBM > EP > SVOM > others), and the smallest error circle wins.

IceCube neutrinos come from the icecube adapter and gravitational waves from gracedb, so their
circulars are skipped here.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from ..models import Event
from ..util import as_utc, make_event, sky
from ._http import FOREVER, FRESH, UpstreamError, client

log = logging.getLogger(__name__)

NAME = "gcn"
LIVE_WITHIN = timedelta(days=3)  # several GRBs a week
INDEX = "https://gcn.nasa.gov/circulars"
INDEX_LOADER = "routes/circulars._archive._index"
PAGE_SIZE = 100
MAX_PAGES = 8
MAX_BODIES_PER_EVENT = 3

GRB = re.compile(r"\bGRB\s?(\d{6}[A-Z])\b")
EP = re.compile(r"\bEP\s?(\d{6}[a-z]{1,2})\b")

# Subject keywords, best position first.
POSITION_SUBJECTS = [
    "enhanced swift-xrt position", "swift-xrt refined", "swift detection of a burst", "swift-bat refined",
    "fermi gbm final", "fermi gbm", "einstein probe detection", "ep-wxt detection", "ep-fxt",
    "svom/eclairs", "detection",
]

_UNITS = {"arcsec": 1 / 3600, "arcsecond": 1 / 3600, "arcmin": 1 / 60, "arcminute": 1 / 60, "deg": 1.0, "degree": 1.0}
_POS = [
    re.compile(r"RA\s*,\s*Dec\s*[=:]?\s*\(?\s*([\d.]+)\s*,\s*([+-]?\s?[\d.]+)", re.IGNORECASE),
    re.compile(r"R\.?A\.?\s*(?:\(J2000\))?\s*=\s*([\d.]+)\s*(?:deg(?:rees)?)?\s*,?\s*Dec\.?\s*(?:\(J2000\))?\s*=\s*([+-]?[\d.]+)", re.IGNORECASE),
]
_ERR = re.compile(r"(?:uncertainty of|radius of|error radius of)\s*(?:about\s*)?([\d.]+)\s*(arcsec(?:ond)?|arcmin(?:ute)?|deg(?:ree)?)s?", re.IGNORECASE)
_TIME = [
    re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)\s*(?:UTC|UT)?"),
    re.compile(r"\bAt (\d\d:\d\d:\d\d(?:\.\d+)?) UT"),
]


def fetch(since: datetime, until: datetime) -> list[Event]:
    groups = _groups(since)
    out = []
    for names, circs in groups:
        date = _name_date(names)
        if date is None or not (since - timedelta(days=1) <= date <= until):
            continue
        try:
            e = _event(names, circs, date)
        except UpstreamError as exc:
            log.warning("GCN circular fetch failed for %s: %s", names, exc)
            continue
        if e and since <= as_utc(e["observed_at"]) <= until:
            out.append(e)
    return out


def last_event_at(now: datetime) -> datetime | None:
    groups = _groups(now - timedelta(days=2), max_pages=1)
    return max((d for names, _ in groups if (d := _name_date(names))), default=None)


def index_page(page: int) -> list[dict]:
    params = {"_data": INDEX_LOADER, "limit": PAGE_SIZE, "page": page}
    return client().get_json(INDEX, params=params, ttl=FRESH).get("items", [])


def circular(cid: int | str) -> dict:
    return client().get_json(f"{INDEX}/{cid}.json", ttl=FOREVER)


def names_in(subject: str) -> set[str]:
    return {f"GRB {m}" for m in GRB.findall(subject)} | {f"EP{m}" for m in EP.findall(subject)}


def _groups(since: datetime, max_pages: int = MAX_PAGES) -> list[tuple[frozenset[str], list[dict]]]:
    """Walk the index newest first until circulars name bursts older than `since`, then join
    names that share a circular (union-find)."""
    items: list[dict] = []
    for page in range(1, max_pages + 1):
        batch = index_page(page)
        items += batch
        dates = [d for it in batch if (d := _name_date(names_in(it["subject"])))]
        if not batch or (dates and max(dates) < since - timedelta(days=2)):
            break

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    by_name: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        ns = sorted(names_in(it["subject"]))
        for n in ns:
            by_name[n].append(it)
            parent[find(n)] = find(ns[0])
    clusters: dict[str, set[str]] = defaultdict(set)
    for n in by_name:
        clusters[find(n)].add(n)
    out = []
    for ns in clusters.values():
        circs = {int(c["circularId"]): c for n in ns for c in by_name[n]}
        out.append((frozenset(ns), [circs[k] for k in sorted(circs)]))
    return out


def _name_date(names: frozenset[str] | set[str]) -> datetime | None:
    for n in sorted(names):
        if m := re.search(r"(\d{2})(\d{2})(\d{2})", n):
            try:
                return datetime(2000 + int(m[1]), int(m[2]), int(m[3]), tzinfo=UTC)
            except ValueError:
                continue
    return None


def _rank(subject: str) -> int:
    s = subject.lower()
    return next((i for i, k in enumerate(POSITION_SUBJECTS) if k in s), len(POSITION_SUBJECTS))


def _event(names: frozenset[str], circs: list[dict], date: datetime) -> Event | None:
    first = circs[0]
    picks = [first] + sorted((c for c in circs[1:] if _rank(c["subject"]) < len(POSITION_SUBJECTS)), key=lambda c: _rank(c["subject"]))
    bodies = [circular(c["circularId"]) for c in picks[:MAX_BODIES_PER_EVENT]]
    positions = [(*p, b["circularId"]) for b in bodies for p in parse_positions(b["body"])]
    if not positions:
        return None
    ra, dec, err, from_id = min(positions, key=lambda x: x[2])
    when = next((t for b in bodies if (t := parse_time(b["body"], date))), None)
    reported = min(datetime.fromtimestamp(b["createdOn"] / 1000, UTC) for b in bodies)

    grb = sorted(n for n in names if n.startswith("GRB"))
    eps = sorted(n for n in names if n.startswith("EP"))
    primary = grb[0] if grb else eps[0]
    kind = "gamma_ray_burst" if grb else "unknown"
    if grb:
        title = f"Gamma-ray burst {primary}"
        summary = (
            f"Space telescopes recorded {primary}, a brief flash of gamma rays usually from a collapsing "
            f"massive star or merging neutron stars far outside our galaxy."
        )
    else:
        title = f"X-ray transient {primary}"
        summary = (
            f"The Einstein Probe X-ray telescope recorded a short-lived X-ray flash, {primary}; "
            "what caused it is not known yet."
        )
    return make_event(
        source=NAME,
        source_id=primary.replace(" ", "_"),
        type=kind,
        title=title,
        summary=summary,
        source_url=f"{INDEX}/{first['circularId']}",
        observed_at=when or date,
        reported_at=reported,
        location=sky(ra, dec, round(err, 5)),
        confidence=1.0,
        confidence_basis="official_report",
        raw={
            "names": sorted(names),
            "circulars": [int(c["circularId"]) for c in circs][:20],
            "position_from_circular": int(from_id),
            "time_precision": "second" if when else "day",
            # Circulars whose subject reports a redshift, best first; distance lookup reads them.
            "redshift_circulars": redshift_circulars(circs),
        },
    )


def redshift_subject_rank(subject: str) -> int | None:
    """Circulars that report a redshift, best first (spectroscopic, other, photometric); None if
    the subject doesn't claim one."""
    s = subject.lower()
    if "redshift" not in s:
        return None
    if "photometric" in s:
        return 2
    return 0 if "spectroscop" in s else 1


def redshift_circulars(circs: list[dict], limit: int = 3) -> list[dict]:
    ranked = [
        {"id": int(c["circularId"]), "subject": c["subject"][:160], "rank": r}
        for c in circs if (r := redshift_subject_rank(c["subject"])) is not None
    ]
    return sorted(ranked, key=lambda c: (c["rank"], c["id"]))[:limit]


def parse_positions(body: str) -> list[tuple[float, float, float]]:
    """Every decimal (ra, dec, error_deg) in a circular body. The error is the first
    'uncertainty of N unit' after the position; positions without one are skipped."""
    out = []
    for pat in _POS:
        for m in pat.finditer(body):
            ra, dec = float(m[1]), float(m[2].replace(" ", ""))
            e = _ERR.search(body, m.end(), m.end() + 600)
            if not e or not (0 <= ra < 360 and -90 <= dec <= 90):
                continue
            unit = e[2].lower().rstrip("s")
            out.append((ra, dec, float(e[1]) * _UNITS.get(unit, 1.0)))
    return out


def parse_time(body: str, date: datetime) -> datetime | None:
    """Trigger time: an ISO timestamp on the burst's date, else 'At hh:mm:ss UT' on that date."""
    for m in _TIME[0].finditer(body):
        t = as_utc(m[1])
        if t.date() == date.date():
            return t
    if m := _TIME[1].search(body):
        return as_utc(f"{date:%Y-%m-%d}T{m[1]}")
    return None
