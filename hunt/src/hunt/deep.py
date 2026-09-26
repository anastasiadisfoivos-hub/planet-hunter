"""Periodic search on the stitched all-sector curve: BLS over the whole period range, TLS where it is affordable.

Three searches, all on the same flattened, stitched curve (every sector, see lightcurve.stitch):

  bls_short  hunter.search.search: 0.5-15 d, per-sector BLS powers summed then refined on the full
             baseline (unchanged pipeline code).
  bls_long   15 d up to half the baseline, BLS on a frequency grid fine enough that a transit of half the
             central-transit duration cannot drift more than a third of that out of phase over the baseline.
             The range is split in factor-of-2 period blocks; each block gets durations from 0.35x the central
             duration for 3x the star's density to 1.5x that for a third of it (1-24 h) and its own bin width.
             Blocks run in increasing period while they fit a LONG_BUDGET_S time budget; the longest period
             reached is recorded (stars with sectors spread over many years have huge grids).
  tls        transitleastsquares (limb-darkened transit template: better than a box for small planets) from
             0.5 d up to half the baseline. TLS costs about (points x periods); its cost is predicted before it
             runs and, if it would exceed TLS_BUDGET_S, TLS runs on the newest sectors that fit instead of the
             whole curve (bls_short and bls_long still cover everything). What ran is recorded per star.

Whatever finds it, a signal becomes a hunter.search.Signal (period, t0, duration, then depth / odd-even
depths / epochs with data from astropy's BLS statistics on the full stitched curve and the pipeline's
red-noise-aware SNR), so every downstream check treats it the same way.
"""

from __future__ import annotations

import contextlib
import io
import math
import time as _time
from dataclasses import dataclass, field

import numpy as np
from astropy.timeseries import BoxLeastSquares

from hunter.clean import robust_sigma
from hunter.search import PERIOD_MAX as SHORT_PMAX
from hunter.search import Signal, bin_by_time, in_transit

from .stars import RHO_SUN_KG_M3, Star

G = 6.674e-11
MIN_TRANSITS = 3
LONG_OVERSAMPLE = 3
LONG_MIN_BIN_MIN, LONG_MAX_BIN_MIN = 10.0, 60.0
LONG_DURATION_MAX_D = 1.0  # 24 h, the same limit as the single-dip search
# astropy's BLS scans phase bins of (shortest duration / oversample); its cost per period grows with the period.
# A third of the shortest duration is the same tolerance the period grid is built on (default is a tenth).
BLS_PHASE_OVERSAMPLE = 3
LONG_BUDGET_S = 180.0  # per round; beyond the period it reaches, long periods are left to the dip search
TLS_BUDGET_S = 60.0
TLS_RATE = 2.0e6  # (points x periods) per second, single thread: measured 1.8-2.7e6 (6 and 13 sectors, loaded laptop)
TLS_OVERSAMPLE = 3
DEFAULT_RHO = 1.0


def central_duration(period: float, rho_solar: float, k: float = 0.0) -> float:
    """Central-transit duration (days) on a circular orbit: P/pi * asin((1+k) R*/a)."""
    a_over_r = (G * rho_solar * RHO_SUN_KG_M3 * (period * 86400) ** 2 / (3 * math.pi)) ** (1 / 3)
    return period / math.pi * math.asin(min(1.0, (1 + k) / a_over_r))


def star_density(star: Star | None) -> tuple[float, bool]:
    rho = star.density_solar()[0] if star is not None else None
    return (rho, True) if rho else (DEFAULT_RHO, False)


# ---- common: turn (P, t0, duration) into a Signal ----------------------------------------------------------

def depth_snr(time, flux, period, t0, duration, depth) -> tuple[float, int]:
    """The pipeline's SNR (hunter.search._depth_snr): depth over the scatter of out-of-transit flux binned at
    the transit duration, divided by sqrt(epochs with in-transit data). Also returns that epoch count."""
    oot = ~in_transit(time, period, t0, duration, scale=2.0)
    intr = in_transit(time, period, t0, duration)
    n_tr = max(1, len(np.unique(np.round((time[intr] - t0) / period))))
    if oot.sum() < 20:
        return 0.0, n_tr
    bt, bf, counts = bin_by_time(time[oot], flux[oot], duration)
    full = counts >= 0.5 * np.median(counts)
    sigma_dur = robust_sigma(bf[full]) if full.sum() > 10 else robust_sigma(flux[oot])
    white = robust_sigma(flux[oot]) / np.sqrt(np.median(counts))
    sigma_dur = max(sigma_dur, white)
    return (float(depth / (sigma_dur / np.sqrt(n_tr))) if sigma_dur > 0 else 0.0), n_tr


