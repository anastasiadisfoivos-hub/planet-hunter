"""Find and download TESS pixel data: SPOC 2-min target pixel files where they exist, else TESScut FFI cutouts."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .cache import DAY, cached_json, fits_dir, retry

SEARCH_TTL_S = 0.25 * DAY
CUTOUT_SIZE = 15  # pixels; 15 × 21″ ≈ 5.2′, enough for every neighbour within 2.5′


@dataclass
class PixelSeries:
    """One sector of pixels. flux is (n_frames, n_rows, n_cols) in e⁻/s; time is BTJD."""

    sector: int
    kind: str  # "tpf" (SPOC 2-min target pixel file) or "ffi" (TESScut full-frame-image cutout)
    time: np.ndarray
    flux: np.ndarray
    quality: np.ndarray
    wcs: object  # astropy.wcs.WCS
    aperture: np.ndarray | None
    filename: str


def _tpf_rows(tic_id: int) -> list[dict]:
    import lightkurve as lk

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = retry(lambda: lk.search_targetpixelfile(f"TIC {tic_id}", mission="TESS", author="SPOC",
                                                          exptime=120))
    rows = []
    for r in result.table:
        if str(r["target_name"]).lstrip("0") != str(tic_id):
            continue  # the cone search also returns neighbours' files
        rows.append({"sector": int(r["sequence_number"]), "kind": "tpf", "uri": str(r["dataURI"]),
                     "filename": str(r["productFilename"])})
    return rows


def _ffi_sectors(ra: float, dec: float) -> list[int]:
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Tesscut

    table = retry(lambda: Tesscut.get_sectors(coordinates=SkyCoord(ra, dec, unit="deg")))
    return sorted({int(s) for s in table["sector"]})


def list_products(tic_id: int, ra: float, dec: float, refresh: bool = False) -> list[dict]:
    """Every sector with pixels for this star: one row per sector, a TPF if SPOC made one, else an FFI cutout."""

    def compute() -> list[dict]:
        tpfs = {r["sector"]: r for r in _tpf_rows(tic_id)}
        rows = list(tpfs.values())
        for s in _ffi_sectors(ra, dec):
            if s not in tpfs:
                rows.append({"sector": s, "kind": "ffi", "uri": None,
                             "filename": f"tesscut_tic{tic_id}_s{s:04d}_{CUTOUT_SIZE}x{CUTOUT_SIZE}.fits"})
        return sorted(rows, key=lambda r: r["sector"])

    return cached_json("pixel-products", f"{tic_id}", SEARCH_TTL_S, compute, refresh)


def choose_products(rows: list[dict], sectors: list[int] | None, max_sectors: int) -> list[dict]:
    """The requested sectors, or else the newest max_sectors sectors."""
    if sectors:
        wanted = {int(s) for s in sectors}
        return [r for r in rows if r["sector"] in wanted]
    return sorted(rows, key=lambda r: -r["sector"])[:max_sectors][::-1]


def _download_tpf(row: dict) -> Path:
    from astroquery.mast import Observations

    path = fits_dir() / row["filename"]
    if not path.exists() or path.stat().st_size == 0:
        tmp = path.with_suffix(".part")
        status, message, _ = retry(lambda: Observations.download_file(row["uri"], local_path=str(tmp), cache=False))
        if status != "COMPLETE":
            raise OSError(f"MAST download failed for {row['filename']}: {message}")
        tmp.replace(path)
    return path


def _download_ffi(row: dict, ra: float, dec: float) -> Path:
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Tesscut

    path = fits_dir() / row["filename"]
    if not path.exists() or path.stat().st_size == 0:
        tmpdir = fits_dir() / "tesscut-tmp"
        tmpdir.mkdir(exist_ok=True)
        manifest = retry(lambda: Tesscut.download_cutouts(coordinates=SkyCoord(ra, dec, unit="deg"),
                                                          size=CUTOUT_SIZE, sector=row["sector"],
                                                          path=str(tmpdir)))
        if len(manifest) == 0:
            raise OSError(f"TESScut returned nothing for sector {row['sector']}")
        Path(str(manifest["Local Path"][0])).replace(path)
    return path


def download(row: dict, ra: float, dec: float) -> Path:
    return _download_tpf(row) if row["kind"] == "tpf" else _download_ffi(row, ra, dec)


def read(path: Path, row: dict) -> PixelSeries:
    import lightkurve as lk

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tpf = lk.TessTargetPixelFile(str(path), quality_bitmask="none")
        flux = np.asarray(tpf.flux.value, dtype=np.float32)
        aperture = np.asarray(tpf.pipeline_mask, dtype=bool) if row["kind"] == "tpf" else None
        return PixelSeries(
            sector=int(row["sector"]),
            kind=row["kind"],
            time=np.asarray(tpf.time.value, dtype=float),
            flux=flux,
            quality=np.asarray(tpf.quality, dtype=np.int64),
            wcs=tpf.wcs,
            aperture=aperture if aperture is not None and aperture.any() else None,
            filename=row["filename"],
        )
