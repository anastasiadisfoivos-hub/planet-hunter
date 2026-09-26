"""Single- and double-dip ("single" / "duo") search on the stitched curve.

Runs after known planets and the periodic signals found on the star are masked.

Search: a box matched filter over durations 1-24 h. Durations are searched in three tiers, each on its own
detrended curve with a biweight window 3x the tier's longest duration (1-4 h: 0.5 d, 6-12 h: 1.5 d,
16-24 h: 3 d), so a dip cannot pull its own trend down. For every duration, box centres are stepped by a sixth
of the duration; the single-event statistic is

    SES = (1 - mean flux in the box) / (sigma_1day * beta_sector / sqrt(points in the box))

with sigma_1day the robust scatter of the flattened flux in the surrounding day (scattered light raises it
locally) and beta_sector the red-noise factor at that duration in that sector. A box needs >= 75% of its
expected cadences. Peaks at least as far apart as their durations are events; each is refined in centre and
duration.

Every event is then vetted (each is a checks.Check):
  edge            the dip (ingress to egress) lies within 0.5 d of a sector edge or a data gap (> 0.25 d)
  momentum_dump   a reaction-wheel dump falls in the dip and the dip loses > half its depth without the hour
                  around it, or > 20% of the dip's cadences are quality-flagged
  shape           the two halves of the dip (re-detrended with the dip masked) differ by > 3 sigma and > 30%
                  of the depth (a ramp), or the flux level before and after differs by > 3 sigma and > 50% of
                  the depth (a step)
  background      the background (SAP_BKG) during the dip is > 3 sigma and > 1 unit of its own scatter above
                  its surroundings (scattered light, a passing asteroid, a glint)
  neighbour_dips  the same dip at the same time in 2+ nearby stars' light curves (run at merge, see sweep.py)

Singles: one surviving dip with no partner. The period is estimated from its duration and the star's density
(Kepler's third law) in a Monte Carlo (period_posterior): log-uniform period prior, impact parameter uniform
0-0.9, eccentricity Beta(0.867, 3.03) (Kipping 2013) with uniform argument of periastron, density with its
error, duration measurement error 20% (log); samples are weighted by the chance of transiting and of a
transit falling in the data (both ~ P^-2/3 and 1/P), and periods that would put another transit where the
data cover it are removed. period_range_d is the 5-95% range.

Duos: two surviving dips in different sectors, depths within 3 sigma or a factor 1.5 of each other and
durations within a factor 1.6. Allowed periods are P = gap / n (P >= 1 d). An alias is dropped when a transit
it predicts falls where the data cover >= 50% of the dip and the flux there is < half the dip depth and
> 3 sigma shallower. The survivors are period_aliases_d, each with its posterior weight from the same
duration/density model; period_d is the most probable one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from hunter.clean import robust_sigma

from . import detrend
from .checks import Check, red_noise_factor
from .deep import G
from .stars import RHO_SUN_KG_M3, Star

DURATIONS_H = np.array([1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0])
TIERS = ((1.0, 4.0), (6.0, 12.0), (16.0, 24.0))  # hours; each is flattened with a window 3x its longest
EVENT_MIN_SES = 7.0  # recorded as an event (for duos and neighbour comparison)
SINGLE_MIN_SNR = 10.0  # a single becomes a candidate at this SES (see README "False alarms")
DUO_MIN_SNR = 10.0  # a duo needs this combined SNR ...
DUO_MIN_EACH = 7.0  # ... and each dip at least this
MAX_EVENTS = 20
MIN_COVERAGE = 0.75
EDGE_D = 0.5
GAP_D = 0.25
DUMP_PAD_D = 1 / 24
FLAGGED_MAX_FRAC = 0.2
SHAPE_SIGMA, SHAPE_FRAC = 3.0, 0.3
BKG_SIGMA, BKG_MIN = 3.0, 1.0
DUO_DEPTH_RATIO, DUO_DURATION_RATIO = 1.5, 1.6
ALIAS_MIN_P = 1.0
ALIAS_COVER = 0.5
MC_SAMPLES = 200_000
SINGLE_MUST_RUN = ("snr", "size", "duration", "edge", "momentum_dump", "shape", "background")
DUO_MUST_RUN = SINGLE_MUST_RUN + ("depth_consistency", "aliases")
COULD_NOT_RUN = {
    "odd_even": "Needs several dips at a known period; a single or double dip has no alternate dips to compare.",
    "secondary_eclipse": "Needs a known period to know where half an orbit later is.",
    "period_alias": "Needs a known period; for a double dip the allowed periods are listed instead.",
    "sector_depth": "Needs dips in several sectors at a known period.",
}


@dataclass
class Event:
    tc: float
    duration: float  # days
    depth: float
    depth_err: float
    ses: float
    sector: int
    n_in: int
    coverage: float
    checks: list[Check] = field(default_factory=list)
    tc_err: float = 0.02
    t12: float | None = None  # ingress duration (days) from the trapezoid fit
    t12_err: float | None = None
    duration_err: float | None = None
    box_duration: float | None = None
    fitted: bool = False
    local: tuple | None = field(default=None, repr=False)  # (time, flux) re-detrended around the dip, dip masked

    def failed(self) -> list[str]:
        return [c.name for c in self.checks if c.passed is False]

    def to_dict(self) -> dict:
        r = lambda x, k=3: None if x is None else round(float(x), k)  # noqa: E731
        return {"mid_btjd": round(self.tc, 5), "mid_err_d": r(self.tc_err, 5),
                "duration_h": round(self.duration * 24, 3),
                "duration_err_h": r(None if self.duration_err is None else self.duration_err * 24),
                "ingress_h": r(None if self.t12 is None else self.t12 * 24),
                "depth_ppm": round(self.depth * 1e6, 1), "depth_err_ppm": round(self.depth_err * 1e6, 1),
                "snr": round(self.ses, 2), "sector": self.sector, "coverage": round(self.coverage, 3),
                "shape_fit": "trapezoid" if self.fitted else "box"}


# ---- data helpers --------------------------------------------------------------------------------------------

def cadence_of(t: np.ndarray, g: np.ndarray) -> np.ndarray:
    """Typical spacing of points per sector (days)."""
    cad = np.full(len(t), 10 / 1440)
    for s in np.unique(g):
        m = g == s
        if m.sum() > 2:
            cad[m] = float(np.median(np.diff(t[m])))
    return cad


def segment_edges(t: np.ndarray, g: np.ndarray) -> np.ndarray:
    """Times where data start or stop: sector starts/ends and both sides of every gap > GAP_D."""
    edges = [t[0], t[-1]] if len(t) else []
    brk = np.flatnonzero((np.diff(t) > GAP_D) | (np.diff(g) != 0))
    for i in brk:
        edges += [t[i], t[i + 1]]
    return np.sort(np.array(edges, float))


class Coverage:
    """Fraction of a window [c - d/2, c + d/2] that has data, from per-point cadences."""

    def __init__(self, t: np.ndarray, cad: np.ndarray):
        self.t = t
        self.csum = np.concatenate([[0.0], np.cumsum(cad)])

    def __call__(self, centres: np.ndarray, duration: float) -> np.ndarray:
        lo = np.searchsorted(self.t, centres - duration / 2)
        hi = np.searchsorted(self.t, centres + duration / 2)
        return np.clip((self.csum[hi] - self.csum[lo]) / duration, 0, 1.5)


def _local_sigma(t: np.ndarray, f: np.ndarray, chunk: float = 1.0) -> np.ndarray:
    """Robust scatter of the flattened flux per chunk of `chunk` days, per point."""
    key = np.floor((t - t[0]) / chunk).astype(np.int64)
    out = np.full(len(t), np.nan)
    uniq, inv = np.unique(key, return_inverse=True)
    glob = robust_sigma(f)
    order = np.argsort(inv, kind="stable")
    bounds = np.searchsorted(inv[order], np.arange(len(uniq) + 1))
    for k in range(len(uniq)):
        idx = order[bounds[k]:bounds[k + 1]]
        s = robust_sigma(f[idx]) if len(idx) >= 20 else glob
        out[idx] = s if np.isfinite(s) and s > 0 else glob
    return out


# ---- matched filter --------------------------------------------------------------------------------------------

@dataclass
class FlatTier:
    t: np.ndarray
    f: np.ndarray
    g: np.ndarray
    sigma: np.ndarray
    cad: np.ndarray
    csum: np.ndarray
    beta: dict  # (sector, duration_h) -> red-noise factor
    window: float


def _tier(t, f, g, mask, window) -> FlatTier:
    flat, keep = detrend.flatten(t, f, window, mask)
    use = keep & ~mask
    tt, ff, gg = t[use], flat[use], g[use]
    cad = cadence_of(tt, gg)
    return FlatTier(tt, ff, gg, _local_sigma(tt, ff), cad, np.concatenate([[0.0], np.cumsum(ff)]), {}, window)


def _beta(tier: FlatTier, sector: int, dur: float) -> float:
    key = (int(sector), round(dur * 24, 2))
    if key not in tier.beta:
        m = tier.g == sector
        tier.beta[key] = red_noise_factor(tier.t[m], tier.f[m], dur) if m.sum() > 100 else 1.0
    return tier.beta[key]


def box_stats(tier: FlatTier, centres: np.ndarray, dur: float) -> tuple[np.ndarray, ...]:
    """(depth, error, ses, n, coverage) of boxes of width dur at the given centres."""
    lo = np.searchsorted(tier.t, centres - dur / 2)
    hi = np.searchsorted(tier.t, centres + dur / 2)
    n = hi - lo
    mean = np.where(n > 0, (tier.csum[hi] - tier.csum[lo]) / np.maximum(n, 1), np.nan)
    mid = np.clip((lo + hi) // 2, 0, len(tier.t) - 1)
    cad = tier.cad[mid]
    cover = n * cad / dur
    sectors = tier.g[mid]
    beta = np.ones(len(sectors))
    for s in np.unique(sectors):
        beta[sectors == s] = _beta(tier, s, dur)
    err = tier.sigma[mid] * beta / np.sqrt(np.maximum(n, 1))
    depth = 1 - mean
    ses = np.where((n >= 3) & (cover >= MIN_COVERAGE), depth / err, 0.0)
    return depth, err, ses, n, cover


def _peaks(tier: FlatTier, durations_h: np.ndarray, min_ses: float) -> list[Event]:
    found = []
    for dh in durations_h:
        dur = dh / 24
        step = dur / 6
        centres = []
        seg_brk = np.flatnonzero(np.diff(tier.t) > GAP_D) + 1
        for seg in np.split(np.arange(len(tier.t)), seg_brk):
            if len(seg) < 3:
                continue
            a, b = tier.t[seg[0]], tier.t[seg[-1]]
            if b - a < dur:
                continue
            centres.append(np.arange(a + dur / 2, b - dur / 2 + step / 2, step))
        if not centres:
            continue
        c = np.concatenate(centres)
        depth, err, ses, n, cover = box_stats(tier, c, dur)
        for i in np.flatnonzero(ses >= min_ses):
            found.append((float(ses[i]), float(c[i]), dur))
    found.sort(reverse=True)
    events: list[tuple[float, float, float]] = []
    for s, c, d in found:
        if all(abs(c - c2) > 0.5 * (d + d2) for _, c2, d2 in events):
            events.append((s, c, d))
        if len(events) >= MAX_EVENTS:
            break
    return [_refine(tier, c, d) for _, c, d in events]


def _refine(tier: FlatTier, tc: float, dur: float) -> Event:
    best = None
    for d in dur * np.geomspace(0.75, 1.33, 7):
        cs = tc + np.linspace(-dur / 4, dur / 4, 25)
        depth, err, ses, n, cover = box_stats(tier, cs, d)
        i = int(np.argmax(ses))
        if best is None or ses[i] > best[0]:
            best = (float(ses[i]), float(cs[i]), float(d), float(depth[i]), float(err[i]), int(n[i]), float(cover[i]))
    s, c, d, dep, e, n, cov = best
    sector = int(tier.g[min(np.searchsorted(tier.t, c), len(tier.t) - 1)])
    return Event(c, d, dep, e, s, sector, n, cov)


def find_events(t: np.ndarray, f: np.ndarray, g: np.ndarray, mask: np.ndarray,
                min_ses: float = EVENT_MIN_SES) -> tuple[list[Event], dict[float, FlatTier]]:
    """Events from all duration tiers (strongest first, no two overlapping). Returns the tiers too, keyed by the
    longest duration (h) they cover, for vetting."""
    tiers: dict[float, FlatTier] = {}
    events: list[Event] = []
    for lo, hi in TIERS:
        tier = _tier(t, f, g, mask, 3 * hi / 24)
        tiers[hi] = tier
        durs = DURATIONS_H[(DURATIONS_H >= lo) & (DURATIONS_H <= hi)]
        events += _peaks(tier, durs, min_ses)
    events.sort(key=lambda e: -e.ses)
    keep: list[Event] = []
    for e in events:
        if all(abs(e.tc - k.tc) > 0.5 * (e.duration + k.duration) for k in keep):
            keep.append(e)
    return keep[:MAX_EVENTS], tiers


def tier_for(tiers: dict[float, FlatTier], duration: float) -> FlatTier:
    for hi in sorted(tiers):
        if duration * 24 <= hi * 1.34:  # refinement can stretch a duration by 1/3
            return tiers[hi]
    return tiers[max(tiers)]



# ---- trapezoid refinement -------------------------------------------------------------------------------------

def trapezoid(t, tc, depth, t14, t12):
    x = np.abs(t - tc)
    t12 = np.minimum(t12, t14 / 2)
    flat = t14 / 2 - t12
    return 1 - np.where(x <= flat, depth, np.where(x < t14 / 2, depth * (t14 / 2 - x) / np.maximum(t12, 1e-6), 0.0))


def fit_trapezoid(e: Event, t: np.ndarray, f: np.ndarray, g: np.ndarray, window: float) -> Event:
    """Re-detrend around the dip with the dip left out of the trend, then fit a trapezoid (mid-time, depth, T14,
    ingress). Errors are scaled by the red-noise factor. Keeps the box values if the fit is not sensible."""
    from scipy.optimize import least_squares

    near = np.abs(t - e.tc) < max(3 * e.duration, 1.0) + window
    if near.sum() < 30:
        return e
    tt, ff, gg = t[near], f[near], g[near]
    inside = np.abs(tt - e.tc) < 0.75 * e.duration
    flat, keep = detrend.flatten(tt, ff, window, inside)
    w = keep & (np.abs(tt - e.tc) < max(3 * e.duration, 1.0))
    x, y = tt[w], flat[w]
    if len(x) < 20 or (np.abs(x - e.tc) < e.duration / 2).sum() < 5:
        return e
    e.local = (x, y)
    p0 = [e.tc, max(e.depth, 1e-5), e.duration, e.duration / 10]
    lo = [e.tc - e.duration / 2, 0.0, 0.5 * e.duration, 0.005]
    hi = [e.tc + e.duration / 2, 0.5, min(2 * e.duration, 1.5), max(0.5 * e.duration, 0.006)]
    try:
        r = least_squares(lambda p: trapezoid(x, *p) - y, np.clip(p0, lo, hi), bounds=(lo, hi))
        dof = max(len(y) - 4, 1)
        cov = np.linalg.pinv(r.jac.T @ r.jac) * float(np.sum(r.fun**2)) / dof
        err = np.sqrt(np.clip(np.diag(cov), 0, None))
    except Exception:
        return e
    tc, depth, t14, t12 = (float(v) for v in r.x)
    oot = np.abs(x - tc) > t14 / 2
    beta = red_noise_factor(x[oot], y[oot], t14) if oot.sum() > 50 else 1.0
    err = err * beta
    if not (depth > 0 and np.all(np.isfinite(err)) and err[1] < depth):
        return e
    e.box_duration = e.duration
    e.tc, e.depth, e.duration, e.t12 = tc, depth, t14, min(t12, t14 / 2)
    e.tc_err, e.depth_err, e.duration_err, e.t12_err = float(err[0]), max(float(err[1]), e.depth_err * 0.5), \
        float(err[2]), float(err[3])
    e.fitted = True
    return e

# ---- per-dip vetting -----------------------------------------------------------------------------------------

def check_edge(e: Event, edges: np.ndarray) -> Check:
    if len(edges) == 0:
        return Check("edge", None, None, "No data edges could be worked out.")
    lo, hi = e.tc - e.duration / 2, e.tc + e.duration / 2
    inside = edges[(edges > lo) & (edges < hi)]
    dist = 0.0 if len(inside) else float(min(np.min(np.abs(edges - lo)), np.min(np.abs(edges - hi))))
    if dist < EDGE_D:
        return Check("edge", False, dist, f"The dip is {dist:.2f} d from a sector edge or data gap (need >= "
                                           f"{EDGE_D} d). Flux near edges and gaps is often disturbed "
                                           f"(thermal settling, scattered light, the detrending itself).", 0.0)
    return Check("edge", True, dist, f"The dip is {dist:.1f} d from the nearest sector edge or data gap.",
                 min(1.0, (dist - EDGE_D) / 2))


def check_dumps(e: Event, tier: FlatTier, dumps: np.ndarray, flagged: np.ndarray, native_cad: float,
                quality_read: bool) -> Check:
    caveat = "" if quality_read else " (quality flags could not be read for every file)"
    lo, hi = e.tc - e.duration / 2, e.tc + e.duration / 2
    n_flag = int(np.sum((flagged > lo) & (flagged < hi))) if len(flagged) else 0
    frac_flag = n_flag * native_cad / e.duration
    on = dumps[(dumps > lo - DUMP_PAD_D / 2) & (dumps < hi + DUMP_PAD_D / 2)] if len(dumps) else np.array([])
    if frac_flag > FLAGGED_MAX_FRAC:
        return Check("momentum_dump", False, frac_flag,
                     f"{frac_flag * 100:.0f}% of the dip's cadences are quality-flagged; the dip is built "
                     f"around missing or bad data{caveat}.", 0.0)
    if len(on) == 0:
        return Check("momentum_dump", True, 0.0, f"No momentum dump falls in the dip{caveat}.", 1.0)
    sel = (tier.t > lo) & (tier.t < hi)
    near = np.zeros(len(tier.t), bool)
    for d in on:
        near |= np.abs(tier.t - d) < DUMP_PAD_D
    clean = sel & ~near
    if clean.sum() < max(3, 0.5 * sel.sum()):
        return Check("momentum_dump", False, float(len(on)),
                     f"{len(on)} momentum dump(s) fall in the dip and too little of the dip is left without the "
                     f"hour around them to tell the dip from the dump{caveat}.", 0.0)
    d_clean = 1 - float(np.mean(tier.f[clean]))
    err = float(np.median(tier.sigma[clean])) / math.sqrt(clean.sum())
    if d_clean < 0.5 * e.depth and (e.depth - d_clean) / math.hypot(err, e.depth_err) > 3:
        return Check("momentum_dump", False, d_clean / e.depth,
                     f"A momentum dump falls in the dip and without the hour around it the dip is only "
                     f"{d_clean / e.depth * 100:.0f}% as deep: the dump makes the dip{caveat}.", 0.0)
    return Check("momentum_dump", True, d_clean / max(e.depth, 1e-12),
                 f"A momentum dump falls in the dip, but without the hour around it the dip keeps "
                 f"{d_clean / e.depth * 100:.0f}% of its depth{caveat}.", 0.5)


def check_shape(e: Event, tier: FlatTier, t_raw: np.ndarray, f_raw: np.ndarray) -> Check:
    """Halves of the dip compared on the curve re-detrended around it with the dip masked (a trend fitted through
    the dip would flatten a ramp); falls back to the tier's curve."""
    lo, hi = e.tc - e.duration / 2, e.tc + e.duration / 2
    if e.local is not None:
        x, y = e.local
        out = (x < lo - 0.1 * e.duration) | (x > hi + 0.1 * e.duration)
        s = robust_sigma(y[out]) if out.sum() > 20 else float(np.median(tier.sigma))
        beta = red_noise_factor(x[out], y[out], e.duration / 2) if out.sum() > 50 else 1.0
    else:
        x, y = tier.t, tier.f
        s = float(np.median(tier.sigma[(x > lo) & (x < hi)])) if ((x > lo) & (x < hi)).any() else robust_sigma(y)
        beta = _beta(tier, e.sector, e.duration / 2)
    a = (x > lo) & (x < e.tc)
    b = (x >= e.tc) & (x < hi)
    if a.sum() < 3 or b.sum() < 3:
        return Check("shape", None, None, "Too few points in the dip to compare its halves.")
    d1, d2 = 1 - float(np.mean(y[a])), 1 - float(np.mean(y[b]))
    e12 = s * math.sqrt(1 / a.sum() + 1 / b.sum()) * beta
    asym = abs(d1 - d2)
    reasons = []
    if asym > SHAPE_SIGMA * e12 and asym > SHAPE_FRAC * e.depth:
        reasons.append(f"the first half is {d1 * 1e6:.0f} ppm deep and the second {d2 * 1e6:.0f} ppm (a ramp, "
                       f"not a transit)")
    # Step: raw (normalised, un-detrended) flux one duration before vs one duration after the dip.
    pre = (t_raw > lo - e.duration) & (t_raw < lo)
    post = (t_raw > hi) & (t_raw < hi + e.duration)
    step = None
    if pre.sum() >= 3 and post.sum() >= 3:
        sr = robust_sigma(f_raw[pre | post]) or s
        step = float(np.median(f_raw[pre]) - np.median(f_raw[post]))
        e_step = sr * math.sqrt(1 / pre.sum() + 1 / post.sum()) * 1.25
        if abs(step) > SHAPE_SIGMA * e_step and abs(step) > 0.5 * e.depth:
            reasons.append(f"the flux before the dip is {step * 1e6:+.0f} ppm from the flux after it (a step)")
    value = asym / max(e.depth, 1e-12)
    if reasons:
        return Check("shape", False, value, "The dip is not transit-shaped: " + "; ".join(reasons) + ".", 0.0)
    margin = max(0.0, 1 - value / SHAPE_FRAC)
    return Check("shape", True, value, f"The two halves of the dip match ({d1 * 1e6:.0f} vs {d2 * 1e6:.0f} ppm)"
                                       + ("" if step is None else f" and the flux level is the same before and "
                                                                  f"after ({step * 1e6:+.0f} ppm)") + ".", margin)


