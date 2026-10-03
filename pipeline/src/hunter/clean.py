"""Cleaning and detrending.

The transit search gets a flattened copy with UPWARD outliers clipped (dips are what we are looking for,
so they are never clipped). The flare search gets the unclipped copy.
"""

from __future__ import annotations

import numpy as np

MAD_TO_SIGMA = 1.4826
GAP_DAYS = 0.5  # a jump in time bigger than this starts a new segment (orbit gap, downlink, sector gap)


def robust_sigma(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan")
    return float(MAD_TO_SIGMA * np.median(np.abs(x - np.median(x))))


def segments(time: np.ndarray, gap: float = GAP_DAYS) -> list[slice]:
    breaks = np.flatnonzero(np.diff(time) > gap) + 1
    edges = np.concatenate([[0], breaks, [len(time)]])
    return [slice(a, b) for a, b in zip(edges[:-1], edges[1:]) if b > a]


def _biweight_location(y: np.ndarray, c: float = 5.0, iterations: int = 5) -> float:
    """Tukey biweight location: robust to the transits themselves if they do slip into the window."""
    loc = np.median(y)
    for _ in range(iterations):
        mad = np.median(np.abs(y - loc))
        if mad == 0:
            break
        u = (y - loc) / (c * mad)
        w = (1 - u**2) ** 2
        w[np.abs(u) >= 1] = 0
        if w.sum() == 0:
            break
        loc = np.sum(w * y) / w.sum()
    return float(loc)


def biweight_trend(
    time: np.ndarray,
    flux: np.ndarray,
    window: float,
    mask: np.ndarray | None = None,
    step: float | None = None,
) -> np.ndarray:
    """Sliding biweight trend, evaluated on a coarse grid per segment and interpolated (fast, smooth).

    ``mask`` marks points to EXCLUDE from the trend estimate (e.g. in-transit points); the trend is still
    returned for them. ``window`` must be ~3x the longest transit so a transit cannot pull the trend down.
    """
    step = step or window / 12
    use = np.ones(len(time), bool) if mask is None else ~mask
    trend = np.full(len(time), np.nan)
    half = window / 2
    for seg in segments(time):
        t, f, u = time[seg], flux[seg], use[seg]
        tu, fu = t[u], f[u]
        if len(tu) < 10:
            trend[seg] = np.median(f)
            continue
        grid = np.arange(t[0], t[-1] + step, step)
        values = np.full(len(grid), np.nan)
        lo = np.searchsorted(tu, grid - half)
        hi = np.searchsorted(tu, grid + half)
        for i, (a, b) in enumerate(zip(lo, hi)):
            if b - a >= 5:
                values[i] = _biweight_location(fu[a:b])
        ok = np.isfinite(values)
        if not ok.any():
            trend[seg] = np.median(fu)
            continue
        trend[seg] = np.interp(t, grid[ok], values[ok])
    return trend


def clip_upward(flux: np.ndarray, sigma: float = 3.0) -> np.ndarray:
    """Boolean keep-mask that drops only points ABOVE median + sigma*robust_sigma."""
    s = robust_sigma(flux)
    return flux < np.median(flux) + sigma * s


def flatten_for_search(
    time: np.ndarray,
    flux: np.ndarray,
    window: float,
    transit_mask: np.ndarray | None = None,
    clip_sigma: float = 3.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (flattened flux, keep-mask). keep-mask removes upward outliers only."""
    trend = biweight_trend(time, flux, window, mask=transit_mask)
    flat = flux / trend
    keep = clip_upward(flat, clip_sigma) & np.isfinite(flat)
    return flat, keep


def bin_consecutive(time: np.ndarray, flux: np.ndarray, max_points: int = 2000) -> tuple[np.ndarray, np.ndarray]:
    """Average runs of consecutive points so the result has at most max_points points."""
    n = len(time)
    if n <= max_points:
        return time.copy(), flux.copy()
    per = int(np.ceil(n / max_points))
    usable = (n // per) * per
    bt = time[:usable].reshape(-1, per).mean(axis=1)
    bf = flux[:usable].reshape(-1, per).mean(axis=1)
    if usable < n:
        bt = np.append(bt, time[usable:].mean())
        bf = np.append(bf, flux[usable:].mean())
    return bt[:max_points], bf[:max_points]
