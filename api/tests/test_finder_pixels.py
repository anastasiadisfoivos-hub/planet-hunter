"""The real PixelsVetter on pixels/' recorded TESS data (offline): WASP-18 b is on target,
TOI-4257's dip is on a neighbour. Skipped when the `finder` extra isn't installed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("skypixels")

from skypixels.render import write_outputs  # noqa: E402
from skypixels.vet import VetInputs, analyze_inputs  # noqa: E402

from api import honesty  # noqa: E402
from api.adapters.finder_real import PixelsVetter  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "pixels" / "tests" / "data"


def recorded(case: str):
    """vet_pixels, replayed from a recorded case instead of MAST."""

    def vet_pixels(tic, period_d, t0_btjd, duration_h, sectors=None, out_dir=None):
        vet, results = analyze_inputs(VetInputs.load(DATA / case))
        if out_dir is not None:
            vet.files = write_outputs(vet, results, Path(out_dir))
        return vet

    return vet_pixels


@pytest.mark.parametrize("case, verdict", [("wasp18", "on target"), ("toi4257", "off target")])
def test_real_vet_has_the_documented_shape(case, verdict):
    if not (DATA / case).is_dir():
        pytest.skip(f"no recorded case {case}")
    candidate = {"tic": 1, "period_d": 0.94, "t0_btjd": 1354.46, "duration_h": 2.2, "sectors": []}
    vet = PixelsVetter(recorded(case)).vet(candidate)
    assert vet["verdict"] == verdict
    for key in ("reason", "on_target_probability", "centroid_offset_arcsec", "offset_sigma",
                "suspect_neighbours", "per_sector"):  # fmt: skip
        assert key in vet
    assert "files" not in vet  # temp paths, gone after the call
    images = vet["images"]
    assert all(images[k] for k in ("out_of_transit", "difference", "markers"))
    assert images["per_sector"] and isinstance(images["sector"], int)
    json.dumps(vet, allow_nan=False)  # storable as jsonb
    assert not honesty.violations(vet)
    if verdict == "off target":
        assert vet["suspect_neighbours"]