def check_background(e: Event, t: np.ndarray, bkg: np.ndarray | None) -> Check:
    if bkg is None:
        return Check("background", None, None, "No background (SAP_BKG) was read for this star.")
    lo, hi = e.tc - e.duration / 2, e.tc + e.duration / 2
    fin = np.isfinite(bkg)
    inn = fin & (t > lo) & (t < hi)
    around = fin & (np.abs(t - e.tc) < e.duration / 2 + 2 * e.duration) & ~((t > lo) & (t < hi))
    wide = fin & (np.abs(t - e.tc) < 3.0)
    if inn.sum() < 3 or around.sum() < 6 or wide.sum() < 20:
        return Check("background", None, None, "Not enough background measurements around the dip.")
    b_in, b_out = float(np.mean(bkg[inn])), float(np.median(bkg[around]))
    tw, bw = t[wide], bkg[wide]
    edges = np.arange(tw.min(), tw.max() + e.duration, e.duration)
    idx = np.digitize(tw, edges)
    means = np.array([bw[idx == k].mean() for k in np.unique(idx) if (idx == k).sum() >= 2])
    s = robust_sigma(means) if len(means) >= 5 else robust_sigma(bw)
    s = max(s if np.isfinite(s) else 0.0, 1e-3)
    z = (b_in - b_out) / s
    if z > BKG_SIGMA and b_in - b_out > BKG_MIN:
        return Check("background", False, z,
                     f"The sky background rises during the dip ({z:.1f} sigma above its surroundings, "
                     f"{b_in - b_out:.1f}x its usual scatter): scattered light or a passing object, not the star.",
                     0.0)
    return Check("background", True, z, f"The sky background is steady during the dip ({z:+.1f} sigma).",
                 float(min(1.0, max(0.0, 1 - z / BKG_SIGMA))))


