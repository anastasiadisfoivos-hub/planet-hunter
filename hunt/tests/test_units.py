"""Unit tests on synthetic data: each added check, the score, catalogue matching, shards, funnel and merge."""

import json
import math
from dataclasses import replace

import numpy as np
from conftest import SUN_LIKE, box, make_lc

from hunt import analyse, checks, inject, sweep, targets
from hunt.catalogs import Catalogue, KnownSignal
from hunt.signals import find_signals, known_transit_mask
from hunt.stars import Star


def _signal_and_checks(lc, star=SUN_LIKE):
    out = find_signals(lc)
    sig = out.signals[0]
    cs, extra = checks.run_all(lc.time[out.use], out.flat[out.use], lc.sector[out.use], sig, star, lc.dumps,
                               lc.flagged)
    return sig, {c.name: c for c in cs}, extra


def test_clean_planet_passes_every_check():
    lc = make_lc()
    lc.flux = lc.flux + box(lc.time, 3.2, 3001.3, 0.12, 2500e-6)
    sig, cs, _ = _signal_and_checks(lc)
    assert abs(sig.period - 3.2) < 0.01
    assert checks.failures(list(cs.values())) == []
    assert cs["single_sector"].passed is None and cs["single_sector"].value == 2


def test_every_second_dip_missing_fails_the_alias_check():
    lc = make_lc()
    # True period 6.4 d, but a weaker dip at the half-way point makes BLS prefer 3.2 d with unequal groups.
    lc.flux = lc.flux + box(lc.time, 6.4, 3001.3, 0.12, 3000e-6) + box(lc.time, 6.4, 3004.5, 0.12, 900e-6)
    sig, cs, _ = _signal_and_checks(lc)
    if abs(sig.period - 3.2) < 0.02:
        assert cs["period_alias"].passed is False or cs["odd_even"].passed is False


def test_alias_check_catches_half_period():
    t = np.arange(0, 54, 10 / 1440)
    rng = np.random.default_rng(1)
    f = 1 + rng.normal(0, 3e-4, len(t)) + box(t, 2.0, 0.5, 0.1, 2000e-6)
    from hunter.search import Signal
    sig = Signal(4.0, 0.5, 0.1, 2000e-6, 1e-5, 50, 20, 13, 2000e-6, 1e-5, 2000e-6, 1e-5)
    ep = checks.epoch_depths(t, f, np.ones(len(t), int), sig)
    c = checks.period_alias(t, f, sig, ep)
    assert c.passed is False and "P/2" in c.reason


def test_transits_on_momentum_dumps_fail():
    lc = make_lc()
    lc.flux = lc.flux + box(lc.time, 3.2, 3001.3, 0.12, 2500e-6)
    centres = 3001.3 + 3.2 * np.arange(-5, 60)
    lc = replace(lc, dumps=np.sort(centres + 0.01))
    _, cs, _ = _signal_and_checks(lc)
    assert cs["momentum_dump"].passed is False
    assert cs["momentum_dump"].value > 0.9


def test_depth_that_changes_between_sectors_fails():
    lc = make_lc(noise=2e-4)
    depth = np.where(lc.sector == 1, 3000e-6, 800e-6)
    lc.flux = lc.flux + box(lc.time, 3.2, 3001.3, 0.12, 1.0) * depth
    _, cs, extra = _signal_and_checks(lc)
    assert cs["sector_depth"].passed is False
    assert set(extra["per_sector"]) == {1, 2}


def test_single_sector_signal_is_flagged_and_sector_test_cannot_run():
    lc = make_lc(n_sectors=1)
    lc.flux = lc.flux + box(lc.time, 3.2, 3001.3, 0.12, 2500e-6)
    _, cs, extra = _signal_and_checks(lc)
    assert cs["sector_depth"].passed is None
    assert "one sector" in cs["single_sector"].reason
    assert extra["sectors_with_transits"] == [1]


