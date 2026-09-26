"""Multi-signal transit search with known transits masked out.

The pipeline's own driver (hunter.core._find_signals) cannot take a mask, so this is the same two-pass
scheme built from hunter's public pieces: flatten -> BLS -> re-flatten with the dips excluded from the
trend -> BLS again -> mask and look for the next signal. Known planets' transits (archive ephemerides) are
excluded from both the trend and the search, so a sibling search sees only the residuals.
"""

from __future__ import annotations

import math
import time as _time
from dataclasses import dataclass, field

import numpy as np

from hunter.clean import flatten_for_search
from hunter.search import DURATIONS, Signal, harmonically_related, in_transit
from hunter.search import search as _bls_search

from . import deep, detrend
from .catalogs import KnownSignal
from .lightcurve import StarLC

FLATTEN_WINDOW = 3 * float(DURATIONS.max())  # as in the pipeline
MAX_SIGNALS = 3
CONTINUE_MIN_SNR = 7.0  # keep looking for a further signal only while the last one was at least this strong
CONTINUE_MIN_SDE = 7.0  # ... and (deep search) this clear a peak in its periodogram
DEFAULT_KNOWN_DURATION_H = 3.0
MASK_HALF_DURATIONS = 1.0  # fixed mask: +-1 listed duration (2x the transit) plus the timing allowance
TTV_ALLOWANCE_FRAC = 0.02  # extra timing allowance, as a fraction of P, for planets the archive flags with TTVs
MAX_TIMING_PAD_D = 0.5  # beyond this a fixed mask is pointless; only the located dips are masked
LOCATE_MIN_SNR = 5.0  # a dip near a predicted transit is taken as the transit if it is this significant
LOCATE_MAX_WINDOW_FRAC = 0.3  # never look further than 0.3 P from the prediction
TLS_MIN_BUDGET_S = 5.0  # a later round runs TLS only if at least this much of the star's TLS budget is left


def search(time: np.ndarray, flux: np.ndarray, groups: np.ndarray) -> Signal | None:
    """hunter.search.search, but None instead of an IndexError when a very wide box leaves no
    out-of-transit points to measure the noise on (happens on heavily masked data)."""
    try:
        return _bls_search(time, flux, groups)
    except IndexError:
        return None


@dataclass
class MaskedPlanet:
    name: str
    period: float
    t0: float
    half_width_d: float
    masked_points: int
    note: str
    located: int = 0  # transits found in the data near their predicted time and masked there
    median_offset_h: float | None = None  # observed minus predicted mid-time of the located transits

    def to_dict(self) -> dict:
        return {"name": self.name, "period_d": round(self.period, 7), "t0_btjd": round(self.t0, 5),
                "mask_half_width_h": round(self.half_width_d * 24, 2), "masked_points": self.masked_points,
                "transits_located": self.located,
                "median_offset_h": None if self.median_offset_h is None else round(self.median_offset_h, 2),
                "note": self.note}


def _timing(k: KnownSignal, time: np.ndarray) -> tuple[float, float]:
    """(3-sigma propagated timing error, TTV allowance), days."""
    n_orbits = abs(float(np.median(time)) - k.t0_btjd) / k.period
    sigma_t = math.hypot(k.t0_err or 0.0, n_orbits * (k.period_err or 0.0))
    return 3 * sigma_t, (TTV_ALLOWANCE_FRAC * k.period if k.ttv_flag else 0.0)


def _locate(t: np.ndarray, f: np.ndarray, sigma: float, centres: np.ndarray, window: float,
            dur: float) -> list[tuple[float, float]]:
    """For each predicted centre, the deepest box of width dur within +-window: (observed centre, offset)
    when it is at least LOCATE_MIN_SNR deep. t must be sorted; f is flattened (baseline 1)."""
    csum = np.concatenate([[0.0], np.cumsum(f)])
    found = []
    step = dur / 8
    for c in centres:
        grid = np.arange(c - window, c + window + step / 2, step)
        lo = np.searchsorted(t, grid - dur / 2)
        hi = np.searchsorted(t, grid + dur / 2)
        n = hi - lo
        ok = n >= 3
        if not ok.any():
            continue
        mean = np.where(ok, (csum[hi] - csum[lo]) / np.maximum(n, 1), np.inf)
        i = int(np.argmin(mean))
        snr = (1 - mean[i]) / (sigma / math.sqrt(n[i]))
        if snr >= LOCATE_MIN_SNR:
            found.append((float(grid[i]), float(grid[i] - c)))
    return found


