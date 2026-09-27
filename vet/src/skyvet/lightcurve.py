"""TESS light curve for a candidate: MAST products via lightkurve, cached per sector as plain arrays.

Product choice per sector: SPOC 2-min (PDCSAP) > TESS-SPOC FFI (PDCSAP) > QLP FFI (KSPSAP). The newest
`max_sectors` sectors are used, limited to the candidate's own `sectors` when it lists them. Cadences flagged by
the default lightkurve quality bitmask and NaNs are dropped; each sector is normalised to its median.

Detrending (for LEO-vetter and TRICERATOPS): lightkurve's Savitzky-Golay `flatten` per sector, with the
candidate's transits (±1 duration around each mid-time) masked out of the trend.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import cache

AUTHOR_RANK = {("SPOC", 120): 0, ("TESS-SPOC", None): 1, ("QLP", None): 2}


@dataclass
class LightCurve:
    tic: int
    time: np.ndarray  # BTJD
    raw: np.ndarray  # normalised, not detrended
    flux: np.ndarray  # detrended
    flux_err: np.ndarray
    sector: np.ndarray
    products: list[dict] = field(default_factory=list)
    apertures: dict[int, list] = field(default_factory=dict)  # sector -> [[col, row], ...] (SPOC / TESS-SPOC)

    @property
    def sectors(self) -> list[int]:
        return sorted({int(p["sector"]) for p in self.products})

    @property
    def cadence_days(self) -> float:
        return float(np.nanmedian(np.diff(self.time)))


def products(tic: int) -> list[dict]:
    """Every TESS light-curve product for the star that we know how to use: [{sector, author, exptime}]."""

    def fetch() -> list[dict]:
        import lightkurve as lk

        res = lk.search_lightcurve(f"TIC {int(tic)}", mission="TESS")
        out = []
        for row in res.table:
            author, exptime = str(row["author"]), float(row["exptime"])
            try:  # MAST's sequence_number is the sector; multi-sector products have none
                sector = int(row["sequence_number"])
            except (TypeError, ValueError, np.ma.MaskError):
                continue
            if _rank(author, exptime) is None:
                continue
            out.append({"sector": sector, "author": author, "exptime": exptime})
        return out

    return cache.cached("lc-products", str(int(tic)), fetch)


def _rank(author: str, exptime: float) -> int | None:
    if (author, int(round(exptime))) in AUTHOR_RANK:
        return AUTHOR_RANK[(author, int(round(exptime)))]
    return AUTHOR_RANK.get((author, None))


def choose(prods: list[dict], sectors: list[int] | None, max_sectors: int) -> list[dict]:
    best: dict[int, dict] = {}
    for p in prods:
        r = _rank(p["author"], p["exptime"])
        if r is None or (sectors and p["sector"] not in sectors):
            continue
        if p["sector"] not in best or r < _rank(best[p["sector"]]["author"], best[p["sector"]]["exptime"]):
            best[p["sector"]] = p
    return [best[s] for s in sorted(best)[-max_sectors:]]


def sector_data(tic: int, prod: dict) -> dict:
    key = f"{int(tic)}:s{prod['sector']}:{prod['author']}:{int(prod['exptime'])}:v2"

    def fetch() -> dict:
        import lightkurve as lk

        res = lk.search_lightcurve(f"TIC {int(tic)}", mission="TESS", sector=prod["sector"], author=prod["author"],
                                   exptime=prod["exptime"])
        if len(res) == 0:
            raise LookupError(f"no {prod['author']} light curve for TIC {tic} sector {prod['sector']}")
        lc = res[0].download(quality_bitmask="default")
        col = "kspsap_flux" if prod["author"] == "QLP" and "kspsap_flux" in lc.colnames else "pdcsap_flux"
        if col in lc.colnames:
            lc = lc.select_flux(col)
        t = np.asarray(lc.time.value, dtype=float)
        f = np.asarray(lc.flux.value, dtype=float)
        e = np.asarray(lc.flux_err.value, dtype=float)
        ok = np.isfinite(t) & np.isfinite(f) & np.isfinite(e) & (e > 0)
        med = np.nanmedian(f[ok])
        return {"time": t[ok], "flux": (f[ok] / med).astype(np.float32), "flux_err": (e[ok] / med).astype(np.float32),
                "flux_column": col, "aperture": _aperture(lc.meta.get("FILENAME")), **prod}

    return cache.cached("lc", key, fetch, fmt="pickle")


def _aperture(path: str | None) -> list[list[int]] | None:
    """The optimal photometric aperture of a SPOC / TESS-SPOC light-curve file as [[col, row], ...] CCD pixels
    (bit 2 of the APERTURE mask), as TRICERATOPS' get_aperture reads it from the target-pixel file."""
    if not path:
        return None
    from astropy.io import fits

    with fits.open(path) as h:
        if "APERTURE" not in h:
            return None
        a, hdr = h["APERTURE"].data.astype(int), h["APERTURE"].header
        if "CRVAL1P" not in hdr:
            return None
        rows, cols = np.nonzero(a & 2)
        return [[int(c + hdr["CRVAL1P"]), int(r + hdr["CRVAL2P"])] for r, c in zip(rows, cols, strict=True)] or None


def transit_mask(t: np.ndarray, period: float, t0: float, duration_d: float, width: float = 2.0) -> np.ndarray:
    """True within ±(width/2) durations of every predicted mid-time."""
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    return np.abs(phase) < 0.5 * width * duration_d


def fetch(tic: int, period: float, t0: float, duration_d: float, sectors: list[int] | None = None,
          max_sectors: int = 3) -> LightCurve:
    import lightkurve as lk

    chosen = choose(products(tic), sectors, max_sectors)
    if not chosen and sectors:  # the candidate's sectors have no usable product: fall back to any sector
        chosen = choose(products(tic), None, max_sectors)
    if not chosen:
        raise LookupError(f"no SPOC, TESS-SPOC or QLP light curve at MAST for TIC {tic}")
    ts, raws, fs, es, ss = [], [], [], [], []
    apertures: dict[int, list] = {}
    for prod in chosen:
        d = sector_data(tic, prod)
        t, f, e = d["time"], d["flux"].astype(float), d["flux_err"].astype(float)
        cad = float(np.median(np.diff(t)))
        window = max(0.75, 3 * duration_d)  # days; long enough not to eat the transit
        wl = int(window / cad) | 1
        mask = transit_mask(t, period, t0, duration_d)
        flat = lk.LightCurve(time=t, flux=f, flux_err=e).flatten(window_length=wl, polyorder=2, mask=mask)
        ts.append(t)
        raws.append(f)
        fs.append(np.asarray(flat.flux.value, dtype=float))
        es.append(e)
        ss.append(np.full(len(t), prod["sector"]))
        if d.get("aperture"):
            apertures[prod["sector"]] = d["aperture"]
    lc = LightCurve(tic=int(tic), time=np.concatenate(ts), raw=np.concatenate(raws), flux=np.concatenate(fs),
                    flux_err=np.concatenate(es), sector=np.concatenate(ss),
                    products=[{k: p[k] for k in ("sector", "author", "exptime")} for p in chosen], apertures=apertures)
    ok = np.isfinite(lc.flux)
    for name in ("time", "raw", "flux", "flux_err", "sector"):
        setattr(lc, name, getattr(lc, name)[ok])
    return lc