def test_too_long_dip_for_a_dense_star_fails_duration():
    m_dwarf = Star(tic=2, ra=0, dec=0, tmag=11, teff=3200, rad=0.2, rad_err=0.01, mass=0.18, rho=22.5,
                   lumclass="DWARF")
    lc = make_lc()
    lc.flux = lc.flux + box(lc.time, 1.3, 3000.4, 0.25, 3000e-6)  # 6 h on a 0.2 R_sun star at 1.3 d: ~5x too long
    _, cs, _ = _signal_and_checks(lc, m_dwarf)
    assert cs["duration"].passed is False and cs["duration"].value > 2


def test_max_duration_for_the_sun_and_earth():
    assert abs(checks.max_duration_days(365.25, 1.0) * 24 - 13.0) < 0.3


def test_density_fallbacks():
    assert Star(tic=1, ra=0, dec=0, rho=2.0).density_solar()[0] == 2.0
    assert math.isclose(Star(tic=1, ra=0, dec=0, rad=0.5, mass=0.5).density_solar()[0], 4.0)
    assert math.isclose(Star(tic=1, ra=0, dec=0, rad=0.5, lumclass="DWARF").density_solar()[0], 4.0)
    assert Star(tic=1, ra=0, dec=0).density_solar()[0] is None


def test_score_formula():
    from hunter.search import Signal
    sig = Signal(3.0, 0.0, 0.1, 1e-3, 1e-5, 30.0, 12.0, 9, 1e-3, 1e-5, 1e-3, 1e-5)
    cs = [checks.Check("odd_even", True, 0.0, "", 1.0), checks.Check("duration", True, 1.0, "", 0.5)]
    s = analyse.score(sig, cs, 10.5, single_sector=False)
    e1 = 1 - math.exp(-1)
    expected = {"snr": 0.4 * e1, "transits": 0.2 * e1, "checks": 0.25 * 0.75, "brightness": 0.15 * 0.5}
    assert set(s["score_parts"]) == {"snr", "transits", "checks", "brightness"}
    for k, v in expected.items():
        assert math.isclose(s["score_parts"][k], v, abs_tol=1e-4)
    assert math.isclose(s["score"], sum(expected.values()), abs_tol=1e-4)
    assert 0 <= s["score"] <= 1
    single = analyse.score(sig, cs, 10.5, single_sector=True)
    assert math.isclose(single["score"], 0.8 * s["score"], abs_tol=1e-4)
    assert math.isclose(sum(single["score_parts"].values()), single["score"], abs_tol=1e-3)


def test_score_is_one_at_most():
    from hunter.search import Signal
    sig = Signal(3.0, 0.0, 0.1, 1e-3, 1e-5, 1e4, 50.0, 500, 1e-3, 1e-5, 1e-3, 1e-5)
    s = analyse.score(sig, [checks.Check("x", True, 0, "", 1.0)], 5.0, single_sector=False)
    assert math.isclose(s["score"], 1.0, abs_tol=1e-3)


def test_stage_order():
    from hunter.search import Signal
    base = Signal(3.0, 0.0, 0.1, 1e-3, 1e-5, 30.0, 12.0, 9, 1e-3, 1e-5, 1e-3, 1e-5)
    assert analyse.first_failed_stage(replace(base, snr=9.9), [], None) == "snr"
    assert analyse.first_failed_stage(replace(base, sde=8.9), [], None) == "sde"
    assert analyse.first_failed_stage(replace(base, n_transits=2), [], None) == "transits"
    assert analyse.first_failed_stage(base, ["odd_even"], None) == "checks"
    assert analyse.first_failed_stage(base, [], {"same_star": [{}], "neighbours": []}) == "known"
    assert analyse.first_failed_stage(base, [], {"same_star": [], "neighbours": [{}]}) == "neighbour"
    assert analyse.first_failed_stage(base, [], {"same_star": [], "neighbours": []}) is None


def _cat():
    return Catalogue([
        KnownSignal(10, "TOI-1.01", "toi", 2.0, 1e-5, 3000.0, 1e-3, 2.0, 50.0, 10.0, "PC"),
        KnownSignal(11, "TIC 11 (TESS EB catalogue)", "eb", 5.0, 1e-5, 3000.0, 1e-3, 3.0, 50.01, 10.01),
        KnownSignal(12, "Far EB", "eb", 7.0, 1e-5, 3000.0, 1e-3, 3.0, 60.0, 10.0),
    ])


