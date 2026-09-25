import numpy as np
import pytest

from skyforecast import CatchType, ForecastConfig, Sphere
from skyforecast.geometry import cap_grid, pixel_area_deg2
from skyforecast.providers import Exposure
from skyforecast.rates import BaseRates

CFG = ForecastConfig()


def _heatmap(cells, nside=4):
    return {"generated_at": "2026-09-01T00:00:00Z", "grid": f"healpix nside={nside}",
            "cells": cells}


def _all_sky(counts_for, visits=100.0, nside=4):
    npix = 12 * nside**2
    cells = [{"pix": p, "counts": {"variable_star": counts_for(p)}} for p in range(npix)
             if counts_for(p)]
    return BaseRates.build(_heatmap(cells, nside),
                           Exposure(f"healpix nside={nside}", {p: visits for p in range(npix)},
                                    365), CFG)


def test_empty_cell_forecasts_stratum_mean_not_zero():
    # Rates are the same everywhere (10 per pixel) except one unlucky empty pixel:
    # Poisson noise explains the scatter, so the prior pools hard and pixel 0 gets ~the mean.
    r = _all_sky(lambda p: 0 if p == 0 else 10)
    own = 10 / (100 * r.pixel_area)
    vs = r.rates[CatchType.variable_star]
    assert vs[5] == pytest.approx(own, rel=0.05)
    assert 0.5 * own < vs[0] < own


def test_genuinely_different_rates_are_not_smoothed_away():
    # Half the sky at 400 per pixel, half at 4: far more scatter than Poisson noise explains.
    r = _all_sky(lambda p: 400 if p % 2 else 4)
    vs = r.rates[CatchType.variable_star] * 100 * r.pixel_area  # back to counts per pixel
    assert vs[1] == pytest.approx(400, rel=0.05)
    assert 4 <= vs[0] < 8  # stays near its own 4, nowhere near the mean of ~200


def test_type_never_seen_gets_positive_floor():
    r = BaseRates.build(_heatmap([{"pix": 0, "counts": {"supernova": 3}}]),
                        Exposure("healpix nside=4", {0: 50.0}, 30), CFG)
    assert np.all(r.rates[CatchType.kilonova] > 0)
    total_E = 50.0 * r.pixel_area
    floor = 0.5 / total_E
    # Nothing to learn from: full pooling onto the floor, exposed or not.
    assert r.rates[CatchType.kilonova][1] == pytest.approx(floor)
    assert r.rates[CatchType.kilonova][0] == pytest.approx(floor, rel=0.01)


def test_well_observed_cell_follows_its_data():
    cells = [{"pix": 7, "counts": {"flare": 5000}}]
    r = BaseRates.build(_heatmap(cells), Exposure("healpix nside=4", {7: 1000.0}, 365), CFG)
    assert r.rates[CatchType.flare][7] == pytest.approx(5000 / (1000 * r.pixel_area), rel=0.01)


def test_unknown_count_keys_are_ignored():
    r = BaseRates.build(_heatmap([{"pix": 0, "counts": {"dragon": 9, "comet": 1}}]), None, CFG)
    assert r.span_days is None
    assert r.rates[CatchType.comet][0] > 0


def test_mismatched_exposure_grid_raises():
    with pytest.raises(ValueError):
        BaseRates.build(_heatmap([]), Exposure("healpix nside=8", {}, 1), CFG)


def test_smoothed_rates_recover_synthetic_truth(heatmap):
    from skyforecast.fakes import synthetic_rate
    from skyforecast.geometry import ecliptic_latitude, galactic_latitude

    r = BaseRates.build(heatmap.heatmap(), heatmap.exposure(), CFG)
    s = Sphere(10, 4, 3)  # on the ecliptic, well exposed
    d = r.density(cap_grid(s))
    truth = synthetic_rate(CatchType.asteroid, ecliptic_latitude(10, 4), galactic_latitude(10, 4))
    assert d[CatchType.asteroid] == pytest.approx(float(truth[0]), rel=0.1)
    assert pixel_area_deg2(r.hp) == pytest.approx(3.357, rel=1e-3)
