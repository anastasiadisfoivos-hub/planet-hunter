"""Light curves: the pipeline's fetch, plus the cadences it drops (quality flags, momentum dumps).

hunter.fetch reads each file with lightkurve's default quality mask, so flagged cadences simply vanish. The
extra checks need to know where they were, so the same cached FITS files are re-read here for TIME/QUALITY.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from hunter import fetch as hfetch
from hunter.cache import fits_dir

MOMENTUM_DUMP_BIT = 32  # "Desaturation event" (reaction-wheel momentum dump) in SPOC and QLP files
DEFAULT_BITMASK = 17087  # lightkurve TessQualityFlags.DEFAULT_BITMASK


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

    @property
    def sectors(self) -> list[int]:
        return sorted({int(p["sector"]) for p in self.products})

    def save(self, path: Path, **meta) -> None:
        np.savez_compressed(path, time=self.time, flux=self.flux.astype(np.float32),
                            flux_err=self.flux_err.astype(np.float32), sector=self.sector.astype(np.int16),
                            dumps=self.dumps, flagged=self.flagged,
                            meta=json.dumps({"products": self.products, "quality_read": self.quality_read, **meta}))

    @classmethod
    def load(cls, path: Path) -> tuple[StarLC, dict]:
        d = np.load(path)
        meta = json.loads(str(d["meta"]))
        lc = cls(d["time"].astype(float), d["flux"].astype(float), d["flux_err"].astype(float),
                 d["sector"].astype(int), meta.pop("products"), d["dumps"], d["flagged"], meta.pop("quality_read"))
        return lc, meta


def _flag_times(product: dict) -> tuple[np.ndarray, np.ndarray]:
    from astropy.io import fits

    path = fits_dir() / product["filename"]
    with fits.open(path, memmap=False) as hdul:
        data = hdul[1].data
        t = np.asarray(data["TIME"], float)
        names = [c.upper() for c in data.columns.names]
        q = np.asarray(data["QUALITY"] if "QUALITY" in names else np.zeros(len(t)), dtype=np.int64)
    ok = np.isfinite(t)
    t, q = t[ok], q[ok]
    dumps = t[(q & MOMENTUM_DUMP_BIT) > 0]
    flagged = t[((q & DEFAULT_BITMASK) > 0) & ((q & MOMENTUM_DUMP_BIT) == 0)]
    return dumps, flagged


def fetch(tic: int, max_sectors: int = 3, refresh: bool = False) -> StarLC:
    lc = hfetch.fetch(int(tic), max_sectors=max_sectors, refresh=refresh)
    dumps, flagged, read_all = [], [], True
    for p in lc.products:
        try:
            d, f = _flag_times(p)
        except Exception:  # unreadable QUALITY: the dump check then reports that it could not fully run
            read_all = False
            continue
        dumps.append(d)
        flagged.append(f)
    cat = (lambda xs: np.sort(np.concatenate(xs)) if xs else np.array([]))
    return StarLC(lc.time, lc.flux, lc.flux_err, lc.sector, lc.products, cat(dumps), cat(flagged), read_all)
