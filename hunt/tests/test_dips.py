"""Unit tests on synthetic data for the deep search: single / duo dips and their checks, the period estimate,
the leave-one-out dip check, scores by kind, sector counts, target groups and the merge-time neighbour test."""

import json
import math
from dataclasses import replace

import numpy as np
import pytest
from conftest import SUN_LIKE, box, make_lc

from hunt import analyse, checks, coverage, singles, sweep, targets
from hunt.checks import max_duration_days
from hunt.stars import Star


def _lc(n_sectors=4, noise=4e-4, seed=1):
    lc = make_lc(n_sectors=n_sectors, noise=noise, seed=seed)
    rng = np.random.default_rng(seed + 100)
    return replace(lc, bkg=rng.normal(0, 1, len(lc.time)))


def _dip(t, tc, dur, depth):
    return np.where(np.abs(t - tc) < dur / 2, -depth, 0.0)


def _search(lc, star=SUN_LIKE):
    return singles.search(star, lc, np.zeros(len(lc.time), bool))


def test_single_dip_is_a_candidate_with_a_period_range_containing_the_truth():
    lc = _lc()
    p_true = 200.0
    dur = max_duration_days(p_true, 1.0, math.sqrt(3000e-6))
    tc = 3093.0  # sector 2 (3087-3114, mid-sector gap 3100-3101): 6 d from any edge
    lc.flux = lc.flux + _dip(lc.time, tc, dur, 3000e-6)
    events, results, _ = _search(lc)
    single = [r for r in results if r.kind == "single" and abs(r.events[0].tc - tc) < 0.1]
    assert single, [e.to_dict() for e in events]
    r = single[0]
    assert r.failed == [], [(c.name, c.reason) for c in r.checks]
    assert r.period.lo < p_true < r.period.hi
    assert abs(r.duration - dur) / dur < 0.15  # trapezoid fit recovers the duration
    names = {c.name: c for c in r.checks}
    for n in ("odd_even", "secondary_eclipse", "period_alias", "sector_depth"):  # cannot run on one dip
        assert names[n].passed is None and names[n].reason.startswith("Could not run")


def test_dip_on_a_momentum_dump_is_rejected():
    lc = _lc()
    t_dump = 3105.0
    lc.flux = lc.flux + _dip(lc.time, t_dump, 1.0 / 24, 4000e-6)  # an hour-long dip centred on the dump
    lc = replace(lc, dumps=np.array([t_dump]))
    events, _, _ = _search(lc)
    e = next(e for e in events if abs(e.tc - t_dump) < 0.05)
    c = next(c for c in e.checks if c.name == "momentum_dump")
    assert c.passed is False and "dump" in c.reason


def test_ramp_is_rejected_by_the_shape_check():
    lc = _lc()
    t, tc, dur = lc.time, 3110.0, 6 / 24
    ramp = np.where(np.abs(t - tc) < dur / 2, -4000e-6 * (t - (tc - dur / 2)) / dur, 0.0)  # sawtooth: 0 -> -4000 ppm
    lc.flux = lc.flux + ramp
    events, _, _ = _search(lc)
    e = min(events, key=lambda e: abs(e.tc - tc))
    assert abs(e.tc - tc) < dur
    assert "shape" in e.failed(), [(c.name, c.reason) for c in e.checks]


def test_dip_with_a_background_spike_is_rejected():
    lc = _lc()
    tc, dur = 3107.0, 4 / 24
    lc.flux = lc.flux + _dip(lc.time, tc, dur, 3000e-6)
    lc.bkg = lc.bkg + np.where(np.abs(lc.time - tc) < dur / 2, 25.0, 0.0)
    events, _, _ = _search(lc)
    e = next(e for e in events if abs(e.tc - tc) < dur)
    c = next(c for c in e.checks if c.name == "background")
    assert c.passed is False and "background" in c.reason


def test_dip_next_to_a_sector_edge_is_rejected():
    lc = _lc()
    start = lc.time[lc.sector == 2].min()
    tc, dur = start + 0.25, 3 / 24
    lc.flux = lc.flux + _dip(lc.time, tc, dur, 5000e-6)
    events, _, _ = _search(lc)
    e = next(e for e in events if abs(e.tc - tc) < dur)
    assert "edge" in e.failed()