def vet_event(e: Event, tiers: dict[float, FlatTier], edges: np.ndarray, lc, t_raw: np.ndarray,
              f_raw: np.ndarray, bkg_raw: np.ndarray | None, native_cad: dict[int, float]) -> Event:
    tier = tier_for(tiers, e.duration)
    e.checks = [check_edge(e, edges),
                check_dumps(e, tier, lc.dumps, lc.flagged, native_cad.get(e.sector, 2 / 1440), lc.quality_read),
                check_shape(e, tier, t_raw, f_raw),
                check_background(e, t_raw, bkg_raw)]
    return e


# ---- period from duration and density --------------------------------------------------------------------------

def transit_duration(period_d, rho_solar, b, k, e, w):
    """Total transit duration (days), small-angle form, eccentric orbit (Winn 2010 eq. 14-16)."""
    a_over_r = (G * rho_solar * RHO_SUN_KG_M3 * (period_d * 86400) ** 2 / (3 * np.pi)) ** (1 / 3)
    chord = np.sqrt(np.clip((1 + k) ** 2 - b**2, 0, None))
    g = np.sqrt(1 - e**2) / (1 + e * np.sin(w))
    x = np.clip(chord / (a_over_r * np.sqrt(np.clip(1 - (b / a_over_r) ** 2, 1e-9, None))), 0, 1)
    return period_d / np.pi * np.arcsin(x) * g


