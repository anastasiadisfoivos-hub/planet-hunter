"""Turn a star name, "TIC 123", 123 or StarTarget into a TIC ID plus stellar parameters from TIC 8.2."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .cache import DAY, cached_json, retry
from .models import StarTarget

_TIC_RE = re.compile(r"^\s*(?:TIC\s*)?(\d+)\s*$", re.IGNORECASE)
_PLANET_SUFFIX_RE = re.compile(r"\s*[b-i]\s*$")


@dataclass(frozen=True)
class StarInfo:
    tic_id: int
    ra_deg: float
    dec_deg: float
    radius_rsun: float | None
    teff_k: float | None
    tmag: float | None
    query: str
    radius_err_rsun: float | None = None


def _num(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _row_to_dict(row) -> dict:
    return {
        "tic_id": int(row["ID"]),
        "ra_deg": float(row["ra"]),
        "dec_deg": float(row["dec"]),
        "radius_rsun": _num(row["rad"]),
        "radius_err_rsun": _num(row["e_rad"]),
        "teff_k": _num(row["Teff"]),
        "tmag": _num(row["Tmag"]),
    }


def _query_by_tic(tic_id: int) -> dict:
    from astroquery.mast import Catalogs

    table = retry(lambda: Catalogs.query_criteria(catalog="Tic", ID=tic_id))
    if len(table) == 0:
        raise LookupError(f"TIC {tic_id} is not in the TESS Input Catalog")
    return _row_to_dict(table[0])


def _query_by_name(name: str) -> dict:
    from astroquery.mast import Catalogs

    last_error: Exception | None = None
    # "WASP-18 b" is a planet name; the star is "WASP-18". Try as given, then without the letter.
    for candidate in dict.fromkeys([name, _PLANET_SUFFIX_RE.sub("", name)]):
        try:
            table = retry(lambda: Catalogs.query_object(candidate, catalog="TIC", radius=0.005))
        except Exception as exc:  # name resolver says "could not resolve"
            last_error = exc
            continue
        if len(table):
            table.sort("dstArcSec")
            return _row_to_dict(table[0])
    raise LookupError(f"could not resolve {name!r} to a TIC star") from last_error


def resolve(target: StarTarget | int | str, refresh: bool = False) -> StarInfo:
    if isinstance(target, StarTarget):
        tic_id, query = target.tic_id, f"TIC {target.tic_id}"
    elif isinstance(target, int):
        tic_id, query = target, f"TIC {target}"
    else:
        match = _TIC_RE.match(target)
        tic_id, query = (int(match.group(1)), f"TIC {match.group(1)}") if match else (None, target.strip())

    if tic_id is not None:
        data = cached_json("tic-v2", str(tic_id), 30 * DAY, lambda: _query_by_tic(tic_id), refresh)
    else:
        data = cached_json("tic-name-v2", query.lower(), 30 * DAY, lambda: _query_by_name(query), refresh)
    return StarInfo(query=query, **data)
