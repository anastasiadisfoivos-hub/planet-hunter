import math

import numpy as np
import pytest

from skypixels import analyze as an
from skypixels.catalog import btjd_to_jyear
from synth import make_sector, star


def run(stars, sectors):
    target, others = stars[0], stars[1:]
    results = [an.analyze_sector(s, target, others) for s in sectors]
    comb = an.combine(results)
    jyear = btjd_to_jyear(sectors[0].epoch_btjd)
    rows = an.neighbour_table(target, others, comb, jyear)
    verdict, reason = an.verdict(comb, rows, results)
    prob = an.on_target_probability(comb, rows) if comb else None
    return verdict, reason, prob, comb, rows, results


def test_dip_on_target_is_on_target(rng):
    stars = [star(0, 0, 10.0, "T"), star(60, 10, 12.0, "N1"), star(-30, -70, 11.0, "N2")]
    verdict, reason, prob, comb, rows, _ = run(stars, [make_sector(rng, stars, host=0, depth=0.01)])
    assert verdict == "on target", reason
    assert prob > 0.95
    assert comb.offset_sigma < 3
    assert abs(comb.depth - 0.01) < 0.001
    n1 = next(r for r in rows if r["gaia_id"] == "N1")
    assert abs(n1["needed_depth"] - 0.01 * 10 ** 0.8) < 0.01  # ΔT = 2 mag → 6.3× deeper
    assert n1["excluded_by_centroid"] and not n1["suspect"]


def test_dip_on_neighbour_is_off_target_and_names_it(rng):
    stars = [star(0, 0, 10.0, "T"), star(30, 25, 12.5, "EB"), star(-50, 40, 12.0, "N2")]
    verdict, reason, prob, comb, rows, _ = run(stars, [make_sector(rng, stars, host=1, depth=0.2)])
    assert verdict == "off target", reason
    assert "EB" in reason
    assert prob < 0.01
    assert abs(comb.offset_arcsec - math.hypot(30, 25)) < 3
    eb = next(r for r in rows if r["gaia_id"] == "EB")
    assert eb["suspect"] and abs(eb["needed_depth"] - 0.2) < 0.03
    n2 = next(r for r in rows if r["gaia_id"] == "N2")
    assert n2["excluded_by_centroid"]


def test_unresolved_bright_neighbour_is_possible_neighbour(rng):
    stars = [star(0, 0, 10.0, "T"), star(3, 2, 13.0, "CLOSE")]
    verdict, reason, prob, comb, rows, _ = run(stars, [make_sector(rng, stars, host=0, depth=0.01)])
    assert verdict == "possible neighbour", reason
    close = rows[0]
    assert close["gaia_id"] == "CLOSE" and close["suspect"]
    assert abs(close["needed_depth"] - 0.01 * 10 ** 1.2) < 0.02
    assert 0.5 < prob < 0.95  # target favoured by prior, neighbour not excluded


def test_neighbour_too_faint_to_host_the_dip_is_not_suspect(rng):
    stars = [star(0, 0, 10.0, "T"), star(3, 2, 16.0, "FAINT")]  # would need a 251% eclipse
    verdict, _, prob, _, rows, _ = run(stars, [make_sector(rng, stars, host=0, depth=0.01)])
    assert verdict == "on target"
    assert rows[0]["needed_depth"] > 1 and not rows[0]["suspect"]
    assert prob > 0.95


def test_no_dip_is_inconclusive(rng):
    stars = [star(0, 0, 10.0, "T"), star(30, 25, 12.5, "N")]
    verdict, reason, prob, comb, rows, results = run(stars, [make_sector(rng, stars, host=None, depth=0)])
    assert verdict == "inconclusive" and "not visible" in reason
    assert comb is None and prob is None
    assert rows[0]["needed_depth"] is None and not rows[0]["suspect"]


def test_wcs_error_is_calibrated_out(rng):
    stars = [star(0, 0, 10.0, "T"), star(60, 10, 11.5, "N1"), star(-45, -30, 11.0, "N2")]
    sec = make_sector(rng, stars, host=0, depth=0.01, wcs_shift=(0.45, -0.35))
    verdict, reason, _, comb, _, results = run(stars, [sec])
    assert verdict == "on target", reason
    assert abs(results[0].scene.dx - 0.45) < 0.05 and abs(results[0].scene.dy + 0.35) < 0.05


def test_proper_motion_is_applied(rng):
    # 2″/yr high-proper-motion target, observed 11 years after Gaia's epoch: 22″ ≈ 1 px of motion.  Bright
    # reference stars pin the WCS; with the target alone the WCS-shift calibration would absorb the motion.
    fast = star(0, 0, 10.0, "T")
    fast.pmra_masyr = 2000.0
    refs = [star(70, 20, 9.5, "R1"), star(-60, 50, 9.8, "R2"), star(-20, -80, 9.6, "R3")]
    sec = make_sector(rng, [fast, *refs], host=0, depth=0.01, epoch_btjd=3000.0)
    verdict, reason, *_ = run([fast, *refs], [sec])
    assert verdict == "on target", reason
    frozen = star(0, 0, 10.0, "T")  # same star with the proper motion ignored → the dip looks off target
    verdict_frozen, *_ = run([frozen, *refs], [sec])
    assert verdict_frozen == "off target"


def test_sectors_combine_with_different_orientations(rng):
    stars = [star(0, 0, 10.0, "T"), star(30, 25, 12.5, "EB")]
    secs = [make_sector(rng, stars, host=1, depth=0.1, sector=s, rot_deg=r, noise=6.0)
            for s, r in ((1, 30.0), (2, 120.0), (3, 210.0))]
    verdict, _, _, comb, _, results = run(stars, secs)
    assert verdict == "off target"
    single = [np.hypot(*r.offset_en) for r in results]
    assert all(abs(s - math.hypot(30, 25)) < 6 for s in single)
    miss = comb.offset_en - np.array([30.0, 25.0])
    assert float(np.sqrt(miss @ np.linalg.solve(comb.cov_en, miss))) < 3
    assert comb.offset_sigma > max(r.to_dict()["offset_sigma"] for r in results)  # more data, more σ


@pytest.mark.parametrize("d_sigma, expected", [(0.0, 0.989), (3.0, 0.5)])
def test_heuristic_calibration_points(d_sigma, expected):
    # Large pixel scale so the heuristic's 0.1 px floor is negligible against σ = 5″.
    comb = an.Combined(np.array([5.0 * d_sigma, 0.0]), np.eye(2) * 25.0, 5.0 * d_sigma, d_sigma, 0.01, 0.001,
                       pixel_scale=1.0, chi2_red=1.0)
    assert abs(an.on_target_probability(comb, []) - expected) < 0.01


def test_excluded_needs_both_sigma_and_pixels():
    cov = np.eye(2) * 0.01  # σ = 0.1″ — tiny
    assert not an.excluded(np.array([5.0, 0.0]), cov, pixel_scale=21.0)  # 50σ but only 0.24 px
    assert an.excluded(np.array([7.0, 0.0]), cov, pixel_scale=21.0)  # 70σ and 0.33 px
    assert not an.excluded(np.array([30.0, 0.0]), np.eye(2) * 200.0, pixel_scale=21.0)  # 1.4 px but 2.1σ
