import json

import pytest
from contract import assert_heatmap
from fixtures import scenarios as sc

from skysources import heatmap


@pytest.fixture
def small_pages(monkeypatch):
    monkeypatch.setattr(heatmap, "PAGE_SIZE", sc.HEATMAP_PAGE_SIZE)
    monkeypatch.setattr(heatmap, "MAX_PAGES_PER_CLASS", sc.HEATMAP_MAX_PAGES)


def test_heatmap_matches_contract(replay, small_pages):
    replay("heatmap")
    h = heatmap.build_heatmap(sc.HEATMAP_NIGHTS, until=sc.HEATMAP_UNTIL)
    assert_heatmap(h)
    assert h["grid"] == "healpix nside=32"
    totals = {}
    for c in h["cells"]:
        for k, v in c["counts"].items():
            totals[k] = totals.get(k, 0) + v
    # 50 recorded ALeRCE objects per class, plus the recorded SSO sample.
    assert totals["supernova"] == 50 and totals["active_galaxy"] == 50 and totals["variable_star"] == 50
    assert totals.get("asteroid", 0) > 0


def test_cli_writes_file(replay, small_pages, tmp_path):
    replay("heatmap")
    out = tmp_path / "heatmap.json"
    assert heatmap.main(["--nights", "1", "--until", sc.HEATMAP_UNTIL, "--out", str(out)]) == 0
    assert_heatmap(json.loads(out.read_text()))


def test_rejects_zero_nights():
    with pytest.raises(ValueError):
        heatmap.build_heatmap(0)
