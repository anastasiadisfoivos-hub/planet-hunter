"""Three worked examples plus an end-to-end backtest, all on FAKE providers.

    uv run python examples/worked_examples.py
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np

from skyforecast import (
    CatchType,
    ForecastConfig,
    Providers,
    Sphere,
    Window,
    backtest,
    chance_of_catch,
    forecast,
)
from skyforecast.fakes import FakeHeatmap, FakeSchedule, FakeSkybot, TruthSky, simulate_night
from skyforecast.geometry import cap_area_deg2, cap_grid
from skyforecast.model import _build_rates

NOW = datetime(2026, 9, 25, 18, tzinfo=UTC)
TONIGHT = Window(datetime(2026, 9, 26, 0, tzinfo=UTC), datetime(2026, 9, 26, 10, tzinfo=UTC))
SHOW = (CatchType.asteroid, CatchType.near_earth_object, CatchType.supernova,
        CatchType.active_galaxy, CatchType.variable_star, CatchType.tidal_disruption_event)


def explain(title: str, sphere: Sphere, providers: Providers) -> None:
    cfg = ForecastConfig()
    f = forecast(sphere, TONIGHT, providers, now=NOW)
    area = cap_area_deg2(sphere.radius_deg)
    print(f"\n=== {title} ===")
    print(f"sphere RA {sphere.ra_deg} Dec {sphere.dec_deg} r {sphere.radius_deg} deg"
          f"   A = 2*pi*(1-cos r) = {area:.3f} deg^2")
    print(f"visits overlapping: {len(f.visits)}   "
          f"P_visit = 1 - prod(1 - q_i) = {f.rubin_visit_probability}")
    rho = _build_rates(providers.heatmap.heatmap(), providers.exposure.exposure(),
                       cfg).density(cap_grid(sphere, cfg.grid_points))
    # Recover V from a non-solar type: mu = rho * A * V
    V = f.mean_count(CatchType.supernova) / (rho[CatchType.supernova] * area)
    print(f"expected sphere-equivalent visits V = sum q_i f_i = {V:.3f}")
    print(f"known solar-system objects in sphere: {len(f.known_solar_system_objects)}")
    print(f"  {'type':<24}{'rho /deg2/visit':>16}{'mu_base':>11}{'mu':>11}{'P(>=1)':>9}")
    for t in SHOW:
        base = rho[t] * area * V
        print(f"  {t:<24}{rho[t]:16.4g}{base:11.4g}{f.mean_count(t):11.4g}"
              f"{chance_of_catch(f, t):9.3f}")
    print("inputs_used:")
    for s in f.inputs_used:
        print(f"  - {s}")


def main() -> None:
    hm = FakeHeatmap()
    full = Providers(schedule=FakeSchedule(), heatmap=hm, exposure=hm, skybot=FakeSkybot())

    explain("1. Small sphere on the ecliptic", Sphere(5.0, 2.2, 0.5), full)
    explain("2. Big sphere at high galactic latitude (south galactic pole)",
            Sphere(12.86, -27.13, 8.0), full)
    explain("3. Sphere outside tonight's schedule", Sphere(150.0, -40.0, 2.0), full)
    explain("3b. Same sphere, schedule provider down (climatology fallback)",
            Sphere(150.0, -40.0, 2.0),
            Providers(heatmap=hm, exposure=hm, skybot=FakeSkybot()))

    print("\n=== End-to-end backtest on simulated reality (8 nights x 200 spheres) ===")
    rng = np.random.default_rng(5)
    truth = TruthSky()
    types = (CatchType.supernova, CatchType.variable_star, CatchType.asteroid,
             CatchType.flare, CatchType.near_earth_object)
    fcs, disc, vis = [], [], []
    for night in range(8):
        start = TONIGHT.start + timedelta(days=night)
        sched = FakeSchedule(night_start=start)
        w = Window(start, start + timedelta(hours=10))
        d, v = simulate_night(sched, w, rng, truth, types=types)
        disc += d
        vis += v
        prov = Providers(schedule=sched, heatmap=hm, exposure=hm)
        for _ in range(200):
            s = Sphere(float(rng.uniform(-45, 45) % 360), float(rng.uniform(-45, 25)),
                       float(math.exp(rng.uniform(math.log(0.05), math.log(3)))))
            fcs.append(forecast(s, w, prov))
    print(backtest(fcs, disc, observed_visits=vis, types=types, min_bin_count=30).summary())


if __name__ == "__main__":
    main()
