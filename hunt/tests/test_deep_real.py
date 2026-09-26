"""Offline proof on recorded real TESS data, every sector stitched (tests/data/record.py, STITCHED).

TOI-813 b (Planet Hunters TESS, Eisner et al. 2020; P = 83.8911 d): recovered as a periodic candidate from the
42-sector stitched curve. TOI-2180 b (Dalba et al. 2022; one TESS transit in year 2, published P = 260.79 d):
found by the single-dip search on the year-2 data with a period range that contains the published period.
A momentum-dump dip in TOI-2180's own data is rejected with the reason. Both stars are searched as if they
were on no list (an empty catalogue), as HUNT's TOI-7303 test does; against the real lists they are known.
"""

from dataclasses import replace

import numpy as np
import pytest
from conftest import load_fixture

pytestmark = pytest.mark.deep  # minutes each: `pytest -m "not deep"` skips them

from hunt import analyse
from hunt.catalogs import Catalogue

TOI813, TOI2180 = 55525572, 298663873
TOI813_P = 83.8911  # Eisner et al. 2020
TOI2180_P = 260.79  # Dalba et al. 2022 (RVs + the one TESS transit)
TOI2180_T0 = 1830.77  # BTJD, the sector-19 transit


def _sectors(lc, lo, hi):
    m = (lc.sector >= lo) & (lc.sector <= hi)
    return replace(lc, time=lc.time[m], flux=lc.flux[m], flux_err=lc.flux_err[m], sector=lc.sector[m],
                   bkg=None if lc.bkg is None else lc.bkg[m],
                   products=[p for p in lc.products if lo <= p["sector"] <= hi])


@pytest.fixture(scope="module")
def toi813():
    star, lc = load_fixture(TOI813)
    return lc, analyse.analyse(star, lc, Catalogue([]), "A")


def test_toi813_b_is_recovered_from_the_stitched_curve(toi813):
    lc, res = toi813
    assert lc.stitch_info()["n_sectors"] == 42 and lc.stitch_info()["baseline_d"] > 2700
    cand = next(c for c in res.candidates if c["kind"] == "periodic")
    assert abs(cand["period_d"] - TOI813_P) / TOI813_P < 1e-3
    assert cand["n_transits"] >= 10 and len(cand["dips"]) >= 10
    assert "bls_long" in cand["found_by"]  # beyond the pipeline's 15-day limit
    assert all(c["passed"] is not False for c in cand["checks"])
    assert cand["sectors_used"] == lc.sectors and cand["baseline_d"] > 2700
    assert res.search["periodic"]["runtime"]["tls_runs"][0]["ran_on"].startswith("newest sectors")


def test_toi813_b_is_known_on_the_real_lists(toi813, catalogue):
    _, res = toi813
    p = next(c for c in res.candidates if c["kind"] == "periodic")["period_d"]
    assert any("TOI-813" in m["name"] for m in catalogue.match(TOI813, p)["same_star"])


@pytest.fixture(scope="module")
def toi2180_year2():
    star, lc = load_fixture(TOI2180)
    return analyse.analyse(star, _sectors(lc, 14, 26), Catalogue([]), "A")


def test_toi2180_b_single_transit_gives_a_period_range_with_the_published_period(toi2180_year2):
    res = toi2180_year2
    cand = next(c for c in res.candidates if c["kind"] == "single")
    assert abs(cand["t0_btjd"] - TOI2180_T0) < 0.05
    assert 22 < cand["duration_h"] < 26  # published 24 h
    lo, hi = cand["period_range_d"]
    assert lo < TOI2180_P < hi
    assert cand["period_d"] is None and cand["folded"] is None
    assert cand["score"] <= 0.24
    could_not = {c["name"] for c in cand["checks"] if c["passed"] is None}
    assert {"odd_even", "secondary_eclipse", "period_alias", "sector_depth"} <= could_not
    # The periodic search folds the same transit into a long "period" with empty epochs; three_dips rejects it,
    # so it is not masked before the dip search.
    assert not any(s["failed_stage"] is None for s in res.signals)


def test_momentum_dump_dip_is_rejected_with_the_reason():
    """Sector 75 of TOI-2180: a 0.9-h dip centred on a reaction-wheel momentum dump."""
    star, lc = load_fixture(TOI2180)
    res = analyse.analyse(star, _sectors(lc, 73, 77), Catalogue([]), "A", deep_search=False)
    ev = next(e for e in res.events if abs(e["mid_btjd"] - 3360.35) < 0.05)
    assert "momentum_dump" in ev["failed_checks"]
    assert "momentum dump" in ev["rejected_because"]["momentum_dump"]
    assert not any(abs(c["t0_btjd"] - 3360.35) < 0.05 for c in res.candidates)
    dump_times = lc.dumps[np.abs(lc.dumps - 3360.35) < 0.1]
    assert len(dump_times) >= 1


def test_toi2180_b_with_every_sector_is_periodic_from_three_transits():
    """TESS has since seen two more transits (sectors 48 and 57), so on the full stitched curve TOI-2180 b is a
    periodic signal with three dips, and the period is measured rather than estimated."""
    star, lc = load_fixture(TOI2180)
    res = analyse.analyse(star, lc, Catalogue([]), "A")
    cand = next(c for c in res.candidates if c["kind"] == "periodic")
    assert abs(cand["period_d"] - 260.167) < 0.05  # within the published 260.79 +- 0.59 d
    assert cand["n_transits"] == 3 and "bls_long" in cand["found_by"]
    assert {round(d["mid_btjd"]) for d in cand["dips"]} == {1831, 2611, 2871}
