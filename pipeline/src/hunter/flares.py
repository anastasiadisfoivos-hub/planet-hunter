"""Flare finder: short upward brightenings with a fast rise and slower decay, on the UNclipped curve."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .clean import biweight_trend, robust_sigma

TREND_WINDOW = 0.25  # days; long enough to ignore flares (minutes to an hour or two), short enough for spots
RUN_SIGMA = 3.0
PEAK_SIGMA = 5.0
MIN_POINTS = 3
DECAY_OVER_RISE = 2.0  # fade must take at least twice as long as the rise (asteroid crossings are symmetric)
MERGE_GAP_CADENCES = 2  # one or two points dipping under the threshold mid-decay do not split a flare


@dataclass
class Flare:
    t_start: float
    t_peak: float
    t_end: float
    amplitude: float  # fractional brightening at peak
    peak_sigma: float
    n_points: int
    equivalent_duration_s: float

    def to_dict(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def find_flares(time: np.ndarray, flux: np.ndarray, exclude: np.ndarray | None = None) -> list[Flare]:
    """``exclude`` marks points to leave out entirely (e.g. transits and eclipses, whose edges would
    otherwise look like brightenings against a trend dragged down by the dip)."""
    if exclude is not None:
        time, flux = time[~exclude], flux[~exclude]
    if len(time) < 50:
        return []
    trend = biweight_trend(time, flux, TREND_WINDOW)
    resid = flux / trend - 1
    sigma = robust_sigma(resid)
    if not np.isfinite(sigma) or sigma <= 0:
        return []
    cadence = float(np.median(np.diff(time)))
    above = resid > RUN_SIGMA * sigma
    # Bridge short dropouts inside a run so one flare is not reported twice.
    idx = np.flatnonzero(above)
    for a, b in zip(idx[:-1], idx[1:]):
        if 1 < b - a <= MERGE_GAP_CADENCES + 1 and time[b] - time[a] < (b - a + 0.5) * cadence:
            above[a:b] = True

    flares: list[Flare] = []
    i, n = 0, len(time)
    while i < n:
        if not above[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and above[j + 1] and time[j + 1] - time[j] < 1.5 * cadence:
            j += 1
        run = slice(i, j + 1)
        k = i + int(np.argmax(resid[run]))
        npts = j - i + 1
        # Fast rise, slower decay. The rise is at least one cadence even if the peak is the first point.
        rise, decay = max(time[k] - time[i], cadence), time[j] - time[k]
        touches_gap = (i == 0 or time[i] - time[i - 1] > 1.5 * cadence) or (
            j == n - 1 or time[j + 1] - time[j] > 1.5 * cadence)
        if (npts >= MIN_POINTS and resid[k] > PEAK_SIGMA * sigma and decay >= DECAY_OVER_RISE * rise
                and not touches_gap):
            flares.append(Flare(
                t_start=float(time[i]), t_peak=float(time[k]), t_end=float(time[j]),
                amplitude=float(resid[k]), peak_sigma=float(resid[k] / sigma), n_points=npts,
                equivalent_duration_s=float(np.sum(resid[run]) * cadence * 86400),
            ))
        i = j + 1
    return flares