@dataclass
class PeriodEstimate:
    lo: float | None
    median: float | None
    hi: float | None
    detail: dict


def period_posterior(duration: float, depth: float, star: Star, tc: float | None = None,
                     covered=None, span: tuple[float, float] | None = None, candidates: np.ndarray | None = None,
                     rng_seed: int = 7) -> tuple[PeriodEstimate, np.ndarray | None]:
    """Monte Carlo period estimate for a transit of this duration on this star (see module docstring).

    covered(times, duration) -> coverage fraction; with tc and span, periods that would show another transit in
    the data are removed. If candidates (a list of allowed periods, for a duo) is given, the posterior weight of
    each is returned as well."""
    rho, source = star.density_solar()
    if rho is None:
        return PeriodEstimate(None, None, None, {"why": "no stellar density: the TIC has no radius"}), None
    rho_err = 0.25 if source == "TIC density" else 0.5  # fractional (lognormal)
    rng = np.random.default_rng(rng_seed)
    k = math.sqrt(max(depth, 1e-8))
    n = MC_SAMPLES
    b = rng.uniform(0, 0.9, n)
    e = np.clip(rng.beta(0.867, 3.03, n), 0, 0.8)
    w = rng.uniform(0, 2 * np.pi, n)
    r = rho * np.exp(rng.normal(0, rho_err, n))
    t_1yr = float(transit_duration(np.array([365.25]), rho, 0.0, k, 0.0, 0.0)[0])
    p_ref = 365.25 * (duration / t_1yr) ** 3  # period for a central circular transit of this duration
    if candidates is None:
        lo_p, hi_p = max(0.3, p_ref / 300), min(1e5, p_ref * 300)
        P = np.exp(rng.uniform(math.log(lo_p), math.log(hi_p), n))  # log-uniform prior
    else:
        P = rng.choice(np.asarray(candidates, float), n)  # uniform over the allowed aliases (then weighted)
    T = transit_duration(P, r, b, k, e, w)
    sig = 0.2
    with np.errstate(divide="ignore", invalid="ignore"):
        like = np.exp(-0.5 * (np.log(np.maximum(T, 1e-9) / duration) / sig) ** 2)
    a_over_r = (G * r * RHO_SUN_KG_M3 * (P * 86400) ** 2 / (3 * np.pi)) ** (1 / 3)
    geo = (1 + e * np.sin(w)) / (1 - e**2) / a_over_r  # chance of transiting ~ (R*/a)(1+e sin w)/(1-e^2)
    catch = 1 / P  # chance a given transit falls in the data (long periods)
    wt = like * geo * catch
    wt[~np.isfinite(wt)] = 0
    detail = {"method": "Monte Carlo: Kepler's third law with the TIC density ("
                        f"{rho:.3f} solar, {rho_err * 100:.0f}% error, from {source}); impact parameter 0-0.9; "
                        "eccentricity Beta(0.867, 3.03); duration error 20%; weighted by transit and "
                        "observing probability", "circular_central_period_d": round(p_ref, 2)}
    if candidates is None and covered is not None and tc is not None and span is not None and wt.sum() > 0:
        pick = rng.choice(n, size=min(20000, n), p=wt / wt.sum())
        Pp = P[pick]
        ok = allowed_single(Pp, tc, duration, covered, span)
        detail["mass_excluded_by_data"] = round(float(1 - ok.mean()), 3)
        if ok.any():
            ep = e[pick][ok]
            detail["eccentricity_median"] = round(float(np.median(ep)), 3)
            detail["fraction_needing_e_above_0.5"] = round(float(np.mean(ep > 0.5)), 3)
        detail["shortest_period_allowed_by_data_d"] = round(float(Pp[ok].min()), 2) if ok.any() else None
        if not ok.any():
            return PeriodEstimate(None, None, None, {**detail, "why": "every period consistent with the "
                                                                      "duration would show another transit"}), None
        q = np.percentile(Pp[ok], [5, 50, 95])
        return PeriodEstimate(float(q[0]), float(q[1]), float(q[2]), detail), None
    if candidates is not None:
        cand = np.asarray(candidates, float)
        post = np.array([wt[P == c].sum() for c in cand])
        fit = np.array([like[P == c].mean() if (P == c).any() else 0.0 for c in cand])
        post = post / post.sum() if post.sum() > 0 else np.full(len(cand), 1 / len(cand))
        best = cand[int(np.argmax(post))]
        return PeriodEstimate(float(cand.min()), float(best), float(cand.max()), detail), np.vstack([post, fit])
    if wt.sum() <= 0:
        return PeriodEstimate(None, None, None, {**detail, "why": "no period fits the duration"}), None
    pick = rng.choice(n, size=min(20000, n), p=wt / wt.sum())
    q = np.percentile(P[pick], [5, 50, 95])
    return PeriodEstimate(float(q[0]), float(q[1]), float(q[2]), detail), None


