import math

import numpy as np
import pytest

from skyforecast import CatchType, Expected, Forecast, Sphere, chance_of_catch, p_at_least_one
from skyforecast.probability import count_cdf


def test_unknown_visit_probability_is_plain_poisson():
    assert p_at_least_one(0.1053605) == pytest.approx(0.1, rel=1e-5)  # "1 in 10"
    assert p_at_least_one(2.0, None) == pytest.approx(1 - math.exp(-2))


def test_never_exceeds_visit_probability():
    assert p_at_least_one(1e6, 0.3) == pytest.approx(0.3)
    assert p_at_least_one(5.0, 0.0) == 0.0
    assert p_at_least_one(0.0, 0.7) == 0.0


def test_certain_visit_reduces_to_poisson():
    assert p_at_least_one(1.3, 1.0) == pytest.approx(1 - math.exp(-1.3))


def test_cdf_is_consistent_with_probability_and_mean():
    mu, pv = 2.5, 0.6
    assert count_cdf(-1, mu, pv) == 0
    assert 1 - count_cdf(0, mu, pv) == pytest.approx(p_at_least_one(mu, pv))
    ks = np.arange(0, 200)
    pmf = np.diff(np.concatenate([[0.0], count_cdf(ks, mu, pv)]))
    assert (pmf * ks).sum() == pytest.approx(mu)


def test_chance_of_catch_uses_forecast_fields():
    from datetime import UTC, datetime, timedelta

    from skyforecast import Window
    t = datetime(2026, 1, 1, tzinfo=UTC)
    f = Forecast(Sphere(0, 0, 1), Window(t, t + timedelta(hours=1)), 0.5, [],
                 [Expected(CatchType.comet, 0.2)], [], t, [])
    assert chance_of_catch(f, "comet") == pytest.approx(0.5 * (1 - math.exp(-0.4)))
    assert chance_of_catch(f, CatchType.flare) == 0


def _brute_p0(mu, coverage):
    """Enumerate every subset of executed visits."""
    import itertools
    q = [c[0] for c in coverage]
    f = [c[1] for c in coverage]
    V = sum(a * b for a, b in coverage)
    lam = mu / V
    total = 0.0
    for bits in itertools.product([0, 1], repeat=len(q)):
        pr = math.prod(qi if b else 1 - qi for qi, b in zip(q, bits, strict=True))
        total += pr * math.exp(-lam * sum(fi for fi, b in zip(f, bits, strict=True) if b))
    return total


def test_coverage_probability_matches_brute_force():
    from skyforecast.probability import p_at_least_one_coverage
    cov = [(0.8, 1.0), (0.8, 1.0), (0.5, 0.02), (0.9, 0.3)]
    for mu in (0.01, 0.5, 3.0, 200.0):
        assert p_at_least_one_coverage(mu, cov)[0] == pytest.approx(1 - _brute_p0(mu, cov))


def test_sliver_does_not_inflate_the_chance():
    """One full pair plus a sliver: the chance is capped by the pair, not by P_visit."""
    from skyforecast.probability import p_at_least_one_coverage
    cov = [(0.8, 1.0), (0.8, 1.0), (0.8, 0.001)]
    p_touch = 1 - 0.2**3
    exact = p_at_least_one_coverage(500.0, cov)[0]
    assert exact == pytest.approx(1 - 0.2 * 0.2 * (1 - 0.8 + 0.8 * math.exp(-500 / 1.6008 *
                                                                            0.001)), rel=1e-6)
    assert exact < p_touch
    assert p_at_least_one(500.0, p_touch) == pytest.approx(p_touch)  # fallback overstates


def test_monte_carlo_cdf_agrees_with_exact_zero_probability():
    from skyforecast.probability import count_cdf_coverage, p_at_least_one_coverage
    cov = [(0.8, 1.0), (0.6, 0.5)]
    rng = np.random.default_rng(0)
    cdf0 = count_cdf_coverage(np.array([0]), np.array([2.0]), cov, rng, draws=20000)[0]
    assert cdf0 == pytest.approx(1 - p_at_least_one_coverage(2.0, cov)[0], abs=0.01)
    assert count_cdf_coverage(np.array([-1]), np.array([2.0]), cov, rng)[0] == 0


def test_chance_of_catch_prefers_coverage_and_json_falls_back(full):
    from conftest import NOW, TONIGHT

    from skyforecast import forecast
    f = forecast(Sphere(5, 2.2, 0.5), TONIGHT, full, now=NOW)
    assert f.coverage is not None
    g = Forecast.from_dict(f.to_dict())
    assert g.coverage is None
    t = CatchType.supernova
    assert chance_of_catch(g, t) == pytest.approx(
        float(p_at_least_one(f.mean_count(t), f.rubin_visit_probability)))
    assert chance_of_catch(f, t) <= chance_of_catch(g, t) + 1e-12
