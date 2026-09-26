"""Newly designated comets (and interstellar objects), from NASA/JPL.

- Which comets: JPL SBDB Query API (https://ssd-api.jpl.nasa.gov/doc/sbdb_query.html), comets
  whose first observation is within the last LOOKBACK_DAYS, plus any strongly hyperbolic comet
  (e > 1.2, an interstellar visitor) still being observed.
- Where they are now: JPL Horizons (https://ssd-api.jpl.nasa.gov/doc/horizons.html), one
  observer ephemeris per comet at the ingest time, rounded to the hour so the cache helps.

The MPC publishes new comets as MPEC circulars but has no machine-readable list of recent ones,
so this uses JPL's copy of the same orbits. Source name "jpl"; id jpl:<designation>.
The window is the comet's first observation, not `since`: a comet found three weeks ago is still
"happening". observed_at = its latest observation in JPL's orbit solution. SBDB gives no report
date, so reported_at = observed_at (raw.reported_at_known=False).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

from astropy.time import Time

from ..models import Event
from ..util import as_utc, make_event, num, sky
from ._http import DAY, FRESH, UpstreamError, client

log = logging.getLogger(__name__)

NAME = "jpl"
LIVE_WITHIN = timedelta(days=90)  # a few new comets a month
LOOKBACK_DAYS = 60
QUERY = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"
FIELDS = "full_name,pdes,prefix,first_obs,last_obs,e,q,tp"
INTERSTELLAR_E = 1.2
# JPL files interstellar comets under their C/ designations.
INTERSTELLAR_NAMES = {"2017 U1": "1I/ʻOumuamua", "2019 Q4": "2I/Borisov", "2025 N1": "3I/ATLAS"}
POSITION_ERROR_DEG = 0.01


def fetch(since: datetime, until: datetime) -> list[Event]:
    rows = _query(until)
    epoch = until.replace(minute=0, second=0, microsecond=0)
    out = []
    for r in rows:
        try:
            pos = ephemeris(r["pdes"], epoch)
        except UpstreamError as exc:
            log.warning("Horizons failed for %s: %s", r["pdes"], exc)
            continue
        if pos:
            out.append(to_event(r, *pos, epoch))
    return out


def last_event_at(now: datetime) -> datetime | None:
    return max((_date(r["last_obs"]) for r in _query(now) if r.get("last_obs")), default=None)


def _query(until: datetime) -> list[dict]:
    start = (until - timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    rows: dict[str, dict] = {}
    for cdata in (
        {"AND": [f"first_obs|GE|{start}"]},
        {"AND": [f"e|GT|{INTERSTELLAR_E}", f"last_obs|GE|{start}"]},
    ):
        doc = client().get_json(
            QUERY, params={"fields": FIELDS, "sb-kind": "c", "sb-cdata": json.dumps(cdata)}, ttl=FRESH
        )
        for vals in doc.get("data") or []:
            r = dict(zip(doc["fields"], vals, strict=False))
            r["full_name"] = r["full_name"].strip()
            rows[r["pdes"]] = r
    return sorted(rows.values(), key=lambda r: r["pdes"])


def ephemeris(pdes: str, epoch: datetime) -> tuple[float, float, float | None] | None:
    """(ra_deg, dec_deg, total magnitude or None) seen from Earth's centre at `epoch`."""
    params = {
        "format": "json",
        "COMMAND": f"'DES={pdes};CAP;NOFRAG'",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": "'500@399'",
        "TLIST": f"'{Time(epoch).jd:.5f}'",
        "QUANTITIES": "'1,9'",
        "ANG_FORMAT": "DEG",
        "OBJ_DATA": "NO",
    }
    result = client().get_json(HORIZONS, params=params, ttl=DAY).get("result", "")
    return parse_ephemeris(result)


def parse_ephemeris(result: str) -> tuple[float, float, float | None] | None:
    m = re.search(r"\$\$SOE\s*\n(.*?)\n", result)
    if not m:
        return None
    # " 2026-Sep-25 14:24:00.000     344.59019 -13.36849   19.357    n.a."
    parts = m[1].split()
    nums = [p for p in parts[2:] if re.fullmatch(r"[+-]?[\d.]+|n\.a\.", p)]
    ra, dec = float(nums[0]), float(nums[1])
    tmag = num(nums[2]) if len(nums) > 2 else None
    return ra, dec, tmag


def _date(s: str) -> datetime:
    return as_utc(f"{s}T00:00:00")


def to_event(r: dict, ra: float, dec: float, tmag: float | None, epoch: datetime) -> Event:
    e = num(r.get("e"))
    q = num(r.get("q"))
    interstellar = e is not None and e > INTERSTELLAR_E
    name = r["full_name"]
    if interstellar and r["pdes"] in INTERSTELLAR_NAMES:
        name = f"{INTERSTELLAR_NAMES[r['pdes']]} ({name})"
    last = _date(r["last_obs"]) if r.get("last_obs") else epoch
    first = r.get("first_obs")
    peri = f" It comes closest to the Sun at {q:.2f} AU." if q is not None else ""
    if interstellar:
        summary = (
            f"Comet {name} is on an open (hyperbolic, e = {e:.2f}) orbit, so it came from outside "
            f"the Solar System and will not return.{peri}"
        )
        kind = "interstellar_object"
    else:
        summary = f"Comet {name} was first observed on {first} and has a published orbit.{peri}"
        kind = "comet"
    if tmag is not None:
        summary += f" Predicted total brightness now: magnitude {tmag:.1f}."
    return make_event(
        source=NAME,
        source_id=(f"{r['prefix']}/" if r.get("prefix") else "") + r["pdes"].replace(" ", "_"),
        type=kind,
        title=f"{'Interstellar object' if interstellar else 'New comet'} {name}",
        summary=summary,
        source_url=f"https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={r['pdes'].replace(' ', '%20')}",
        observed_at=last,
        reported_at=last,
        location=sky(ra, dec, POSITION_ERROR_DEG),
        confidence=1.0,
        confidence_basis="official_report",
        brightness_mag=tmag,
        raw={
            "names": [r["full_name"], (f"{r['prefix']}/" if r.get("prefix") else "") + r["pdes"]],
            "designation": r["full_name"],
            "first_obs": first,
            "last_obs": r.get("last_obs"),
            "eccentricity": e,
            "perihelion_au": q,
            "position_epoch": epoch.isoformat(timespec="minutes"),
            "reported_at_known": False,
        },
    )
