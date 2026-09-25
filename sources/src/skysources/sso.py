"""Rubin detections of known solar-system objects, from Fink's SSO bulk file.

Fink's cone search only returns diaObjects. Rubin associates every other diaSource to an
ssObject (a catalogued orbit), and Fink publishes all of those light curves as one Parquet file
(/api/v1/ssobulk). We scan it locally instead of asking per object.

Rubin's ssObjectId is the MPC *packed* primary provisional designation read as a big-endian
integer (verified against Fink /api/v1/sso: '2011 BU146' -> 'K11BE6U' -> 21164710888289877).
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass

import numpy as np
import pyarrow.compute as pc
import pyarrow.parquet as pq

from . import fink
from .models import CatchType

_B62 = string.digits + string.ascii_uppercase + string.ascii_lowercase
_CENTURY = {"18": "I", "19": "J", "20": "K"}
_PROVISIONAL = re.compile(r"^(18|19|20)(\d\d) ([A-Z])([A-Z])(\d*)$")
_SURVEY = re.compile(r"^(\d{4}) (P-L|T-1|T-2|T-3)$")
_SURVEY_CODE = {"P-L": "PLS", "T-1": "T1S", "T-2": "T2S", "T-3": "T3S"}


def pack_designation(designation: str) -> str | None:
    """MPC packed form of a provisional or survey designation; None if not one of those."""
    if m := _PROVISIONAL.match(designation.strip()):
        century, yy, half, letter, cycle = m.groups()
        n = int(cycle or 0)
        if n > 619:
            return None
        packed_cycle = f"{n:02d}" if n < 100 else f"{_B62[n // 10]}{n % 10}"
        return f"{_CENTURY[century]}{yy}{half}{packed_cycle}{letter}"
    if m := _SURVEY.match(designation.strip()):
        number, survey = m.groups()
        return f"{_SURVEY_CODE[survey]}{number}"
    return None


def ss_object_id(designation: str) -> int | None:
    packed = pack_designation(designation)
    return int.from_bytes(packed.encode(), "big") if packed else None


@dataclass
class SsoSighting:
    designation: str
    ra_deg: float  # at the latest detection inside the window
    dec_deg: float
    mjd_tai: float
    band: str
    n_detections: int  # inside the window
    helio_au: float | None
    topo_au: float | None


def sightings(
    t0_mjd_tai: float,
    t1_mjd_tai: float,
    cone: tuple[float, float, float] | None = None,
    *,
    path=None,
) -> list[SsoSighting]:
    """One entry per object detected in [t0, t1] (optionally inside cone (ra, dec, radius_deg))."""
    table = pq.read_table(
        path or fink.sso_bulk(),
        columns=["designation", "cra", "cdec", "cmidpointMjdTai", "cband", "chelioRange", "ctopoRange"],
    )
    if table.num_rows == 0:
        return []
    parent = pc.list_parent_indices(table["cmidpointMjdTai"]).to_numpy()
    mjd = pc.list_flatten(table["cmidpointMjdTai"]).to_numpy(zero_copy_only=False)
    ra = pc.list_flatten(table["cra"]).to_numpy(zero_copy_only=False)
    dec = pc.list_flatten(table["cdec"]).to_numpy(zero_copy_only=False)

    mask = (mjd >= t0_mjd_tai) & (mjd <= t1_mjd_tai)
    if cone is not None:
        cra, cdec, rad = cone
        mask &= _sep_deg(ra, dec, cra, cdec) <= rad
    idx = np.nonzero(mask)[0]
    if idx.size == 0:
        return []

    # Latest detection per object: sort by (parent, mjd) and keep the last of each run.
    order = idx[np.lexsort((mjd[idx], parent[idx]))]
    last_of_run = np.r_[parent[order][1:] != parent[order][:-1], True]
    counts = np.bincount(parent[idx], minlength=table.num_rows)

    band = pc.list_flatten(table["cband"]).to_numpy(zero_copy_only=False)
    helio = pc.list_flatten(table["chelioRange"]).to_numpy(zero_copy_only=False)
    topo = pc.list_flatten(table["ctopoRange"]).to_numpy(zero_copy_only=False)
    names = table["designation"].to_pylist()
    out = []
    for i in order[last_of_run]:
        p = int(parent[i])
        out.append(
            SsoSighting(
                designation=names[p],
                ra_deg=float(ra[i]),
                dec_deg=float(dec[i]),
                mjd_tai=float(mjd[i]),
                band=str(band[i]),
                n_detections=int(counts[p]),
                helio_au=_num(helio[i]),
                topo_au=_num(topo[i]),
            )
        )
    return out


# Solar-system type when SkyBoT has no class for the object. Each rule is a sufficient condition,
# so the answer can be too generic but not wrong: an NEA seen at r >= 1.3 AU stays "asteroid".
NEO_MAX_HELIO_AU = 1.3  # perihelion <= r, and NEOs are defined by perihelion < 1.3 AU
TNO_MIN_HELIO_AU = 30.07  # beyond Neptune's semi-major axis


def heuristic_type(designation: str, helio_au: float | None) -> CatchType:
    if re.match(r"^\d+I/", designation):
        return "interstellar_object"
    if re.match(r"^([CPDX]/|\d+P)", designation):
        return "comet"
    if helio_au is not None and helio_au >= TNO_MIN_HELIO_AU:
        return "trans_neptunian_object"
    if helio_au is not None and helio_au < NEO_MAX_HELIO_AU:
        return "near_earth_object"
    return "asteroid"


def _num(v: object) -> float | None:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def _sep_deg(ra, dec, ra0: float, dec0: float):
    ra, dec = np.radians(ra), np.radians(dec)
    r0, d0 = np.radians(ra0), np.radians(dec0)
    c = np.sin(dec) * np.sin(d0) + np.cos(dec) * np.cos(d0) * np.cos(ra - r0)
    return np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))
