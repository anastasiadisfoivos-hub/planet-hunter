"""Offline tests on recorded real TESS data (tests/data, made by tests/data/record.py)."""

import json

import numpy as np
import pytest
from conftest import EB_TIC, QUIET_TIC, TOI_TIC, load_fixture

from hunt import analyse, inject
from hunt.catalogs import Catalogue


@pytest.fixture(scope="module")
def toi_result(catalogue):
    star, lc = load_fixture(TOI_TIC)
    return analyse.analyse(star, lc, catalogue, "A")


def test_known_toi_is_found_but_filtered_as_already_known(toi_result):
    sig = toi_result.signals[0]
    assert abs(sig["period_d"] - 2.3368358) / 2.3368358 < 0.01
    assert sig["snr"] >= 10 and sig["sde"] >= 9 and sig["n_transits"] >= 3
    assert sig["failed_checks"] == []  # a clean signal: only the known-list stage stops it
    assert sig["failed_stage"] == "known"
    assert sig["known_names"] == ["TOI-7303.01"]
    assert toi_result.candidates == []


def test_same_toi_without_the_lists_would_be_a_candidate():
    star, lc = load_fixture(TOI_TIC)
    res = analyse.analyse(star, lc, Catalogue([]), "A")
    assert res.signals[0]["failed_stage"] is None
    assert len(res.candidates) == 1


def test_sibling_search_masks_the_known_transits(catalogue):
    star, lc = load_fixture(TOI_TIC)
    res = analyse.analyse(star, lc, catalogue, "B")
    assert res.masked_known and res.masked_known[0]["name"] == "TOI-7303.01"
    assert res.masked_known[0]["masked_points"] > 0
    assert not any(abs(s["period_d"] - 2.3368358) / 2.3368358 < 0.01 for s in res.signals)


def test_eclipsing_binary_is_rejected_by_the_checks(catalogue):
    star, lc = load_fixture(EB_TIC)
    res = analyse.analyse(star, lc, catalogue, "A")
    sig = res.signals[0]
    assert abs(sig["period_d"] - 4.0317118) / 4.0317118 < 0.01
    assert sig["failed_stage"] == "checks"
    assert "secondary_eclipse" in sig["failed_checks"]
    assert "TESS EB catalogue" in sig["known_names"][0]  # and it is on the EB list as well
    assert res.candidates == []


@pytest.fixture(scope="module")
def quiet():
    return load_fixture(QUIET_TIC)


def test_quiet_star_has_no_detection(quiet):
    star, lc = quiet
    assert inject.is_quiet(analyse.analyse(star, lc, None, "A", check_known=False))


def test_injected_planet_is_recovered_as_candidate(quiet, tmp_path):
    star, lc = quiet
    period, t0, r_earth = 3.37, float(lc.time.min()) + 1.1, 1.6
    depth = (r_earth / inject.REARTH_PER_RSUN / star.rad) ** 2
    dur = inject.max_duration_days(period, star.density_solar()[0], np.sqrt(depth)) * 0.9
    res = analyse.analyse(star, inject.inject(lc, period, t0, dur, depth), None, "A", check_known=False)
    hit = [s for s in res.signals if inject.matches(s, period, t0, dur)]
    assert hit and hit[0]["failed_stage"] is None
    cand = res.candidates[0]
    for key in ("tic", "period_d", "t0_btjd", "duration_h", "depth_ppm", "snr", "sde", "n_transits", "sectors",
                "radius_rjup", "checks", "score", "known", "curves", "created_at"):
        assert key in cand
    lo, hi = cand["radius_rjup"]
    assert lo < r_earth / 11.2 < hi * 1.5
    assert {c["name"] for c in cand["checks"]} >= {"snr", "odd_even", "secondary_eclipse", "size", "period_alias",
                                                   "momentum_dump", "sector_depth", "duration", "single_sector"}
    assert all({"name", "value", "passed", "reason"} <= set(c) for c in cand["checks"])
    assert {"folded", "folded_zoom", "unfolded"} <= set(cand["curves"])
    json.dumps(cand)  # serialisable
    analyse.plot_candidate(cand, tmp_path / "c.png")
    assert (tmp_path / "c.png").stat().st_size > 1000


def test_injection_run_on_one_star_counts_recoveries(quiet):
    star, lc = quiet
    out = inject.star_injections(star, lc, [(2, 3), (1, 1)], seed=3, check_quiet=False)  # 3-4 and 2-3 R_earth
    assert len(out["injections"]) == 2
    assert all(i["recovered"] for i in out["injections"])  # big planets on a small star: easy
    summary = inject.summarise([out])
    assert summary["n_injections"] == 2 and summary["overall_recovery_fraction"] == 1.0