def allowed_single(periods: np.ndarray, tc: float, duration: float, covered, span: tuple[float, float]) -> np.ndarray:
    """True where no other transit (tc + kP, k != 0) would fall on data covering >= ALIAS_COVER of the dip.
    Walks k = 1, 2, ... outwards on both sides; a period drops out as soon as one of its transits is covered."""
    periods = np.asarray(periods, float)
    ok = np.ones(len(periods), bool)
    t_min, t_max = span
    k_lo = np.floor((tc - t_min) / periods).astype(int)
    k_hi = np.floor((t_max - tc) / periods).astype(int)
    live = np.flatnonzero((k_lo > 0) | (k_hi > 0))
    k = 1
    while len(live):
        p = periods[live]
        for sign, lim in ((-1, k_lo), (1, k_hi)):
            valid = lim[live] >= k
            if valid.any():
                hit = np.zeros(len(live), bool)
                hit[valid] = covered(tc + sign * k * p[valid], duration) >= ALIAS_COVER
                ok[live[hit]] = False
        k += 1
        live = live[ok[live] & ((k_lo[live] >= k) | (k_hi[live] >= k))]
    return ok


# ---- duos ----------------------------------------------------------------------------------------------------------

def alias_table(e1: Event, e2: Event, tier: FlatTier, covered, span: tuple[float, float]) -> list[dict]:
    """Every P = gap / n >= ALIAS_MIN_P with its fate. At each transit an alias predicts (other than the two
    dips), if the data cover >= ALIAS_COVER of the dip the deepest box within the timing tolerance is measured:
    the alias is dropped if it is < half the dip depth and > 3 sigma shallower; a dip of the right depth there
    counts as an extra dip. Tolerance: 3 sigma of the predicted time (from the two mid-time errors) + 1 h."""
    a, b = sorted([e1, e2], key=lambda e: e.tc)
    gap = b.tc - a.tc
    dur = 0.5 * (a.duration + b.duration)
    # Reference depth measured exactly as the predicted transits will be: a box of this width on this curve
    # (a box over a trapezoid is shallower than its flat bottom).
    ref, ref_err, _, _, _ = box_stats(tier, np.array([a.tc, b.tc]), dur)
    depth = float(np.nanmean(ref)) if np.isfinite(ref).any() else 0.5 * (a.depth + b.depth)
    derr = 0.5 * float(np.hypot(*np.nan_to_num(ref_err, nan=0.0))) or 0.5 * math.hypot(a.depth_err, b.depth_err)
    n_all = np.arange(1, int(gap / ALIAS_MIN_P) + 1)
    # all (alias, epoch) pairs at once
    ns, ks = [], []
    for n in n_all:
        p = gap / n
        k = np.arange(-math.floor((a.tc - span[0]) / p), math.floor((span[1] - a.tc) / p) + 1)
        k = k[(k != 0) & (k != n)]
        ns.append(np.full(len(k), n))
        ks.append(k)
    n_e = np.concatenate(ns) if ns else np.array([], int)
    k_e = np.concatenate(ks) if ks else np.array([], int)
    times = a.tc + k_e * gap / np.maximum(n_e, 1)
    missing_n: dict[int, list[float]] = {}
    extra_n: dict[int, int] = {}
    if len(times):
        cov = covered(times, dur)
        sel = cov >= ALIAS_COVER
        n_s, k_s, t_s = n_e[sel], k_e[sel], times[sel]
        s_pred = np.hypot(a.tc_err * np.abs(1 - k_s / n_s), b.tc_err * np.abs(k_s / n_s))
        tol = np.minimum(3 * s_pred + 1 / 24, 0.5 * dur)
        offs = np.linspace(-1, 1, 9)
        grid = (t_s[:, None] + tol[:, None] * offs[None, :]).ravel()
        d, err, _, _, cv = box_stats(tier, grid, dur)
        d = np.where(np.isfinite(d) & (cv >= ALIAS_COVER), d, -np.inf).reshape(len(t_s), 9)
        err = err.reshape(len(t_s), 9)
        j = np.argmax(d, axis=1)
        dd = d[np.arange(len(t_s)), j]
        ee = err[np.arange(len(t_s)), j]
        good = np.isfinite(dd)
        comb = np.hypot(ee, derr)
        miss = good & (dd < 0.5 * depth) & ((depth - dd) / comb > 3)
        extra = good & ~miss & ((np.abs(dd - depth) < 3 * comb) | (dd >= 0.7 * depth))
        for n, tt in zip(n_s[miss], t_s[miss]):
            missing_n.setdefault(int(n), []).append(round(float(tt), 3))
        for n in n_s[extra]:
            extra_n[int(n)] = extra_n.get(int(n), 0) + 1
    return [{"n": int(n), "period_d": gap / n, "dropped": int(n) in missing_n,
             "missed_dips_btjd": missing_n.get(int(n), [])[:3], "extra_dips": extra_n.get(int(n), 0)}
            for n in n_all]


