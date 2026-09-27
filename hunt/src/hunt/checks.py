"""Vetting checks for one signal: the pipeline's four plus five more.

Every check returns a value, pass / fail (None = could not run, or a flag that is not a test), a plain
reason, and a margin in [0, 1] (how comfortably it passed; 0 at the threshold) used by the score.

Pipeline (hunter.vet): snr, odd_even, secondary_eclipse, size.
Added here: period_alias (P/2, 2P, 3P), momentum_dump (transits on dumps / quality-flagged cadences),
sector_depth (depth consistent between sectors), duration (plausible for the star's density),
three_dips (the signal does not rest on one dip), single_sector (flag only).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace

import numpy as np
from scipy import stats

from hunter.clean import robust_sigma
from hunter.measure import implied_radius
from hunter.search import Signal, in_transit
from hunter.vet import VetResult, odd_even, secondary_eclipse, size, snr

from .stars import RHO_SUN_KG_M3, Star

G = 6.674e-11
ALIAS_MIN_RATIO = 0.5  # a group of dips shallower than half the rest (and > 3 sigma) means a wrong period
ALIAS_SIGMA = 3.0
DUMP_WINDOW_PAD_D = 30 / 1440  # a dump within half a duration + 30 min of mid-transit counts as coinciding ...
DUMP_CENTRE_D = 1 / 24  # ... but at most 1 h + 30 min: a day-long transit nearly always contains a dump
# somewhere; only one near its middle can make the dip (dumps elsewhere are caught by the depth test below)
DUMP_MAX_FRACTION = 0.5
SECTOR_P_MIN = 1e-3
SECTOR_MAX_SPREAD = 0.5
DURATION_MIN_RATIO = 0.1
DURATION_MAX_RATIO = 2.0  # BLS duration grid is coarse (~25% steps) and eccentric orbits run long
THREE_DIPS_MIN_RATIO = 0.5  # without its strongest dip, the signal must keep half its depth ...
THREE_DIPS_SIGMA = 3.0  # ... and still be this significant
MUST_RUN = ("snr", "odd_even", "secondary_eclipse", "size", "period_alias", "momentum_dump", "duration",
            "three_dips")


@dataclass
class Check:
    name: str
    passed: bool | None
    value: float | None
    reason: str
    margin: float | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("value", "margin"):
            if d[k] is not None:
                d[k] = round(float(d[k]), 6) if math.isfinite(d[k]) else None
        return d


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x))) if math.isfinite(x) else 0.0


def _from_vet(v: VetResult, margin: float | None) -> Check:
    return Check(v.name, v.passed, v.value, v.reason, margin)


@dataclass
class Epochs:
    epoch: np.ndarray
    centre: np.ndarray
    sector: np.ndarray
    depth: np.ndarray
    err: np.ndarray


def red_noise_factor(t: np.ndarray, f: np.ndarray, duration: float) -> float:
    """beta >= 1: scatter of duration-long bin means over what white noise predicts."""
    edges = np.arange(t.min(), t.max() + duration, duration)
    idx = np.digitize(t, edges)
    _, inv, counts = np.unique(idx, return_inverse=True, return_counts=True)
    means = np.bincount(inv, weights=f) / counts
    full = counts >= 0.5 * np.median(counts)
    if full.sum() < 10:
        return 1.0
    white = robust_sigma(f) / math.sqrt(float(np.median(counts[full])))
    return max(1.0, robust_sigma(means[full]) / white) if white > 0 else 1.0


def epoch_depths(t: np.ndarray, f: np.ndarray, g: np.ndarray, sig: Signal) -> Epochs:
    """Depth of every observed transit against its local baseline, errors inflated for red noise."""
    P, t0, dur = sig.period, sig.t0, sig.duration
    e = np.round((t - t0) / P).astype(np.int64)
    dt = t - (t0 + e * P)
    intr = np.abs(dt) < dur / 2
    near = (np.abs(dt) > 0.75 * dur) & (np.abs(dt) < min(2.5 * dur, 0.45 * P))
    oot = ~in_transit(t, P, t0, dur, scale=1.5)
    sigma = robust_sigma(f[oot]) if oot.sum() > 10 else robust_sigma(f)
    beta = red_noise_factor(t[oot], f[oot], dur) if oot.sum() > 50 else 1.0
    base_all = float(np.median(f[oot])) if oot.any() else 1.0
    rows = []
    for k in np.unique(e[intr]):
        a = intr & (e == k)
        n_in = int(a.sum())
        if n_in < 3:
            continue
        b = near & (e == k)
        n_b = int(b.sum())
        base = float(np.median(f[b])) if n_b >= 5 else base_all
        err = sigma * beta * math.sqrt(1 / n_in + (1 / n_b if n_b >= 5 else 0.0))
        rows.append((k, t0 + k * P, int(np.median(g[a])), base - float(np.mean(f[a])), err))
    if not rows:
        return Epochs(*(np.array([]) for _ in range(5)))
    arr = np.array(rows, dtype=float)
    return Epochs(arr[:, 0].astype(int), arr[:, 1], arr[:, 2].astype(int), arr[:, 3], arr[:, 4])


def odd_even_scale(ep: "Epochs") -> float:
    """Over-dispersion of per-dip depths WITHIN the odd and within the even dips (sqrt of reduced chi-square about
    each group's own mean, at least 1). Depths that change between sectors (crowding corrections differ per
    sector) then do not look like an odd/even difference, while an eclipsing binary's alternation, which is
    between the groups, is untouched."""
    if len(ep.epoch) < 3:
        return 1.0
    chi2, dof = 0.0, 0
    for par in (0, 1):
        m = ep.epoch % 2 == par
        if m.sum() >= 2:
            mu, _ = _wmean(ep.depth[m], ep.err[m])
            chi2 += float(np.sum((ep.depth[m] - mu) ** 2 / ep.err[m] ** 2))
            dof += int(m.sum()) - 1
    return float(max(1.0, math.sqrt(chi2 / dof))) if dof > 0 else 1.0


def odd_even_signal(sig: Signal, ep: "Epochs", scale: float) -> Signal:
    """The signal with odd / even depths from the per-dip depths (each against its own local baseline, errors
    inflated for red noise) when both parities have a dip, else BLS's; errors times the over-dispersion scale.
    A global baseline mis-measures a dip next to a sector edge (TOI-2180 b's sector-48 transit starts 0.35 d
    after the first cadence) and, with three transits, that alone looked like an odd/even difference."""
    odd, even = ep.epoch % 2 == 1, ep.epoch % 2 == 0
    if odd.any() and even.any():
        (do, eo), (de, ee) = _wmean(ep.depth[odd], ep.err[odd]), _wmean(ep.depth[even], ep.err[even])
        return replace(sig, depth_odd=do, depth_odd_err=eo * scale, depth_even=de, depth_even_err=ee * scale)
    return replace(sig, depth_odd_err=sig.depth_odd_err * scale, depth_even_err=sig.depth_even_err * scale)


def _wmean(d: np.ndarray, e: np.ndarray) -> tuple[float, float]:
    w = 1 / e**2
    return float(np.sum(w * d) / np.sum(w)), float(1 / math.sqrt(np.sum(w)))


# ---- added checks ---------------------------------------------------------------------------------------

def period_alias(t: np.ndarray, f: np.ndarray, sig: Signal, ep: Epochs) -> Check:
    P, dur = sig.period, sig.duration
    notes, worst_margin, failed = [], 1.0, []

    # P/2: is there an equally deep dip half an orbit later? (then the events we "skipped" are real)
    phase = ((t - sig.t0) / P + 0.5) % 1.0 - 0.5
    oot = ~in_transit(t, P, sig.t0, dur, scale=1.5)
    box = oot & (np.abs(np.abs(phase) - 0.5) < 0.5 * dur / P)
    half_ratio = 0.0
    if box.sum() >= 5:
        sigma = robust_sigma(f[oot])
        d_half = float(np.median(f[oot]) - np.mean(f[box]))
        err = sigma / math.sqrt(box.sum())
        half_ratio = d_half / max(sig.depth, 1e-12)
        if half_ratio > ALIAS_MIN_RATIO and d_half / err > ALIAS_SIGMA:
            failed.append(f"half an orbit later there is a dip {half_ratio * 100:.0f}% as deep, so the true period "
                          f"is probably {P / 2:.4f} days (P/2)")
        worst_margin = min(worst_margin, _clip01((ALIAS_MIN_RATIO - half_ratio) / ALIAS_MIN_RATIO))
        notes.append(f"P/2: dip at half phase {half_ratio * 100:.0f}% of the main one")

    # 2P and 3P: split the dips into every-2nd / every-3rd groups; all groups must be about equally deep.
    min_ratio = 1.0
    for k in (2, 3):
        if len(ep.epoch) < k:
            continue
        groups = [ep.epoch % k == c for c in range(k)]
        if sum(g.any() for g in groups) < 2:
            continue
        means = [(_wmean(ep.depth[g], ep.err[g]) if g.any() else None) for g in groups]
        for c, m in enumerate(means):
            if m is None:
                continue
            rest = [x for j, x in enumerate(means) if j != c and x is not None]
            rd, re = _wmean(np.array([x[0] for x in rest]), np.array([x[1] for x in rest]))
            if rd <= 0:
                continue
            ratio = m[0] / rd
            min_ratio = min(min_ratio, ratio)
            if ratio < ALIAS_MIN_RATIO and (rd - m[0]) / math.hypot(re, m[1]) > ALIAS_SIGMA:
                failed.append(f"every {'second' if k == 2 else 'third'} dip is much shallower "
                              f"({ratio * 100:.0f}% of the others), so the true period may be {k * P:.4f} days "
                              f"({k}P)")
                break
        notes.append(f"{k}P: shallowest group {min_ratio * 100:.0f}% of the rest")
        worst_margin = min(worst_margin, _clip01((min_ratio - ALIAS_MIN_RATIO) / (1 - ALIAS_MIN_RATIO)))

    if failed:
        return Check("period_alias", False, min_ratio, "The period may be wrong: " + "; ".join(failed) + ".", 0.0)
    if not notes:
        return Check("period_alias", None, None, "Too few dips to test the period against P/2, 2P and 3P.")
    return Check("period_alias", True, min_ratio,
                 "The period holds up against P/2, 2P and 3P: " + "; ".join(notes) + ".", worst_margin)


def momentum_dump(ep: Epochs, sig: Signal, dumps: np.ndarray, flagged: np.ndarray, quality_read: bool) -> Check:
    if len(ep.epoch) == 0:
        return Check("momentum_dump", None, None, "No individual dips could be measured.")
    window = min(sig.duration / 2, DUMP_CENTRE_D) + DUMP_WINDOW_PAD_D

    def hits(times: np.ndarray) -> np.ndarray:
        if len(times) == 0:
            return np.zeros(len(ep.centre), bool)
        i = np.searchsorted(times, ep.centre)
        lo = np.abs(ep.centre - times[np.clip(i - 1, 0, len(times) - 1)])
        hi = np.abs(times[np.clip(i, 0, len(times) - 1)] - ep.centre)
        return np.minimum(lo, hi) < window

    on_dump, on_flag = hits(dumps), hits(flagged)
    bad = on_dump | on_flag
    frac = float(bad.mean())
    n_clean = int((~bad).sum())
    caveat = "" if quality_read else " (quality flags could not be read for every file)"
    what = (f"{int(on_dump.sum())} of {len(bad)} dips coincide with a momentum dump and {int((on_flag & ~on_dump).sum())} "
            f"more with quality-flagged cadences")
    if n_clean < 2:
        return Check("momentum_dump", False, frac,
                     f"{what}; fewer than two dips are clean, so the signal may come from the spacecraft{caveat}.", 0.0)
    all_d, all_e = _wmean(ep.depth, ep.err)
    clean_d, clean_e = _wmean(ep.depth[~bad], ep.err[~bad])
    if clean_d < 0.5 * all_d and (all_d - clean_d) / math.hypot(all_e, clean_e) > 3:
        return Check("momentum_dump", False, frac,
                     f"{what}; without them the dip is only {clean_d / all_d * 100:.0f}% as deep, so the "
                     f"spacecraft events drive the signal{caveat}.", 0.0)
    if frac > DUMP_MAX_FRACTION:
        return Check("momentum_dump", False, frac,
                     f"{what}; that is more than half of them, a warning sign of a spacecraft artefact{caveat}.", 0.0)
    return Check("momentum_dump", True, frac,
                 f"{what}; the clean dips alone are {clean_d / all_d * 100:.0f}% as deep as all of them, so the "
                 f"signal does not come from spacecraft events{caveat}.",
                 _clip01(1 - frac / DUMP_MAX_FRACTION))


def sector_depth(ep: Epochs) -> tuple[Check, dict]:
    per = {}
    for s in np.unique(ep.sector):
        m = ep.sector == s
        d, e = _wmean(ep.depth[m], ep.err[m])
        per[int(s)] = {"depth_ppm": round(d * 1e6, 1), "err_ppm": round(e * 1e6, 1), "n_transits": int(m.sum())}
    if len(per) < 2:
        return Check("sector_depth", None, None,
                     "Transits were seen in only one sector, so depths cannot be compared between sectors."), per
    d = np.array([v["depth_ppm"] for v in per.values()])
    e = np.array([v["err_ppm"] for v in per.values()])
    mean, _ = _wmean(d, e)
    chi2 = float(np.sum((d - mean) ** 2 / e**2))
    p = float(stats.chi2.sf(chi2, len(d) - 1))
    spread = float((d.max() - d.min()) / max(abs(mean), 1e-9))
    listing = ", ".join(f"S{s} {v['depth_ppm']:.0f}±{v['err_ppm']:.0f}" for s, v in per.items())
    margin = _clip01(1 + math.log10(max(p, 1e-300)) / 3)
    if p < SECTOR_P_MIN and spread > SECTOR_MAX_SPREAD:
        return Check("sector_depth", False, p,
                     f"The dip depth changes between sectors ({listing} ppm; chance {p:.1e}). A real planet gives "
                     f"the same depth every time; this points to light from a neighbouring star or a systematic.",
                     0.0), per
    return Check("sector_depth", True, p,
                 f"The dip depth agrees between sectors ({listing} ppm; chance of this scatter {p:.2f}).", margin), per


def max_duration_days(period: float, rho_solar: float, k: float = 0.0) -> float:
    """Central-transit duration on a circular orbit: P/pi * asin((1+k) R*/a)."""
    rho = rho_solar * RHO_SUN_KG_M3
    a_over_r = (G * rho * (period * 86400) ** 2 / (3 * math.pi)) ** (1 / 3)
    return period / math.pi * math.asin(min(1.0, (1 + k) / a_over_r))


def duration(sig: Signal, star: Star) -> Check:
    rho, source = star.density_solar()
    if rho is None:
        return Check("duration", None, None, "The TIC has no radius for this star, so the expected transit "
                                             "duration cannot be worked out.")
    tmax = max_duration_days(sig.period, rho, math.sqrt(max(sig.depth, 0.0)))
    ratio = sig.duration / tmax
    base = (f"The dip lasts {sig.duration * 24:.1f} h; a planet crossing the middle of this star (density "
            f"{rho:.2f} solar, from {source}) on a {sig.period:.3f}-day orbit would take about {tmax * 24:.1f} h")
    margin = _clip01(min(math.log(ratio / DURATION_MIN_RATIO), math.log(DURATION_MAX_RATIO / ratio)) / math.log(2))
    if ratio > DURATION_MAX_RATIO:
        return Check("duration", False, ratio, f"{base}. It is {ratio:.1f}x too long for this star, which suggests "
                                               f"a bigger star (e.g. a background binary) is being eclipsed.", 0.0)
    if ratio < DURATION_MIN_RATIO:
        return Check("duration", False, ratio, f"{base}. It is too short even for a grazing transit.", 0.0)
    return Check("duration", True, ratio, f"{base}, so the length fits.", margin)


def three_dips(ep: Epochs) -> Check:
    """A periodic signal needs three real dips. Leave out the strongest one: the rest must keep half the depth and
    stay 3 sigma deep; otherwise one dip (a single transit, or a glitch) is carrying a 'periodic' fold of empty
    epochs. This matters for the long-period search, where 3 epochs with data are easy to line up."""
    n = len(ep.epoch)
    if n < 3:
        return Check("three_dips", False if n else None, float(n),
                     f"Only {n} dip(s) could be measured; a periodic signal needs three." if n else
                     "No individual dips could be measured.", 0.0 if n else None)
    all_d, _ = _wmean(ep.depth, ep.err)
    k = int(np.argmax(ep.depth / ep.err))
    rest = np.arange(n) != k
    rest_d, rest_e = _wmean(ep.depth[rest], ep.err[rest])
    ratio = rest_d / all_d if all_d > 0 else 0.0
    if ratio < THREE_DIPS_MIN_RATIO or rest_d / rest_e < THREE_DIPS_SIGMA:
        return Check("three_dips", False, ratio,
                     f"Without its strongest dip (BTJD {ep.centre[k]:.2f}) the signal is only {ratio * 100:.0f}% as "
                     f"deep ({rest_d / rest_e:.1f} sigma): one dip carries it, so it is not a repeating signal.", 0.0)
    return Check("three_dips", True, ratio,
                 f"Without its strongest dip the other {n - 1} keep {ratio * 100:.0f}% of the depth "
                 f"({rest_d / rest_e:.1f} sigma): the signal repeats.",
                 _clip01((ratio - THREE_DIPS_MIN_RATIO) / (1 - THREE_DIPS_MIN_RATIO)))


def single_sector(ep: Epochs) -> Check:
    n = len(np.unique(ep.sector))
    if n <= 1:
        return Check("single_sector", None, float(n),
                     "Flag: every dip is in one sector, so the signal has not been seen twice in independent data.")
    return Check("single_sector", None, float(n), f"Not a single-sector signal: dips were seen in {n} sectors.")


# ---- all together --------------------------------------------------------------------------------------

def run_all(t: np.ndarray, f: np.ndarray, g: np.ndarray, sig: Signal, star: Star, dumps: np.ndarray,
            flagged: np.ndarray, quality_read: bool = True) -> tuple[list[Check], dict]:
    """t, f, g: flattened curve with other signals and known transits removed."""
    sz = implied_radius(sig.depth, star.rad, sig.depth_err, star.rad_err)
    sec_vet, sec = secondary_eclipse(t, f, sig)
    sec_frac = sec["depth"] / max(sig.depth, 1e-12)
    ep = epoch_depths(t, f, g, sig)
    scale = odd_even_scale(ep)
    oe = odd_even(odd_even_signal(sig, ep, scale))
    if scale > 1:
        oe = replace(oe, reason=oe.reason + f" (Errors widened x{scale:.1f}: dips of the same parity already differ "
                                            f"that much from each other, e.g. between sectors.)")
    sd, per_sector = sector_depth(ep)
    checks = [
        _from_vet(snr(sig), None),
        _from_vet(oe, _clip01(1 - (oe.value or 0) / 3)),
        _from_vet(sec_vet, max(_clip01(1 - (sec_vet.value or 0) / 3), _clip01(1 - sec_frac / 0.10))),
        _from_vet(size(sz), None if sz.lower_rjup is None else _clip01(1 - sz.lower_rjup / 2.0)),
        period_alias(t, f, sig, ep),
        momentum_dump(ep, sig, dumps, flagged, quality_read),
        sd,
        duration(sig, star),
        three_dips(ep),
        single_sector(ep),
    ]
    extra = {
        "radius_rjup": sz.radius_rjup, "radius_lower_rjup": sz.lower_rjup, "radius_upper_rjup": sz.upper_rjup,
        "radius_rearth": sz.radius_rearth, "per_sector": per_sector,
        "transit_times_btjd": [round(float(x), 5) for x in ep.centre],
        "transit_depths_ppm": [round(float(x) * 1e6, 1) for x in ep.depth],
        "transit_depth_errs_ppm": [round(float(x) * 1e6, 1) for x in ep.err],
        "sectors_with_transits": sorted({int(s) for s in ep.sector}),
        "n_transits_measured": int(len(ep.epoch)),
    }
    return checks, extra


def failures(checks: list[Check]) -> list[str]:
    """Names of checks that failed, or that had to run and could not."""
    out = []
    for c in checks:
        if c.passed is False or (c.passed is None and c.name in MUST_RUN):
            out.append(c.name)
    return out