def test_catalogue_matches_period_aliases_and_neighbours():
    cat = _cat()
    assert cat.match(10, 2.01, 50.0, 10.0)["status"] == "known"
    assert cat.match(10, 4.0, 50.0, 10.0)["same_star"][0]["alias"] == "our period is twice the listed one"
    assert cat.match(10, 2.1, 50.0, 10.0)["status"] == "not_on_lists"  # 5% off: not a match
    near = cat.match(99, 2.5, 50.005, 10.005)  # 2.5 d = 1/2 of the EB's 5 d; EB is ~0.7' away
    assert near["status"] == "known_on_neighbour" and near["neighbours"][0]["tic"] == 11
    assert cat.match(99, 7.0, 50.005, 10.005)["status"] == "not_on_lists"  # the 7-d EB is far away


def test_known_transit_mask_covers_listed_transits():
    t = np.arange(3000, 3027, 2 / 1440)
    mask, masked = known_transit_mask(t, None, [_cat().entries[0]])
    assert masked[0].masked_points == mask.sum() > 0
    phase = (t - 3000.0 + 1.0) % 2.0 - 1.0
    assert mask[np.abs(phase) < 1 / 12].all() and not mask[np.abs(phase) > 0.2].any()  # +-1 listed duration
    bad = replace(_cat().entries[0], period_err=0.05)  # 0.05 d x ~6.75 orbits x 3 sigma = 1 d > 0.5 d cap
    _, m2 = known_transit_mask(t, None, [bad])
    assert m2[0].masked_points == 0 and "no fixed mask" in m2[0].note


def test_mask_follows_transits_that_moved_off_the_ephemeris():
    """TTV-like case: real dips 3 h later than listed, with a tiny listed timing error."""
    lc = make_lc(noise=3e-4)
    listed = KnownSignal(5, "Moving b", "confirmed", 4.0, 1e-6, 3000.5, 1e-4, 2.0, 0.0, 0.0)
    lc.flux = lc.flux + box(lc.time, 4.0, 3000.5 + 3 / 24, 2 / 24, 3000e-6)
    no_flux, _ = known_transit_mask(lc.time, None, [listed])
    with_flux, masked = known_transit_mask(lc.time, lc.flux, [listed])
    phase = (lc.time - (3000.5 + 3 / 24) + 2.0) % 4.0 - 2.0
    real = np.abs(phase) < 1 / 24
    assert not no_flux[real].all()  # the fixed mask alone misses part of every dip
    assert with_flux[real].all()  # located and masked where it is
    assert masked[0].located >= 10 and abs(masked[0].median_offset_h - 3.0) < 0.5


def test_ttv_flag_widens_the_fixed_mask():
    t = np.arange(3000, 3027, 2 / 1440)
    k = KnownSignal(5, "b", "confirmed", 8.0, 1e-6, 3000.5, 1e-4, 2.0, 0.0, 0.0)
    _, plain = known_transit_mask(t, None, [k])
    _, ttv = known_transit_mask(t, None, [replace(k, ttv_flag=True)])
    assert math.isclose(ttv[0].half_width_d - plain[0].half_width_d, 0.02 * 8.0, abs_tol=1e-3)


def test_target_tiers_rank_m_dwarfs_then_small_stars():
    m = Star(tic=1, ra=0, dec=0, tmag=12.5, teff=3300, logg=5.0, rad=0.3, lumclass="DWARF")
    k = Star(tic=2, ra=0, dec=0, tmag=9.0, teff=4500, logg=4.6, rad=0.7, lumclass="DWARF")
    g = Star(tic=3, ra=0, dec=0, tmag=8.0, teff=5800, logg=4.4, rad=1.0, lumclass="DWARF")
    giant = Star(tic=4, ra=0, dec=0, tmag=6.0, teff=4800, logg=2.5, rad=10.0, lumclass="GIANT")
    assert [s.tic for s in sorted([giant, g, k, m], key=targets.rank_key)] == [1, 2, 3, 4]