def test_duo_keeps_the_true_period_and_drops_aliases_the_data_rule_out():
    lc = _lc(n_sectors=4)
    # Sectors: 3000-3027, 3087-3114, 3174-3201, 3261-3288. A 58-d planet with a transit at 3005 transits again at
    # 3063 and 3121 (no data), 3179 (sector 3), 3237 and 3295 (no data): two dips, 174 d apart. Of the aliases
    # 174/n, n = 2 (87 d) predicts a transit at 3092 in sector 2, which the data rule out.
    t1 = 3005.0
    p_true = 58.0
    t2 = t1 + 3 * p_true
    dur = max_duration_days(p_true, 1.0, math.sqrt(2500e-6))
    lc.flux = lc.flux + _dip(lc.time, t1, dur, 2500e-6) + _dip(lc.time, t2, dur, 2500e-6)
    events, results, _ = _search(lc)
    duo = next(r for r in results if r.kind == "duo")
    periods = [a["period_d"] for a in duo.aliases]
    assert any(abs(p - p_true) / p_true < 0.01 for p in periods), periods
    rows = singles.alias_table(duo.events[0], duo.events[1], singles.tier_for(
        singles.find_events(lc.time, lc.flux, lc.sector, np.zeros(len(lc.time), bool))[1], dur),
        singles.Coverage(lc.time, singles.cadence_of(lc.time, lc.sector)), (lc.time.min(), lc.time.max()))
    dropped = [r for r in rows if r["dropped"]]
    assert dropped, "some gap/n periods put a transit on data that shows none"
    assert all(r["missed_dips_btjd"] for r in dropped)
    assert duo.failed == [], [(c.name, c.reason) for c in duo.checks]


def test_period_posterior_for_an_earth_transit_of_the_sun():
    est, _ = singles.period_posterior(13.0 / 24, 84e-6, SUN_LIKE)
    assert est.lo < 365.25 < est.hi


def test_long_dip_on_an_m_dwarf_is_too_long_for_the_star():
    m = Star(tic=3, ra=0, dec=0, tmag=11, teff=3200, rad=0.2, rad_err=0.01, mass=0.18, rho=22.5, lumclass="DWARF")
    lc = _lc()
    lc.flux = lc.flux + _dip(lc.time, 3093.0, 20 / 24, 5000e-6)
    _, results, _ = _search(lc, m)
    r = next(r for r in results if abs(r.events[0].tc - 3093.0) < 0.3)
    assert "duration" in r.failed


def test_scores_by_kind_are_capped():
    lc = _lc()
    lc.flux = lc.flux + _dip(lc.time, 3093.0, 8 / 24, 20000e-6)
    _, results, _ = _search(lc)
    r = next(r for r in results if r.kind == "single")
    sc = analyse.dip_score(r, 6.0)
    assert sc["score"] <= 0.3 * (0.40 + 0.25 + 0.15) + 1e-9  # single: no orbit term, K = 0.3
    assert math.isclose(sum(sc["score_parts"].values()), sc["score"], abs_tol=1e-3)
    assert sc["score_parts"]["transits"] == 0
    duo = replace(r, kind="duo", aliases=[{"period_d": 100.0}])
    assert analyse.dip_score(duo, 6.0)["score"] <= 0.5 + 1e-9


def test_three_dips_check_rejects_one_dip_folded_with_empty_epochs():
    ep = checks.Epochs(np.arange(4), np.arange(4) * 50.0, np.ones(4, int), np.array([3000e-6, 50e-6, -40e-6, 20e-6]),
                       np.full(4, 100e-6))
    c = checks.three_dips(ep)
    assert c.passed is False and "one dip carries it" in c.reason
    ep2 = replace(ep, depth=np.array([1000e-6, 900e-6, 1100e-6, 950e-6]))
    assert checks.three_dips(ep2).passed is True


