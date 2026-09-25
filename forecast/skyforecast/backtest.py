"""Backtest: compare past forecasts with the Discoveries that actually arrived.

A Discovery counts toward a forecast when its detected_at is in [start, end) and it lies within
the sphere. For each (forecast, CatchType) we have a predicted mean mu and an observed count n.

1. Probability calibration ("did 1 in 10 happen ~1 in 10 times?"):
   p = P(n >= 1), exact from the forecast's per-visit coverage when it has it (in-process
   Forecasts), else P_visit * (1 - exp(-mu / P_visit)) (see probability.py). Outcome
   y = [n >= 1]. Forecasts are binned by p; per bin we report the mean p, the observed
   frequency of y and a Wilson 95% interval. A bin is flagged when a Bonferroni-adjusted
   Wilson interval excludes the mean p. The correction is 1 - 0.05/k over ALL k judged tests
   (bins, types, visit bins), so an honestly calibrated forecaster gets a MISCALIBRATED
   verdict only ~5% of the time. Brier score = mean((p - y)^2).
2. Count calibration per type: observed / expected with a 95% interval. Totals are exact
   Poisson when every visit is certain; otherwise visit uncertainty adds variance
   (lambda^2 sum q(1-q) f^2 with coverage, else mu^2 (1 - P_visit) / P_visit) and a normal
   interval is used. A type is flagged when O/E is significantly off AND off by more than
   type_tolerance (10%). Plus a randomized PIT histogram (Czado, Gneiting & Held 2009): PIT
   variance ~1/12 when calibrated; larger means reality is more spread out than forecast.
3. Visit calibration (optional, if actual Rubin visits are supplied): same as (1) for
   rubin_visit_probability, outcome = any actual visit's footprint touched the sphere.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

from .config import RUBIN_FOV_RADIUS_DEG
from .contract import CatchType, Forecast, parse_time
from .geometry import separation_deg
from .probability import (
    count_cdf,
    count_cdf_coverage,
    p_at_least_one,
    p_at_least_one_coverage,
)

DEFAULT_BIN_EDGES = (0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0)
Z95 = 1.959963984540054


def wilson_interval(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, centre - half)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return lo, hi


def poisson_interval(k: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact (Garwood) interval for a Poisson mean given k observed."""
    lo = 0.0 if k == 0 else stats.chi2.ppf(alpha / 2, 2 * k) / 2
    hi = stats.chi2.ppf(1 - alpha / 2, 2 * k + 2) / 2
    return float(lo), float(hi)


@dataclass(frozen=True)
class CalibrationBin:
    lo: float
    hi: float
    n: int
    mean_predicted: float
    observed_frequency: float
    ci_lo: float
    ci_hi: float
    # None when the bin has too few forecasts to judge.
    calibrated: bool | None


@dataclass(frozen=True)
class TypeCount:
    type: CatchType
    n_forecasts: int
    expected: float
    observed: int
    ratio: float | None
    ratio_ci: tuple[float, float] | None
    calibrated: bool | None


@dataclass
class BacktestReport:
    n_forecasts: int
    n_discoveries_matched: int
    bins: list[CalibrationBin]
    brier: float | None
    types: list[TypeCount]
    pit_histogram: list[int]
    pit_variance: float | None
    visit_bins: list[CalibrationBin] = field(default_factory=list)
    visit_brier: float | None = None

    @property
    def miscalibrated_bins(self) -> list[CalibrationBin]:
        return [b for b in self.bins + self.visit_bins if b.calibrated is False]

    @property
    def miscalibrated_types(self) -> list[TypeCount]:
        return [t for t in self.types if t.calibrated is False]

    @property
    def calibrated(self) -> bool:
        return not self.miscalibrated_bins and not self.miscalibrated_types

    def summary(self) -> str:
        out = [f"Backtest: {self.n_forecasts} forecasts, "
               f"{self.n_discoveries_matched} discoveries matched",
               f"Verdict: {'CALIBRATED' if self.calibrated else 'MISCALIBRATED'}", ""]
        out.append(_bin_table("P(at least one catch of a type)", self.bins, self.brier))
        out.append("")
        out.append("Counts by type (observed / expected, 95% CI):")
        for t in self.types:
            if t.ratio is None:
                out.append(f"  {t.type:<24} exp {t.expected:9.3f}  obs {t.observed:5d}")
                continue
            flag = "" if t.calibrated is not False else "  <-- off"
            out.append(f"  {t.type:<24} exp {t.expected:9.3f}  obs {t.observed:5d}  "
                       f"O/E {t.ratio:5.2f} [{t.ratio_ci[0]:.2f}, {t.ratio_ci[1]:.2f}]{flag}")
        if self.pit_variance is not None:
            out.append("")
            out.append(f"PIT histogram (10 bins): {self.pit_histogram}  "
                       f"variance {self.pit_variance:.4f} (calibrated ~ {1 / 12:.4f})")
        if self.visit_bins:
            out.append("")
            out.append(_bin_table("Rubin visit probability", self.visit_bins, self.visit_brier))
        return "\n".join(out)


