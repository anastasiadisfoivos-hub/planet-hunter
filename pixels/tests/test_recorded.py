"""Offline replays of real TESS data (recorded with scripts/record_fixtures.py)."""

import json

import numpy as np
import pytest

from conftest import CASES, DATA
from skypixels import analyze as an
from skypixels.reduce import make_images
from skypixels.render import write_outputs
from skypixels.vet import VetInputs, _stars, analyze_inputs


@pytest.fixture(scope="module")
def vets():
    return {name: analyze_inputs(VetInputs.load(DATA / name)) for name in CASES}


@pytest.mark.parametrize("name", list(CASES))
def test_verdicts_match_the_known_answer(vets, name):
    vet, _ = vets[name]
    assert vet.verdict == CASES[name]["expect"], vet.reason


def test_wasp18b_is_on_target_with_the_right_depth(vets):
    vet, _ = vets["wasp18"]
    assert vet.on_target_probability > 0.95
    assert vet.offset_sigma < 3 and vet.centroid_offset_arcsec < 3
    assert 0.009 < vet.depth_on_target < 0.0125  # TOI-185.01: 11 445 ppm
    assert vet.suspect_neighbours == []
    assert all(s["detected"] for s in vet.per_sector) and len(vet.per_sector) == 3


def test_toi4257_points_at_tic75208617(vets):
    vet, _ = vets["toi4257"]
    case = CASES["toi4257"]
    assert vet.on_target_probability < 0.01
    assert vet.offset_sigma > 10
    assert 20 < vet.centroid_offset_arcsec < 30  # TIC 75208617 is 25.1″ away
    best = min(vet.suspect_neighbours, key=lambda s: s["centroid_distance_sigma"])
    assert best["gaia_id"] == case["culprit_gaia_dr3"]  # = TIC 75208617's Gaia id
    assert best["centroid_distance_sigma"] < 3
    assert 0.01 < best["needed_depth"] < 0.1  # a few-percent eclipse on a T = 13.9 star: an ordinary EB
    # every sector (two SPOC TPFs and one TESScut FFI) independently sees it off target
    for s in vet.per_sector:
        assert s["detected"] and s["offset_sigma"] > 5 and 20 < s["centroid_offset_arcsec"] < 30


def test_quiet_star_is_a_clean_non_detection(vets):
    vet, _ = vets["quiet"]
    assert vet.on_target_probability is None and vet.centroid_offset_arcsec is None
    assert vet.suspect_neighbours == []
    assert vet.depth_upper_limit_3sigma < 5e-4
    assert all(not s["detected"] and abs(s["diff_snr"]) < 5 for s in vet.per_sector)
    assert {s["kind"] for s in vet.per_sector} == {"ffi", "tpf"}


def test_outputs_for_the_web_ui(vets, tmp_path):
    vet, results = vets["toi4257"]
    files = write_outputs(vet, results, tmp_path)
    assert len(files["pngs"]) == len(files["json"]) == 3
    assert all((tmp_path / f).stat().st_size > 10_000 for f in files["pngs"])
    d = json.loads((tmp_path / files["json"][0]).read_text())
    ny, nx = d["shape"]
    assert len(d["out_of_transit"]) == ny and len(d["out_of_transit"][0]) == nx
    assert len(d["difference"]) == ny
    kinds = {m["kind"] for m in d["markers"]}
    assert {"target", "suspect", "neighbour"} <= kinds
    assert d["centroid"]["used"] is True
    assert (tmp_path / files["json"][0]).stat().st_size < 60_000
    json.dumps(vet.to_dict())  # whole result is JSON-serialisable


def test_reduction_on_real_wasp18_pixels():
    """Raw frames (8 transits of sector 105) → difference image → centroid on WASP-18."""
    raw = np.load(DATA / "wasp18_s105_raw_crop.npz")
    case = CASES["wasp18"]
    img = make_images(105, "tpf", raw["time"], raw["flux"], raw["quality"], str(raw["wcs_header"]),
                      case["period_d"], case["t0_btjd"], case["duration_h"] / 24)
    assert img is not None and img.n_transits >= 4  # 8 cropped, some lost to gaps and flagged frames
    inputs = VetInputs.load(DATA / "wasp18")
    target, others = _stars(inputs.tic, inputs.gaia)
    res = an.analyze_sector(img, target, others)
    assert res.detected and res.diff.snr > 10
    assert np.hypot(*res.offset_en) < 5
    assert 0.008 < res.depth < 0.013


def test_no_pixel_data_is_inconclusive():
    rec = VetInputs.load(DATA / "wasp18")
    vet, _ = analyze_inputs(VetInputs(rec.tic, rec.gaia, rec.ephemeris, [], [], []))
    assert vet.verdict == "inconclusive" and "no usable TESS pixel data" in vet.reason
    assert vet.per_sector == [] and vet.on_target_probability is None
