"""Catalogue lookups behind event distances. All free, no login, all through the shared client.

- TNS public search (CSV), objects with a redshift: one paged request per 500 objects, matched to
  events by name (TNS name or internal survey name) or position.
- SIMBAD TAP (https://simbad.cds.unistra.fr/simbad/sim-tap): galaxies, AGN and quasars with a
  redshift at an event's position. Many cones per ADQL query.
- Gaia DR3 TAP (https://gea.esac.esa.int/tap-server/tap): the nearest Gaia source at an event's
  position, with its parallax.
- GCN Circulars: the redshift a circular reports for a burst.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta

from .adapters import gcn as gcn_adapter
from .adapters._http import DAY, FRESH, client
from .dedup import norm_name
from .util import dms_to_deg, hms_to_deg, num, sep_deg

# ------------------------------------------------------------------ TNS

TNS_SEARCH = "https://www.wis-tns.org/search"
TNS_PAGE = 500
TNS_MAX_PAGES = 6
TNS_LOOKBACK = timedelta(days=90)


class TnsRedshifts:
    """TNS objects with a redshift, first seen from `start` on, indexed by name and position."""

    def __init__(self, rows: list[dict], truncated: bool, start: str) -> None:
        self.rows = rows
        self.truncated = truncated
        self.start = start
        self.by_name: dict[str, dict] = {}
        self.by_band: dict[int, list[dict]] = defaultdict(list)
        for r in rows:
            for n in r["names"]:
                self.by_name[norm_name(n)] = r
            self.by_band[int(r["dec"] // 0.05)].append(r)

    def match(self, names: list[str], ra: float, dec: float, radius_deg: float) -> dict | None:
        for n in names:
            if r := self.by_name.get(norm_name(n)):
                return r
        b = int(dec // 0.05)
        near = [r for k in (b - 1, b, b + 1) for r in self.by_band.get(k, [])]
        best = min(near, key=lambda r: sep_deg(ra, dec, r["ra"], r["dec"]), default=None)
        if best and sep_deg(ra, dec, best["ra"], best["dec"]) <= radius_deg:
            return best
        return None


def tns_redshifts(earliest: datetime) -> TnsRedshifts:
    start = (earliest - TNS_LOOKBACK).date().isoformat()
    rows: list[dict] = []
    truncated = False
    for page in range(TNS_MAX_PAGES):
        params = {"format": "csv", "num_page": TNS_PAGE, "page": page, "redshift_min": "0.00001",
                  "discovery_date_start": start}
        batch = list(csv.DictReader(io.StringIO(client().request_text("GET", TNS_SEARCH, params=params, ttl=FRESH))))
        rows += [p for r in batch if (p := _tns_row(r))]
        if len(batch) < TNS_PAGE:
            break
    else:
        truncated = True
    return TnsRedshifts(rows, truncated, start)


def _tns_row(r: dict) -> dict | None:
    name = (r.get("Name") or "").strip()
    if not name or not r.get("RA"):
        return None
    z, hz = num(r.get("Redshift")), num(r.get("Host Redshift"))
    if not (z or hz):
        return None
    internal = [s.strip() for s in (r.get("Disc. Internal Name") or "").split(",") if s.strip()]
    return {
        "name": name,
        "names": [name, name.split(" ", 1)[-1], *internal],
        "ra": hms_to_deg(r["RA"]),
        "dec": dms_to_deg(r["DEC"]),
        "redshift": z,
        "host_redshift": hz,
        "host": (r.get("Host Name") or "").strip() or None,
    }


# ------------------------------------------------------------------ TAP (SIMBAD, Gaia)

SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
CONES_PER_QUERY = 50

# SIMBAD object types that are galaxies or galaxy nuclei (their redshift is the event's host's).
GALAXY_OTYPES = {
    "G", "G?", "GiC", "GiG", "GiP", "BiC", "IG", "PaG", "GrG", "CGG", "LSB", "bCG", "SBG", "H2G", "EmG", "rG",
    "AGN", "AG?", "LIN", "LI?", "SyG", "Sy?", "Sy1", "Sy2", "Bla", "Bz?", "BLL", "BL?", "OVV", "QSO", "Q?", "LeG",
}


def _tap(url: str, query: str) -> list[dict]:
    body = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": query}
    doc = json.loads(client().request_text("POST", url, data=body, ttl=30 * DAY))
    cols = [c["name"] for c in doc["metadata"]]
    return [dict(zip(cols, row, strict=False)) for row in doc["data"]]


def _cones(points: list[tuple[float, float]], radius_deg: float) -> str:
    return " OR ".join(
        f"1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra:.7f},{dec:.7f},{radius_deg:.7f}))" for ra, dec in points
    )


def _nearest(points: list[tuple[float, float]], rows: list[dict], radius_deg: float, ok=lambda r: True) -> list[dict | None]:
    out = []
    for ra, dec in points:
        cands = [(sep_deg(ra, dec, r["ra"], r["dec"]), r) for r in rows if ok(r)]
        cands = [c for c in cands if c[0] <= radius_deg]
        out.append(min(cands, key=lambda c: c[0])[1] if cands else None)
    return out


def simbad_galaxies(points: list[tuple[float, float]], radius_deg: float) -> list[dict | None]:
    """Per point, the nearest SIMBAD galaxy/AGN/QSO with a positive redshift within radius."""
    out: list[dict | None] = []
    for i in range(0, len(points), CONES_PER_QUERY):
        chunk = points[i : i + CONES_PER_QUERY]
        q = ("SELECT main_id, ra, dec, otype, rvz_redshift, rvz_qual, rvz_bibcode FROM basic "
             f"WHERE rvz_redshift > 0 AND ({_cones(chunk, radius_deg)})")
        rows = _tap(SIMBAD_TAP, q)
        out += _nearest(chunk, rows, radius_deg, ok=lambda r: (r["otype"] or "").strip() in GALAXY_OTYPES)
    return out


def gaia_sources(points: list[tuple[float, float]], radius_deg: float) -> list[dict | None]:
    """Per point, the nearest Gaia DR3 source within radius (any parallax quality)."""
    out: list[dict | None] = []
    for i in range(0, len(points), CONES_PER_QUERY):
        chunk = points[i : i + CONES_PER_QUERY]
        q = ("SELECT source_id, ra, dec, parallax, parallax_error, phot_g_mean_mag FROM gaiadr3.gaia_source "
             f"WHERE {_cones(chunk, radius_deg)}")
        out += _nearest(chunk, _tap(GAIA_TAP, q), radius_deg)
    return out


# ------------------------------------------------------------------ GCN circulars

_Z_SUBJECT = re.compile(r"\bz\s*[=~]\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_Z_BODY = [
    re.compile(r"\bredshift\s+(?:of\s+)?z\s*[=~]\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\bredshift\s+of\s+(?:about\s+|approximately\s+)?(\d+\.\d+)", re.IGNORECASE),
]  # never a bare "z = x" in a body: circulars also quote z-band magnitudes that way


def gcn_redshift(circulars: list[dict]) -> tuple[float, int, str] | None:
    """(z, circular id, subject) from the best redshift circular; the subject's own "z = ..."
    if it has one, else the body."""
    for c in circulars:
        if m := _Z_SUBJECT.search(c["subject"]):
            return float(m[1]), c["id"], c["subject"]
        body = gcn_adapter.circular(c["id"]).get("body", "")
        for pat in _Z_BODY:
            if (m := pat.search(body)) and 0 < float(m[1]) < 20:
                return float(m[1]), c["id"], c["subject"]
    return None


__all__ = ["TnsRedshifts", "gaia_sources", "gcn_redshift", "simbad_galaxies",
           "tns_redshifts"]
