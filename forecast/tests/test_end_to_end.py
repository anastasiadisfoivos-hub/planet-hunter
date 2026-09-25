"""Model + backtest together: forecasts made from the fake heatmap and schedule should be
calibrated against a reality simulated (one shared sky per night) from the same synthetic truth."""

import math
from datetime import UTC, datetime, timedelta

import numpy as np

from skyforecast import CatchType, Providers, Sphere, Window, backtest, forecast
from skyforecast.fakes import FakeSchedule, TruthSky, simulate_night

TYPES = (CatchType.supernova, CatchType.variable_star, CatchType.asteroid, CatchType.flare,
         CatchType.near_earth_object)


def run_world(heatmap, nights=8, spheres=60, seed=11):
    rng = np.random.default_rng(seed)
    truth = TruthSky()
    forecasts, discoveries, visits = [], [], []
    for night in range(nights):
        start = datetime(2026, 9, 26, tzinfo=UTC) + timedelta(days=night)
        sched = FakeSchedule(night_start=start)
        w = Window(start, start + timedelta(hours=10))
        d, v = simulate_night(sched, w, rng, truth, types=TYPES)
        discoveries += d
        visits += v
        prov = Providers(schedule=sched, heatmap=heatmap, exposure=heatmap)
        for _ in range(spheres):
            s = Sphere(float(rng.uniform(-45, 45) % 360), float(rng.uniform(-45, 25)),
                       float(math.exp(rng.uniform(math.log(0.05), math.log(3)))))
            forecasts.append(forecast(s, w, prov))
    return forecasts, discoveries, visits


def test_model_is_calibrated_against_simulated_reality(heatmap):
    f, d, v = run_world(heatmap)
    r = backtest(f, d, observed_visits=v, types=TYPES, min_bin_count=30)
    assert {t.type for t in r.types} == set(TYPES)
    assert r.calibrated, r.summary()
    for t in r.types:
        assert 0.8 < t.ratio < 1.25, r.summary()
