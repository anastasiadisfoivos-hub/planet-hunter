"""Offline unit tests on synthetic data (no network)."""

import math

import numpy as np
import pytest

from skyfaint import coverage, noise, targets, tglc


def test_url_matches_mast_layout():
    # The MAST data URI of TIC 218795833 (TOI-519) in sector 7, as the MAST API lists it.
    assert tglc.url_for(5707485527450614656, 7, 2, 3) == (
        "https://archive.stsci.edu/hlsps/tglc/s0007/cam2-ccd3/0057/0748/5527/4506/"
        "hlsp_tglc_tess_ffi_gaiaid-5707485527450614656-s0007-cam2-ccd3_tess_v1_llc.fits")


def _white(cadence_min: float, sigma: float, days: float = 25, seed: int = 0):
    rng = np.random.default_rng(seed)
    t = np.arange(0, days, cadence_min / 1440)
    return t, 1 + rng.normal(0, sigma, len(t))


@pytest.mark.parametrize("cadence", [10.0, 30.0])
def test_cdpp_white_noise(cadence):
    sigma = 5e-3
    t, f = _white(cadence, sigma)
    for hours in (1.0, 2.0):
        c, _ = noise.sector_cdpp(t, f, hours)
        expect = sigma / math.sqrt(hours * 60 / cadence) * 1e6
        assert c == pytest.approx(expect, rel=0.12)


def test_cdpp_keeps_red_noise():
    t, f = _white(10.0, 2e-3)
    f = f + 2e-3 * np.sin(2 * np.pi * t / 0.2)  # 5-hour wiggle survives the 1-day median filter
    c1, _ = noise.sector_cdpp(t, f, 1.0)
    c2, _ = noise.sector_cdpp(t, f, 2.0)
    assert c2 / c1 > 2 ** -0.5 * 1.1  # scatter falls slower than white noise


def test_detectable_radius_formula():
    star = {"rad": 0.3, "rho": 10.0}
    d = noise.detectable_radius(star, 2000.0, 2000.0 * 2 ** -0.5, days=100.0)
    p5 = d["by_period"]["5"]
    dur = 13 * (5 / 365.25) ** (1 / 3) * 10 ** (-1 / 3)
    depth = 10 * 2000e-6 * dur ** -0.5 / math.sqrt(100 / 5)
    assert p5["duration_h"] == pytest.approx(dur, abs=0.01)
    assert p5["radius_rearth"] == pytest.approx(0.3 * math.sqrt(depth) * 109.1, abs=0.01)
    r = [d["by_period"][k]["radius_rearth"] for k in ("1", "5", "10")]
    assert r == sorted(r)  # longer periods: fewer transits, larger minimum radius


def test_tiers_and_reason():
    assert targets.tier(0.25, 5, 0.02) == 1
    assert targets.tier(0.25, 2, 0.02) == 2  # too few sectors for tier 1
    assert targets.tier(0.5, 3, 0.2) == 2
    assert targets.tier(0.5, 1, 0.0) == 3
    assert targets.tier(0.3, 6, 0.5) == 3  # crowded
    row = {"rad": 0.25, "teff": 3200, "tmag": 14.1, "sectors": [1, 2, 28], "contratio": 0.02,
           "pred_rmin_p5_rearth": 1.3}
    text = targets.reason(row)
    assert "late M dwarf" in text and "3 TGLC sectors (S1-S28)" in text and "low" in text
    assert "not a TOI, CTOI, confirmed host or known EB" in text


def test_footprint_matches_tess_point():
    # TOI-1680: tess-point puts it on silicon in 24 TGLC sectors; the fast footprint must agree to within one
    ra, dec = 292.313380728815, 65.9743672333425
    exact = {s for s, _, _ in coverage.pointings([ra], [dec])[0]}
    fast = set(coverage.sectors_of(coverage.sector_mask([ra], [dec])[0]))
    assert len(exact) == 24
    assert len(exact ^ fast) <= 1
    assert max(exact) <= 55


def _sector(sector, t0, n, cadence_min, depth_at=None):
    t = t0 + np.arange(n) * cadence_min / 1440
    f = np.ones(n)
    return tglc.Sector(sector, t, f, np.full(n, 1e-3), np.zeros(n), np.array([t0 + 1.0]), np.array([]),
                       {"sector": sector, "author": "TGLC", "exptime": cadence_min * 60, "filename": f"s{sector}.fits"})


def test_stitch_and_hunt_shape():
    lc = tglc.stitch([_sector(30, 2100.0, 3000, 10), _sector(3, 1400.0, 1000, 30)])
    assert lc.sectors == [3, 30]
    assert np.all(np.diff(lc.time) > 0)
    assert set(np.unique(lc.sector)) == {3, 30}
    assert len(lc.dumps) == 2 and lc.bin_minutes is None
    h = lc.to_hunt()
    from hunt.lightcurve import StarLC

    assert isinstance(h, StarLC)
    assert h.time is lc.time and h.flux is lc.flux and h.sector is lc.sector and h.products == lc.products