def make_signal(time, flux, period, t0, duration, sde) -> Signal | None:
    """Depths and errors from astropy's BLS statistics. The errors there assume white noise; they are scaled by
    the red-noise factor at the transit duration (checks.red_noise_factor), because long dips spread over many
    sectors otherwise look 'significantly' different from each other (TOI-813 b: odd/even 3.7 sigma apart on
    white-noise errors, 1.9 sigma on red-noise errors)."""
    from .checks import red_noise_factor

    dy = np.full(len(flux), robust_sigma(flux) or 1e-3)
    try:
        st = BoxLeastSquares(time, flux, dy).compute_stats(period, duration, t0)
    except Exception:
        return None
    oot = ~in_transit(time, period, t0, duration, scale=1.5)
    beta = red_noise_factor(time[oot], flux[oot], duration) if oot.sum() > 50 else 1.0
    depth, depth_err = (float(x) for x in st["depth"])
    odd, odd_err = (float(x) for x in st["depth_odd"])
    even, even_err = (float(x) for x in st["depth_even"])
    depth_err, odd_err, even_err = depth_err * beta, odd_err * beta, even_err * beta
    counts = np.asarray(st["per_transit_count"])
    snr, _ = depth_snr(time, flux, period, t0, duration, depth)
    return Signal(period=float(period), t0=float(t0), duration=float(duration), depth=depth,
                  depth_err=depth_err, snr=snr, sde=float(sde), n_transits=int(np.sum(counts > 0)),
                  depth_odd=odd, depth_odd_err=odd_err, depth_even=even, depth_even_err=even_err)


def refine(time: np.ndarray, flux: np.ndarray, sig: Signal) -> Signal:
    """Fine period / epoch / duration around a find from the coarse grids (bls_long, tls): BLS on P +- (one duration
    of phase drift over the baseline) in 101 steps and 5 durations. A few transits over years need this: 0.02 d
    of period error moves TOI-2180 b's third transit by 2 h."""
    baseline = float(np.ptp(time))
    if baseline <= 0 or len(time) < 50:
        return sig
    dp = sig.duration * sig.period / baseline
    periods = np.linspace(max(sig.period - dp, 0.5), sig.period + dp, 101)
    durs = sig.duration * np.array([0.8, 0.9, 1.0, 1.1, 1.25])
    durs = durs[(durs < 0.5 * periods.min()) & (durs <= LONG_DURATION_MAX_D)]
    if len(durs) == 0:
        return sig
    bt, bf, cnt = bin_by_time(time, flux, min(10 / 1440, sig.duration / 6))
    dy = (robust_sigma(bf - np.median(bf)) or 1e-3) * np.sqrt(np.median(cnt) / cnt)
    try:
        res = BoxLeastSquares(bt, bf, dy).power(periods, durs, objective="likelihood", oversample=10)
    except Exception:
        return sig
    i = int(np.argmax(np.nan_to_num(np.asarray(res.power), nan=-np.inf)))
    from dataclasses import replace
    return replace(sig, period=float(res.period[i]), t0=float(res.transit_time[i]), duration=float(res.duration[i]))


# ---- long-period BLS ---------------------------------------------------------------------------------------

def _grid_block(p_lo: float, p_hi: float, baseline: float, dmin_of) -> np.ndarray:
    """Periods with frequency step D_min(P) / (oversample * P * baseline): a transit cannot slip more than
    D_min / oversample over the whole baseline between neighbouring trial periods."""
    ps = []
    p = p_lo
    while p < p_hi:
        n = 2000
        step = p * dmin_of(p) / (LONG_OVERSAMPLE * baseline)
        block = p + step * np.arange(n)  # the step grows slowly with P; recomputed every 2000 periods
        block = block[block < p_hi]
        ps.append(block)
        p = float(block[-1]) + step if len(block) else p_hi
    return np.concatenate(ps) if ps else np.array([])