# ---- checks shared with periodic candidates -----------------------------------------------------------------

def size_check(depth: float, depth_err: float, star: Star) -> tuple[Check, dict]:
    from hunter.measure import implied_radius
    from hunter.vet import size

    sz = implied_radius(depth, star.rad, depth_err, star.rad_err)
    v = size(sz)
    margin = None if sz.lower_rjup is None else float(min(1, max(0, 1 - sz.lower_rjup / 2.0)))
    return Check(v.name, v.passed, v.value, v.reason, margin), {
        "radius_rjup": sz.radius_rjup, "radius_lower_rjup": sz.lower_rjup, "radius_upper_rjup": sz.upper_rjup,
        "radius_rearth": sz.radius_rearth}


def could_not_run() -> list[Check]:
    return [Check(name, None, None, "Could not run: " + why) for name, why in COULD_NOT_RUN.items()]


def must_run_failures(checks: list[Check], kind: str) -> list[str]:
    must = SINGLE_MUST_RUN if kind == "single" else DUO_MUST_RUN
    return [c.name for c in checks if c.passed is False or (c.passed is None and c.name in must)]


# ---- the whole single / duo search for one star ------------------------------------------------------------------

MAX_PLAUSIBLE_PERIOD_D = 10_000.0  # a dip that needs > ~27 yr (circular central transit, or posterior median) is
# too long for this star
DURATION_FIT_MIN = 0.01  # mean duration likelihood below which an alias cannot produce this duration


