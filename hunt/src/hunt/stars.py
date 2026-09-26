"""Stellar parameters from TIC 8.2: in bulk (CDS xMatch by position, then TIC-ID equality) and per star (MAST)."""

from __future__ import annotations

import csv
import hashlib
import io
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, fields

import requests

from hunter.cache import retry

from .cache import DAY, cached_json

XMATCH_URL = "http://cdsxmatch.u-strasbg.fr/xmatch/api/v1/sync"
TIC_VIZIER = "vizier:IV/39/tic82"
XMATCH_CHUNK = 50_000
RHO_SUN_KG_M3 = 1408.0


@dataclass
class Star:
    tic: int
    ra: float
    dec: float
    tmag: float | None = None
    teff: float | None = None
    logg: float | None = None
    rad: float | None = None
    rad_err: float | None = None
    mass: float | None = None
    rho: float | None = None  # solar units
    lumclass: str | None = None
    contratio: float | None = None

    def density_solar(self) -> tuple[float | None, str]:
        """Stellar density in solar units and where it came from."""
        if self.rho and self.rho > 0:
            return self.rho, "TIC density"
        if self.rad and self.mass and self.rad > 0 and self.mass > 0:
            return self.mass / self.rad**3, "TIC mass and radius"
        if self.rad and self.rad > 0 and (self.lumclass or "DWARF") == "DWARF" and self.rad < 1.5:
            return 1.0 / self.rad**2, "TIC radius with a main-sequence mass (M = R) assumed"
        return None, "no radius in the TIC"

    @property
    def is_m_dwarf(self) -> bool:
        return self.teff is not None and self.teff < 4000 and (self.lumclass or "DWARF") == "DWARF"

    def to_row(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> Star:
        kw = {}
        for f in fields(cls):
            v = row.get(f.name)
            if v in (None, "", "None", "nan"):
                kw[f.name] = None
            elif f.name == "tic":
                kw[f.name] = int(float(v))
            elif f.name == "lumclass":
                kw[f.name] = str(v).strip() or None
            else:
                x = float(v)
                kw[f.name] = x if math.isfinite(x) else None
        return cls(**kw)


def _num(x) -> float | None:
    try:
        v = float(str(x).strip())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


XMATCH_COLS = {"TIC": "tic", "RAJ2000": "ra", "DEJ2000": "dec", "Tmag": "tmag", "Teff": "teff", "logg": "logg",
               "Rad": "rad", "s_Rad": "rad_err", "Mass": "mass", "rho": "rho", "LClass": "lumclass",
               "Rcont": "contratio"}


def _xmatch_chunk(rows: list[tuple[int, float, float]], max_tmag: float) -> list[dict]:
    body = "tic,ra,dec\n" + "".join(f"{t},{r:.7f},{d:.7f}\n" for t, r, d in rows)

    def call() -> str:
        r = requests.post(XMATCH_URL, timeout=900, data={
            "request": "xmatch", "distMaxArcsec": 2, "selection": "all", "RESPONSEFORMAT": "csv",
            "cat2": TIC_VIZIER, "colRA1": "ra", "colDec1": "dec"}, files={"cat1": ("cat1.csv", body)})
        r.raise_for_status()
        return r.text

    out = []
    for rec in csv.DictReader(io.StringIO(retry(call))):
        if rec.get("tic") != rec.get("TIC"):  # keep the TIC row of the star itself, not a neighbour
            continue
        tmag = _num(rec.get("Tmag"))
        if tmag is None or tmag > max_tmag:
            continue
        star = {dst: rec.get(src) for src, dst in XMATCH_COLS.items()}
        star["lumclass"] = (star["lumclass"] or "").strip() or None
        out.append(star)
    return out


def bulk(rows: list[tuple[int, float, float]], max_tmag: float, label: str, workers: int = 4) -> list[Star]:
    """TIC parameters for many (tic, ra, dec) rows, keeping stars with Tmag <= max_tmag. Cached for good per chunk."""
    chunks = [rows[i:i + XMATCH_CHUNK] for i in range(0, len(rows), XMATCH_CHUNK)]

    def one(chunk) -> list[dict]:
        key = hashlib.sha1(("%s|%.2f|" % (label, max_tmag) + ",".join(str(r[0]) for r in chunk)).encode()).hexdigest()
        return cached_json(f"xmatch/{key[:20]}", 3650 * DAY, lambda: _xmatch_chunk(chunk, max_tmag))

    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(one, chunks))
    return [Star.from_row(r) for part in results for r in part]


def _mast_star(tic: int) -> dict:
    from astroquery.mast import Catalogs

    t = retry(lambda: Catalogs.query_criteria(catalog="Tic", ID=int(tic)))
    if len(t) == 0:
        raise LookupError(f"TIC {tic} is not in the TESS Input Catalog")
    r = t[0]
    return {"tic": int(r["ID"]), "ra": float(r["ra"]), "dec": float(r["dec"]), "tmag": _num(r["Tmag"]),
            "teff": _num(r["Teff"]), "logg": _num(r["logg"]), "rad": _num(r["rad"]), "rad_err": _num(r["e_rad"]),
            "mass": _num(r["mass"]), "rho": _num(r["rho"]), "lumclass": str(r["lumclass"] or "").strip() or None,
            "contratio": _num(r["contratio"])}


def star(tic: int, refresh: bool = False) -> Star:
    """One star's TIC row via MAST (cached 30 days)."""
    return Star.from_row(cached_json(f"tic/{int(tic)}", 30 * DAY, lambda: _mast_star(tic), refresh))

