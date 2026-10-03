import math

from skypixels.catalog import btjd_to_jyear, gaia_to_tmag, match_target, propagate, sky_offset_arcsec


def test_gaia_to_tmag_matches_stassun_2019():
    # eq. 1 worked by hand: BP−RP = 0.82 (Sun-like) → G − T = 0.430; BP−RP = 2.5 (M dwarf) → G − T = 1.077
    assert abs((10 - gaia_to_tmag(10.0, 0.82)) - 0.430) < 0.002
    assert abs((12 - gaia_to_tmag(12.0, 2.5)) - 1.077) < 0.002
    assert gaia_to_tmag(10.0, None) == 10.0 - 0.430


def test_proper_motion_propagation():
    ra, dec = propagate(10.0, 60.0, pmra=1000.0, pmdec=-500.0, from_year=2016.0, to_year=2026.0)
    e, n = sky_offset_arcsec(10.0, 60.0, ra, dec)
    assert abs(e - 10.0) < 1e-3 and abs(n + 5.0) < 1e-3
    assert propagate(1.0, 2.0, None, None, 2016, 2030) == (1.0, 2.0)


def test_sky_offset_wraps_ra():
    e, n = sky_offset_arcsec(359.999, 0.0, 0.001, 0.0)
    assert abs(e - 7.2) < 1e-6 and n == 0


def test_btjd_epoch():
    assert abs(btjd_to_jyear(0.0) - 2014.93498) < 1e-5  # BTJD 0 = JD 2457000.0 = 2014 Dec 8.5
    assert abs(btjd_to_jyear(3000.0) - btjd_to_jyear(0.0) - 3000 / 365.25) < 1e-9


def test_match_target_prefers_the_dr2_id_then_position():
    stars = [
        {"gaia_id": "1", "ra_deg": 100.0, "dec_deg": 0.0, "gmag": 10.0},
        {"gaia_id": "2", "ra_deg": 100.0 + 2 / 3600, "dec_deg": 0.0, "gmag": 15.0},
    ]
    tic = {"ra_deg": 100.0, "dec_deg": 0.0, "pmra_masyr": 0.0, "pmdec_masyr": 0.0, "gaia_dr2_id": "2", "gmag": 15.0}
    assert match_target(tic, stars)["gaia_id"] == "2"
    tic = {**tic, "gaia_dr2_id": "999", "gmag": 10.1}
    assert match_target(tic, stars)["gaia_id"] == "1"
    tic = {**tic, "ra_deg": 100.0 + 10 / 3600 / math.cos(0)}
    assert match_target(tic, stars) is None