@dataclass
class DipResult:
    kind: str  # "single" | "duo"
    events: list[Event]
    snr: float
    depth: float
    depth_err: float
    duration: float
    checks: list[Check]
    period: PeriodEstimate
    aliases: list[dict]  # duo: surviving aliases with posterior weight; single: []
    extra: dict

    @property
    def failed(self) -> list[str]:
        return must_run_failures(self.checks, self.kind)


def _wmean(vals, errs) -> tuple[float, float]:
    w = 1 / np.asarray(errs) ** 2
    return float(np.sum(w * np.asarray(vals)) / w.sum()), float(1 / math.sqrt(w.sum()))


def _merge_event_checks(events: list[Event]) -> list[Check]:
    """One check per name over all dips: fails if any dip fails, could-not-run if any could not, else passes
    with the smallest margin."""
    out = []
    for name in ("edge", "momentum_dump", "shape", "background"):
        cs = [c for e in events for c in e.checks if c.name == name]
        label = [f"dip {i + 1}: " if len(events) > 1 else "" for i in range(len(cs))]
        reason = " ".join(lb + c.reason for lb, c in zip(label, cs))
        if any(c.passed is False for c in cs):
            bad = next(c for c in cs if c.passed is False)
            out.append(Check(name, False, bad.value, reason, 0.0))
        elif any(c.passed is None for c in cs):
            out.append(Check(name, None, None, reason))
        else:
            ms = [c.margin for c in cs if c.margin is not None]
            out.append(Check(name, True, cs[0].value, reason, min(ms) if ms else None))
    return out


def _snr_check(snr: float, need: float, what: str) -> Check:
    if snr < need:
        return Check("snr", False, snr, f"The {what} stands {snr:.1f} times above the noise (need {need:.0f}).", 0.0)
    return Check("snr", True, snr, f"The {what} stands {snr:.1f} times above the local, red-noise-corrected "
                                   f"noise (need {need:.0f}).", None)


def _single(e: Event, star: Star, covered, span) -> DipResult:
    est, _ = period_posterior(e.duration, e.depth, star, e.tc, covered, span)
    sz, sz_extra = size_check(e.depth, e.depth_err, star)
    if est.median is None:
        dur = Check("duration", None if "no stellar density" in est.detail.get("why", "") else False, None,
                    "The duration cannot be matched to an orbit: " + est.detail.get("why", "") + ".",
                    None if "no stellar density" in est.detail.get("why", "") else 0.0)
    elif max(est.median, est.detail.get("circular_central_period_d", 0)) > MAX_PLAUSIBLE_PERIOD_D:
        p_c = est.detail.get("circular_central_period_d", est.median)
        dur = Check("duration", False, p_c,
                    f"A {e.duration * 24:.1f} h dip on this star needs an orbit of about {p_c / 365.25:.0f} years "
                    f"even crossing the middle of the star on a circular orbit; it is too long for this star, which "
                    f"points to a bigger (background) star being eclipsed.", 0.0)
    else:
        dur = Check("duration", True, est.median,
                    f"A {e.duration * 24:.1f} h dip on this star fits orbits of {est.lo:.0f}-{est.hi:.0f} d "
                    f"(5-95%, median {est.median:.0f} d) that would show no other transit in the data.",
                    float(min(1.0, max(0.0, 1 - math.log10(max(est.median, 1)) / math.log10(MAX_PLAUSIBLE_PERIOD_D)))))
    checks = [_snr_check(e.ses, SINGLE_MIN_SNR, "dip"), sz, dur, *_merge_event_checks([e]), *could_not_run(),
              Check("depth_consistency", None, None, "Could not run: needs two or more dips."),
              Check("aliases", None, None, "Could not run: one dip gives a period range, not a list of periods.")]
    return DipResult("single", [e], e.ses, e.depth, e.depth_err, e.duration, checks, est, [],
                     {**sz_extra, "period_detail": est.detail})


