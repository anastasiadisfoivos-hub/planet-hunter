"""Offline proof on recorded real data (tests/data/cache, made by tests/data/record.py).

Every candidate is vetted again with SKYVET_OFFLINE=1: any network call would raise instead. Each tool actually
re-runs on the recorded inputs (LEO-vetter's flux metrics and its PRF fit to the recorded difference images,
TRICERATOPS' calc_probs with the recorded field and seed, the Gaia/VSX logic) and must reproduce the recorded
numbers.

- WASP-18 b (confirmed): not failed; TRICERATOPS FPP low; Gaia's SB1 orbit at its period is planetary.
- TOI-4257.01 (TFOPWG FP, NEB on TIC 75208617): failed, off-target, and the nearby-EB probability is high.
- TIC 408512382 (HUNT's EB test star): failed on LEO's secondary and size tests and Gaia's stellar SB1 orbit.
- WASP-126 b (confirmed, extra): TRICERATOPS validates it, but LEO's odd-even test fires (a 2.7% odd/even depth
  difference at 3.2-3.6 sigma; LEO has no fractional floor), so it fails. Recorded as it is.

TRICERATOPS dominates the run time; SKYVET_TEST_TRICERATOPS=0 skips its replay (the rest still runs).
"""

import json
import os
from pathlib import Path

import pytest

from skyvet.cli import _quiet
from skyvet.core import vet_candidate

DATA = Path(__file__).parent / "data"
EXPECTED = json.loads((DATA / "expected.json").read_text())
RUN_TRI = os.environ.get("SKYVET_TEST_TRICERATOPS", "1") != "0"


@pytest.fixture(scope="module", autouse=True)
def offline_cache():
    old = {k: os.environ.get(k) for k in ("SKYVET_CACHE_DIR", "SKYVET_OFFLINE", "SKYVET_WORK_DIR")}
    os.environ.update(SKYVET_CACHE_DIR=str(DATA / "cache"), SKYVET_OFFLINE="1",
                      SKYVET_WORK_DIR=str(DATA / "no-work-dir"))
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


_results: dict[str, dict] = {}


def vetted(name: str) -> dict:
    if name not in _results:
        cand = json.loads((DATA / "candidates" / f"{name}.json").read_text())
        exp = EXPECTED[name]
        with _quiet():
            _results[name] = vet_candidate(cand, triceratops=RUN_TRI, tri_n=exp["triceratops"]["N"],
                                           tri_budget_s=4 * 3600)["vetting"]
    return _results[name]


ALLOWED_PINGS = {"gea.esac.esa.int"}  # astroquery.gaia's import-time status message (no data)


def _all_ran(v: dict) -> None:
    from skyvet import cache

    assert v["offline"] is True
    assert {a[0] for a in cache.NETWORK_ATTEMPTS} <= ALLOWED_PINGS, cache.NETWORK_ATTEMPTS
    assert v["leo"]["ran"] and v["leo"]["pixel"]["ran"], v["leo"].get("reason") or v["leo"]["pixel"]
    assert v["gaia"]["ran"], v["gaia"].get("reason")
    assert v["variability"]["ran"], v["variability"].get("reason")
    if RUN_TRI:
        assert v["triceratops"]["ran"], v["triceratops"].get("reason")


def _reproduces(name: str, v: dict) -> None:
    exp = EXPECTED[name]
    assert v["leo"]["flags"] == exp["leo"]["flags"]
    assert v["leo"]["metrics"] == pytest.approx(exp["leo"]["metrics"], rel=1e-6, nan_ok=True)
    assert v["leo"]["pixel"]["offset_arcsec"] == pytest.approx(exp["leo"]["pixel"]["offset_arcsec"], abs=0.01)
    assert v["gaia"] == exp["gaia"]
    if RUN_TRI:
        assert v["triceratops"]["fpp"] == pytest.approx(exp["triceratops"]["fpp"], rel=1e-6, abs=1e-9)
        assert v["triceratops"]["nfpp"] == pytest.approx(exp["triceratops"]["nfpp"], rel=1e-6, abs=1e-9)
        assert v["summary"] == exp["summary"]
    else:
        assert v["summary"]["verdict"] in (exp["summary"]["verdict"], "flag")


def test_wasp18b_confirmed_planet():
    v = vetted("wasp18b")
    _all_ran(v)
    _reproduces("wasp18b", v)
    assert v["summary"]["verdict"] != "fail"
    orbit = v["gaia"]["nss_orbit"]
    assert orbit["period_match"] == "same" and orbit["companion"] == "planetary"
    assert 9 < orbit["m2_min_mjup"] < 12  # WASP-18 b: 10.4 M_Jup (Hellier et al. 2009)
    assert not any(f.startswith("FP") for f in v["leo"]["flags"])
    assert v["leo"]["pixel"]["offset_arcsec"] < 15
    if RUN_TRI:
        assert v["triceratops"]["background_population"]
        assert v["triceratops"]["fpp"] < 0.015 and v["triceratops"]["nfpp"] < 0.001  # validated


def test_toi4257_01_nearby_eclipsing_binary():
    v = vetted("toi4257_01")
    _all_ran(v)
    _reproduces("toi4257_01", v)
    assert v["summary"]["verdict"] == "fail"
    assert "FP: off-target" in v["leo"]["flags"]
    assert v["leo"]["pixel"]["offset_arcsec"] > 15
    src = v["leo"]["pixel"]["source"]
    assert src["tic"] == "75208617"  # the star ExoFOP names: "offset on TIC 75208617 in SPOC s62"
    assert src["gaia_dr3"] == "5423774792624492928" and src["sep_from_fit_arcsec"] < 5
    off = next(r for r in v["summary"]["reasons"] if "off-target" in r)
    assert "TIC 75208617" in off
    if RUN_TRI:
        assert v["triceratops"]["nfpp"] > 0.1
        assert any("nearby false positive" in r for r in v["summary"]["reasons"])


def test_hunt_eclipsing_binary():
    v = vetted("eb_408512382")
    _all_ran(v)
    _reproduces("eb_408512382", v)
    assert v["summary"]["verdict"] == "fail"
    assert {"FP: significant secondary", "FP: radius too large"} <= set(v["leo"]["flags"])
    orbit = v["gaia"]["nss_orbit"]
    assert orbit["companion"] == "stellar" and orbit["m2_min_msun"] > 0.3
    assert any("stellar eclipsing binary" in r for r in v["summary"]["reasons"])


def test_wasp126b_confirmed_planet_trips_leo_odd_even_only():
    v = vetted("wasp126b")
    _all_ran(v)
    _reproduces("wasp126b", v)
    assert v["leo"]["flags"] == ["FP: odd-even transit differences"]
    m = v["leo"]["metrics"]
    assert 3 < m["sig_dep"] < 4 and abs(m["odd_dep"] / m["even_dep"] - 1) < 0.05  # > 3 sigma but < 5 %
    assert v["summary"]["reasons"] == ["LEO-vetter FP: odd-even transit differences"]
    if RUN_TRI:
        assert v["triceratops"]["classification"].startswith("validated")
