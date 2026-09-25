"""Box Least Squares transit search (astropy), two-stage so multi-year baselines stay tractable.

Stage 1 (coarse): each sector is searched on its own on a grid fine enough for one sector's baseline, and
the BLS log-likelihood powers are summed across sectors (they are additive for independent data).
Stage 2 (fine): the full data set is searched in a narrow window around the best coarse period, on a
grid fine enough for the full baseline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from astropy.timeseries import BoxLeastSquares

from .clean import robust_sigma

PERIOD_MIN = 0.5
PERIOD_MAX = 15.0
DURATIONS = np.array([0.03, 0.04, 0.05, 0.065, 0.08, 0.1, 0.13, 0.16, 0.2, 0.25, 0.3])
COARSE_BIN_DAYS = 10 / 1440  # the coarse stage works on 10-minute bins
OVERSAMPLE = 3


@dataclass
class Signal:
    period: float
    t0: float  # BTJD, mid-transit
    duration: float
    depth: float  # fractional; BLS box depth
    depth_err: float
    snr: float
    sde: float
    n_transits: int
    depth_odd: float
    depth_odd_err: float
    depth_even: float
    depth_even_err: float
    halved: bool = False  # True if the period was halved because the "empty" alternate events were real

    def to_dict(self) -> dict:
        return {k: (round(v, 8) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def in_transit(time: np.ndarray, period: float, t0: float, duration: float, scale: float = 1.0) -> np.ndarray:
    phase = (time - t0 + 0.5 * period) % period - 0.5 * period
    return np.abs(phase) < scale * duration / 2


def bin_by_time(time: np.ndarray, flux: np.ndarray, width: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    key = np.floor((time - time[0]) / width).astype(np.int64)
    _, idx, counts = np.unique(key, return_index=True, return_counts=True)
    bt = np.add.reduceat(time, idx) / counts
    bf = np.add.reduceat(flux, idx) / counts
    return bt, bf, counts


def _period_grid(pmin: float, pmax: float, baseline: float) -> np.ndarray:
    dlnp = DURATIONS.min() / (OVERSAMPLE * max(baseline, 1.0))
    return np.exp(np.arange(np.log(pmin), np.log(pmax), dlnp))


def _coarse(time: np.ndarray, flux: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    spans = [np.ptp(time[groups == g]) for g in np.unique(groups)]
    periods = _period_grid(PERIOD_MIN, PERIOD_MAX, max(spans))
    total = np.zeros(len(periods))
    for g in np.unique(groups):
        sel = groups == g
        if sel.sum() < 50:
            continue
        bt, bf, counts = bin_by_time(time[sel], flux[sel], COARSE_BIN_DAYS)
        sigma = robust_sigma(bf - np.median(bf)) or 1e-3
        # Binned errors scale with 1/sqrt(points per bin).
        dy = sigma * np.sqrt(np.median(counts) / counts)
        usable = DURATIONS[DURATIONS < np.ptp(bt) / 2]
        result = BoxLeastSquares(bt, bf, dy).power(periods, usable, objective="likelihood")
        total += np.nan_to_num(np.asarray(result.power), nan=0.0)
    return periods, total


def _fine(time, flux, dy, center: float, baseline: float):
    grid = _period_grid(center * 0.995, center * 1.005, baseline)
    bls = BoxLeastSquares(time, flux, dy)
    result = bls.power(grid, DURATIONS[DURATIONS < center / 2], objective="likelihood")
    i = int(np.argmax(result.power))
    return bls, float(result.period[i]), float(result.transit_time[i]), float(result.duration[i])


def _depth_snr(time, flux, period, t0, duration, depth) -> float:
    """SNR against correlated noise: scatter of out-of-transit flux binned at the transit duration."""
    oot = ~in_transit(time, period, t0, duration, scale=2.0)
    n_transits = max(1, len(np.unique(np.round((time[~oot] - t0) / period))))
    bt, bf, counts = bin_by_time(time[oot], flux[oot], duration)
    full = counts >= 0.5 * np.median(counts)
    sigma_dur = robust_sigma(bf[full]) if full.sum() > 10 else robust_sigma(flux[oot])
    white = robust_sigma(flux[oot]) / np.sqrt(np.median(counts))
    sigma_dur = max(sigma_dur, white)
    return float(depth / (sigma_dur / np.sqrt(n_transits))) if sigma_dur > 0 else 0.0


def search(time: np.ndarray, flux: np.ndarray, groups: np.ndarray) -> Signal | None:
    """Best box-shaped periodic dip in (flattened, normalised) flux. groups = sector per point."""
    if len(time) < 200:
        return None
    periods, power = _coarse(time, flux, groups)
    if not np.any(power > 0):
        return None
    best = float(periods[int(np.argmax(power))])
    sde = float((power.max() - power.mean()) / power.std()) if power.std() > 0 else 0.0

    baseline = float(np.ptp(time))
    dy = np.full(len(flux), robust_sigma(flux) or 1e-3)
    bls, period, t0, duration = _fine(time, flux, dy, best, baseline)
    stats = bls.compute_stats(period, duration, t0)

    halved = False
    # If folding at P/2 gives (nearly) the same depth, the "gaps" between our events are real events too.
    half_depth, half_err = stats["depth_half"]
    depth0 = stats["depth"][0]
    if period / 2 >= PERIOD_MIN and depth0 > 0 and half_depth > 0.8 * depth0 and half_depth > 5 * half_err:
        bls, period, t0, duration = _fine(time, flux, dy, period / 2, baseline)
        stats = bls.compute_stats(period, duration, t0)
        halved = True

    depth, depth_err = (float(x) for x in stats["depth"])
    odd, odd_err = (float(x) for x in stats["depth_odd"])
    even, even_err = (float(x) for x in stats["depth_even"])
    counts = np.asarray(stats["per_transit_count"])
    return Signal(
        period=period,
        t0=t0,
        duration=duration,
        depth=depth,
        depth_err=depth_err,
        snr=_depth_snr(time, flux, period, t0, duration, depth),
        sde=sde,
        n_transits=int(np.sum(counts > 0)),
        depth_odd=odd,
        depth_odd_err=odd_err,
        depth_even=even,
        depth_even_err=even_err,
        halved=halved,
    )


def harmonically_related(p1: float, p2: float, tol: float = 0.01) -> bool:
    ratio = p1 / p2
    return any(abs(ratio - k) / k < tol for k in (1, 2, 3, 1 / 2, 1 / 3))
