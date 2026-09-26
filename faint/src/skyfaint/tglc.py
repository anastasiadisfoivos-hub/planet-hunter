"""TGLC light curves (TESS-Gaia Light Curves, Han & Brandt 2023): every published sector for one star, quality-flagged,
normalised per sector and stitched, in the shape hunt/ searches.

Where the files are. TGLC names files by Gaia DR3 source id, sector, camera and CCD:

    https://archive.stsci.edu/hlsps/tglc/s<SSSS>/cam<C>-ccd<D>/<id // 1e5 as 16 digits, in 4-digit groups>/
        hlsp_tglc_tess_ffi_gaiaid-<id>-s<SSSS>-cam<C>-ccd<D>_tess_v1_llc.fits

Sectors 1-55 are published (1-11 are also in the MAST API; 12-55 only at these URLs). resolve() finds the star's
Gaia DR3 id (Gaia archive: dr2_neighbourhood from the TIC's DR2 id), predicts sector / camera / CCD with
tess-point, and HEAD-checks each URL (then the other CCDs of the same camera, for stars near a CCD edge). Every
downloaded file's TICID header must match the star. All of this is free, anonymous public access.

What is kept (read_sector()):
  flux       cal_aper_flux (default) or cal_psf_flux: TGLC's decontaminated flux, already divided by a 1-day
             wotan biweight trend by the TGLC team; normalised again to median 1 per sector. If the calibrated
             column is unusable (TGLC's known issue for very faint primary-mission stars near variables: fewer
             than half the cadences finite and positive) the raw aperture / PSF flux / median is used instead,
             and the product says so.
  flux_err   TGLC's per-sector calibrated error (CAPE_ERR or CPSF_ERR header), constant within a sector
  quality    dropped: TESS_flags & 17087 (lightkurve's default bitmask), TGLC_flags != 0, non-finite or
             non-positive flux.
             Optional scattered-light cut (max_bkg_z, off by default): also drop cadences whose background is more
             than max_bkg_z robust sigma above the sector median. TGLC over-subtracts a fast-rising background,
             which leaves dips of several percent in faint stars (TOI-1680, S52: 9% for hours), and a cut at 3
             removes about half of the >4-sigma low points. It is off because it leaves the shoulders of each
             event next to a new gap, where detrending cannot follow them: on TOI-5688 it made sector 51's
             strongest false peak 2.7x stronger and hunt's SDE for the planet fell from 10.1 to 5.6. Searches
             should instead use `bkg` to veto dips (DEEPHUNT's background check does). Times of momentum dumps (TESS bit 32) and of other dropped cadences are kept in
             `dumps` / `flagged` for hunt's momentum_dump check.
  bkg        TGLC background, per sector as (b - median) / robust sigma, as DEEPHUNT's StarLC has it.

Downloads are cached under <cache>/tglc/ for good (TGLC files do not change); the per-star file index for 90 days.
"""

from __future__ import annotations

import json
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import numpy as np
import requests

from . import coverage, tic as ticmod
from .cache import DAY, FOREVER, cache_dir, cached_json, retry

BASE = "https://archive.stsci.edu/hlsps/tglc"
GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
MOMENTUM_DUMP_BIT = 32
DEFAULT_BITMASK = 17087  # lightkurve TessQualityFlags.DEFAULT_BITMASK, as hunt uses
FLUX_COLUMNS = {"aper": ("cal_aper_flux", "aperture_flux", "CAPE_ERR"),
                "psf": ("cal_psf_flux", "psf_flux", "CPSF_ERR")}
MIN_GOOD_FRACTION = 0.5
MIN_POINTS = 100
MAX_BKG_Z = None  # scattered-light cut off by default (see module docstring)
INDEX_TTL = 90 * DAY
HTTP_TIMEOUT = 120


def url_for(gaia_dr3: int | str, sector: int, camera: int, ccd: int) -> str:
    gid = int(gaia_dr3)
    p = f"{gid // 100_000:016d}"
    path = "/".join(p[i:i + 4] for i in range(0, 16, 4))
    return (f"{BASE}/s{sector:04d}/cam{camera}-ccd{ccd}/{path}/"
            f"hlsp_tglc_tess_ffi_gaiaid-{gid}-s{sector:04d}-cam{camera}-ccd{ccd}_tess_v1_llc.fits")