def _bin_table(title: str, bins: list[CalibrationBin], brier: float | None) -> str:
    rows = [f"{title}:" + (f"  Brier {brier:.4f}" if brier is not None else "")
            + "  (flags use Bonferroni-adjusted intervals)",
            "  bin           n   predicted  observed  95% CI"]
    for b in bins:
        if b.n == 0:
            continue
        flag = {True: "", False: "  <-- off", None: "  (too few)"}[b.calibrated]
        rows.append(f"  [{b.lo:.2f},{b.hi:.2f}) {b.n:6d}   {b.mean_predicted:7.3f}   "
                    f"{b.observed_frequency:7.3f}  [{b.ci_lo:.3f}, {b.ci_hi:.3f}]{flag}")
    return "\n".join(rows)


def _bonferroni_z(k: int, alpha: float = 0.05) -> float:
    return float(stats.norm.ppf(1 - alpha / (2 * max(k, 1))))


def _bin_index(p: np.ndarray, edges: tuple[float, ...]) -> np.ndarray:
    return np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)


def _n_judged_bins(p: np.ndarray, edges: tuple[float, ...], min_count: int) -> int:
    idx = _bin_index(p, edges)
    return sum(int((idx == i).sum()) >= min_count for i in range(len(edges) - 1))


def _calibration(p: np.ndarray, y: np.ndarray, edges: tuple[float, ...], min_count: int,
                 z_adj: float) -> tuple[list[CalibrationBin], float | None]:
    bins = []
    idx = _bin_index(p, edges)
    for i in range(len(edges) - 1):
        m = idx == i
        n = int(m.sum())
        if n == 0:
            bins.append(CalibrationBin(edges[i], edges[i + 1], 0, math.nan, math.nan, 0, 1, None))
            continue
        k = int(y[m].sum())
        mp = float(p[m].mean())
        lo, hi = wilson_interval(k, n)
        alo, ahi = wilson_interval(k, n, z_adj)
        ok = (alo <= mp <= ahi) if n >= min_count else None
        bins.append(CalibrationBin(edges[i], edges[i + 1], n, mp, k / n, lo, hi, ok))
    brier = float(np.mean((p - y) ** 2)) if len(p) else None
    return bins, brier


def _as_forecast(f: Forecast | dict) -> Forecast:
    return f if isinstance(f, Forecast) else Forecast.from_dict(f)


