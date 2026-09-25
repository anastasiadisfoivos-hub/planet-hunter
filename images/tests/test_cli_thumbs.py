import json

from recording import FIXTURES

from skypictures import cli, net, thumbnail_url

EVENTS = json.loads((FIXTURES / "example_events.json").read_text())
EXPECTED = json.loads((FIXTURES / "example_pictures.json").read_text())["pictures"]
NOAA = json.loads((FIXTURES / "noaa_event.json").read_text())


def test_thumbnails():
    h = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits?hips=CDS%2FP%2FDSS2%2Fcolor&width=800&height=800&fov=1"
    assert "width=256&height=256" in thumbnail_url(h) and "fov=1" in thumbnail_url(h)
    s = "https://sdo.gsfc.nasa.gov/assets/img/browse/2026/09/19/20260919_181456_1024_0131.jpg"
    assert thumbnail_url(s) == s.replace("_1024_", "_512_")
    hv = "https://api.helioviewer.org/v2/downloadImage/?id=1&width=1024&height=1024&type=jpg"
    assert thumbnail_url(hv) == "https://api.helioviewer.org/v2/downloadImage/?id=1&width=256&height=256&type=jpg"
    fink = "https://api.ztf.fink-portal.org/api/v1/cutouts?objectId=ZTF1&kind=Science&output-format=PNG"
    assert thumbnail_url(fink) == fink


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
    thumbs = json.loads((tmp_path / "out.thumbs.json").read_text())
    assert set(thumbs) == {i["url"] for e in got for i in e["images"]}
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


def test_short_lived_noaa_frame_is_rehosted(replay, monkeypatch, tmp_path, capsys):
    replay("noaa")
    monkeypatch.setattr(net.Net, "download", lambda self, url: ("image/jpeg", b"\xff\xd8jpegbytes"))
    src = tmp_path / "events.json"
    src.write_text(json.dumps([NOAA["event"]]))
    out = tmp_path / "site" / "events.json"
    out.parent.mkdir()
    cli.main([str(src), "-o", str(out), "--rehost-base", "/pictures-cache"])
    [img] = json.loads(out.read_text())[0]["images"]
    assert img["url"].startswith("/pictures-cache/aurora_N_") and img["url"].endswith(".jpg")
    saved = out.parent / "pictures-cache" / img["url"].rsplit("/", 1)[1]
    assert saved.read_bytes() == b"\xff\xd8jpegbytes"
    assert img["credit"] == NOAA["pictures"][0]["credit"]
    assert "re-hosted 1" in capsys.readouterr().err


def test_no_check_mode_is_offline_for_probes(replay, monkeypatch, tmp_path):
    replay("examples")
    monkeypatch.setattr(net.Net, "probe", lambda self, url: (_ for _ in ()).throw(AssertionError("probed")))
    src = tmp_path / "e.json"
    src.write_text(json.dumps([e for e in EVENTS if e["type"] == "kilonova"]))
    cli.main([str(src), "--no-check"])
    [e] = json.loads(src.read_text())
    assert [i["kind"] for i in e["images"]] == ["sky_context"]
