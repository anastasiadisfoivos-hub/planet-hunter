"""Scattered-light rejection before the search: which cadences to leave out of the detrending and the search.

A cadence is masked when, in its sector,
  - the background (SAP_BKG, or TGLC's, normalised per sector to median 0 and robust sigma 1) is above Z_HIGH, or
  - the background changes faster than RATE_PER_H robust sigmas per hour (sharp ramps at orbit starts),
and every masked stretch is grown by SHOULDER_D on both sides. Every orbit gap and sector edge (a gap > 0.5 d)
also gets EDGE_D masked on its data side.

Why the shoulders and edge windows: FAINT (faint/README section 2) found that a hard background cut without them
backfires. It leaves each event's dimmed shoulders beside a fresh gap, where the detrending cannot follow them;
on TOI-5688 hunt's SDE for the real planet fell from 10.1 to 5.6. Masked cadences are left out of the trend and
of the search alike, so no new edge is exposed. The numbers were chosen on FAINT's TOI-1680 and TOI-5688 TGLC
curves (README, "Scattered light").
"""

from __future__ import annotations

import numpy as np

Z_HIGH = 3.0
RATE_PER_H = 1.0
SHOULDER_D = 0.5
EDGE_D = 0.25
GAP_D = 0.5


def _grow(t: np.ndarray, m: np.ndarray, width: float) -> np.ndarray:
    """Every point within `width` days of a masked point (t sorted)."""
    if width <= 0 or not m.any():
        return m.copy()
    tm = t[m]
    i = np.searchsorted(tm, t)
    lo = np.abs(t - tm[np.clip(i - 1, 0, len(tm) - 1)])
    hi = np.abs(tm[np.clip(i, 0, len(tm) - 1)] - t)
    return np.minimum(lo, hi) <= width


def edge_mask(t: np.ndarray, width: float = EDGE_D, gap: float = GAP_D) -> np.ndarray:
    if len(t) == 0:
        return np.zeros(0, bool)
    brk = np.flatnonzero(np.diff(t) > gap)
    starts = np.concatenate([[t[0]], t[brk + 1]])
    ends = np.concatenate([t[brk], [t[-1]]])
    m = np.zeros(len(t), bool)
    for a, b in zip(starts, ends):
        m |= ((t >= a) & (t < a + width)) | ((t <= b) & (t > b - width))
    return m


def scattered_light_mask(time: np.ndarray, sector: np.ndarray, bkg: np.ndarray | None,
                         z_high: float = Z_HIGH, rate_per_h: float = RATE_PER_H, shoulder_d: float = SHOULDER_D,
                         edge_d: float = EDGE_D) -> tuple[np.ndarray, dict]:
    """(mask, info). Without a background only the edge windows are masked."""
    n = len(time)
    core = np.zeros(n, bool)
    have_bkg = bkg is not None and np.isfinite(bkg).any()
    if have_bkg:
        for s in np.unique(sector):
            idx = np.flatnonzero(sector == s)
            if len(idx) < 3:
                continue
            t, b = time[idx], np.asarray(bkg[idx], float)
            ok = np.isfinite(b)
            high = ok & (b > z_high)
            rate = np.zeros(len(idx))
            if ok.sum() >= 3:
                rate[ok] = np.abs(np.gradient(b[ok], t[ok])) / 24
            core[idx] = high | (rate > rate_per_h)
    grown = _grow(time, core, shoulder_d) if core.any() else core
    edges = edge_mask(time, edge_d)
    mask = grown | edges
    info = {"masked_fraction": round(float(mask.mean()), 4) if n else 0.0,
            "background_fraction": round(float(core.mean()), 4) if n else 0.0,
            "shoulder_fraction": round(float((grown & ~core).mean()), 4) if n else 0.0,
            "edge_fraction": round(float((edges & ~grown).mean()), 4) if n else 0.0,
            "background_used": bool(have_bkg),
            "rule": f"background > {z_high:g} sigma or changing > {rate_per_h:g} sigma/h, grown by {shoulder_d:g} d; "
                    f"{edge_d:g} d at every orbit gap and sector edge"}
    return mask, info
