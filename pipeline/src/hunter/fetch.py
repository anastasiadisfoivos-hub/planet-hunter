"""Find and download TESS light curves: SPOC 2-min PDCSAP first, then TESS-SPOC, then QLP."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .cache import DAY, cached_json, fits_dir, retry

AUTHORS = ("SPOC", "TESS-SPOC", "QLP")
SEARCH_TTL_S = 0.25 * DAY  # new sectors appear every ~27 days; a few hours of staleness is fine


@dataclass
class LightCurveData:
    """Normalised light curve, concatenated over sectors. Time is BTJD (BJD - 2457000, TDB)."""

    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    sector: np.ndarray
    products: list[dict] = field(default_factory=list)

    @property
    def sectors(self) -> list[int]:
        return sorted({p["sector"] for p in self.products})


def _rank(row: dict) -> tuple[int, float]:
    """Lower is better: SPOC 2-min, then TESS-SPOC, then QLP; shorter cadence within an author."""
    if row["author"] == "SPOC":
        return (0, 0.0) if row["exptime"] == 120 else (9, row["exptime"])  # 20-s "fast" not wanted
    return (AUTHORS.index(row["author"]), row["exptime"])


def _search_rows(tic_id: int) -> list[dict]:
    import lightkurve as lk

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = retry(lambda: lk.search_lightcurve(f"TIC {tic_id}", mission="TESS", author=list(AUTHORS)))
    rows = []
    for r in result.table:
        # Guard against neighbours returned by the cone search.
        if str(r["target_name"]).lstrip("0") != str(tic_id):
            continue
        rows.append(
            {
                "sector": int(r["sequence_number"]),
                "author": str(r["author"]),
                "exptime": float(r["exptime"]),
                "uri": str(r["dataURI"]),
                "filename": str(r["productFilename"]),
            }
        )
    return rows


def search_products(tic_id: int, refresh: bool = False) -> list[dict]:
    """All usable light-curve products for this star (a MAST query, no downloads). Cached for a few hours."""
    return cached_json("lc-search", str(tic_id), SEARCH_TTL_S, lambda: _search_rows(tic_id), refresh)


def latest_data_marker(tic_id: int, refresh: bool = False) -> str | None:
    """Newest TESS sector with a usable light curve for this star, e.g. "sector-74"; None if there is none.

    Queries MAST's product listing only; no light curves are downloaded. Network errors raise.
    """
    rows = search_products(int(tic_id), refresh)
    usable = [r for r in rows if _rank(r)[0] < 9]
    return f"sector-{max(r['sector'] for r in usable)}" if usable else None


def choose_products(rows: list[dict], max_sectors: int) -> list[dict]:
    """Best product per sector, then prefer better products, then newer sectors, up to max_sectors."""
    best: dict[int, dict] = {}
    for row in rows:
        if _rank(row)[0] >= 9:
            continue
        if row["sector"] not in best or _rank(row) < _rank(best[row["sector"]]):
            best[row["sector"]] = row
    ordered = sorted(best.values(), key=lambda r: (_rank(r)[0], -r["sector"]))
    return sorted(ordered[:max_sectors], key=lambda r: r["sector"])


def _download(row: dict) -> Path:
    from astroquery.mast import Observations

    path = fits_dir() / row["filename"]
    if not path.exists() or path.stat().st_size == 0:
        tmp = path.with_suffix(".part")
        status, message, _ = retry(lambda: Observations.download_file(row["uri"], local_path=str(tmp), cache=False))
        if status != "COMPLETE":
            raise OSError(f"MAST download failed for {row['filename']}: {message}")
        tmp.replace(path)
    return path


def _read(path: Path, author: str):
    import lightkurve as lk

    # QLP files have no PDCSAP column; their default (sap_flux) is QLP's own systematics-corrected flux.
    kwargs = {"flux_column": "pdcsap_flux"} if author in ("SPOC", "TESS-SPOC") else {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return lk.read(str(path), quality_bitmask="default", **kwargs)


def fetch(tic_id: int, max_sectors: int = 2, refresh: bool = False) -> LightCurveData:
    rows = search_products(tic_id, refresh)
    chosen = choose_products(rows, max_sectors)
    if not chosen:
        raise LookupError(f"no SPOC, TESS-SPOC or QLP light curve found for TIC {tic_id}")

    times, fluxes, errs, sectors, products = [], [], [], [], []
    for row in chosen:
        lc = _read(_download(row), row["author"])
        t = np.asarray(lc.time.value, dtype=float)
        f = np.asarray(lc.flux.value, dtype=float)
        e = np.asarray(lc.flux_err.value, dtype=float)
        good = np.isfinite(t) & np.isfinite(f) & (f > 0)
        e = np.where(np.isfinite(e), e, np.nan)
        t, f, e = t[good], f[good], e[good]
        if len(t) < 100:
            continue
        median = np.median(f)
        times.append(t)
        fluxes.append(f / median)
        errs.append(e / median)
        sectors.append(np.full(len(t), row["sector"]))
        products.append({**row, "flux_column": "pdcsap_flux" if row["author"] != "QLP" else "sap_flux"})

    if not times:
        raise LookupError(f"TIC {tic_id}: downloaded light curves had no usable points")
    order = np.argsort(np.concatenate(times))
    err = np.concatenate(errs)[order]
    flux = np.concatenate(fluxes)[order]
    if not np.all(np.isfinite(err)):
        err = np.where(np.isfinite(err), err, np.nanmedian(np.abs(np.diff(flux))) / np.sqrt(2))
    return LightCurveData(np.concatenate(times)[order], flux, err, np.concatenate(sectors)[order], products)
