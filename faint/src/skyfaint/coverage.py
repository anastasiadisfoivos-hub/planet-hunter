"""Which TESS sectors (and camera / CCD) observed a position, and which of those TGLC has published.

TGLC on MAST covers sectors 1-55 (2018-07 to 2022-09): sectors 1-11 through the MAST API, sectors 12-55 as
files at predictable URLs (target lists and bulk curl scripts only; checked 2026-09-26: s0056 and later 404).
Pointings come from tess-point (the TESS mission's own footprint tool), so coverage is a prediction; the loader
confirms each file exists before counting it.
"""

from __future__ import annotations

import numpy as np

TGLC_FIRST, TGLC_LAST = 1, 55


def tgl_sectors(sector: int) -> bool:
    return TGLC_FIRST <= sector <= TGLC_LAST


def pointings(ra, dec) -> list[list[tuple[int, int, int]]]:
    """For each star, [(sector, camera, ccd)] of every TGLC sector (1-55) whose CCDs cover it."""
    from tess_stars2px import tess_stars2px_function_entry as t2p

    ra = np.atleast_1d(np.asarray(ra, float))
    dec = np.atleast_1d(np.asarray(dec, float))
    out: list[list[tuple[int, int, int]]] = [[] for _ in range(len(ra))]
    if len(ra) == 0:
        return out
    ids = np.arange(len(ra))
    sid, _, _, sec, cam, ccd, *_ = t2p(ids, ra, dec)
    for i, s, c, d in zip(sid, sec, cam, ccd):
        if i >= 0 and tgl_sectors(int(s)):
            out[int(i)].append((int(s), int(c), int(d)))
    for lst in out:
        lst.sort()
    return out


HALF_FOV_DEG = 12.0  # each camera sees 24 x 24 degrees


def _unit(ra_deg, dec_deg) -> np.ndarray:
    ra, dec = np.radians(ra_deg), np.radians(dec_deg)
    return np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)], axis=-1)


def sector_mask(ra, dec) -> np.ndarray:
    """Vectorised footprint test for many stars: an int64 bitmask per star, bit (s - 1) set when TGLC sector s
    (1-55) put the star inside one of its four cameras' 24 x 24 degree fields.

    Uses tess-point's own camera pointings, but treats each camera as a square in the tangent plane (sides along
    and across the spacecraft's boresight line) and ignores the gaps between CCDs (about 0.1 degree), so it is a
    few-percent approximation at field edges. pointings() (exact, but ~10 ms per star) is used per star by the
    loader; this is for ranking millions of stars."""
    from tess_stars2px import TESS_Spacecraft_Pointing_Data

    sc = TESS_Spacecraft_Pointing_Data()
    stars = _unit(np.asarray(ra, float), np.asarray(dec, float))  # (n, 3)
    mask = np.zeros(len(stars), np.int64)
    lim = np.tan(np.radians(HALF_FOV_DEG))
    for j, s in enumerate(sc.sectors):
        s = int(s)
        if not tgl_sectors(s):
            continue
        bore = _unit(sc.ras[j], sc.decs[j])
        hit = np.zeros(len(stars), bool)
        for cam in range(4):
            c = _unit(sc.camRa[cam, j], sc.camDec[cam, j])
            u = bore - np.dot(bore, c) * c  # direction towards the boresight, in the tangent plane at c
            u /= np.linalg.norm(u)
            v = np.cross(c, u)
            z = stars @ c
            front = z > 0
            x = (stars @ u) / np.where(front, z, 1)
            y = (stars @ v) / np.where(front, z, 1)
            hit |= front & (np.abs(x) < lim) & (np.abs(y) < lim)
        mask[hit] |= np.int64(1) << (s - 1)
    return mask


def sectors_of(bits: int) -> list[int]:
    return [s for s in range(TGLC_FIRST, TGLC_LAST + 1) if (int(bits) >> (s - 1)) & 1]
