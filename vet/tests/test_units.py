"""Unit tests: cache, period matching, the SB1 minimum mass, and the verdict rules on synthetic blocks."""

import pytest

from skyvet import cache
from skyvet.gaia import min_companion_mass
from skyvet.summary import summarise
from skyvet.variability import period_match


def test_offline_cache_miss_raises_instead_of_downloading(tmp_path, monkeypatch):
    monkeypatch.setenv("SKYVET_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("SKYVET_OFFLINE", "1")
    with pytest.raises(cache.OfflineMiss):
        cache.cached("x", "k", lambda: pytest.fail("fetch must not run offline"))


def test_cache_stores_and_replays(tmp_path, monkeypatch):
    monkeypatch.setenv("SKYVET_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("SKYVET_OFFLINE", raising=False)  # the fetch functions below are local
    assert cache.cached("x", "k", lambda: {"a": 1}) == {"a": 1}
    assert cache.cached("x", "k", lambda: pytest.fail("cached")) == {"a": 1}
    assert cache.cached("y", "k", lambda: [1, 2], fmt="pickle") == [1, 2]
    assert cache.cached("y", "k", lambda: pytest.fail("cached"), fmt="pickle") == [1, 2]


def test_cache_does_not_retry_code_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("SKYVET_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("SKYVET_OFFLINE", raising=False)
    calls = []

    def boom():
        calls.append(1)
        raise ValueError("bug")

    with pytest.raises(ValueError):
        cache.cached("x", "boom", boom)
    assert calls == [1]


@pytest.mark.parametrize(("p", "q", "want"), [(2.0, 2.01, "same"), (2.0, 4.0, "x2"), (2.0, 1.0, "x1/2"),
                                               (2.0, 2.1, None), (2.0, None, None)])
def test_period_match(p, q, want):
    assert period_match(p, q) == want


def test_network_is_blocked_in_tests():
    import socket

    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("mast.stsci.edu", 443), timeout=5)
    assert cache.NETWORK_ATTEMPTS[-1] == ("mast.stsci.edu", 443)
    cache.NETWORK_ATTEMPTS.pop()


def test_min_companion_mass_jupiter():
    # The Sun's reflex from Jupiter: P = 4332.6 d, K = 12.5 m/s -> ~1 M_Jup.
    m = min_companion_mass(4332.6, 0.0125, 0.048, 1.0) * 1047.57
    assert 0.95 < m < 1.05


def _ok_blocks():
    return {
        "leo": {"ran": True, "flags": [], "not_evaluated": [], "pixel": {"ran": True, "offset_arcsec": 2.0}},
        "triceratops": {"ran": True, "fpp": 0.001, "nfpp": 1e-5, "top_scenarios": []},
        "gaia": {"ran": True, "binary_hint": False, "binary_reasons": [], "neighbours": [], "nss_orbit": None},
        "variability": {"ran": True, "vsx_ran": True, "gaia_ran": True, "vsx_all": [],
                        "gaia_variable": {"class": None, "eclipsing_binaries_within_63arcsec": []}},
    }


def test_everything_clean_passes():
    s = summarise(_ok_blocks(), None, None)
    assert s["verdict"] == "pass" and s["reasons"] == []


@pytest.mark.parametrize("tool", ["leo", "triceratops", "gaia"])
def test_a_tool_that_did_not_run_never_passes(tool):
    v = _ok_blocks()
    v[tool] = {"ran": False, "reason": "network down"}
    s = summarise(v, None, None)
    assert s["verdict"] == "flag"
    assert any("did not run: network down" in r for r in s["reasons"])


def test_leo_test_that_could_not_be_evaluated_is_a_flag():
    v = _ok_blocks()
    v["leo"]["not_evaluated"] = ["FP: offset (offset_qual is NaN)"]
    assert summarise(v, None, None)["verdict"] == "flag"


def test_leo_fp_fails_and_fa_flags():
    v = _ok_blocks()
    v["leo"]["flags"] = ["FA: sinusoidal variations"]
    assert summarise(v, None, None)["verdict"] == "flag"
    v["leo"]["flags"] = ["FP: significant secondary"]
    assert summarise(v, None, None)["verdict"] == "fail"


@pytest.mark.parametrize(("fpp", "nfpp", "verdict"), [(0.01, 0.0005, "pass"), (0.2, 0.0005, "flag"),
                                                       (0.2, 0.05, "flag"), (0.9, 0.05, "fail"), (0.3, 0.2, "fail")])
def test_triceratops_thresholds(fpp, nfpp, verdict):
    v = _ok_blocks()
    v["triceratops"].update(fpp=fpp, nfpp=nfpp)
    assert summarise(v, None, None)["verdict"] == verdict


def test_stellar_orbit_at_candidate_period_fails_planetary_one_does_not():
    v = _ok_blocks()
    v["gaia"]["nss_orbit"] = {"solution_type": "SB1", "period_d": 4.03, "period_match": "same",
                              "m2_min_msun": 0.47, "m2_min_mjup": 489.0, "companion": "stellar"}
    assert summarise(v, None, None)["verdict"] == "fail"
    v["gaia"]["nss_orbit"].update(m2_min_msun=0.01, m2_min_mjup=10.5, companion="planetary")
    assert summarise(v, None, None)["verdict"] == "pass"


def test_catalogued_eclipsing_binary_at_the_period_fails():
    v = _ok_blocks()
    v["variability"]["vsx_all"] = [{"name": "X", "type": "EA", "period_d": 8.0, "sep_arcsec": 30.0,
                                    "period_match": "x2", "eclipsing": True}]
    s = summarise(v, None, None)
    assert s["verdict"] == "fail" and "VSX eclipsing binary X" in s["reasons"][0]
