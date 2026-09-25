"""known_solar_system(sphere, time): known asteroids and comets in a sphere, from IMCCE SkyBoT.

Queried through astroquery.imcce (https://astroquery.readthedocs.io/en/latest/imcce/imcce.html).
SkyBoT caps the cone at 10 deg (the contract's max sphere is also 10 deg, so no tiling needed).
Positions are computed for Rubin's observatory code X05 (Cerro Pachon).
"""

from __future__ import annotations

import re
import warnings
from datetime import datetime
from io import BytesIO

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time

from .classes import skybot_class_to_catch_type
from .http import RateLimiter, UpstreamError
from .models import KnownSolarSystemObject, Sphere, validate_sphere
from .util import as_utc, float_or_none

RUBIN_OBSERVATORY_CODE = "X05"
SKYBOT_HOST = "ssp.imcce.fr"
_limiter = RateLimiter()

def fetch_skybot_votable(sphere: Sphere, epoch: Time) -> bytes:
    """Raw SkyBoT VOTable for this cone. Split out so tests can replay recorded bytes."""
    from astroquery.imcce import Skybot

    _limiter.wait(SKYBOT_HOST)
    coo = SkyCoord(sphere["ra_deg"] * u.deg, sphere["dec_deg"] * u.deg)
    try:
        raw = Skybot.cone_search(
            coo,
            sphere["radius_deg"] * u.deg,
            epoch,
            location=RUBIN_OBSERVATORY_CODE,
            find_planets=False,
            get_raw_response=True,
        )
    except Exception as exc:  # astroquery raises requests errors; normalize
        raise UpstreamError(f"SkyBoT query failed: {exc}") from exc
    return raw.encode() if isinstance(raw, str) else raw


def parse_skybot_votable(raw: bytes) -> list[KnownSolarSystemObject]:
    status = re.search(rb'name="QUERY_STATUS" value="([A-Z]+)"', raw)
    if status and status.group(1) == b"ERROR" or raw.lstrip().startswith(b"{"):
        raise UpstreamError(f"SkyBoT returned an error: {raw[:300]!r}")
    if not re.search(rb"<(vot:)?TR>", raw):
        return []  # empty cone: VOTable with no rows
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = Table.read(BytesIO(raw), format="votable")
    if len(table) == 0:
        return []
    coo = SkyCoord(ra=list(table["ra"]), dec=list(table["de"]), unit=(u.hourangle, u.deg))
    out: list[KnownSolarSystemObject] = []
    for row, ra, dec in zip(table, coo.ra.deg, coo.dec.deg):
        name = str(row["name"]).strip()
        num = str(row["num"]).strip()
        klass = str(row["class"]).strip()
        out.append(
            {
                "name": name,
                "type": skybot_class_to_catch_type(klass, name),
                "ra_deg": round(float(ra), 6),
                "dec_deg": round(float(dec), 6),
                "number": num if num and num != "-" and num != "--" else None,
                "skybot_class": klass,
                "v_mag": float_or_none(row["magV"]),
                "position_error_arcsec": float_or_none(row["errpos"]),
            }
        )
    return out


def known_solar_system(sphere: Sphere, time: datetime | str) -> list[KnownSolarSystemObject]:
    """Known asteroids/comets inside `sphere` at `time` (UTC), as seen from Rubin (X05)."""
    sphere = validate_sphere(sphere)
    epoch = Time(as_utc(time))
    return parse_skybot_votable(fetch_skybot_votable(sphere, epoch))
