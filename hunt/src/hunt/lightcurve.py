"""Light curves: the pipeline's fetch, plus what it drops (quality flags, momentum dumps, background), and the
stitched all-sector curve the deep search runs on.

hunter.fetch reads each file with lightkurve's default quality mask, so flagged cadences simply vanish. The
extra checks need to know where they were, and the single-dip search needs the background (SAP_BKG) to spot
scattered light, so the same cached FITS files are re-read here for TIME / QUALITY / SAP_BKG.

Stitching (stitch()): every sector with a light curve, best product per sector (SPOC 2-min, else TESS-SPOC,
else QLP FFI; hunter.fetch.choose_products), each normalised by its own median (hunter.fetch), quality-flagged
cadences dropped (lightkurve "default" bitmask). The curve keeps its native cadence; the searches work on a copy
averaged into BIN_MINUTES bins inside each sector (bin_lc: a 40-sector star is ~150k points instead of ~650k;
cadences already longer than a bin are kept as they are) and measure and vet on the native curve, because
10-min bins smear transits shorter than about an hour. Detrending happens later (hunt.detrend), with a window
matched to the search.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from hunter import fetch as hfetch
from hunter.cache import fits_dir

MOMENTUM_DUMP_BIT = 32  # "Desaturation event" (reaction-wheel momentum dump) in SPOC and QLP files
DEFAULT_BITMASK = 17087  # lightkurve TessQualityFlags.DEFAULT_BITMASK
ALL_SECTORS = 999
BIN_MINUTES = 10.0


@dataclass
class StarLC:
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    sector: np.ndarray
    products: list[dict] = field(default_factory=list)
    dumps: np.ndarray = field(default_factory=lambda: np.array([]))  # BTJD of momentum-dump cadences
    flagged: np.ndarray = field(default_factory=lambda: np.array([]))  # BTJD of other default-masked cadences
    quality_read: bool = True  # False if some file's QUALITY column could not be read
    bkg: np.ndarray | None = None  # SAP_BKG per point, normalised per sector (median 0, robust sigma 1); NaN if missing
    bin_minutes: float | None = None  # None: native cadence

    @property
    def sectors(self) -> list[int]:
        return sorted({int(p["sector"]) for p in self.products})

    def stitch_info(self) -> dict:
        """sectors used, baseline and cadence mix, for the candidate JSON and results."""
        mix: dict[str, list[int]] = {}
        for p in self.products:
            mix.setdefault(f"{p['author']} {int(p['exptime'])} s", []).append(int(p["sector"]))
        return {"sectors_used": self.sectors, "n_sectors": len(self.sectors),
                "baseline_d": round(float(np.ptp(self.time)), 2) if len(self.time) else 0.0,
                "cadence_mix": {k: sorted(v) for k, v in sorted(mix.items())},
                "bin_minutes": self.bin_minutes, "n_points": int(len(self.time)),
                "days_with_data": round(_days_with_data(self.time), 1),
                "background_read": self.bkg is not None and bool(np.isfinite(self.bkg).any())}

    def save(self, path: Path, **meta) -> None:
        extra = {} if self.bkg is None else {"bkg": self.bkg.astype(np.float32)}
        np.savez_compressed(path, time=self.time, flux=self.flux.astype(np.float32),
                            flux_err=self.flux_err.astype(np.float32), sector=self.sector.astype(np.int16),
                            dumps=self.dumps, flagged=self.flagged, **extra,
                            meta=json.dumps({"products": self.products, "quality_read": self.quality_read,
                                             "bin_minutes": self.bin_minutes, **meta}))

    @classmethod
    def load(cls, path: Path) -> tuple[StarLC, dict]:
        d = np.load(path)
        meta = json.loads(str(d["meta"]))
        bkg = d["bkg"].astype(float) if "bkg" in d.files else None
        lc = cls(d["time"].astype(float), d["flux"].astype(float), d["flux_err"].astype(float),
                 d["sector"].astype(int), meta.pop("products"), d["dumps"], d["flagged"], meta.pop("quality_read"),
                 bkg, meta.pop("bin_minutes", None))
        return lc, meta


def _days_with_data(t: np.ndarray, step: float = 0.5) -> float:
    return float(len(np.unique(np.floor(t / step)))) * step if len(t) else 0.0


def _read_extras(product: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """(dump times, flagged times, time, SAP_BKG, header bits) from one cached FITS file."""
    from astropy.io import fits

    path = fits_dir() / product["filename"]
    with fits.open(path, memmap=False) as hdul:
        data = hdul[1].data
        hdr = hdul[0].header
        t = np.asarray(data["TIME"], float)
        names = [c.upper() for c in data.columns.names]
        q = np.asarray(data["QUALITY"] if "QUALITY" in names else np.zeros(len(t)), dtype=np.int64)
        bkg = np.asarray(data["SAP_BKG"], float) if "SAP_BKG" in names else np.full(len(t), np.nan)
        head = {k.lower(): hdr.get(k) for k in ("CAMERA", "CCD") if hdr.get(k) is not None}
    ok = np.isfinite(t)
    t, q, bkg = t[ok], q[ok], bkg[ok]
    dumps = t[(q & MOMENTUM_DUMP_BIT) > 0]
    flagged = t[((q & DEFAULT_BITMASK) > 0) & ((q & MOMENTUM_DUMP_BIT) == 0)]
    return dumps, flagged, t, bkg, head


def _normalise_bkg(b: np.ndarray) -> np.ndarray:
    """Per-sector background in units of its own robust scatter about the median (spikes stand out as >> 1)."""
    from hunter.clean import robust_sigma

    ok = np.isfinite(b)
    if ok.sum() < 20:
        return np.full(len(b), np.nan)
    med = float(np.median(b[ok]))
    s = robust_sigma(b[ok]) or 1.0
    return (b - med) / s


def fetch(tic: int, max_sectors: int = 3, refresh: bool = False) -> StarLC:
    lc = hfetch.fetch(int(tic), max_sectors=max_sectors, refresh=refresh)
    dumps, flagged, read_all = [], [], True
    bkg = np.full(len(lc.time), np.nan)
    products = []
    for p in lc.products:
        try:
            d, f, tb, b, head = _read_extras(p)
        except Exception:  # unreadable file: the dump and background checks then report they could not fully run
            read_all = False
            products.append(p)
            continue
        products.append({**p, **head})
        dumps.append(d)
        flagged.append(f)
        sel = np.flatnonzero(lc.sector == p["sector"])
        if len(sel) and len(tb):
            order = np.argsort(tb)
            tb, b = tb[order], _normalise_bkg(b[order])
            i = np.clip(np.searchsorted(tb, lc.time[sel]), 0, len(tb) - 1)
            j = np.clip(i - 1, 0, len(tb) - 1)
            k = np.where(np.abs(tb[j] - lc.time[sel]) < np.abs(tb[i] - lc.time[sel]), j, i)
            close = np.abs(tb[k] - lc.time[sel]) < 1e-4
            bkg[sel[close]] = b[k[close]]
    cat = (lambda xs: np.sort(np.concatenate(xs)) if xs else np.array([]))
    return StarLC(lc.time, lc.flux, lc.flux_err, lc.sector, products, cat(dumps), cat(flagged), read_all, bkg)


def bin_lc(lc: StarLC, minutes: float = BIN_MINUTES) -> StarLC:
    """Average into `minutes` bins within each sector (flux, error / sqrt(n), background). Sectors whose cadence
    is already >= the bin width are left as they are."""
    width = minutes / 1440
    ts, fs, es, gs, bs = [], [], [], [], []
    has_bkg = lc.bkg is not None
    for s in np.unique(lc.sector):
        m = lc.sector == s
        t, f, e = lc.time[m], lc.flux[m], lc.flux_err[m]
        b = lc.bkg[m] if has_bkg else np.full(m.sum(), np.nan)
        if len(t) < 2 or np.median(np.diff(t)) >= 0.9 * width:
            ts.append(t), fs.append(f), es.append(e), gs.append(np.full(len(t), s)), bs.append(b)
            continue
        key = np.floor((t - t[0]) / width).astype(np.int64)
        _, idx, n = np.unique(key, return_index=True, return_counts=True)
        ts.append(np.add.reduceat(t, idx) / n)
        fs.append(np.add.reduceat(f, idx) / n)
        es.append(np.sqrt(np.add.reduceat(e**2, idx)) / n)
        gs.append(np.full(len(idx), s))
        bfin = np.where(np.isfinite(b), b, 0.0)
        nb = np.add.reduceat(np.isfinite(b).astype(float), idx)
        # A binned background of k samples has scatter ~1/sqrt(k) of one sample; keep it in per-sample units
        # so spikes stay comparable across cadences (the check measures its own local scatter anyway).
        bs.append(np.where(nb > 0, np.add.reduceat(bfin, idx) / np.maximum(nb, 1), np.nan))
    cat = np.concatenate
    t = cat(ts)
    order = np.argsort(t, kind="stable")
    return replace(lc, time=t[order], flux=cat(fs)[order], flux_err=cat(es)[order], sector=cat(gs)[order],
                   bkg=cat(bs)[order] if has_bkg else None, bin_minutes=minutes)


def stitch(tic: int, max_sectors: int = ALL_SECTORS, minutes: float | None = None,
           refresh: bool = False) -> StarLC:
    """Every available sector, normalised per sector, quality-masked; binned to `minutes` if given. The sweep keeps
    the native cadence: the searches bin a copy themselves and measure on the native curve."""
    lc = fetch(tic, max_sectors=max_sectors, refresh=refresh)
    return bin_lc(lc, minutes) if minutes else lc