def gaia_dr3_id(gaia_dr2: str | None, refresh: bool = False) -> tuple[str | None, str]:
    """(Gaia DR3 source id, how it was found) for a TIC star's Gaia DR2 id. Cached for good."""
    if not gaia_dr2:
        return None, "no Gaia id in the TIC"

    def compute() -> dict:
        q = ("SELECT dr3_source_id, angular_distance, magnitude_difference FROM gaiadr3.dr2_neighbourhood "
             f"WHERE dr2_source_id = {int(gaia_dr2)} ORDER BY angular_distance ASC")

        def call() -> str:
            r = requests.post(GAIA_TAP, data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": q},
                              timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            return r.text
        lines = [ln for ln in retry(call).strip().splitlines()[1:] if ln.strip()]
        if not lines:
            return {"dr3": None}
        # prefer the same number (the usual case), else the closest match
        ids = [ln.split(",")[0] for ln in lines]
        return {"dr3": str(gaia_dr2) if str(gaia_dr2) in ids else ids[0], "n": len(ids)}
    try:
        d = cached_json(f"gaia-dr3/{gaia_dr2}", FOREVER, compute, refresh)
    except Exception as e:  # Gaia archive down: the DR2 id is the DR3 id for most stars; the TICID check guards it
        return str(gaia_dr2), f"Gaia archive unreachable ({type(e).__name__}); assumed DR3 id = DR2 id"
    if d["dr3"] is None:
        return str(gaia_dr2), "no DR3 match listed for the DR2 id; tried the DR2 id"
    return d["dr3"], "DR3 id = DR2 id" if d["dr3"] == str(gaia_dr2) else "DR3 id from Gaia dr2_neighbourhood"


def _exists(url: str) -> int | None:
    """Content length if the file exists, None if it does not (404). Other errors raise."""
    def call():
        r = requests.head(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return int(r.headers.get("content-length") or 0)
    return retry(call)


def resolve(tic: int, refresh: bool = False) -> dict:
    """Every published TGLC file for this star: {tic, gaia_dr3, gaia_note, predicted_sectors, files: [...]}."""
    def compute() -> dict:
        star = ticmod.star(tic)
        gid, note = gaia_dr3_id(star["gaia_dr2"])
        pts = coverage.pointings([star["ra"]], [star["dec"]])[0]
        files = []
        if gid:
            def one(p):
                s, cam, ccd = p
                for c in [ccd] + [x for x in (1, 2, 3, 4) if x != ccd]:
                    u = url_for(gid, s, cam, c)
                    size = _exists(u)
                    if size is not None:
                        return {"sector": s, "camera": cam, "ccd": c, "url": u, "bytes": size}
                return None
            with ThreadPoolExecutor(8) as pool:
                files = [f for f in pool.map(one, pts) if f]
        return {"tic": int(tic), "gaia_dr3": gid, "gaia_note": note,
                "predicted_sectors": [p[0] for p in pts], "files": files,
                "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return cached_json(f"tglc-index/{int(tic)}", INDEX_TTL, compute, refresh)


def download(f: dict) -> Path:
    path = cache_dir() / "tglc" / f"s{f['sector']:04d}" / f["url"].rsplit("/", 1)[1]
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)

    def call() -> None:
        r = requests.get(f["url"], timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(r.content)
        tmp.replace(path)
    retry(call)
    return path


def _float(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _robust_sigma(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if len(x) else float("nan")


@dataclass
class Sector:
    sector: int
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    bkg: np.ndarray
    dumps: np.ndarray
    flagged: np.ndarray
    product: dict


def read_sector(path: Path, tic: int, flux: str = "aper", max_bkg_z: float | None = MAX_BKG_Z) -> Sector | None:
    """One TGLC file -> quality-masked, median-normalised arrays. None if too few good points."""
    from astropy.io import fits

    cal_col, raw_col, err_key = FLUX_COLUMNS[flux]
    with fits.open(path, memmap=False) as hdul:
        h0, h1, d = hdul[0].header, hdul[1].header, hdul[1].data
        if str(h0.get("TICID", "")).strip() not in ("", str(int(tic))):
            raise ValueError(f"{path.name}: TICID {h0.get('TICID')} is not TIC {tic}")
        t = np.asarray(d["time"], float)
        cal = np.asarray(d[cal_col], float)
        raw = np.asarray(d[raw_col], float)
        bkg = np.asarray(d["background"], float)
        tq = np.asarray(d["TESS_flags"], np.int64)
        gq = np.asarray(d["TGLC_flags"], np.int64)
        err_rel = _float(h1.get(err_key))
        exptime = float(h1.get("XPTIME") or round(float(h1.get("TIMEDEL", 0)) * 86400))
        sector, camera, ccd = int(h0["SECTOR"]), int(h0["CAMERA"]), int(h0["CCD"])
        head = {"tessmag_tglc": h0.get("TESSMAG"), "gaia_dr3": str(h0.get("GAIADR3")), "near_edge": bool(h1.get("NEAREDGE"))}

    finite_t = np.isfinite(t)
    bad_q = ((tq & DEFAULT_BITMASK) > 0) | (gq != 0)
    n_scattered = 0
    if max_bkg_z is not None:
        ref = finite_t & ~bad_q & np.isfinite(bkg)
        if ref.sum() > 20:
            z = (bkg - np.median(bkg[ref])) / (_robust_sigma(bkg[ref]) or 1.0)
            high = finite_t & ~bad_q & np.isfinite(z) & (z > max_bkg_z)
            n_scattered = int(high.sum())
            bad_q = bad_q | high
    dumps = t[finite_t & ((tq & MOMENTUM_DUMP_BIT) > 0)]
    flagged = t[finite_t & bad_q & ((tq & MOMENTUM_DUMP_BIT) == 0)]
    base = finite_t & ~bad_q
    column, note = cal_col, "TGLC calibrated flux (1-day biweight-detrended by TGLC)"
    ok = base & np.isfinite(cal) & (cal > 0)
    if ok.sum() < MIN_GOOD_FRACTION * base.sum():
        column, note = raw_col, f"{cal_col} unusable ({ok.sum()} of {base.sum()} good cadences); raw {raw_col} / median"
        ok = base & np.isfinite(raw) & (raw > 0)
        f = raw
    else:
        f = cal
    n_total = int(finite_t.sum())
    if ok.sum() < MIN_POINTS:
        return None
    med = float(np.median(f[ok]))
    fn = f[ok] / med
    if column == cal_col and err_rel is not None and err_rel > 0:
        e = np.full(ok.sum(), err_rel / med)
    else:  # point-to-point scatter as the error
        e = np.full(ok.sum(), float(np.median(np.abs(np.diff(fn)))) * 1.4826 / np.sqrt(2))
    b = bkg[ok]
    s = _robust_sigma(b)
    bn = (b - np.nanmedian(b)) / (s if s and np.isfinite(s) and s > 0 else 1.0)
    product = {"sector": sector, "author": "TGLC", "exptime": exptime, "camera": camera, "ccd": ccd,
               "filename": path.name, "flux_column": column, "flux_note": note,
               "n_good": int(ok.sum()), "n_total": n_total, "n_scattered_light": n_scattered, **head}
    return Sector(sector, t[ok], fn, e, bn, np.sort(dumps), np.sort(flagged), product)


@dataclass
class FaintLC:
    """Same fields, names, units and conventions as hunt.lightcurve.StarLC (hunt and DEEPHUNT branches).

    time      BTJD (BJD - 2457000, TDB), sorted, float64
    flux      normalised to median 1 in each sector
    flux_err  same units as flux
    sector    TESS sector number of each point (int)
    products  one dict per sector used: sector, author "TGLC", exptime (s), camera, ccd, filename, flux_column, ...
    dumps     BTJD of momentum-dump cadences (removed from time/flux)
    flagged   BTJD of other removed cadences (quality flags and the scattered-light cut)
    quality_read  True: every file's quality columns were read
    bkg       background per point, per sector (b - median) / robust sigma
    bin_minutes   None (native TGLC cadence: 30 min in sectors 1-26, 10 min in 27-55)
    """

    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    sector: np.ndarray
    products: list[dict] = field(default_factory=list)
    dumps: np.ndarray = field(default_factory=lambda: np.array([]))
    flagged: np.ndarray = field(default_factory=lambda: np.array([]))
    quality_read: bool = True
    bkg: np.ndarray | None = None
    bin_minutes: float | None = None
    meta: dict = field(default_factory=dict)  # tic, gaia id, sectors predicted / published / used, download stats

    @property
    def sectors(self) -> list[int]:
        return sorted({int(p["sector"]) for p in self.products})

    def to_hunt(self):
        """The same data as a hunt.lightcurve.StarLC (whichever hunt branch is installed: fields it lacks are
        left out)."""
        from hunt.lightcurve import StarLC

        names = {f.name for f in fields(StarLC)}
        return StarLC(**{k: getattr(self, k) for k in names if hasattr(self, k)})

    def save(self, path: Path) -> None:
        np.savez_compressed(path, time=self.time, flux=self.flux.astype(np.float32),
                            flux_err=self.flux_err.astype(np.float32), sector=self.sector.astype(np.int16),
                            dumps=self.dumps, flagged=self.flagged,
                            bkg=(self.bkg if self.bkg is not None else np.full(len(self.time), np.nan)).astype(np.float32),
                            meta=json.dumps({"products": self.products, "quality_read": self.quality_read,
                                             "bin_minutes": self.bin_minutes, "meta": self.meta}))

    @classmethod
    def load(cls, path: Path) -> FaintLC:
        d = np.load(path)
        m = json.loads(str(d["meta"]))
        return cls(d["time"].astype(float), d["flux"].astype(float), d["flux_err"].astype(float),
                   d["sector"].astype(int), m["products"], d["dumps"], d["flagged"], m["quality_read"],
                   d["bkg"].astype(float), m["bin_minutes"], m["meta"])


def stitch(parts: list[Sector], meta: dict | None = None) -> FaintLC:
    if not parts:
        raise LookupError("no usable TGLC sector")
    parts = sorted(parts, key=lambda p: p.sector)
    cat = np.concatenate
    t = cat([p.time for p in parts])
    order = np.argsort(t, kind="stable")
    return FaintLC(t[order], cat([p.flux for p in parts])[order], cat([p.flux_err for p in parts])[order],
                   cat([np.full(len(p.time), p.sector) for p in parts])[order], [p.product for p in parts],
                   np.sort(cat([p.dumps for p in parts])), np.sort(cat([p.flagged for p in parts])), True,
                   cat([p.bkg for p in parts])[order], None, meta or {})


def get_lightcurves(tic: int, flux: str = "aper", sectors: list[int] | None = None, refresh: bool = False,
                    max_bkg_z: float | None = MAX_BKG_Z) -> FaintLC:
    """Every TGLC sector for this star, quality-flagged, normalised per sector and stitched (see FaintLC).

    flux: "aper" (cal_aper_flux, default) or "psf" (cal_psf_flux). sectors: restrict to these (default: all).
    max_bkg_z: scattered-light cut (None keeps every cadence the quality flags allow).
    Raises LookupError when the star has no usable TGLC light curve."""
    t0 = time.time()
    index = resolve(tic, refresh)
    files = [f for f in index["files"] if sectors is None or f["sector"] in sectors]
    t_resolve = time.time() - t0

    def one(f):
        cached = (cache_dir() / "tglc" / f"s{f['sector']:04d}" / f["url"].rsplit("/", 1)[1]).exists()
        return download(f), cached

    t1 = time.time()
    with ThreadPoolExecutor(8) as pool:
        got = list(pool.map(one, files))
    t_download = time.time() - t1
    parts, skipped = [], []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for (path, _), f in zip(got, files):
            sec = read_sector(path, tic, flux, max_bkg_z)
            if sec is None:
                skipped.append(f["sector"])
            else:
                parts.append(sec)
    if not parts:
        raise LookupError(f"TIC {tic}: no usable TGLC light curve (predicted sectors {index['predicted_sectors']}, "
                          f"published {[f['sector'] for f in index['files']]})")
    meta = {"tic": int(tic), "gaia_dr3": index["gaia_dr3"], "gaia_note": index["gaia_note"], "flux": flux,
            "max_bkg_z": max_bkg_z,
            "sectors_predicted": index["predicted_sectors"], "sectors_published": [f["sector"] for f in index["files"]],
            "sectors_too_few_points": skipped,
            "download": {"files": len(files), "bytes": int(sum(f["bytes"] for f in files)),
                         "from_cache": int(sum(c for _, c in got)), "resolve_s": round(t_resolve, 2),
                         "download_s": round(t_download, 2), "total_s": round(time.time() - t0, 2)}}
    return stitch(parts, meta)


def as_dict(lc: FaintLC) -> dict:
    return {k: v for k, v in asdict(lc).items() if not isinstance(v, np.ndarray)}