def known_transit_mask(time: np.ndarray, flux: np.ndarray | None,
                       known: list[KnownSignal]) -> tuple[np.ndarray, list[MaskedPlanet]]:
    """Mask the transits of every listed signal with an ephemeris, in two ways.

    1. Fixed: +-(1 listed duration + 3 sigma of the propagated timing error + a TTV allowance of 2% of P when
       the archive flags TTVs) around every predicted mid-time.
    2. Observed: near each predicted mid-time (within the same allowance, at least 1.5 durations) the
       deepest dip of the listed duration is located; if it is >= 5 sigma it is masked +-1 duration around
       where it actually is. This follows transit-timing variations and drifted or rounded ephemerides.

    Every list's entry is used (a TOI often has a newer ephemeris than the confirmed-planet row), so the
    union of all predictions is masked.
    """
    mask = np.zeros(len(time), bool)
    masked: list[MaskedPlanet] = []
    usable = [k for k in known if k.period and k.t0_btjd is not None]
    if len(time) == 0 or not usable:
        return mask, masked
    if flux is not None:
        # Preliminary flattening with generous fixed masks, so the dips being located do not bend the trend.
        pre = np.zeros(len(time), bool)
        for k in usable:
            dur = (k.duration_h or DEFAULT_KNOWN_DURATION_H) / 24
            pad, ttv = _timing(k, time)
            pre |= in_transit(time, k.period, k.t0_btjd, 2 * (1.5 * dur + min(pad + ttv, MAX_TIMING_PAD_D)))
        flat, keep = flatten_for_search(time, flux, FLATTEN_WINDOW, transit_mask=pre)
        good = keep & np.isfinite(flat)
        t_ok, f_ok = time[good], flat[good]
        from hunter.clean import robust_sigma
        sigma = robust_sigma(f_ok[~pre[good]]) if (~pre[good]).sum() > 50 else robust_sigma(f_ok)
    for k in usable:
        dur = (k.duration_h or DEFAULT_KNOWN_DURATION_H) / 24
        pad, ttv = _timing(k, time)
        allowance = pad + ttv
        m = np.zeros(len(time), bool)
        notes = []
        if allowance <= MAX_TIMING_PAD_D:
            half = MASK_HALF_DURATIONS * dur + allowance
            m |= in_transit(time, k.period, k.t0_btjd, 2 * half)
            notes.append("fixed mask " + ("with listed duration" if k.duration_h else "assuming a 3 h duration")
                         + (", TTV allowance" if ttv else ""))
        else:
            half = 0.0
            notes.append(f"no fixed mask: timing uncertainty {allowance * 24:.1f} h is too large")
        located, offsets = 0, []
        if flux is not None and sigma and np.isfinite(sigma):
            e0, e1 = np.floor((time.min() - k.t0_btjd) / k.period), np.ceil((time.max() - k.t0_btjd) / k.period)
            centres = k.t0_btjd + np.arange(e0, e1 + 1) * k.period
            window = min(max(1.5 * dur, allowance + dur), LOCATE_MAX_WINDOW_FRAC * k.period)
            for centre, off in _locate(t_ok, f_ok, sigma, centres, window, dur):
                m |= np.abs(time - centre) < MASK_HALF_DURATIONS * dur
                located += 1
                offsets.append(off)
            if located:
                notes.append(f"{located} transits located in the data and masked where they are")
        mask |= m
        masked.append(MaskedPlanet(k.name, k.period, k.t0_btjd, half, int(m.sum()), "; ".join(notes), located,
                                   float(np.median(offsets)) * 24 if offsets else None))
    return mask, masked


