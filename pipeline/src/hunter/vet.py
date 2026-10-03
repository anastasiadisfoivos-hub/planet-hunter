"""Vetting tests. Each returns pass/fail (or None when it cannot be run) plus a plain-English reason."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .clean import robust_sigma
from .measure import Size
from .search import Signal, in_transit

MIN_SNR = 7.0
MAX_RADIUS_RJUP = 2.0
ODD_EVEN_SIGMA = 3.0
ODD_EVEN_MIN_FRACTION = 0.05  # ignore statistically "significant" but tiny differences on very bright stars
SECONDARY_SIGMA = 3.0
SECONDARY_MIN_FRACTION = 0.10  # hot-Jupiter occultations are a few % of the transit depth at most


@dataclass
class VetResult:
    name: str
    passed: bool | None
    reason: str
    value: float | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["value"] is not None:
            d["value"] = round(float(d["value"]), 6)
        return d


def odd_even(sig: Signal) -> VetResult:
    diff = abs(sig.depth_odd - sig.depth_even)
    err = float(np.hypot(sig.depth_odd_err, sig.depth_even_err)) or 1e-12
    nsig = diff / err
    frac = diff / max(abs(sig.depth), 1e-12)
    if nsig > ODD_EVEN_SIGMA and frac > ODD_EVEN_MIN_FRACTION:
        return VetResult("odd_even", False,
                         f"Alternate dips have different depths ({sig.depth_odd * 100:.3f}% vs "
                         f"{sig.depth_even * 100:.3f}%, {nsig:.1f} sigma apart). A planet makes identical dips; "
                         f"two stars eclipsing each other usually do not, so the true period is likely "
                         f"{2 * sig.period:.4f} days.", nsig)
    return VetResult("odd_even", True,
                     f"Alternate dips have matching depths ({sig.depth_odd * 100:.3f}% vs "
                     f"{sig.depth_even * 100:.3f}%), as expected for a planet.", nsig)


def secondary_eclipse(time: np.ndarray, flux: np.ndarray, sig: Signal) -> tuple[VetResult, dict]:
    """Look for a dip of the same width anywhere between phase 0.4 and 0.6 (allows mildly eccentric orbits)."""
    primary = in_transit(time, sig.period, sig.t0, sig.duration, scale=1.5)
    phase = ((time - sig.t0) / sig.period) % 1.0
    oot = ~primary
    base = np.median(flux[oot])
    sigma = robust_sigma(flux[oot])
    half_w = 0.5 * sig.duration / sig.period
    best = {"depth": 0.0, "err": np.inf, "nsig": 0.0, "phase": 0.5}
    for center in np.arange(0.4, 0.6 + 1e-9, max(half_w / 2, 0.002)):
        box = oot & (np.abs(phase - center) < half_w)
        n = int(box.sum())
        if n < 5:
            continue
        depth = base - float(np.mean(flux[box]))
        err = sigma / np.sqrt(n)
        if depth / err > best["nsig"]:
            best = {"depth": depth, "err": err, "nsig": depth / err, "phase": float(center)}
    frac = best["depth"] / max(sig.depth, 1e-12)
    if best["nsig"] > SECONDARY_SIGMA and frac > SECONDARY_MIN_FRACTION:
        return VetResult("secondary_eclipse", False,
                         f"There is a second, shallower dip at phase {best['phase']:.2f} "
                         f"({best['depth'] * 100:.3f}% deep, {frac * 100:.0f}% of the main dip). A dip that big "
                         f"halfway round the orbit means the companion gives off a lot of light itself, "
                         f"like a star does.", best["nsig"]), best
    reason = (f"Halfway round the orbit there is a faint {best['depth'] * 1e6:.0f} ppm dip at phase "
              f"{best['phase']:.2f}, small enough to be a planet passing behind its star."
              if best["nsig"] > SECONDARY_SIGMA
              else "Halfway round the orbit there is no significant dip, consistent with a planet.")
    return VetResult("secondary_eclipse", True, reason, best["nsig"]), best


def size(sz: Size) -> VetResult:
    if sz.radius_rjup is None:
        return VetResult("size", None, sz.note + " The size test was skipped.")
    # Fail only when even the low end of the likely range is too big (star-size and depth errors included).
    if sz.lower_rjup is not None and sz.lower_rjup > MAX_RADIUS_RJUP:
        return VetResult("size", False,
                         f"{sz.note} Even the low end is bigger than any known planet (limit "
                         f"{MAX_RADIUS_RJUP:.0f} Jupiter radii), so it is too large to be a planet.", sz.radius_rjup)
    if sz.radius_rjup > MAX_RADIUS_RJUP:
        return VetResult("size", True,
                         f"{sz.note} The best estimate is above the {MAX_RADIUS_RJUP:.0f} Jupiter-radius limit but "
                         f"the low end is not, so a planet cannot be ruled out on size.", sz.radius_rjup)
    return VetResult("size", True, f"{sz.note} That is within the size range of planets.", sz.radius_rjup)


def snr(sig: Signal) -> VetResult:
    if sig.snr < MIN_SNR:
        return VetResult("snr", False,
                         f"The dip stands only {sig.snr:.1f} times above the noise (need {MIN_SNR:.0f}), "
                         f"so there is no convincing repeating signal.", sig.snr)
    return VetResult("snr", True,
                     f"The dip stands {sig.snr:.0f} times above the noise over {sig.n_transits} events.", sig.snr)
