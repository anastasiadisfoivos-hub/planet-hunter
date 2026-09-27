"""Offline proof on FAINT's recorded TGLC curves (faint/tests/data, loaded with skyfaint.tglc.FaintLC.load).

TOI-1680 b (1.47 R_earth, 24 sectors, Tmag 13.3) was missed by HUNT's per-sector search and by the first deep
search (FAINT, faint/README "Proof"): the transit is in the data, but per sector it is at SNR ~5, the pipeline's
coarse stage adds sector powers without aligning phases, and scattered-light dips filled every signal slot. The
deep search now runs one phase-coherent BLS over all sectors, masks scattered light with shoulders and edge
windows before searching, and keeps searching (up to 6 signals) while the SDE stays up.

TOI-5688 A b: a hard 3-sigma background cut without shoulders made hunt's SDE fall from 10.1 to 5.6 (FAINT);
with the shoulder mask it must stay found.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from hunt import analyse
from hunt.catalogs import Catalogue
from hunt.stars import Star

pytestmark = pytest.mark.deep

FAINT = Path(__file__).resolve().parents[2] / "faint" / "tests" / "data"
TOI1680, TOI5688 = 259168516, 193634953


def _facts() -> dict:
    return json.loads((FAINT / "facts.json").read_text())


def _load(tic: int):
    from skyfaint.tglc import FaintLC

    star = Star.from_row(json.loads((FAINT / f"{tic}.json").read_text())["star"])
    return star, FaintLC.load(FAINT / f"{tic}.npz").to_hunt()


def test_toi1680_transit_is_in_the_tglc_data():
    """FAINT's pinned facts (test_toi1680_in_data_but_missed_by_the_per_sector_search, parts 1-2): the transit is there."""
    from hunter.clean import robust_sigma
    from hunter.search import in_transit

    from hunt import detrend

    f = _facts()["toi1680"]
    _, lc = _load(TOI1680)
    P, T0, D = f["period_d"], f["t0_btjd"], f["duration_h"] / 24
    flat, keep = detrend.flatten(lc.time, lc.flux, 0.9, in_transit(lc.time, P, T0, D, 2))
    it = in_transit(lc.time, P, T0, 0.8 * D) & keep
    depth = 1 - flat[it].mean()
    snr = depth / (robust_sigma(flat[keep & ~it]) / np.sqrt(it.sum()))
    assert depth * 1e6 == pytest.approx(f["depth_ppm"], rel=0.3) and snr > 15


@pytest.fixture(scope="module")
def toi1680():
    star, lc = _load(TOI1680)
    return analyse.analyse(star, lc, Catalogue([]), "A")


def test_toi1680_b_is_recovered_by_the_coherent_search(toi1680):
    P = _facts()["toi1680"]["period_d"]
    hit = [s for s in toi1680.signals if abs(s["period_d"] / P - 1) < 0.01]
    assert hit, [(s["period_d"], s["snr"], s["sde"]) for s in toi1680.signals]
    s = hit[0]
    assert s["sde"] >= 9 and s["snr"] >= 10 and s["n_transits"] >= 3 and "bls_short" in s["found_by"]
    cand = next(c for c in toi1680.candidates if c["kind"] == "periodic" and abs(c["period_d"] / P - 1) < 0.01)
    assert 1.2 < cand["radius_rearth_best"] < 1.8
    sl = toi1680.search["scattered_light"]
    assert sl["applied"] and 0.05 < sl["masked_fraction"] < 0.35


def test_toi5688_b_survives_the_scattered_light_mask():
    f = _facts()["toi5688"]
    star, lc = _load(TOI5688)
    res = analyse.analyse(star, lc, Catalogue([]), "A")
    cand = next(c for c in res.candidates if c["kind"] == "periodic")
    assert abs(cand["period_d"] / f["period_d"] - 1) < 0.01
    assert cand["sde"] > 10.1  # FAINT: 10.1 without a cut, 5.6 with a hard cut and no shoulders
    assert abs(cand["depth_ppm"] / f["depth_ppm_from_ratror"] - 1) < 0.15
