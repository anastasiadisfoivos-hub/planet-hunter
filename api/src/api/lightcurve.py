"""The unfolded light curve we keep per star: normalised flux averaged over runs of consecutive
points, never across a data gap, so at most MAX_LC_POINTS remain."""

from __future__ import annotations

import math

import numpy as np

from api.models import MAX_LC_POINTS, LightCurve

GAP_DAYS = 0.5  # as pipeline/'s cleaning: a bigger jump starts a new segment


def bin_lightcurve(
    time: np.ndarray, flux: np.ndarray, sectors: list[int], max_points: int = MAX_LC_POINTS
) -> LightCurve:
    good = np.isfinite(time) & np.isfinite(flux)
    t, f = np.asarray(time, float)[good], np.asarray(flux, float)[good]
    order = np.argsort(t, kind="stable")
    t, f = t[order], f[order]
    n = len(t)
    breaks = np.flatnonzero(np.diff(t) > GAP_DAYS) + 1
    edges = np.concatenate([[0], breaks, [n]]).astype(int)
    if len(edges) - 1 > max_points:  # more gaps than bins: gaps can't all be respected
        edges = np.array([0, n])
    lengths = [int(b - a) for a, b in zip(edges[:-1], edges[1:], strict=True) if b > a]
    per = max(1, math.ceil(n / max_points))
    while sum(math.ceil(k / per) for k in lengths) > max_points:
        per += 1
    bt: list[float] = []
    bf: list[float] = []
    for a, b in zip(edges[:-1], edges[1:], strict=True):
        for start in range(int(a), int(b), per):
            stop = min(start + per, int(b))
            bt.append(round(float(t[start:stop].mean()), 5))
            bf.append(round(float(f[start:stop].mean()), 6))
    return LightCurve(time_btjd=bt, flux=bf, binned_from=n, sectors=sorted(set(sectors)))
