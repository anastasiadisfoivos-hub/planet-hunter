"""Offline tests on recorded real TGLC data (tests/data, made by tests/data/record.py), searched with hunt/'s own
search (hunt.signals.find_signals, imported read-only from the hunt branch).

Criteria fixed before the searches were run: period within 1% of the catalogue; depth consistent with the
catalogue radius ratio (BLS box depth within 15% of (Rp/R*)^2, which is what a box measures for a flat-bottomed
transit).
"""

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from conftest import DATA, load
from skyfaint import noise, tglc

TOI5688, TOI1680 = 193634953, 259168516


# ---- reader ---------------------------------------------------------------------------------------------------

def raw_fits() -> Path:
    return next(DATA.glob("hlsp_tglc_*s0025*.fits"))


def test_reader_quality_and_normalisation():
    path = raw_fits()
    sec = tglc.read_sector(path, TOI5688)
    with fits.open(path) as h:
        d = h[1].data
        tq, gq = np.asarray(d["TESS_flags"]), np.asarray(d["TGLC_flags"])
    assert sec.sector == 25 and sec.product["exptime"] == 1800
    assert sec.product["flux_column"] == "cal_aper_flux"
    assert np.median(sec.flux) == pytest.approx(1.0, abs=1e-9)
    assert np.all(np.diff(sec.time) > 0)
    # every flagged cadence is gone, and its time is listed as a dump or as flagged
    removed = int(((tq & tglc.DEFAULT_BITMASK) > 0).sum() + ((gq != 0) & ((tq & tglc.DEFAULT_BITMASK) == 0)).sum())
    assert len(sec.dumps) + len(sec.flagged) >= removed
    assert len(sec.time) + len(sec.dumps) + len(sec.flagged) <= len(tq)
    assert len(sec.dumps) == int(((tq & 32) > 0).sum())


def test_reader_rejects_another_star():
    with pytest.raises(ValueError, match="TICID"):
        tglc.read_sector(raw_fits(), 123)


def test_scattered_light_cut_only_removes_high_background():
    path = raw_fits()
    cut, keep_all = tglc.read_sector(path, TOI5688, max_bkg_z=3.0), tglc.read_sector(path, TOI5688)
    assert len(keep_all.time) - len(cut.time) == cut.product["n_scattered_light"]
    gone = ~np.isin(keep_all.time, cut.time)
    assert np.all(keep_all.bkg[gone] > np.median(keep_all.bkg))


def test_recorded_curves_have_hunt_shape():
    lc, _ = load(TOI5688)
    h = lc.to_hunt()
    assert h.time.dtype == np.float64 and np.all(np.diff(h.time) >= 0)
    assert len(h.time) == len(h.flux) == len(h.flux_err) == len(h.sector)
    for s in h.sectors:
        assert np.median(h.flux[h.sector == s]) == pytest.approx(1.0, abs=2e-3)
    assert {p["author"] for p in h.products} == {"TGLC"}


# ---- recoveries with hunt's search -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def toi5688_search():
    from hunt.signals import find_signals

    lc, _ = load(TOI5688)
    return find_signals(lc.to_hunt())


def test_toi5688_recovered(toi5688_search, facts):
    f = facts["toi5688"]
    best = toi5688_search.signals[0]
    assert abs(best.period / f["period_d"] - 1) < 0.01
    assert best.snr >= 10
    assert abs(best.depth * 1e6 / f["depth_ppm_from_ratror"] - 1) < 0.15


def test_toi1680_in_data_but_missed_by_hunt(facts):
    """TOI-1680 b is NOT recovered by hunt's search. This test pins down why (see README, Proof):

    1. the transit is in the TGLC data: at the catalogue ephemeris, the in-transit mean is ~4000 ppm low at
       SNR > 15;
    2. a phase-coherent BLS on the same stitched curve finds the period (SDE > 9);
    3. hunt's coarse stage searches each of the 24 sectors separately and adds their powers without phase
       coherence; per sector the transit has SNR ~ 4, below each sector's own noise peaks, so the summed power at
       the true period is not significant and the fine stage never looks there.
    If hunt's search changes so that it finds TOI-1680 b, this test fails: update it and the README."""
    from astropy.timeseries import BoxLeastSquares
    from hunter import search as hs
    from hunter.clean import flatten_for_search, robust_sigma
    from hunter.search import in_transit
    from hunt.signals import find_signals

    f = facts["toi1680"]
    lc, _ = load(TOI1680)
    P, T0, D = f["period_d"], f["t0_btjd"], f["duration_h"] / 24
    flat, keep = flatten_for_search(lc.time, lc.flux, 0.9, transit_mask=in_transit(lc.time, P, T0, D, 2))
    t, y, g = lc.time[keep], flat[keep], lc.sector[keep]
    it = in_transit(t, P, T0, 0.8 * D)
    depth = 1 - y[it].mean()
    snr = depth / (robust_sigma(y[~it]) / np.sqrt(it.sum()))
    assert depth * 1e6 == pytest.approx(f["depth_ppm"], rel=0.3)
    assert snr > 15

    grid = np.exp(np.arange(np.log(4.0), np.log(6.0), 0.03 / (3 * np.ptp(t))))
    flat2, keep2 = flatten_for_search(lc.time, lc.flux, 0.9)
    r = BoxLeastSquares(lc.time[keep2], flat2[keep2]).power(grid, [0.04, 0.05, 0.065], objective="snr")
    sde = (r.power - np.mean(r.power)) / np.std(r.power)
    k = int(np.argmax(r.power))
    assert abs(grid[k] / P - 1) < 0.001 and sde[k] > 9

    per, pw = hs._coarse(lc.time[keep2], flat2[keep2], lc.sector[keep2])
    near = np.abs(per / P - 1) < 0.002
    z = (pw - np.median(pw)) / np.std(pw)
    assert z[near].max() < 3  # nothing there for the fine stage to refine

    sigs = find_signals(lc.to_hunt()).signals
    assert not any(abs(s.period / P - 1) < 0.01 for s in sigs)


# ---- a quiet faint star ------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def quiet(facts):
    return load(facts["quiet"]["tic"])


def test_quiet_star_flat(quiet):
    """No signal passes hunt's first three cuts (SNR >= 10, SDE >= 9, >= 3 transits)."""
    from hunt.analyse import MIN_SDE, MIN_SNR, MIN_TRANSITS
    from hunt.signals import find_signals

    lc, _ = quiet
    sigs = find_signals(lc.to_hunt()).signals
    passing = [s for s in sigs if s.snr >= MIN_SNR and s.sde >= MIN_SDE and s.n_transits >= MIN_TRANSITS]
    assert passing == []


def test_quiet_star_noise_level(quiet):
    """Measured CDPP matches the Tmag noise model (fitted on 60 other faint M dwarfs) within 2x its scatter."""
    lc, star = quiet
    n = noise.star_noise(lc, star)
    pred = noise.predicted_cdpp_1h(star["tmag"])
    assert abs(np.log10(n["cdpp_1h_ppm"] / pred)) < 2 * noise.NOISE_MODEL["rms_dex"]
    assert 0.5 < n["cdpp_2h_ppm"] / n["cdpp_1h_ppm"] < 1.0
    det = n["detectable"]["by_period"]
    assert det["1"]["radius_rearth"] < det["5"]["radius_rearth"] < det["10"]["radius_rearth"]
