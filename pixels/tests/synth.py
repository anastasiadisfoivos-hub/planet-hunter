"""Synthetic TESS-like sectors with a known answer: a scene of stars, one of which dims."""

import numpy as np

from conftest import simple_wcs_header
from skypixels.analyze import Star
from skypixels.catalog import btjd_to_jyear
from skypixels.psf import Shape, prf_sum
from skypixels.reduce import SectorImages

RA, DEC = 120.0, -30.0
SHAPE = Shape(0.9, 0.85, 0.3)
ZP = 1.5e4  # e⁻/s at T = 10


def star(east_arcsec: float, north_arcsec: float, tmag: float, gid: str) -> Star:
    ra = RA + east_arcsec / 3600 / np.cos(np.radians(DEC))
    return Star(gid, ra, DEC + north_arcsec / 3600, 0.0, 0.0, tmag + 0.4, tmag)


def scene_positions(wcs_header: str, stars: list[Star], epoch_btjd: float) -> np.ndarray:
    from astropy.io import fits
    from astropy.wcs import WCS

    w = WCS(fits.Header.fromstring(wcs_header))
    return w.all_world2pix(np.array([s.at(btjd_to_jyear(epoch_btjd)) for s in stars]), 0)


def make_sector(rng, stars: list[Star], host: int | None, depth: float, noise: float = 3.0, sector: int = 1,
                n: int = 13, wcs_shift=(0.0, 0.0), rot_deg: float = 30.0, epoch_btjd: float = 3000.0) -> SectorImages:
    """stars[0] is the target. host = index of the star that dims by `depth` (None = no dip)."""
    hdr = simple_wcs_header(RA, DEC, crpix=((n + 1) / 2, (n + 1) / 2), rot_deg=rot_deg)
    xy = scene_positions(hdr, stars, epoch_btjd) + np.array(wcs_shift)  # the WCS is off by wcs_shift
    flux = np.array([ZP * 10 ** (-0.4 * (s.tmag - 10)) for s in stars])
    oot = prf_sum((n, n), xy[:, 0], xy[:, 1], flux, SHAPE) + 200.0
    frame_var = np.abs(oot) * 2.0 + 25.0
    oot = oot + rng.normal(0, 1.0, oot.shape) * np.sqrt(frame_var / 1000)
    diff = np.zeros((n, n))
    if host is not None:
        diff += depth * flux[host] * prf_sum((n, n), [xy[host, 0]], [xy[host, 1]], [1.0], SHAPE)
    diff_var = np.full((n, n), noise**2)
    diff = diff + rng.normal(0, noise, (n, n))
    return SectorImages(sector, "ffi", oot, diff, diff_var, frame_var, hdr, epoch_btjd, 10, 300, 600)
