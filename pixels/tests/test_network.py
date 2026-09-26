import pytest

from skypixels import vet_pixels


@pytest.mark.network
def test_live_wasp18_one_sector(tmp_path):
    v = vet_pixels(100100827, 0.9414525, 3205.353322, 2.05, sectors=[105], out_dir=tmp_path)
    assert v.verdict == "on target"
    assert (tmp_path / "pixel_vet.json").exists()


@pytest.mark.network
def test_live_toi4257_ffi_sector(tmp_path):
    v = vet_pixels(75208638, 4.6512523, 2990.712909, 2.251, sectors=[89])
    assert v.per_sector[0]["kind"] == "ffi"
    assert v.verdict == "off target"
