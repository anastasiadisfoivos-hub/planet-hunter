"""Multi-signal transit search with known transits masked out.

The pipeline's own driver (hunter.core._find_signals) cannot take a mask, so this is the same two-pass
scheme built from hunter's public pieces: flatten -> BLS -> re-flatten with the dips excluded from the
trend -> BLS again -> mask and look for the next signal. Known planets' transits (archive ephemerides) are
excluded from both the trend and the search, so a sibling search sees only the residuals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from hunter.clean import flatten_for_search
from hunter.search import DURATIONS, Signal, harmonically_related, in_transit
from hunter.search import search as _bls_search

from .catalogs import KnownSignal
from .lightcurve import StarLC

FLATTEN_WINDOW = 3 * float(DURATIONS.max())  # as in the pipeline
MAX_SIGNALS = 3
CONTINUE_MIN_SNR = 7.0  # keep looking for a further signal only while the last one was at least this strong
DEFAULT_KNOWN_DURATION_H = 3.0
MASK_HALF_DURATIONS = 1.0  # fixed mask: +-1 listed duration (2x the transit) plus the timing allowance
TTV_ALLOWANCE_FRAC = 0.02  # extra timing allowance, as a fraction of P, for planets the archive flags with TTVs
MAX_TIMING_PAD_D = 0.5  # beyond this a fixed mask is pointless; only the located dips are masked
LOCATE_MIN_SNR = 5.0  # a dip near a predicted transit is taken as the transit if it is this significant
LOCATE_MAX_WINDOW_FRAC = 0.3  # never look further than 0.3 P from the prediction


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
    flat: np.ndarray  # flattened flux with all found signals and known transits excluded from the trend
    use: np.ndarray  # points usable for vetting (upward outliers and known transits removed)
    premask: np.ndarray


def find_signals(lc: StarLC, premask: np.ndarray | None = None, max_signals: int = MAX_SIGNALS) -> SearchOutput:
    t, f, g = lc.time, lc.flux, lc.sector
    premask = np.zeros(len(t), bool) if premask is None else premask
    flat, keep = flatten_for_search(t, f, FLATTEN_WINDOW, transit_mask=premask)
    use = keep & ~premask
    signals: list[Signal] = []
    first = search(t[use], flat[use], g[use])
    if first is not None:
        trend_mask = premask | in_transit(t, first.period, first.t0, first.duration, scale=2.0)
        flat2, keep2 = flatten_for_search(t, f, FLATTEN_WINDOW, transit_mask=trend_mask)
        use2 = keep2 & ~premask
        signals.append(search(t[use2], flat2[use2], g[use2]) or first)

    while signals and len(signals) < max_signals and signals[-1].snr >= CONTINUE_MIN_SNR:
        masked = premask.copy()
        for s in signals:
            masked |= in_transit(t, s.period, s.t0, s.duration, scale=2.0)
        flat3, keep3 = flatten_for_search(t, f, FLATTEN_WINDOW, transit_mask=masked)
        sel = keep3 & ~masked
        nxt = search(t[sel], flat3[sel], g[sel])
        if nxt is None or any(harmonically_related(nxt.period, s.period) for s in signals):
            break
        signals.append(nxt)

    final_mask = premask.copy()
    for s in signals:
        final_mask |= in_transit(t, s.period, s.t0, s.duration, scale=2.0)
    flat, keep = flatten_for_search(t, f, FLATTEN_WINDOW, transit_mask=final_mask)
    return SearchOutput(signals, flat, keep & ~premask, premask)
