from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from skyforecast import CatchType, Expected, Forecast, Sphere, Window, backtest
from skyforecast.backtest import poisson_interval, wilson_interval

T0 = datetime(2026, 1, 1, tzinfo=UTC)
GEN = datetime(2025, 12, 31, tzinfo=UTC)


def make_world(n=3000, scale=1.0, seed=3):
    """Synthetic forecasts with known means. Reality follows the zero-inflated model: Rubin
    visits with probability pv, then catches ~ Poisson(mean / pv * scale)."""
    rng = np.random.default_rng(seed)
    forecasts, discoveries, visits = [], [], []
    for i in range(n):
        s = Sphere(float(rng.uniform(0, 360)), float(rng.uniform(-60, 20)), 1.0)
        w = Window(T0 + timedelta(days=i), T0 + timedelta(days=i, hours=10))
        mus = {t: float(rng.choice([0.01, 0.05, 0.12, 0.3, 0.7, 2.0])) for t in
               (CatchType.supernova, CatchType.asteroid, CatchType.flare)}
        pv = float(rng.uniform(0.05, 1))
        forecasts.append(Forecast(s, w, pv, [], [Expected(t, m) for t, m in mus.items()], [],
                                  GEN, ["fake"]))
        if rng.random() >= pv:
            continue  # Rubin never came: nothing can be caught
        visits.append({"time": (w.start + timedelta(hours=1)).isoformat(),
                       "ra_deg": s.ra_deg, "dec_deg": s.dec_deg})
        for t, m in mus.items():
            for _ in range(rng.poisson(m / pv * scale)):
                discoveries.append({"type": t.value, "ra_deg": s.ra_deg, "dec_deg": s.dec_deg,
                                    "detected_at": (w.start + timedelta(hours=5)).isoformat()})
    return forecasts, discoveries, visits


def test_calibrated_world_passes():
    f, d, v = make_world()
    r = backtest(f, d, observed_visits=v)
    assert r.calibrated, r.summary()
    judged = [b for b in r.bins if b.calibrated is not None]
    assert len(judged) >= 5
    assert r.pit_variance == pytest.approx(1 / 12, abs=0.01)
    assert all(b.calibrated for b in r.visit_bins if b.calibrated is not None)
    assert "CALIBRATED" in r.summary()


def test_tripled_reality_is_flagged():
    f, d, _ = make_world(scale=3.0)
    r = backtest(f, d)
    assert not r.calibrated
    assert r.miscalibrated_bins
    for t in r.types:
        assert t.calibrated is False and t.ratio == pytest.approx(3, rel=0.15)
    assert "<-- off" in r.summary()


def test_matching_respects_window_sphere_and_type():
    s = Sphere(10, 10, 1)
    w = Window(T0, T0 + timedelta(hours=1))
    f = Forecast(s, w, None, [], [Expected(CatchType.comet, 0.1)], [], GEN, [])
    d = [
        {"type": "comet", "ra_deg": 10.5, "dec_deg": 10, "detected_at": T0.isoformat()},  # in
        {"type": "comet", "ra_deg": 10, "dec_deg": 11.2, "detected_at": T0.isoformat()},  # far
        {"type": "comet", "ra_deg": 10, "dec_deg": 10,
         "detected_at": (T0 + timedelta(hours=1)).isoformat()},                          # end
        {"type": "flare", "ra_deg": 10, "dec_deg": 10, "detected_at": T0.isoformat()},  # type
        {"type": "not-a-type", "ra_deg": 10, "dec_deg": 10, "detected_at": T0.isoformat()},
    ]
    r = backtest([f], d)
    assert r.n_discoveries_matched == 2  # the comet and the flare fall in the trap
    comet = next(t for t in r.types if t.type == CatchType.comet)
    assert comet.observed == 1


def test_accepts_contract_dicts():
    f, d, _ = make_world(n=50)
    r = backtest([x.to_dict() for x in f], d)
    assert r.n_forecasts == 50


def test_interval_helpers():
    lo, hi = wilson_interval(10, 100)
    assert lo < 0.1 < hi
    assert poisson_interval(0)[0] == 0
    lo, hi = poisson_interval(10)
    assert lo == pytest.approx(4.795, abs=1e-3) and hi == pytest.approx(18.39, abs=1e-2)


def test_false_alarm_rate_is_controlled():
    """One Bonferroni correction over all tests -> ~5% false alarms on honest worlds."""
    flagged = 0
    runs = 20
    for seed in range(100, 100 + runs):
        f, d, v = make_world(n=800, seed=seed)
        flagged += not backtest(f, d, observed_visits=v).calibrated
    assert flagged / runs <= 0.15


def test_power_against_mild_bias():
    """A 30% overestimate is caught most of the time at this sample size."""
    caught = sum(not backtest(*make_world(n=1500, scale=0.7, seed=s)[:2]).calibrated
                 for s in range(200, 210))
    assert caught >= 8
