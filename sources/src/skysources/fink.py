"""Thin client for the Fink LSST REST API. No login.

API: https://api.lsst.fink-portal.org (Swagger at the root, spec at /swagger.json)
Docs: https://doc.lsst.fink-broker.org/services/api/
Portal: https://lsst.fink-portal.org
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from .http import HOST_MIN_INTERVAL, get_client

FINK_API = "https://api.lsst.fink-portal.org/api/v1"
FINK_PORTAL = "https://lsst.fink-portal.org"
HOST_MIN_INTERVAL.setdefault("api.lsst.fink-portal.org", 1.0)

MAX_CONE_DEG = 5.0  # conesearch radius cap (18000 arcsec)

# Only what alerts() needs: keeps a 1-degree cone from being tens of MB.
CONE_COLUMNS = [
    "r:diaObjectId",
    "r:diaSourceId",
    "r:ssObjectId",
    "r:ra",
    "r:dec",
    "r:midpointMjdTai",
    "r:band",
    "r:psfFlux",
    "r:psfFluxErr",
    "r:reliability",
    "r:nDiaSources",
    "r:observation_reason",
    "f:firstDiaSourceMjdTaiFink",
    "f:main_label_classifier",
    "f:main_label_crossmatch",
    "f:clf_cats_class",
    "f:clf_cats_score",
    "f:clf_snnSnVsOthers_score",
    "f:is_cataloged",
    "f:is_sso",
    "f:xm_simbad_otype",
    "f:xm_tns_fullname",
    "f:xm_tns_type",
    "f:xm_vsx_Type",
    "f:xm_gaiadr3_DR3Name",
]


def conesearch(
    ra: float, dec: float, radius_deg: float, start_mjd: float, stop_mjd: float, ttl: float
) -> list[dict[str, Any]]:
    """Objects with at least one alert in [start, stop] (kind=across), one row per diaObject,
    carrying that object's most recent alert. Dates filter on first detection per Fink docs, and
    `across` widens that to objects seen during the window."""
    body = {
        "ra": ra,
        "dec": dec,
        "radius": round(min(radius_deg, MAX_CONE_DEG) * 3600, 3),
        "startdate": f"{start_mjd:.6f}",
        "stopdate": f"{stop_mjd:.6f}",
        "kind": "across",
        "columns": ",".join(CONE_COLUMNS),
    }
    return get_client().post_json(f"{FINK_API}/conesearch", json_body=body, ttl=ttl)


def sso_rows(designation: str, ttl: float = 86400.0) -> list[dict[str, Any]]:
    """All Rubin detections Fink has for one solar-system object (by designation or number)."""
    body = {
        "n_or_d": designation,
        "columns": "r:ssObjectId,r:diaSourceId,r:midpointMjdTai,r:ra,r:dec,r:band",
    }
    return get_client().post_json(f"{FINK_API}/sso", json_body=body, ttl=ttl)


def sources(dia_object_id: int | str, ttl: float = 3600.0) -> list[dict[str, Any]]:
    """Light curve (difference-image detections) for one diaObject."""
    body = {
        "diaObjectId": str(dia_object_id),
        "columns": "r:midpointMjdTai,r:band,r:psfFlux,r:psfFluxErr,r:diaSourceId",
    }
    return get_client().post_json(f"{FINK_API}/sources", json_body=body, ttl=ttl)


def statistics(date: str, ttl: float = 3600.0) -> list[dict[str, Any]]:
    """Per-night alert statistics; `date` is YYYYMMDD, YYYYMM or YYYY."""
    return get_client().post_json(
        f"{FINK_API}/statistics", json_body={"date": date, "columns": "f:night,f:alerts"}, ttl=ttl
    )


def sso_bulk(ttl: float = 86400.0) -> Path:
    """Parquet with every Rubin solar-system light curve Fink holds (~40 MB, one row per object:
    designation + lists cra, cdec, cmidpointMjdTai, cband, chelioRange, ...)."""
    return get_client().download(f"{FINK_API}/ssobulk", "fink_ssobulk.parquet", json_body={}, ttl=ttl)


def cutout_url(dia_source_id: int | str, kind: str) -> str:
    """Direct PNG URL (usable as <img src>). kind: Science | Template | Difference."""
    q = urlencode({"diaSourceId": str(dia_source_id), "kind": kind, "output-format": "PNG"})
    return f"{FINK_API}/cutouts?{q}"


def portal_url(dia_object_id: int | str) -> str:
    return f"{FINK_PORTAL}/{dia_object_id}"


def cone_tiles(ra: float, dec: float, radius_deg: float) -> list[tuple[float, float, float]]:
    """Cover a cone of up to 10 deg with Fink's 5-deg cones: one central cone plus a ring of 8
    at 0.75 R (checked: every point within R is within 5 deg of some tile centre)."""
    if radius_deg <= MAX_CONE_DEG:
        return [(ra, dec, radius_deg)]
    tiles = [(ra, dec, MAX_CONE_DEG)]
    d = 0.75 * radius_deg
    for k in range(8):
        tiles.append((*_offset(ra, dec, d, 45.0 * k), MAX_CONE_DEG))
    return tiles


def _offset(ra: float, dec: float, dist_deg: float, bearing_deg: float) -> tuple[float, float]:
    """Point at great-circle distance/bearing from (ra, dec)."""
    r1, d1 = math.radians(ra), math.radians(dec)
    dd, b = math.radians(dist_deg), math.radians(bearing_deg)
    d2 = math.asin(math.sin(d1) * math.cos(dd) + math.cos(d1) * math.sin(dd) * math.cos(b))
    r2 = r1 + math.atan2(math.sin(b) * math.sin(dd) * math.cos(d1), math.cos(dd) - math.sin(d1) * math.sin(d2))
    return (math.degrees(r2) % 360.0, math.degrees(d2))
