"""How many TESS sectors have observed a star, for many stars at once (no downloads).

tess-point's pointing and camera-geometry tables, applied to all stars together: for each sector and camera, the
star's direction is rotated into camera coordinates with tess-point's own rotation matrix, and the star counts
as observed when it falls inside the camera's field (+-12.0 deg) and outside the strips (+-0.3 deg) along the
camera axes where its four CCDs meet. tess_stars2px_function_entry does the exact pixel mapping star by star in
Python, which takes over 10 minutes per 100k stars; this takes about a second. Checked against it on 600 random
stars not used to choose the two numbers: see tests/test_dips.py and the README for the agreement.

Only sectors up to the newest public one are counted. tess-point's table ends at its own last planned sector
(132 in 0.9.5); later sectors are not counted until the package is updated.
"""

from __future__ import annotations

import numpy as np

FOV_HALF_DEG = 12.0  # 4096 px x 21" = 23.9 deg per camera
CCD_GAP_HALF_DEG = 0.3  # strips along the camera's axes where the four CCDs meet (tess-point: not observed)


def _pointing():
    from tess_stars2px import TESS_Spacecraft_Pointing_Data

    return TESS_Spacecraft_Pointing_Data()


def observed_sectors(ra: np.ndarray, dec: np.ndarray, max_sector: int, chunk: int = 200_000) -> list[list[int]]:
    """Sectors (<= max_sector) whose cameras covered each star."""
    ra, dec = np.atleast_1d(np.asarray(ra, float)), np.atleast_1d(np.asarray(dec, float))
    sc = _pointing()
    out: list[list[int]] = [[] for _ in range(len(ra))]
    lim = np.tan(np.radians(FOV_HALF_DEG))
    gap = np.tan(np.radians(CCD_GAP_HALF_DEG))
    for a in range(0, len(ra), chunk):
        r, d = np.radians(ra[a:a + chunk]), np.radians(dec[a:a + chunk])
        vec = np.vstack([np.cos(r) * np.cos(d), np.sin(r) * np.cos(d), np.sin(d)])
        hits = []
        for idx, sec in enumerate(sc.sectors):
            if sec > max_sector or sec >= 1000:  # >= 1000: special pointings (e.g. 3I/ATLAS), not survey sectors
                continue
            fpg = sc.fpgObjs[idx]
            seen = np.zeros(vec.shape[1], bool)
            for j in range(fpg.NCAM):
                cam = fpg.rmat4[j] @ vec
                ok = cam[2] > np.cos(np.radians(20.0))  # within 20 deg of the camera boresight
                with np.errstate(divide="ignore", invalid="ignore"):
                    x, y = np.abs(cam[0] / cam[2]), np.abs(cam[1] / cam[2])
                seen |= ok & (x <= lim) & (y <= lim) & (x >= gap) & (y >= gap)
            hits.append((int(sec), np.flatnonzero(seen)))
        for sec, idx in hits:
            for i in idx:
                out[a + i].append(sec)
    return out


def sector_counts(ra: np.ndarray, dec: np.ndarray, max_sector: int) -> np.ndarray:
    return np.array([len(s) for s in observed_sectors(ra, dec, max_sector)], int)