def long_blocks(pmin: float, pmax: float, rho: float) -> list[tuple[float, float, np.ndarray]]:
    """(p_lo, p_hi, durations) blocks, factor 2 in period."""
    out = []
    lo = pmin
    while lo < pmax:
        hi = min(2 * lo, pmax)
        d_lo = max(0.35 * central_duration(lo, 3 * rho), 1.0 / 24)
        d_hi = min(1.5 * central_duration(hi, rho / 3), LONG_DURATION_MAX_D)
        d_hi = max(d_hi, d_lo * 1.3)
        n = max(3, int(math.ceil(math.log(d_hi / d_lo) / math.log(1.3))) + 1)
        out.append((lo, hi, np.geomspace(d_lo, d_hi, n)))
        lo = hi
    return out


@dataclass
class LongResult:
    signal: Signal | None
    n_periods: int
    seconds: float
    pmax: float  # longest period actually searched
    pmax_target: float = 0.0  # half the baseline
    stopped_by_budget: bool = False


def bls_long(time: np.ndarray, flux: np.ndarray, rho: float, pmin: float = SHORT_PMAX,
             pmax: float | None = None, budget_s: float | None = None) -> LongResult:
    """Blocks in increasing period. The grid step uses half the central-transit duration at the star's density
    (the Ofir 2014 / TLS convention; shorter, grazing durations are still searched, on the same grid). A block
    starts only if its predicted time (the last block's time per period x its periods x 2, as the phase-bin
    count doubles) fits in budget_s; the longest period reached is reported."""
    t_start = _time.perf_counter()
    budget = LONG_BUDGET_S if budget_s is None else budget_s
    baseline = float(np.ptp(time)) if len(time) else 0.0
    target = baseline / 2 if pmax is None else min(pmax, baseline / 2)
    if target <= pmin or len(time) < 200:
        return LongResult(None, 0, 0.0, min(pmin, target), target)
    all_p, all_pow, best = [], [], None
    reached, stopped, per_period = pmin, False, None
    for lo, hi, durs in long_blocks(pmin, target, rho):
        periods = _grid_block(lo, hi, baseline, lambda p: 0.5 * central_duration(p, rho))
        if len(periods) == 0:
            continue
        if per_period is not None:
            predicted = per_period * 2 * len(periods)
            if _time.perf_counter() - t_start + predicted > budget:
                stopped = True
                break
        tb = _time.perf_counter()
        bin_d = min(max(durs[0] / 3, LONG_MIN_BIN_MIN / 1440), LONG_MAX_BIN_MIN / 1440)
        bt, bf, cnt = bin_by_time(time, flux, bin_d)
        sigma = robust_sigma(bf - np.median(bf)) or 1e-3
        dy = sigma * np.sqrt(np.median(cnt) / cnt)
        res = BoxLeastSquares(bt, bf, dy).power(periods, durs, objective="likelihood",
                                                oversample=BLS_PHASE_OVERSAMPLE)
        per_period = (_time.perf_counter() - tb) / len(periods)
        pw = np.nan_to_num(np.asarray(res.power), nan=0.0)
        all_p.append(periods)
        all_pow.append(pw)
        reached = hi
        i = int(np.argmax(pw))
        if best is None or pw[i] > best[0]:
            best = (float(pw[i]), float(res.period[i]), float(res.transit_time[i]), float(res.duration[i]))
    n_periods = int(sum(len(p) for p in all_p))
    if best is None:
        return LongResult(None, n_periods, _time.perf_counter() - t_start, reached, target, stopped)
    power = np.concatenate(all_pow)
    sde = float((power.max() - power.mean()) / power.std()) if power.std() > 0 else 0.0
    _, period, t0, dur = best
    sig = make_signal(time, flux, period, t0, dur, sde)
    return LongResult(sig, n_periods, _time.perf_counter() - t_start, reached, target, stopped)


# ---- TLS -----------------------------------------------------------------------------------------------------

def _tls_star(star: Star | None) -> dict:
    r = (star.rad if star is not None and star.rad else 1.0)
    rho, _ = star_density(star)
    m = (star.mass if star is not None and star.mass else max(0.1, min(rho * r**3, 3.0)))
    return {"R_star": r, "M_star": m, "R_star_min": max(0.1, r / 2), "R_star_max": min(10.0, r * 2),
            "M_star_min": max(0.1, m / 2), "M_star_max": min(3.0, m * 2)}


