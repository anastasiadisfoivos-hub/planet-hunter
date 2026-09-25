"""Turning a Forecast's mean counts into probabilities.

Exact (in-process Forecasts, which carry per-visit coverage (q_i, f_i)):
With independent visits and lambda = mu / V (V = sum q_i f_i), a visit i that happens
contributes Poisson(lambda * f_i) catches, so

    P(n = 0)  = prod_i (1 - q_i + q_i * exp(-lambda * f_i))
    P(n >= 1) = 1 - P(n = 0)

Fallback (Forecasts read back from JSON, which carry only the contract fields): a
zero-inflated Poisson - with probability 1 - P_visit nothing is seen, otherwise Poisson with
mean mu / P_visit:

    P(n >= 1) = P_visit * (1 - exp(-mu / P_visit))

and plain Poisson 1 - exp(-mu) when P_visit is unknown. The fallback overstates P(n >= 1)
when the sphere hangs on few visits and a sliver of a neighbouring field inflates P_visit.

Use chance_of_catch, not 1 - exp(-mu), for "1 in N" statements in the UI.
"""

from __future__ import annotations

import numpy as np
from scipy import special, stats

from .contract import CatchType, Forecast


def _pv(p_visit) -> np.ndarray:
    pv = np.asarray(p_visit, dtype=float)
    return np.where(np.isnan(pv) | (pv >= 1.0), 1.0, pv)


def p_at_least_one(mu, p_visit=None) -> np.ndarray:
    """Zero-inflated fallback, vectorised. p_visit None/NaN means unknown -> plain Poisson."""
    mu = np.asarray(mu, dtype=float)
    pv = _pv(np.nan if p_visit is None else p_visit)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = pv * (1.0 - np.exp(-mu / pv))
    return np.where(pv > 0, p, 0.0)


def count_cdf(k, mu, p_visit=None) -> np.ndarray:
    """P(n <= k) under the zero-inflated fallback (k < 0 -> 0)."""
    k, mu = np.asarray(k), np.asarray(mu, dtype=float)
    pv = _pv(np.nan if p_visit is None else p_visit)
    with np.errstate(divide="ignore", invalid="ignore"):
        inner = np.where(pv > 0, stats.poisson.cdf(k, np.where(pv > 0, mu / pv, 0.0)), 1.0)
    return np.where(k < 0, 0.0, (1.0 - pv) + pv * inner)


def p_at_least_one_coverage(mu, coverage) -> np.ndarray:
    """Exact P(n >= 1) for each mean in mu, given [(q_i, f_i)] of the planned visits."""
    mu = np.atleast_1d(np.asarray(mu, dtype=float))
    if not coverage:
        return np.zeros_like(mu)
    q, f = np.asarray(coverage, dtype=float).T
    V = float(np.sum(q * f))
    if V <= 0:
        return np.zeros_like(mu)
    lam = mu / V
    log_p0 = np.log(1.0 - q[None, :] + q[None, :] * np.exp(-lam[:, None] * f[None, :])).sum(1)
    return 1.0 - np.exp(log_p0)


def count_cdf_coverage(k, mu, coverage, rng: np.random.Generator,
                       draws: int = 400) -> np.ndarray:
    """P(n <= k) for each (k, mu) pair, by Monte Carlo over which visits happen."""
    k = np.atleast_1d(np.asarray(k))
    mu = np.atleast_1d(np.asarray(mu, dtype=float))
    if not coverage:
        return np.where(k < 0, 0.0, 1.0)
    q, f = np.asarray(coverage, dtype=float).T
    V = float(np.sum(q * f))
    if V <= 0:
        return np.where(k < 0, 0.0, 1.0)
    covered = (rng.random((draws, len(q))) < q) @ f           # (draws,)
    lam = (mu / V)[:, None] * covered[None, :]                # (n, draws)
    kk = np.maximum(k, 0)[:, None] + 1.0
    # Poisson cdf(k; lam) = Q(k + 1, lam); lam = 0 -> 1.
    cdf = np.where(lam > 0, special.gammaincc(kk, np.where(lam > 0, lam, 1.0)), 1.0).mean(1)
    return np.where(k < 0, 0.0, cdf)


def chance_of_catch(f: Forecast, t: CatchType | str) -> float:
    """P(at least one catch of type t in this forecast's sphere and window)."""
    mu = f.mean_count(t)
    if f.coverage is not None:
        return float(p_at_least_one_coverage(mu, f.coverage)[0])
    return float(p_at_least_one(mu, f.rubin_visit_probability))