def backtest(forecasts: Iterable[Forecast | dict], discoveries: Iterable[dict[str, Any]], *,
             observed_visits: Iterable[dict[str, Any]] | None = None,
             types: Iterable[CatchType | str] | None = None,
             bin_edges: tuple[float, ...] = DEFAULT_BIN_EDGES, min_bin_count: int = 20,
             min_type_expected: float = 5.0, type_tolerance: float = 0.10,
             fov_radius_deg: float = RUBIN_FOV_RADIUS_DEG,
             seed: int = 0) -> BacktestReport:
    """types: restrict scoring to these CatchTypes (e.g. only those whose source is live).
    type_tolerance: a type's total is flagged only if O/E is significantly off AND off by more
    than this fraction (big totals make tiny, harmless biases 'significant')."""
    fcs = [_as_forecast(f) for f in forecasts]
    keep = {CatchType(t) for t in types} if types is not None else set(CatchType)

    type_code = {t: i for i, t in enumerate(CatchType)}
    code_of = {str(t): i for t, i in type_code.items()}
    d_code, d_ra, d_dec, d_ts = [], [], [], []
    for d in discoveries:
        c = code_of.get(d["type"])
        if c is None:
            continue
        d_code.append(c)
        d_ra.append(float(d["ra_deg"]))
        d_dec.append(float(d["dec_deg"]))
        d_ts.append(parse_time(d["detected_at"]).timestamp())
    order = np.argsort(d_ts, kind="stable")
    d_ts_a = np.asarray(d_ts, dtype=float)[order]
    d_ra_a = np.asarray(d_ra, dtype=float)[order]
    d_dec_a = np.asarray(d_dec, dtype=float)[order]
    d_code_a = np.asarray(d_code, dtype=int)[order]

    mus, ns, ts, pvs, fidx = [], [], [], [], []
    matched = 0
    for fi, f in enumerate(fcs):
        lo = np.searchsorted(d_ts_a, f.window.start.timestamp(), side="left")
        hi = np.searchsorted(d_ts_a, f.window.end.timestamp(), side="left")
        counts = np.zeros(len(type_code), dtype=int)
        if hi > lo:
            dec = d_dec_a[lo:hi]
            near = np.flatnonzero(np.abs(dec - f.sphere.dec_deg) <= f.sphere.radius_deg) + lo
            sep = separation_deg(d_ra_a[near], d_dec_a[near], f.sphere.ra_deg,
                                 f.sphere.dec_deg)
            hit_codes = d_code_a[near[sep <= f.sphere.radius_deg]]
            matched += len(hit_codes)
            counts = np.bincount(hit_codes, minlength=len(type_code))
        for e in f.expected:
            if e.type not in keep:
                continue
            mus.append(e.mean_count)
            pvs.append(np.nan if f.rubin_visit_probability is None
                       else f.rubin_visit_probability)
            fidx.append(fi)
            ns.append(int(counts[type_code[e.type]]))
            ts.append(e.type)
    mu = np.array(mus, dtype=float)
    n = np.array(ns, dtype=int)
    types_arr = np.array([str(t) for t in ts])

    pv = np.array(pvs, dtype=float)
    fidx_a = np.array(fidx, dtype=int)
    p = p_at_least_one(mu, pv)
    # Exact probabilities where the forecast carries per-visit coverage.
    exact = np.zeros(len(mu), dtype=bool)
    starts = np.searchsorted(fidx_a, np.arange(len(fcs) + 1))
    rows = {fi: slice(starts[fi], starts[fi + 1]) for fi, f in enumerate(fcs)
            if f.coverage is not None and starts[fi + 1] > starts[fi]}
    for fi, sl in rows.items():
        p[sl] = p_at_least_one_coverage(mu[sl], fcs[fi].coverage)
        exact[sl] = True
    y = (n >= 1).astype(float)

    # Visit outcomes (optional): did any actual visit's footprint touch the sphere?
    pv_visit, y_visit = np.array([]), np.array([])
    if observed_visits is not None:
        vis = list(observed_visits)
        v_ra = np.array([float(v["ra_deg"]) for v in vis])
        v_dec = np.array([float(v["dec_deg"]) for v in vis])
        v_ts = np.array([parse_time(v["time"]).timestamp() for v in vis])
        pvl, yvl = [], []
        for f in fcs:
            if f.rubin_visit_probability is None:
                continue
            m = (v_ts >= f.window.start.timestamp()) & (v_ts < f.window.end.timestamp())
            hit = bool(m.any() and np.any(
                separation_deg(v_ra[m], v_dec[m], f.sphere.ra_deg, f.sphere.dec_deg)
                < f.sphere.radius_deg + fov_radius_deg))
            pvl.append(f.rubin_visit_probability)
            yvl.append(float(hit))
        pv_visit, y_visit = np.array(pvl, dtype=float), np.array(yvl)

    # Per-type totals and their standard deviation under the zero-inflated model.
    present = [t for t in CatchType if np.any(types_arr == str(t))]
    pv1 = np.where(np.isnan(pv), 1.0, np.clip(pv, 0.0, 1.0))
    # Extra (beyond-Poisson) variance of each (forecast, type) count from visit uncertainty.
    extra_var = mu**2 * (1 - pv1) / np.where(pv1 > 0, pv1, 1)
    for fi, sl in rows.items():
        if not fcs[fi].coverage:
            continue
        q, fr = np.asarray(fcs[fi].coverage, dtype=float).T
        V = float(np.sum(q * fr))
        if V > 0:
            extra_var[sl] = (mu[sl] / V) ** 2 * float(np.sum(q * (1 - q) * fr**2))
    totals = []
    for t in present:
        m = types_arr == str(t)
        extra = float(extra_var[m].sum())
        totals.append((t, int(m.sum()), float(mu[m].sum()), int(n[m].sum()), extra))
    type_judged = [max(e, o) >= min_type_expected for _, _, e, o, _ in totals]

    # One Bonferroni correction over every judged test, so the overall verdict has ~5% false
    # alarm rate on an honestly calibrated forecaster.
    k_total = (_n_judged_bins(p, bin_edges, min_bin_count) + sum(type_judged)
               + _n_judged_bins(pv_visit, bin_edges, min_bin_count))
    alpha_adj = 0.05 / max(k_total, 1)
    z_adj = _bonferroni_z(k_total)

    bins, brier = _calibration(p, y, bin_edges, min_bin_count, z_adj)

    type_rows = []
    for (t, count, exp_n, obs_n, extra), judged in zip(totals, type_judged, strict=True):
        if exp_n <= 0:
            type_rows.append(TypeCount(t, count, exp_n, obs_n, None, None,
                                       None if obs_n == 0 else False))
            continue
        if extra > 1e-12:
            sd = math.sqrt(exp_n + extra)
            lo, hi = obs_n - Z95 * sd, obs_n + Z95 * sd
            alo, ahi = obs_n - z_adj * sd, obs_n + z_adj * sd
        else:
            lo, hi = poisson_interval(obs_n)
            alo, ahi = poisson_interval(obs_n, alpha_adj)
        type_rows.append(TypeCount(t, count, exp_n, obs_n, obs_n / exp_n,
                                   (max(lo, 0.0) / exp_n, hi / exp_n),
                                   (alo <= exp_n <= ahi
                                    or abs(obs_n / exp_n - 1) <= type_tolerance)
                                   if judged else None))

    rng = np.random.default_rng(seed)
    pos = mu > 0
    if pos.any():
        cdf_hi = count_cdf(n, mu, pv)
        cdf_lo = count_cdf(n - 1, mu, pv)
        for fi, sl in rows.items():
            idx = np.arange(sl.start, sl.stop)[pos[sl]]
            if len(idx):
                ks = np.concatenate([n[idx], n[idx] - 1])
                both = count_cdf_coverage(ks, np.concatenate([mu[idx], mu[idx]]),
                                          fcs[fi].coverage, rng)
                cdf_hi[idx], cdf_lo[idx] = both[: len(idx)], both[len(idx):]
        cdf_hi, cdf_lo = cdf_hi[pos], cdf_lo[pos]
        u = cdf_lo + rng.random(pos.sum()) * (cdf_hi - cdf_lo)
        pit_hist = np.histogram(u, bins=10, range=(0, 1))[0].tolist()
        pit_var: float | None = float(np.var(u))
    else:
        pit_hist, pit_var = [0] * 10, None

    report = BacktestReport(len(fcs), matched, bins, brier, type_rows, pit_hist, pit_var)
    if observed_visits is not None:
        report.visit_bins, report.visit_brier = _calibration(
            pv_visit, y_visit, bin_edges, min_bin_count, z_adj)
    return report


__all__ = ["BacktestReport", "CalibrationBin", "TypeCount", "backtest"]
