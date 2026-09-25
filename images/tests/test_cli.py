import json

from recording import FIXTURES

from skypictures import cli, net

EVENTS = json.loads((FIXTURES / "example_events.json").read_text())
EXPECTED = json.loads((FIXTURES / "example_pictures.json").read_text())["pictures"]


def test_enrich_file_list_input(replay, tmp_path, capsys):
    replay("examples")
    src = tmp_path / "events.json"
    src.write_text(json.dumps(EVENTS))
    out = tmp_path / "out.json"
    assert cli.main([str(src), "-o", str(out), "--workers", "4"]) == 0
    got = json.loads(out.read_text())
    assert [e["id"] for e in got] == [e["id"] for e in EVENTS]
    for e in got:
        assert e["images"] == EXPECTED[e["id"]]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["events.json", "out.json"]  # no sidecars, no cache dir
    err = capsys.readouterr().err
    assert "20 events, 18 with pictures" in err and "dropped 0 dead/blank (0.0%)" in err


def test_enrich_keeps_wrapper_and_existing_images(replay, tmp_path):
    replay("examples")
    sn = next(e for e in EVENTS if e["type"] == "supernova")
    mine = EXPECTED[sn["id"]][0]
    doc = {"generated_at": "x", "events": [{**sn, "images": [mine]}]}
    src = tmp_path / "events.json"
    src.write_text(json.dumps(doc))
    cli.main([str(src)])  # in place
    got = json.loads(src.read_text())
    assert got["generated_at"] == "x"
    assert got["events"][0]["images"] == EXPECTED[sn["id"]]  # no duplicate of the existing picture


def test_existing_image_without_thumb_url_gets_null(replay, tmp_path):
    replay("examples")
    kn = next(e for e in EVENTS if e["type"] == "kilonova")
    old = {k: v for k, v in EXPECTED[kn["id"]][0].items() if k != "thumb_url"}
    old["url"] = old["url"].replace("width=800", "width=801")
    src = tmp_path / "e.json"
    src.write_text(json.dumps([{**kn, "images": [old]}]))
    cli.main([str(src), "--no-check"])
    [e] = json.loads(src.read_text())
    assert [i["thumb_url"] for i in e["images"]] == [EXPECTED[kn["id"]][0]["thumb_url"], None]


def test_no_check_mode_is_offline_for_probes(replay, monkeypatch, tmp_path):
    replay("examples")
    monkeypatch.setattr(net.Net, "probe", lambda self, url: (_ for _ in ()).throw(AssertionError("probed")))
    src = tmp_path / "e.json"
    src.write_text(json.dumps([e for e in EVENTS if e["type"] == "kilonova"]))
    cli.main([str(src), "--no-check"])
    [e] = json.loads(src.read_text())
    assert [i["kind"] for i in e["images"]] == ["sky_context"]
