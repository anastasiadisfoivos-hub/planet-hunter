"""TIC 8.2 row for the target (MAST), cached."""

from __future__ import annotations

import math

from . import cache

COLUMNS = ("ID", "ra", "dec", "pmRA", "pmDEC", "Tmag", "GAIAmag", "GAIA", "Teff", "e_Teff", "logg", "e_logg",
           "rad", "e_rad", "mass", "e_mass", "rho", "e_rho", "lumclass", "contratio", "plx", "d")


def row(tic: int) -> dict:
    def fetch() -> dict:
        from astroquery.mast import Catalogs

        tab = Catalogs.query_criteria(catalog="Tic", ID=int(tic))
        if len(tab) == 0:
            raise LookupError(f"TIC {tic} not found at MAST")
        r = tab[0]
        return {c: _plain(r[c]) for c in COLUMNS if c in tab.colnames}

    return cache.cached("tic", str(int(tic)), fetch)


def _plain(v):
    try:
        if hasattr(v, "mask") and v.mask:
            return None
    except Exception:
        pass
    if isinstance(v, bytes):
        v = v.decode()
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, str):
        return v.strip() or None
    return v


def by_gaia(source_id: str) -> str | None:
    """TIC ID of a Gaia source (TIC 8.2 carries Gaia DR2 ids, which equal DR3 ids for almost all stars)."""

    def fetch() -> dict:
        from astroquery.mast import Catalogs

        tab = Catalogs.query_criteria(catalog="Tic", GAIA=str(source_id))
        return {"tic": str(tab[0]["ID"]) if len(tab) else None}

    return cache.cached("tic-by-gaia", str(source_id), fetch)["tic"]
