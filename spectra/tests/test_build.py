import json

from sample import ELEMENTS, PLANETS, SUN_RANGE, TICS

from skyspectra import cli, net
from skyspectra.build import build


def _files(out):
    return sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())


def test_build_writes_exactly_the_contract(replay, tmp_path):
    out = tmp_path / "out"
    index = build(out, net.Net(), TICS, element_symbols=ELEMENTS, sun_range=SUN_RANGE, planets=sorted(PLANETS))
    assert _files(out) == [
        "elements.json", "index.json",
        "planets/hd-189733-b.atmosphere.json", "planets/wasp-121-b.atmosphere.json",
        "stars/22529346.abundances.json", "stars/22529346.gaia_xp.json",
        "stars/256364928.abundances.json", "stars/256364928.gaia_xp.json",
        "sun_spectrum.json",
    ]
    assert index["counts"] == {"stars_with_abundances": 2, "stars_with_gaia_xp": 2, "planets": 2,
                               "planets_with_spectrum": 2}
    assert index["requested_tics_not_in_archive"] == [1]
    assert index["total_bytes"] == sum((out / f).stat().st_size for f in _files(out) if f != "index.json")
    assert index["stars"]["22529346"]["gaia_xp"]["path"] == "stars/22529346.gaia_xp.json"
    assert index["planets"]["wasp-121-b"]["has_spectrum"] is True

    # every file says where it came from, who to credit, and under what licence
    for f in _files(out):
        doc = json.loads((out / f).read_text())
        for d in doc if isinstance(doc, list) else [doc]:
            assert d["source"] and d["credit"] and d["licence"], f


def test_rebuild_prunes_files_that_no_longer_apply(replay, tmp_path):
    out = tmp_path / "out"
    (out / "stars").mkdir(parents=True)
    (out / "stars" / "999.gaia_xp.json").write_text("{}")
    (out / "stars" / "notes.txt").write_text("mine")
    build(out, net.Net(), TICS, parts=("stars",))
    assert not (out / "stars" / "999.gaia_xp.json").exists()
    assert (out / "stars" / "notes.txt").exists()  # only our own file patterns are touched


def test_cli_build_with_tic_file(replay, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(net, "_net", None)
    tics = tmp_path / "tics.txt"
    tics.write_text("TIC 22529346\n256364928  # HD 189733\n1\n")
    out = tmp_path / "out"
    assert cli.main(["build", "--out", str(out), "--tic-file", str(tics), "--only", "stars", "-q"]) == 0
    assert "2 stars with abundances, 2 with Gaia XP" in capsys.readouterr().out
    assert json.loads((out / "index.json").read_text())["stars"]["22529346"]["name"] == "WASP-121"
