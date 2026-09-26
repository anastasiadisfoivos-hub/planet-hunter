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
from hunter.search import DURATIONS, Signal, harmonically_related, in_transit, search

from .catalogs import KnownSignal
from .lightcurve import StarLC

FLATTEN_WINDOW = 3 * float(DURATIONS.max())  # as in the pipeline
MAX_SIGNALS = 3
CONTINUE_MIN_SNR = 7.0  # keep looking for a further signal only while the last one was at least this strong
DEFAULT_KNOWN_DURATION_H = 3.0
MAX_TIMING_PAD_D = 0.5  # beyond this the ephemeris is too uncertain to mask usefully


@dataclass
class MaskedPlanet:
    name: str
    period: float
    t0: float
    half_width_d: float
    masked_points: int
    note: str

    def to_dict(self) -> dict:
        return {"name": self.name, "period_d": round(self.period, 7), "t0_btjd": round(self.t0, 5),
                "mask_half_width_h": round(self.half_width_d * 24, 2), "masked_points": self.masked_points,
                "note": self.note}


def known_transit_mask(time: np.ndarray, known: list[KnownSignal]) -> tuple[np.ndarray, list[MaskedPlanet]]:
    """Mask every listed transit with an ephemeris: 1.5x the listed duration, widened by 3 sigma of the
    propagated timing error (t0 error and period error times the number of orbits since t0)."""
    mask = np.zeros(len(time), bool)
    masked: list[MaskedPlanet] = []
    seen: list[float] = []
    for k in known:
        if not k.period or k.t0_btjd is None or len(time) == 0:
            continue
        if any(abs(k.period - p) / p < 0.001 for p in seen):  # same planet on two lists
            continue
        dur = (k.duration_h or DEFAULT_KNOWN_DURATION_H) / 24
        n_orbits = abs(float(np.median(time)) - k.t0_btjd) / k.period
        sigma_t = math.hypot(k.t0_err or 0.0, n_orbits * (k.period_err or 0.0))
        pad = 3 * sigma_t
        if pad > MAX_TIMING_PAD_D:
            masked.append(MaskedPlanet(k.name, k.period, k.t0_btjd, 0.0, 0,
                                       f"not masked: timing uncertainty {pad * 24:.1f} h is too large"))
            continue
        half = 0.75 * dur + pad
        m = in_transit(time, k.period, k.t0_btjd, 2 * half)
        mask |= m
        seen.append(k.period)
        masked.append(MaskedPlanet(k.name, k.period, k.t0_btjd, half, int(m.sum()),
                                   f"masked {'with listed duration' if k.duration_h else 'assuming a 3 h duration'}"))
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
