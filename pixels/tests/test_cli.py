import json

from conftest import DATA
from skypixels import cli, vet
from skypixels.vet import VetInputs


def test_cli_vet_offline(monkeypatch, tmp_path, capsys):
    recorded = VetInputs.load(DATA / "wasp18")
    seen = {}

    def fake_gather(tic_id, period_d, t0_btjd, duration_h, sectors, max_sectors, refresh, timings):
        seen.update(tic=tic_id, period=period_d, t0=t0_btjd, dur=duration_h, sectors=sectors)
        return recorded

    monkeypatch.setattr(vet, "gather", fake_gather)
    out = tmp_path / "o"
    rc = cli.main(["vet", "--tic", "100100827", "--period", "0.9414525", "--t0", "2460205.353322",
                   "--duration", "2.05", "--sectors", "104", "105", "--out", str(out)])
    assert rc == 0
    assert seen == {"tic": 100100827, "period": 0.9414525, "t0": 2460205.353322, "dur": 2.05, "sectors": [104, 105]}
    summary = json.loads(capsys.readouterr().out)
    assert summary["verdict"] == "on target"
    full = json.loads((out / "pixel_vet.json").read_text())
    assert full["verdict"] == "on target" and full["timings_s"]["total"] >= 0
    assert all((out / p).exists() for p in full["files"]["pngs"] + full["files"]["json"])


def test_t0_accepts_full_bjd():
    assert vet.normalise_t0(2460205.353322) == 2460205.353322 - 2457000
    assert vet.normalise_t0(3205.35) == 3205.35
