from skyspectra import net
from skyspectra.sun import BIN_NM, HIGH_NM, LOW_NM, MAX_POINTS, bin_mean, build_sun, find_line, parse_atlas


def test_full_window_fits_the_point_budget():
    assert round((HIGH_NM - LOW_NM) / BIN_NM) <= MAX_POINTS


def test_bin_mean_averages_samples():
    wl = [1.00, 1.01, 1.02, 1.06, 1.07]
    fx = [1.0, 0.5, 0.0, 1.0, 0.0]
    w, f = bin_mean(wl, fx, 1.0, 1.1, 0.05)
    assert w == [1.025, 1.075] and f == [0.5, 0.5]


def test_parse_atlas_skips_header_text():
    text = "Kitt Peak Flux Atlas 2005\n300 to 1000 nm by 0.0005 nm\n 300.0000  0.3595\n 300.0005  0.3534\n"
    assert parse_atlas(text) == ([300.0, 300.0005], [0.3595, 0.3534])


def test_find_line_ignores_continuum():
    assert find_line([500.0, 500.01], [0.99, 0.98], 500.0) is None


def test_build_sun_real_atlas_na_d(replay):
    doc = build_sun(net.Net(), 585.0, 592.0)
    assert doc["source"] and doc["credit"] and doc["licence"]
    assert len(doc["wavelength_nm"]) == len(doc["flux"]) <= MAX_POINTS
    assert 585.0 < doc["wavelength_nm"][0] < doc["wavelength_nm"][-1] < 592.0
    labels = {ln["label"]: ln for ln in doc["lines"]}
    assert set(labels) == {"D2 (Na I)", "D1 (Na I)"}
    for ln in labels.values():
        assert ln["element"] == "Na" and ln["atlas_min_flux"] < 0.1  # the D lines are >90% deep
        assert abs(ln["atlas_min_nm"] - ln["nm"]) < 0.005
    # even binned, the flux dips at the D lines and is near continuum between features
    i = min(range(len(doc["flux"])), key=doc["flux"].__getitem__)
    assert abs(doc["wavelength_nm"][i] - 589.0) < 0.7
    assert max(doc["flux"]) > 0.95


def test_build_sun_real_atlas_ca_hk(replay):
    doc = build_sun(net.Net(), 392.0, 398.0)
    assert {ln["label"] for ln in doc["lines"]} == {"K (Ca II)", "H (Ca II)"}