def test_read_plain_tic_list(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("TIC 123\n456  # comment\n\n")
    assert [r["tic"] for r in targets.read(p)] == ["123", "456"]


def test_shards_partition_the_list():
    rows = [{"tic": str(i)} for i in range(45)]
    parts = [sweep.shard_rows(rows, i, 20) for i in range(20)]
    assert sorted(int(r["tic"]) for p in parts for r in p) == list(range(45))
    assert parts[0][0]["tic"] == "0" and parts[1][0]["tic"] == "1"


def test_funnel_and_merge(tmp_path):
    def sig(stage, fails=()):
        return {"failed_stage": stage, "failed_checks": list(fails)}
    s1 = {"tic": 1, "signals": [sig("snr"), sig(None)]}
    s2 = {"tic": 2, "signals": [sig("checks", ["duration", "size"]), sig("known")]}
    s3 = {"tic": 3, "error": "no_data: nothing", "signals": []}
    for d, ss in (("a", [s1, s3]), ("b", [s2])):
        (tmp_path / d / "results").mkdir(parents=True)
        (tmp_path / d / "candidates").mkdir()
        for s in ss:
            (tmp_path / d / "results" / f"{s['tic']}.json").write_text(json.dumps(s))
    (tmp_path / "a" / "candidates" / "1_2.json").write_text(json.dumps({
        "id": "hunt:1:2", "tic": 1, "score": 0.5,
        "score_parts": {"snr": 0.2, "transits": 0.1, "checks": 0.1, "brightness": 0.1}, "period_d": 3.0, "depth_ppm": 900, "snr": 12, "sde": 10,
        "n_transits": 5, "radius_rjup": [0.1, 0.2], "radius_rearth_best": 1.7, "single_sector_only": False,
        "search_list": "new-star search"}))
    (tmp_path / "sens.json").write_text('{"n_stars": 1}')
    out = sweep.merge([tmp_path / "a", tmp_path / "b"], tmp_path / "m", assigned=5, sensitivity=tmp_path / "sens.json")
    summary = json.loads((tmp_path / "m" / "summary.json").read_text())
    assert summary["funnel"]["candidates"] == 1 and summary["n_candidates"] == 1
    assert json.loads((tmp_path / "m" / "sensitivity.json").read_text()) == {"n_stars": 1}
    f = out["funnel"]
    assert f["stars_in_list"] == 5 and f["stars_searched"] == 3 and f["stars_with_data"] == 2
    assert f["signals_found"] == 4 and f["after_snr"] == 3 and f["after_checks"] == 2 and f["after_known"] == 1
    assert f["candidates"] == 1 and f["stars_with_candidates"] == 1
    assert f["check_failures_among_signals_rejected_by_checks"] == {"duration": 1, "size": 1}
    assert (tmp_path / "m" / "candidates" / "1_2.json").exists()
    assert out["candidates"][0]["id"] == "hunt:1:2"


def test_injection_helpers():
    lc = make_lc(n_sectors=1)
    inj = inject.inject(lc, 3.0, 3001.0, 0.1, 0.01)
    assert math.isclose(inj.flux.min(), lc.flux[np.argmin(inj.flux)] * 0.99)
    assert inject.matches({"period_d": 3.01, "t0_btjd": 3004.02, "duration_h": 2.4}, 3.0, 3001.0, 0.1)
    assert not inject.matches({"period_d": 3.1, "t0_btjd": 3001.0, "duration_h": 2.4}, 3.0, 3001.0, 0.1)
    rng = np.random.default_rng(0)
    for b in inject.bins():
        r, p = inject.draw(rng, b)
        assert inject.RADIUS_EDGES[b[0]] <= r <= inject.RADIUS_EDGES[b[0] + 1]
        assert inject.PERIOD_EDGES[b[1]] <= p <= inject.PERIOD_EDGES[b[1] + 1]
    assert len(inject.bins()) == 42