@dataclass
class SearchOutput:
    signals: list[Signal]
    flat: np.ndarray  # flattened flux (short window) with all found signals and known transits excluded from the trend
    use: np.ndarray  # points usable for vetting (upward outliers and known transits removed)
    premask: np.ndarray
    flat_long: np.ndarray | None = None  # the same with the long-search window (deep search only)
    use_long: np.ndarray | None = None
    methods: list[dict] = field(default_factory=list)  # per signal: which searches found it, which one was kept
    runtime: dict = field(default_factory=dict)  # seconds per search, TLS coverage, long-BLS grid size
    long_window_d: float | None = None

    def vetting_curve(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """(flat, use) to vet signal i on: the long-window curve for signals kept from bls_long or tls."""
        if self.flat_long is not None and i < len(self.methods) and self.methods[i]["kept"] != "bls_short":
            return self.flat_long, self.use_long
        return self.flat, self.use


def long_window(star, baseline: float) -> float:
    """3x the longest duration the long-period BLS looks for on this star and baseline (0.9-3 d)."""
    rho, _ = deep.star_density(star)
    blocks = deep.long_blocks(deep.SHORT_PMAX, baseline / 2, rho) if baseline / 2 > deep.SHORT_PMAX else []
    longest = max((b[2].max() for b in blocks), default=1.5 * deep.central_duration(max(baseline / 2, 1.0), rho / 3))
    return float(min(3 * deep.LONG_DURATION_MAX_D, max(FLATTEN_WINDOW, 3 * longest)))


def _mask_of(t: np.ndarray, sigs: list[Signal], base: np.ndarray) -> np.ndarray:
    m = base.copy()
    for s in sigs:
        m |= in_transit(t, s.period, s.t0, s.duration, scale=2.0)
    return m


def _short_round(t, f, g, mask) -> Signal | None:
    """The pipeline's two-pass BLS (0.5-15 d): flatten, search, re-flatten without its dips, search again."""
    flat, keep = flatten_for_search(t, f, FLATTEN_WINDOW, transit_mask=mask)
    use = keep & ~mask
    first = search(t[use], flat[use], g[use])
    if first is None:
        return None
    trend_mask = mask | in_transit(t, first.period, first.t0, first.duration, scale=2.0)
    flat2, keep2 = flatten_for_search(t, f, FLATTEN_WINDOW, transit_mask=trend_mask)
    use2 = keep2 & ~mask
    return search(t[use2], flat2[use2], g[use2]) or first


def _remeasure(t, f, mask, sig: Signal, window: float, pipeline_flatten: bool = False) -> Signal:
    """Measure a found signal on the native-cadence curve: re-flatten with its dips left out of the trend, then
    depth, odd/even depths, epochs with data and SNR (deep.make_signal). Search periods and SDE are kept."""
    trend_mask = mask | in_transit(t, sig.period, sig.t0, sig.duration, scale=2.0)
    if pipeline_flatten:
        flat, keep = flatten_for_search(t, f, window, transit_mask=trend_mask)
    else:
        flat, keep = detrend.flatten(t, f, window, trend_mask)
    use = keep & ~mask
    again = deep.make_signal(t[use], flat[use], sig.period, sig.t0, sig.duration, sig.sde)
    return again or sig


@dataclass
class _Curves:
    """The native-cadence curve (measuring, vetting) and a 10-min binned copy (searching)."""
    t: np.ndarray
    f: np.ndarray
    g: np.ndarray
    tb: np.ndarray
    fb: np.ndarray
    gb: np.ndarray
    idx: np.ndarray  # for each binned point, a native point inside its bin (to carry masks over)

    def to_binned(self, native_mask: np.ndarray) -> np.ndarray:
        return native_mask[self.idx]


def _curves(lc: StarLC) -> _Curves:
    from .lightcurve import BIN_MINUTES, bin_lc

    lb = bin_lc(lc, BIN_MINUTES) if lc.bin_minutes is None else lc
    i = np.clip(np.searchsorted(lc.time, lb.time), 0, len(lc.time) - 1)
    j = np.clip(i - 1, 0, len(lc.time) - 1)
    idx = np.where(np.abs(lc.time[j] - lb.time) < np.abs(lc.time[i] - lb.time), j, i)
    return _Curves(lc.time, lc.flux, lc.sector, lb.time, lb.flux, lb.sector, idx)


def _deep_round(c: _Curves, mask, star, window, tls_left: float, runtime: dict) -> tuple[Signal | None, dict]:
    """Search the binned copy with all three searches, measure each find on the native curve, keep the best."""
    mb = c.to_binned(mask)
    tic = _time.perf_counter()
    found: list[tuple[Signal, str]] = []
    s = _short_round(c.tb, c.fb, c.gb, mb)
    runtime["bls_short_s"] = runtime.get("bls_short_s", 0.0) + _time.perf_counter() - tic
    if s is not None:
        found.append((s, "bls_short"))
    tic = _time.perf_counter()
    flat, keep = detrend.flatten(c.tb, c.fb, window, mb)
    use = keep & ~mb
    runtime["detrend_long_s"] = runtime.get("detrend_long_s", 0.0) + _time.perf_counter() - tic
    rho, _ = deep.star_density(star)
    lr = deep.bls_long(c.tb[use], flat[use], rho)
    runtime["bls_long_s"] = runtime.get("bls_long_s", 0.0) + lr.seconds
    runtime["bls_long_periods"] = max(runtime.get("bls_long_periods", 0), lr.n_periods)
    runtime["bls_long_pmax_d"] = round(lr.pmax, 2)
    if lr.signal is not None:
        found.append((lr.signal, "bls_long"))
    if tls_left >= TLS_MIN_BUDGET_S:
        tr = deep.tls_search(c.tb[use], flat[use], c.gb[use], star, budget_s=tls_left)
        runtime["tls_s"] = runtime.get("tls_s", 0.0) + tr.seconds
        runtime.setdefault("tls_runs", []).append({"ran_on": tr.ran_on, "points": tr.n_points,
                                                   "periods": tr.n_periods, "seconds": round(tr.seconds, 1),
                                                   "predicted_s": round(tr.predicted_s, 1),
                                                   "sde": round(tr.sde, 2)})
        if tr.signal is not None:
            found.append((tr.signal, "tls"))
    else:
        runtime.setdefault("tls_runs", []).append({"ran_on": "skipped: TLS budget used up"})
    if not found:
        return None, {}
    tic = _time.perf_counter()
    cands = [(_remeasure(c.t, c.f, mask, sg, FLATTEN_WINDOW if m == "bls_short" else window, m == "bls_short"), m)
             for sg, m in found]
    runtime["measure_s"] = runtime.get("measure_s", 0.0) + _time.perf_counter() - tic
    best, kept = max(cands, key=lambda x: x[0].snr)
    found_by = sorted({m for sg, m in cands if harmonically_related(sg.period, best.period)})
    others = {m: {"period_d": round(sg.period, 6), "snr": round(sg.snr, 2), "sde": round(sg.sde, 2)}
              for sg, m in cands}
    return best, {"kept": kept, "found_by": found_by, "each_search": others}


def find_signals(lc: StarLC, premask: np.ndarray | None = None, max_signals: int = MAX_SIGNALS,
                 star=None, deep_search: bool = False, tls_budget_s: float = deep.TLS_BUDGET_S) -> SearchOutput:
    """Up to max_signals periodic signals, each found with the others masked.

    deep_search=False: the pipeline's BLS only (0.5-15 d), as HUNT ran it.
    deep_search=True: every round searches a 10-min binned copy with bls_short, bls_long (15 d to half the
    baseline) and TLS (within tls_budget_s over the whole star), measures each find on the native-cadence curve
    (binning smears transits under an hour), keeps the one with the highest SNR and records which searches found
    the same period. Another round follows while the last signal had SNR >= 7 and (deep only) SDE >= 7: a
    red-noise bump from the long-period search with a low SDE is not worth masking and searching around."""
    t, f, g = lc.time, lc.flux, lc.sector
    premask = np.zeros(len(t), bool) if premask is None else premask
    signals: list[Signal] = []
    methods: list[dict] = []
    runtime: dict = {}
    window = long_window(star, float(np.ptp(t)) if len(t) else 0.0) if deep_search else None
    curves = _curves(lc) if deep_search else None

    def one_round(mask) -> tuple[Signal | None, dict]:
        if not deep_search:
            return _short_round(t, f, g, mask), {"kept": "bls_short", "found_by": ["bls_short"]}
        return _deep_round(curves, mask, star, window, tls_budget_s - runtime.get("tls_s", 0.0), runtime)

    def go_on(sig: Signal) -> bool:
        return sig.snr >= CONTINUE_MIN_SNR and (not deep_search or sig.sde >= CONTINUE_MIN_SDE)

    first, info = one_round(premask)
    if first is not None:
        signals.append(first)
        methods.append(info)
    while signals and len(signals) < max_signals and go_on(signals[-1]):
        nxt, info = one_round(_mask_of(t, signals, premask))
        if nxt is None or any(harmonically_related(nxt.period, s.period) for s in signals):
            break
        signals.append(nxt)
        methods.append(info)

    final_mask = _mask_of(t, signals, premask)
    flat, keep = flatten_for_search(t, f, FLATTEN_WINDOW, transit_mask=final_mask)
    out = SearchOutput(signals, flat, keep & ~premask, premask, methods=methods, runtime=runtime,
                       long_window_d=window)
    if deep_search:
        flat_l, keep_l = detrend.flatten(t, f, window, final_mask)
        out.flat_long, out.use_long = flat_l, keep_l & ~premask
    return out
