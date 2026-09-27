"""TIC 8.2 rows from MAST: in bulk (the filtered catalogue service, one declination strip at a time) and per star.

Bulk selection: Tmag 13-16, Teff < 4000 K (an M dwarf in the TIC's Gaia-based Teff), luminosity class DWARF,
object type STAR, and not flagged SPLIT / DUPLICATE / ARTIFACT. Each strip is cached for good (TIC 8.2 is
frozen). The TIC's GAIA column is the Gaia DR2 source id; TGLC names its files by Gaia DR3 id, which is the same
number for the great majority of stars (the loader confirms it, see tglc.resolve).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import requests

from .cache import FOREVER, DAY, cached_json, retry

MAST_API = "https://mast.stsci.edu/api/v0/invoke"
COLUMNS = "ID,ra,dec,Tmag,Teff,logg,rad,e_rad,mass,rho,lumclass,contratio,GAIA,disposition,objType"
PAGE = 50_000
BAD_DISPOSITIONS = {"SPLIT", "DUPLICATE", "ARTIFACT"}


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _invoke(service: str, params: dict, page: int = 1, pagesize: int = PAGE) -> dict:
    req = {"service": service, "format": "json", "params": params, "pagesize": pagesize, "page": page}

    def call() -> dict:
        r = requests.post(MAST_API, data="request=" + requests.utils.quote(json.dumps(req)), timeout=900,
                          headers={"Content-type": "application/x-www-form-urlencoded"})
        r.raise_for_status()
        d = r.json()
        if d.get("status") not in ("COMPLETE", None):
            raise OSError(f"MAST {service}: {d.get('status')} {d.get('msg')}")
        return d
    return retry(call)


def row(r: dict) -> dict:
    """A TIC record in the field names used everywhere in skyfaint (and hunt.stars.Star)."""
    return {"tic": int(r["ID"]), "ra": _num(r["ra"]), "dec": _num(r["dec"]), "tmag": _num(r["Tmag"]),
            "teff": _num(r["Teff"]), "logg": _num(r["logg"]), "rad": _num(r["rad"]), "rad_err": _num(r.get("e_rad")),
            "mass": _num(r["mass"]), "rho": _num(r["rho"]), "lumclass": (r.get("lumclass") or "").strip() or None,
            "contratio": _num(r["contratio"]), "gaia_dr2": str(r["GAIA"]) if r.get("GAIA") else None,
            "disposition": (r.get("disposition") or "").strip() or None}


def _filters(dec_lo: float, dec_hi: float, tmag: tuple[float, float], max_teff: float) -> list[dict]:
    return [{"paramName": "Tmag", "values": [{"min": tmag[0], "max": tmag[1]}]},
            {"paramName": "Teff", "values": [{"min": 1000, "max": max_teff}]},
            {"paramName": "lumclass", "values": ["DWARF"]},
            {"paramName": "objType", "values": ["STAR"]},
            {"paramName": "dec", "values": [{"min": dec_lo, "max": dec_hi}]}]


def strip(dec_lo: float, dec_hi: float, tmag: tuple[float, float] = (13.0, 16.0), max_teff: float = 4000.0,
          refresh: bool = False) -> list[dict]:
    """Every selected TIC star with dec_lo <= Dec < dec_hi (cached for good)."""
    def compute() -> list[dict]:
        params = {"columns": COLUMNS, "filters": _filters(dec_lo, dec_hi, tmag, max_teff)}
        first = _invoke("Mast.Catalogs.Filtered.Tic.Rows", params)
        rows = list(first["data"])
        for page in range(2, int(first["paging"]["pagesFiltered"]) + 1):
            rows += _invoke("Mast.Catalogs.Filtered.Tic.Rows", params, page)["data"]
        out = []
        for r in rows:
            d = row(r)
            # the service's max is inclusive; keep strips disjoint
            if d["dec"] is not None and dec_lo <= d["dec"] < dec_hi and d["disposition"] not in BAD_DISPOSITIONS:
                out.append(d)
        return out
    key = f"tic-strips/t{tmag[0]:.1f}-{tmag[1]:.1f}_teff{max_teff:.0f}/{dec_lo:+06.1f}_{dec_hi:+06.1f}"
    return cached_json(key, FOREVER, compute, refresh)


def sky(step_deg: float = 1.0, workers: int = 6, log: Callable[[str], None] = print, **kw) -> list[dict]:
    """The selection over the whole sky, strip by strip (resumable: finished strips are cached)."""
    edges = [-90.0 + i * step_deg for i in range(int(round(180 / step_deg)) + 1)]
    bands = list(zip(edges[:-1], edges[1:]))
    bands[-1] = (bands[-1][0], 90.0001)
    done = [0]

    def one(b):
        rows = strip(b[0], b[1], **kw)
        done[0] += 1
        if done[0] % 10 == 0 or done[0] == len(bands):
            log(f"TIC strips {done[0]}/{len(bands)}")
        return rows

    with ThreadPoolExecutor(workers) as pool:
        parts = list(pool.map(one, bands))
    return [r for p in parts for r in p]


def star(tic: int, refresh: bool = False) -> dict:
    """One star's TIC row (cached 30 days)."""
    def compute() -> dict:
        d = _invoke("Mast.Catalogs.Filtered.Tic.Rows",
                    {"columns": COLUMNS, "filters": [{"paramName": "ID", "values": [int(tic)]}]}, pagesize=5)
        if not d["data"]:
            raise LookupError(f"TIC {tic} is not in the TESS Input Catalog")
        return row(d["data"][0])
    return cached_json(f"tic/{int(tic)}", 30 * DAY, compute, refresh)