def _duo(e1: Event, e2: Event, star: Star, tier: FlatTier, covered, span) -> DipResult | None:
    rows = alias_table(e1, e2, tier, covered, span)
    alive = [r for r in rows if not r["dropped"]]
    depth, depth_err = _wmean([e1.depth, e2.depth], [e1.depth_err, e2.depth_err])
    dur = 0.5 * (e1.duration + e2.duration)
    snr = math.hypot(e1.ses, e2.ses)
    sz, sz_extra = size_check(depth, depth_err, star)
    dd = abs(e1.depth - e2.depth)
    dsig = dd / math.hypot(e1.depth_err, e2.depth_err)
    ratio = max(e1.depth, e2.depth) / max(min(e1.depth, e2.depth), 1e-12)
    dratio = max(e1.duration, e2.duration) / min(e1.duration, e2.duration)
    if dsig > 3 and ratio > DUO_DEPTH_RATIO:
        dc = Check("depth_consistency", False, dsig, f"The two dips have different depths ({e1.depth * 1e6:.0f} "
                   f"and {e2.depth * 1e6:.0f} ppm, {dsig:.1f} sigma apart); one planet makes the same dip every time.",
                   0.0)
    elif dratio > DUO_DURATION_RATIO:
        dc = Check("depth_consistency", False, dratio, f"The two dips last {e1.duration * 24:.1f} h and "
                   f"{e2.duration * 24:.1f} h; one planet makes dips of the same length.", 0.0)
    else:
        dc = Check("depth_consistency", True, dsig, f"The two dips match: {e1.depth * 1e6:.0f} and "
                   f"{e2.depth * 1e6:.0f} ppm ({dsig:.1f} sigma apart), {e1.duration * 24:.1f} and "
                   f"{e2.duration * 24:.1f} h.", float(max(0.0, 1 - dsig / 3)))
    est = PeriodEstimate(None, None, None, {})
    if alive:
        est, pf = period_posterior(dur, depth, star, candidates=np.array([r["period_d"] for r in alive]))
        if pf is not None:
            for r, w, fit in zip(alive, pf[0], pf[1]):
                r["weight"], r["duration_fit"] = float(w), float(fit)
    gap = abs(e2.tc - e1.tc)
    if not alive:
        al = Check("aliases", False, 0, f"Every period that fits the {gap:.1f}-day gap (gap/n) would put another "
                                       f"dip where the data show none.", 0.0)
    else:
        al = Check("aliases", True, len(alive), f"{len(alive)} of {len(rows)} periods gap/n (>= {ALIAS_MIN_P:.0f} "
                   f"d) survive; the others would put a dip where the data show none.", 1 / len(alive))
    rho = star.density_solar()[0]
    if not alive:
        dcheck = Check("duration", None, None, "Could not run: no period survives.")
    elif rho is None:
        dcheck = Check("duration", None, None, "Could not run: the TIC has no radius for this star.")
    else:
        ok = [r for r in alive if r.get("duration_fit", 0) >= DURATION_FIT_MIN]
        if ok:
            dcheck = Check("duration", True, len(ok), f"{len(ok)} of the surviving periods give a "
                           f"{dur * 24:.1f} h transit on this star (density {rho:.2f} solar), allowing for "
                           f"eccentric orbits and impact parameters up to 0.9.",
                           float(min(1.0, max(r['duration_fit'] for r in ok))))
        else:
            dcheck = Check("duration", False, 0, f"None of the surviving periods gives a {dur * 24:.1f} h transit "
                           f"on this star (density {rho:.2f} solar), even on an eccentric orbit.", 0.0)
    checks = [_snr_check(snr, DUO_MIN_SNR, "pair of dips"), sz, dcheck, dc, al, *_merge_event_checks([e1, e2]),
              *could_not_run()]
    alive.sort(key=lambda r: -r.get("weight", 0))
    return DipResult("duo", sorted([e1, e2], key=lambda e: e.tc), snr, depth, depth_err, dur, checks, est, alive,
                     {**sz_extra, "aliases_tested": len(rows), "aliases_dropped": len(rows) - len(alive),
                      "period_detail": est.detail})


def _pairable(a: Event, b: Event) -> bool:
    if a.sector == b.sector:
        return False
    ratio = max(a.depth, b.depth) / max(min(a.depth, b.depth), 1e-12)
    dsig = abs(a.depth - b.depth) / math.hypot(a.depth_err, b.depth_err)
    dratio = max(a.duration, b.duration) / min(a.duration, b.duration)
    return (dsig <= 3 or ratio <= DUO_DEPTH_RATIO) and dratio <= DUO_DURATION_RATIO


def search(star: Star, lc, mask: np.ndarray) -> tuple[list[Event], list[DipResult], dict]:
    """All events (vetted) and the single / duo results built from them."""
    import time as _t

    t0 = _t.perf_counter()
    t, f, g = lc.time, lc.flux, lc.sector
    events, tiers = find_events(t, f, g, mask)
    t_search = _t.perf_counter() - t0
    edges = segment_edges(t, g)
    native = {int(p["sector"]): float(p["exptime"]) / 86400 for p in lc.products}
    for e in events:
        fit_trapezoid(e, t[~mask], f[~mask], g[~mask], tier_for(tiers, e.box_duration or e.duration).window)
        vet_event(e, tiers, edges, lc, t, f, lc.bkg, native)
    base = tiers[min(tiers)]
    covered = Coverage(base.t, base.cad)
    span = (float(t.min()), float(t.max())) if len(t) else (0.0, 0.0)
    clean = [e for e in events if not e.failed()]
    results: list[DipResult] = []
    used: set[int] = set()
    pairs = sorted(((i, j) for i in range(len(clean)) for j in range(i + 1, len(clean))
                    if min(clean[i].ses, clean[j].ses) >= DUO_MIN_EACH and _pairable(clean[i], clean[j])),
                   key=lambda ij: -math.hypot(clean[ij[0]].ses, clean[ij[1]].ses))
    for i, j in pairs:
        if i in used or j in used:
            continue
        d = _duo(clean[i], clean[j], star, tier_for(tiers, 0.5 * (clean[i].duration + clean[j].duration)),
                 covered, span)
        if d is not None and d.aliases:
            results.append(d)
            used |= {i, j}
    for i, e in enumerate(clean):
        if i not in used and e.ses >= SINGLE_MIN_SNR:
            results.append(_single(e, star, covered, span))
    # Events that failed a dip check but are strong enough to have been candidates are kept too, so the funnel
    # (and the tests) can show what the checks threw away.
    for e in events:
        if e.failed() and e.ses >= SINGLE_MIN_SNR:
            r = _single(e, star, covered, span)
            results.append(r)
    info = {"events": len(events), "clean_events": len(clean), "search_s": round(t_search, 2),
            "total_s": round(_t.perf_counter() - t0, 2),
            "windows_d": {f"{lo:g}-{hi:g} h": round(3 * hi / 24, 3) for lo, hi in TIERS}}
    return events, results, info
