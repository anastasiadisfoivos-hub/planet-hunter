"""Detrending for the deep search: wotan's robust time-windowed biweight, with points to leave out of the trend.

The window is about 3x the longest dip the search that uses it looks for, so a dip cannot drag the trend down
with it: 0.9 d for the short-period search (dips up to 7.2 h), 3x the longest duration for the long-period
search, and per duration tier in the single-dip search. Segments are split at gaps > 0.5 d (sector and orbit
gaps). Only upward outliers are clipped afterwards; dips are what we look for.
"""

from __future__ import annotations

import numpy as np

from hunter.clean import clip_upward

BREAK_TOLERANCE_D = 0.5


def trend(time: np.ndarray, flux: np.ndarray, window: float, mask: np.ndarray | None = None) -> np.ndarray:
    """Biweight trend (wotan). mask marks points to EXCLUDE from the estimate; the trend is interpolated
    across them within their segment."""
    from wotan import flatten as wflatten

    use = np.isfinite(flux) & np.isfinite(time)
    if mask is not None:
        use &= ~mask
    out = np.full(len(time), np.nan)
    if use.sum() < 10:
        return np.full(len(time), np.nanmedian(flux[use]) if use.any() else 1.0)
    _, tr = wflatten(time[use], flux[use], method="biweight", window_length=window, edge_cutoff=0.0,
                     break_tolerance=BREAK_TOLERANCE_D, return_trend=True)
    ok = np.isfinite(tr)
    tu, tr = time[use][ok], tr[ok]
    if len(tu) == 0:
        return np.full(len(time), np.nanmedian(flux))
    out = np.interp(time, tu, tr)
    # Do not bridge gaps: a masked point further than a window from any estimate gets the nearest segment's
    # value, which np.interp already does at the ends; inside long gaps there is no data to worry about.
    return out


def flatten(time: np.ndarray, flux: np.ndarray, window: float, mask: np.ndarray | None = None,
            clip_sigma: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """(flux / trend, keep-mask). keep drops upward outliers and points without a trend."""
    tr = trend(time, flux, window, mask)
    flat = flux / tr
    keep = np.isfinite(flat)
    keep[keep] = clip_upward(flat[keep], clip_sigma)
    return flat, keep