def tls_cost(n_points: int, baseline: float, star: Star | None, pmin: float = 0.5) -> tuple[float, int]:
    """Predicted TLS seconds and number of trial periods for this many points and this baseline."""
    from transitleastsquares import period_grid

    p = _tls_star(star)
    n_p = len(period_grid(R_star=p["R_star"], M_star=p["M_star"], time_span=max(baseline, 1.0),
                          period_min=pmin, period_max=max(baseline / 2, pmin * 1.01),
                          oversampling_factor=TLS_OVERSAMPLE))
    return n_points * n_p / TLS_RATE, n_p


def tls_subset(time: np.ndarray, sector: np.ndarray, star: Star | None,
               budget_s: float = TLS_BUDGET_S) -> tuple[np.ndarray, str]:
    """Points TLS runs on: all of them if the predicted cost fits the budget, else the newest sectors that fit."""
    cost, _ = tls_cost(len(time), float(np.ptp(time)), star)
    if cost <= budget_s:
        return np.ones(len(time), bool), "all sectors"
    use = np.zeros(len(time), bool)
    kept = []
    for s in sorted(np.unique(sector))[::-1]:
        trial = use | (sector == s)
        c, _ = tls_cost(int(trial.sum()), float(np.ptp(time[trial])), star)
        if kept and c > budget_s:
            break
        use, kept = trial, kept + [int(s)]
        if c > budget_s:  # even one sector is over budget: run it anyway (short curves are cheap in practice)
            break
    return use, f"newest sectors that fit the {budget_s:.0f} s budget: {sorted(kept)}"


@dataclass
class TLSResult:
    signal: Signal | None
    ran_on: str
    n_points: int
    n_periods: int
    seconds: float
    predicted_s: float
    sde: float = 0.0
    extra: dict = field(default_factory=dict)


def tls_search(time: np.ndarray, flux: np.ndarray, sector: np.ndarray, star: Star | None,
               budget_s: float = TLS_BUDGET_S, threads: int = 1) -> TLSResult:
    """TLS on the flattened curve (or its newest sectors). The best period becomes a Signal measured on the full
    stitched curve."""
    from transitleastsquares import transitleastsquares

    t_start = _time.perf_counter()
    if len(time) < 200:  # e.g. everything masked by known planets
        return TLSResult(None, "skipped: too few points", int(len(time)), 0, 0.0, 0.0)
    use, ran_on = tls_subset(time, sector, star, budget_s)
    t, f = time[use], flux[use]
    baseline = float(np.ptp(t)) if len(t) else 0.0
    if len(t) < 200 or baseline < 1.0:
        return TLSResult(None, ran_on, int(len(t)), 0, 0.0, 0.0)
    predicted, n_p = tls_cost(len(t), baseline, star)
    dy = np.full(len(f), robust_sigma(f) or 1e-3)
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            res = transitleastsquares(t, f, dy).power(
                period_min=0.5, period_max=max(baseline / 2, 0.51), oversampling_factor=TLS_OVERSAMPLE,
                duration_grid_step=1.1, use_threads=threads, show_progress_bar=False, T0_fit_margin=0.01,
                transit_depth_min=5e-6, **_tls_star(star))
    except Exception as exc:  # TLS raises on degenerate inputs (e.g. no period fits); BLS still covers the range
        return TLSResult(None, f"{ran_on}; TLS failed: {type(exc).__name__}", int(len(t)), n_p,
                         _time.perf_counter() - t_start, predicted)
    sde = float(res.SDE) if np.isfinite(res.SDE) else 0.0
    sig = None
    if np.isfinite(res.period) and np.isfinite(res.T0) and np.isfinite(res.duration) and res.duration > 0:
        sig = make_signal(time, flux, float(res.period), float(res.T0), float(res.duration), sde)
    return TLSResult(sig, ran_on, int(len(t)), int(len(res.periods)), _time.perf_counter() - t_start, predicted,
                     sde, {"tls_depth_ppm": round((1 - float(res.depth)) * 1e6, 1) if np.isfinite(res.depth) else None,
                           "tls_transit_count": int(res.transit_count), "tls_distinct_transit_count":
                           int(res.distinct_transit_count)})
