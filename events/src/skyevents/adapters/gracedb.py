"""Gravitational-wave candidates from LIGO/Virgo/KAGRA, via GraceDB (public, no login).

API: https://gracedb.ligo.org/api/superevents/ (docs: https://gracedb.ligo.org/documentation/).
Only production superevents that passed the rapid-response advocate check (label ADVOK) and
were not retracted. For each, the newest public alert file (<id>-{preliminary,initial,
update}.json, the same content as the GCN Kafka alert) gives the time, FAR, source
classification and a multi-order HEALPix sky map. The Event position is the most probable
pixel; error_deg is the radius of a circle with the 90% credible area (sky maps are banana-
shaped, so the full map is the thing to show; raw.area90_deg2 has the true area).

Confidence = 1 - P(terrestrial) from the alert, a pipeline estimate: machine_guess.
"""

from __future__ import annotations

import base64
import io
import logging
import math
import re
from datetime import datetime, timedelta

import numpy as np
from astropy.table import Table
from astropy.time import Time

from ..models import Event
from ..util import as_utc, make_event, sky
from ._http import FOREVER, FRESH, UpstreamError, client

log = logging.getLogger(__name__)

NAME = "gracedb"
LIVE_WITHIN = timedelta(days=14)
API = "https://gracedb.ligo.org/api/superevents/"
PUBLIC = "https://gracedb.ligo.org/superevents/{}/view/"
STAGES = {"preliminary": 0, "initial": 1, "update": 2}


def fetch(since: datetime, until: datetime) -> list[Event]:
    g0, g1 = Time(since).gps, Time(until).gps
    out = []
    for s in _superevents(f"category: Production ADVOK gpstime: {g0:.0f} .. {g1:.0f}"):
        try:
            if e := superevent_event(s["superevent_id"]):
                out.append(e)
        except UpstreamError as exc:
            log.warning("GraceDB files for %s unavailable: %s", s["superevent_id"], exc)
    return out


def last_event_at(now: datetime) -> datetime | None:
    rows = _superevents("category: Production ADVOK", count=1)
    return as_utc(Time(rows[0]["t_0"], format="gps").utc.to_datetime()) if rows else None


def _superevents(query: str, count: int = 100) -> list[dict]:
    doc = client().get_json(API, params={"query": query, "count": count, "orderby": "-t_0"}, ttl=FRESH)
    return doc.get("superevents", [])


def superevent_event(sid: str) -> Event | None:
    files = client().get_json(f"{API}{sid}/files/", ttl=FRESH)
    names = [k for k in files if "," not in k]
    if any(re.search(r"-retraction\.json$", k, re.IGNORECASE) for k in names):
        return None
    alerts = [k for k in names if re.fullmatch(rf"{sid}-(preliminary|initial|update)\.json", k, re.IGNORECASE)]
    if not alerts:
        return None
    newest = max(alerts, key=lambda k: STAGES[k.rsplit("-", 1)[1][:-5].lower()])
    alert = client().get_json(f"{API}{sid}/files/{newest}", ttl=FOREVER)
    return alert_to_event(alert)


def alert_to_event(alert: dict) -> Event | None:
    ev = alert.get("event") or {}
    if not ev.get("skymap"):
        return None
    ra, dec, area90 = skymap_summary(base64.b64decode(ev["skymap"]))
    cls = ev.get("classification") or {}
    terrestrial = float(cls.get("Terrestrial", 0.0))
    kinds = {k: v for k, v in cls.items() if k != "Terrestrial"}
    likely = max(kinds, key=kinds.get) if kinds else None
    sid = alert["superevent_id"]
    what = {
        "BBH": "two black holes merging",
        "BNS": "two neutron stars merging",
        "NSBH": "a neutron star and a black hole merging",
    }.get(likely or "", "a compact-object merger")
    when = as_utc(ev["time"])
    return make_event(
        source=NAME,
        source_id=sid,
        type="gravitational_wave",
        title=f"Gravitational-wave candidate {sid}",
        summary=(
            f"The {'/'.join(ev.get('instruments') or [])} detectors recorded a gravitational-wave signal; "
            f"the pipeline's best guess is {what} ({(kinds.get(likely, 0) if likely else 0) * 100:.0f}% probability). "
            f"It came from a patch of sky covering about {area90:.0f} square degrees."
        ),
        source_url=PUBLIC.format(sid),
        observed_at=when,
        reported_at=as_utc(alert.get("time_created") or ev["time"]),
        location=sky(ra, dec, round(math.sqrt(area90 / math.pi), 3)),
        confidence=1.0 - terrestrial,
        confidence_basis="machine_guess",
        raw={
            "names": [sid],
            "alert_type": alert.get("alert_type"),
            "far_hz": ev.get("far"),
            "classification": {k: round(v, 4) for k, v in cls.items()},
            "properties": ev.get("properties"),
            "area90_deg2": round(area90, 1),
            "pipeline": ev.get("pipeline"),
            "group": ev.get("group"),
        },
    )


def skymap_summary(fits_bytes: bytes) -> tuple[float, float, float]:
    """(ra, dec) of the most probable pixel and the 90% credible area (deg²) of a multi-order map."""
    from astropy_healpix import HEALPix

    t = Table.read(io.BytesIO(fits_bytes), format="fits")
    uniq = np.asarray(t["UNIQ"], dtype=np.int64)
    dens = np.asarray(t["PROBDENSITY"], dtype=float)  # per steradian
    order = (np.log2(uniq // 4) // 2).astype(int)
    ipix = uniq - 4 * (1 << (2 * order))
    area_sr = 4 * np.pi / (12 * 4.0**order)
    prob = dens * area_sr

    best = int(np.argmax(dens))
    hp = HEALPix(nside=1 << int(order[best]), order="nested")
    lon, lat = hp.healpix_to_lonlat([int(ipix[best])])
    ra, dec = float(lon.deg[0]), float(lat.deg[0])

    idx = np.argsort(dens)[::-1]
    cum = np.cumsum(prob[idx])
    n90 = int(np.searchsorted(cum, 0.9 * cum[-1])) + 1
    area90 = float(area_sr[idx[:n90]].sum() * (180 / np.pi) ** 2)
    return ra, dec, area90