def test_dip_candidate_json_has_the_new_and_the_old_fields():
    lc = _lc()
    lc.flux = lc.flux + _dip(lc.time, 3093.0, 6 / 24, 3000e-6)
    res = analyse.analyse(SUN_LIKE, lc, None, "A", check_known=False, deep_search=False)
    cand = next(c for c in res.candidates if c["kind"] == "single")
    for key in ("tic", "period_d", "t0_btjd", "duration_h", "depth_ppm", "snr", "sde", "n_transits", "sectors",
                "radius_rjup", "radius_low", "radius_high", "checks", "score", "score_parts", "known_lists",
                "folded", "unfolded", "created_at", "kind", "period_range_d", "period_aliases_d", "dips",
                "sectors_used", "baseline_d"):
        assert key in cand
    assert cand["period_d"] is None and cand["folded"] is None and len(cand["period_range_d"]) == 2
    assert cand["dips"][0]["mid_btjd"] == pytest.approx(3093.0, abs=0.05)
    json.dumps(cand)
    assert res.dips and res.events


def test_sector_counts_match_tess_point():
    from tess_stars2px import tess_stars2px_function_entry as exact

    ra, dec = np.array([72.694, 277.944, 150.0]), np.array([-60.905, 56.651, 10.0])
    mine = coverage.observed_sectors(ra, dec, 100)
    out = exact(np.arange(3), ra, dec)
    for i in range(3):
        ref = {int(s) for t, s in zip(out[0], out[3]) if t == i and s <= 100}
        assert abs(len(mine[i]) - len(ref)) <= 3 and len(set(mine[i]) ^ ref) <= 4


def test_many_sector_bright_quiet_stars_rank_first():
    m_few = Star(tic=1, ra=0, dec=0, tmag=12.5, teff=3300, logg=5.0, rad=0.3, lumclass="DWARF")
    g_many = Star(tic=2, ra=0, dec=0, tmag=10.0, teff=5800, logg=4.4, rad=1.0, lumclass="DWARF", contratio=0.01)
    faint_many = Star(tic=3, ra=0, dec=0, tmag=12.0, teff=5800, logg=4.4, rad=1.0, lumclass="DWARF")
    n = {1: 2, 2: 12, 3: 12}
    order = sorted([m_few, faint_many, g_many], key=lambda s: targets.rank_key(s, n[s.tic]))
    assert [s.tic for s in order] == [2, 3, 1]
    assert targets.group(g_many, 12) == 0 and targets.group(faint_many, 12) == 1 and targets.group(m_few, 2) == 2


def test_merge_drops_a_dip_seen_in_two_nearby_stars(tmp_path):
    def star(tic, ra):
        return {"tic": tic, "ra": ra, "dec": 10.0}
    ev = {"mid_btjd": 3100.0, "duration_h": 4.0, "snr": 9.0, "sector": 2}
    summaries = [
        {"tic": 1, "star": star(1, 50.0), "sectors": [2], "signals": [], "events": [ev],
         "dips": [{"n": 1, "kind": "single", "failed_stage": None, "failed_checks": [], "snr": 12}]},
        {"tic": 2, "star": star(2, 50.3), "sectors": [2], "signals": [], "events": [{**ev, "mid_btjd": 3100.03}],
         "dips": []},
        {"tic": 3, "star": star(3, 50.6), "sectors": [2], "signals": [], "events": [{**ev, "mid_btjd": 3099.98}],
         "dips": []},
    ]
    d = tmp_path / "a"
    (d / "results").mkdir(parents=True)
    (d / "candidates").mkdir()
    for s in summaries:
        (d / "results" / f"{s['tic']}.json").write_text(json.dumps(s))
    cand = {"id": "hunt:1:s1", "tic": 1, "kind": "single", "score": 0.1, "score_parts": {}, "period_d": None,
            "depth_ppm": 900, "snr": 12, "sde": None, "n_transits": 1, "radius_rjup": [0.1, 0.2],
            "radius_rearth_best": 1.7, "single_sector_only": True, "search_list": "new-star search",
            "checks": [], "dips": [{"mid_btjd": 3100.0, "duration_h": 4.0, "sector": 2}]}
    (d / "candidates" / "1_s1.json").write_text(json.dumps(cand))
    out = sweep.merge([d], tmp_path / "m")
    assert out["candidates"] == []
    assert "1:s1" in out["rejected_at_merge"]
    assert out["funnel"]["dips"]["single"]["after_neighbour_dips"] == 0
    assert not (tmp_path / "m" / "candidates" / "1_s1.json").exists()
