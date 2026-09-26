"""Per-star Lab: the unfolded light curve (migration 0004), GET /stars/{tic}/lab,
GET /stars/{tic}/lightcurve, the NASA Exoplanet Archive cache and the SPECTRA index."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from api import lab, precompute
from api.fakes.archive import WASP_121
from api.lightcurve import bin_lightcurve
from api.models import HostSystem, KnownPlanet, LightCurve, StoredAnalysis, StoredLightCurve
from api.spectra_index import SpectraIndex
from tests.conftest import TIC, wait_job

T = datetime(2026, 9, 20, 3, 4, 5, 123456, tzinfo=UTC)


def analyze(client, tic):
    r = client.post("/analyze", json={"tic_id": tic})
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    return job


def legacy_result(services, tic) -> StoredAnalysis:
    """A result as stored before 0004: no light curve row."""
    a = services.analyzer
    marker = a._marker(tic)
    rec = StoredAnalysis(
        tic_id=tic,
        data_marker=marker,
        analyzed_at=datetime.now(UTC),
        marker_checked_at=datetime.now(UTC),
        analysis=a._result(tic, marker).model_copy(update={"lightcurve": None}),
    )
    services.storage.put_star_analysis(rec)
    return rec


@pytest.fixture
def spectra_file(tmp_path):
    path = tmp_path / "index.json"
    path.write_text(
        json.dumps(
            {
                "stars": {
                    str(WASP_121): {
                        "tic": WASP_121,
                        "name": "WASP-121",
                        "gaia_xp": {"path": f"stars/{WASP_121}.gaia_xp.json", "bytes": 9},
                        "abundances": {"path": f"stars/{WASP_121}.abundances.json", "bytes": 9},
                    },
                    "42": {"tic": 42, "gaia_xp": {"path": "stars/42.gaia_xp.json", "bytes": 1}},
                },
                "planets": {
                    "wasp-121-b": {"planet": "WASP-121 b", "host": "WASP-121", "tic": WASP_121},
                    "wasp-18-b": {"planet": "WASP-18 b", "host": "WASP-18", "tic": 100100827},
                },
            }
        )
    )
    return path


# binning --------------------------------------------------------------------------------


def test_bin_lightcurve_caps_points_and_never_crosses_gaps():
    t = np.concatenate([np.arange(0, 13, 2 / 1440), np.arange(14, 27, 2 / 1440)])
    f = np.ones_like(t)
    f[::97] = np.nan  # dropped, not averaged
    lc = bin_lightcurve(t, f, [5, 5])
    assert len(lc.time_btjd) <= 3000 and len(lc.time_btjd) == len(lc.flux)
    assert lc.binned_from == int(np.isfinite(f).sum()) and lc.sectors == [5]
    assert not any(13 < x < 14 for x in lc.time_btjd)  # no bin straddles the gap
    assert lc.time_btjd == sorted(lc.time_btjd) and set(lc.flux) == {1.0}
    small = bin_lightcurve(np.arange(10.0), np.ones(10), [1])
    assert small.time_btjd == list(np.arange(10.0)) and small.binned_from == 10
    many = bin_lightcurve(np.arange(0, 3001 * 0.6, 0.6), np.ones(3001), [1])  # 3001 segments
    assert len(many.time_btjd) <= 3000


def test_lightcurve_model_caps_points():
    with pytest.raises(ValueError):
        LightCurve(time_btjd=[0.0] * 3001, flux=[1.0] * 3001, binned_from=3001)
    with pytest.raises(ValueError):
        LightCurve(time_btjd=[0.0], flux=[], binned_from=1)


# storage (both backends) ------------------------------------------------------------------


def test_lightcurve_and_known_planet_rows(storage):
    assert storage.get_star_lightcurve(1) is None and storage.get_known_planets(1) is None
    curve = LightCurve(time_btjd=[1.5, 2.5], flux=[1.0, 0.99], binned_from=40, sectors=[3])
    rec = StoredLightCurve(tic_id=1, status="stored", data_marker="sector-3", stored_at=T,
                           curve=curve)  # fmt: skip
    storage.put_star_lightcurve(rec)
    assert storage.get_star_lightcurve(1) == rec
    none = StoredLightCurve(tic_id=2, status="no_data", stored_at=T)
    storage.put_star_lightcurve(none)
    assert storage.get_star_lightcurve(2) == none
    host = HostSystem(
        tic_id=1,
        host_name="WASP-121",
        planets=[KnownPlanet(name="WASP-121 b", period_d=1.27, a_au=0.0257, mass_kind="Mass")],
        fetched_at=T,
    )
    storage.put_known_planets(host)
    storage.put_known_planets(host)
    assert storage.get_known_planets(1) == host
    empty = HostSystem(tic_id=3, fetched_at=T)
    storage.put_known_planets(empty)
    assert storage.get_known_planets(3) == empty


# analysis keeps the unfolded curve -----------------------------------------------------------


def test_analysis_stores_unfolded_curve_apart(client, services):
    job = analyze(client, TIC)
    assert "lightcurve" not in job["result"]["analysis"]
    stored = client.get(f"/stars/{TIC}/analysis").json()
    assert "lightcurve" not in stored["analysis"]
    r = client.get(f"/stars/{TIC}/lightcurve")
    assert r.status_code == 200, r.text
    body = r.json()
    un = body["unfolded"]
    assert 0 < len(un["time_btjd"]) == len(un["flux"]) <= 3000 < un["binned_from"]
    assert body["data_marker"] == stored["data_marker"]
    sigs = stored["analysis"]["signals"]
    assert [f["signal_id"] for f in body["folded"]] == [s["id"] for s in sigs]
    for f, s in zip(body["folded"], sigs, strict=True):
        for k in ("period_days", "t0_btjd", "duration_hours", "depth_ppm"):
            assert f[k] == s[k]
        assert f["phase"] == s["folded"]["phase"] and len(f["flux"]) <= 1000
    assert min(un["flux"]) < 1.0  # the dips are in it


def test_lightcurve_404_reasons(client, services):
    r = client.get("/stars/777/lightcurve")
    assert r.status_code == 404 and r.json()["detail"]["reason"] == "not analyzed yet"
    services.analyzer.markers[778] = None
    assert client.post("/analyze", json={"tic_id": 778}).status_code == 404
    r = client.get("/stars/778/lightcurve")
    assert r.status_code == 404 and r.json()["detail"]["reason"] == "no TESS data"
    services.analyzer.fail_for.add(779)  # MAST lists data, but no usable light curve
    job = wait_job(client, client.post("/analyze", json={"tic_id": 779}).json()["job_id"])
    assert job["status"] == "failed"
    assert client.get("/stars/779/lightcurve").json()["detail"]["reason"] == "no TESS data"
    services.archive.rows[780] = [{"pl_name": "Bright b", "hostname": "Bright", "sy_tmag": 2.1}]
    client.get("/stars/780/lab")  # caches the archive answer (Tmag 2.1)
    r = client.get("/stars/780/lightcurve")
    assert r.json()["detail"]["reason"] == "too bright for TESS (Tmag < ~4)"
    assert client.get("/stars/0/lightcurve").status_code == 422


def test_no_data_never_replaces_a_stored_curve(storage):
    curve = LightCurve(time_btjd=[1.0], flux=[1.0], binned_from=1)
    storage.put_star_lightcurve(
        StoredLightCurve(tic_id=5, status="stored", stored_at=T, curve=curve)
    )
    from api import analysis

    analysis.record_no_data(storage, 5, T)
    assert storage.get_star_lightcurve(5).status == "stored"
    analysis.record_no_data(storage, 6, T)
    assert storage.get_star_lightcurve(6).status == "no_data"


# backfill: re-read on next analysis, no new search -----------------------------------------


def test_backfill_rereads_lightcurve_without_a_hunt(client, services):
    legacy_result(services, TIC)
    a = services.analyzer
    assert client.get(f"/stars/{TIC}/lab").json()["lightcurve"]["reason_if_not"] == (
        "not analyzed yet"
    )
    r = client.post("/analyze", json={"tic_id": TIC})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cached"] is True and body["result"]["tic_id"] == TIC and body["job_id"] is None
    job = wait_job(client, body["lightcurve_job_id"])
    assert job["status"] == "done", job
    names = [s["name"] for s in job["steps"]]
    assert "re-reading the light curve (no new search)" in names
    assert names[-1].startswith("stored light curve (")
    assert a.hunt_calls == [] and a.lightcurve_calls == [TIC]
    lc = client.get(f"/stars/{TIC}/lightcurve")
    assert lc.status_code == 200 and lc.json()["data_marker"] == body["result"]["data_marker"]
    assert client.get(f"/stars/{TIC}/lab").json()["lightcurve"]["available"] is True
    again = client.post("/analyze", json={"tic_id": TIC}).json()
    assert again["lightcurve_job_id"] is None and a.lightcurve_calls == [TIC]


def test_backfill_failure_leaves_the_result_alone(client, services):
    rec = legacy_result(services, TIC)
    services.analyzer.lightcurve_fail_for.add(TIC)
    body = client.post("/analyze", json={"tic_id": TIC}).json()
    job = wait_job(client, body["lightcurve_job_id"])
    assert job["status"] == "failed" and job["error"].startswith("could not re-read")
    assert services.storage.get_star_analysis(TIC) == rec
    assert client.get(f"/stars/{TIC}/lightcurve").status_code == 404


def test_no_backfill_while_mast_is_down(client, services):
    legacy_result(services, TIC)
    rec = services.storage.get_star_analysis(TIC)
    services.storage.touch_star_analysis(TIC, rec.marker_checked_at - timedelta(hours=7))
    services.analyzer.marker_down = True
    body = client.post("/analyze", json={"tic_id": TIC}).json()
    assert body["note"] and body["lightcurve_job_id"] is None


def test_precompute_backfills_skipped_stars(services):
    storage, a = services.storage, services.analyzer
    legacy_result(services, 1001)
    a.markers[1002] = None
    s = precompute.run(storage, a, [1001, 1002, 1003])
    assert s.skipped == [1001] and s.lightcurves_reread == [1001] and a.hunt_calls == [1003]
    assert s.no_data == [1002] and storage.get_star_lightcurve(1002).status == "no_data"
    assert storage.get_star_lightcurve(1001).status == "stored"
    assert storage.get_star_lightcurve(1003).status == "stored"
    again = precompute.run(storage, a, [1001, 1003])
    assert again.skipped == [1001, 1003] and again.lightcurves_reread == []


# GET /stars/{tic}/lab ------------------------------------------------------------------------


def test_lab_for_wasp_121(make_client, services, spectra_file):
    services.spectra = SpectraIndex(str(spectra_file))
    client = make_client()
    before = client.get(f"/stars/{WASP_121}/lab")
    assert before.status_code == 200, before.text
    b = before.json()
    assert b["tic"] == WASP_121 and b["name"] == "WASP-121"
    assert b["lightcurve"] == {
        "available": False, "reason_if_not": "not analyzed yet", "n_points": None, "sectors": []
    }  # fmt: skip
    assert b["signals"] == [] and b["analyzed_at"] is None
    assert b["mass"] == 1.33 and b["distance"] == 269.898 and b["teff"] == 6628.0
    assert b["known_planets"] == [
        {"name": "WASP-121 b", "period_d": 1.27492504, "a_au": 0.02571,
         "radius": 19.52604438, "mass": 371.85923619, "mass_kind": "Mass"}
    ]  # fmt: skip
    assert b["spectra"] == {
        "gaia_xp": True, "abundances": True, "planet_atmospheres": ["wasp-121-b"],
        "index_available": True,
    }  # fmt: skip
    analyze(client, WASP_121)
    after = client.get(f"/stars/{WASP_121}/lab").json()
    assert after["lightcurve"]["available"] is True and after["lightcurve"]["reason_if_not"] is None
    assert 0 < after["lightcurve"]["n_points"] <= 3000 and after["lightcurve"]["sectors"]
    stored = services.storage.get_star_analysis(WASP_121).analysis
    assert [s["id"] for s in after["signals"]] == [s.id for s in stored.signals]
    assert set(after["signals"][0]) >= {"period_days", "t0_btjd", "duration_hours", "depth_ppm"}
    assert "folded" not in after["signals"][0]
    assert after["analyzed_at"] is not None


def test_lab_for_any_star(client, services):
    body = client.get("/stars/123456/lab").json()
    assert body["tic"] == 123456 and body["name"] is None and body["known_planets"] == []
    assert body["lightcurve"]["reason_if_not"] == "not analyzed yet"
    assert body["spectra"] == {
        "gaia_xp": False, "abundances": False, "planet_atmospheres": [], "index_available": False
    }  # fmt: skip
    assert client.get("/stars/abc/lab").status_code == 422
    assert client.get("/stars/10000000000/lab").status_code == 422


def test_known_planets_are_cached(make_client, services):
    client = make_client(known_planets_ttl_s=3600)
    archive = services.archive
    client.get(f"/stars/{WASP_121}/lab")
    client.get(f"/stars/{WASP_121}/lab")
    assert archive.calls == [WASP_121]
    client.get("/stars/5/lab")
    client.get("/stars/5/lab")  # "hosts nothing" is cached too
    assert archive.calls == [WASP_121, 5]
    host = services.storage.get_known_planets(WASP_121)
    services.storage.put_known_planets(host.model_copy(update={"fetched_at": T}))  # stale
    archive.down = True
    body = client.get(f"/stars/{WASP_121}/lab").json()
    assert body["known_planets"][0]["name"] == "WASP-121 b"
    assert body["known_planets_note"] == lab.NOTE_ARCHIVE_STALE
    body = client.get("/stars/6/lab").json()
    assert body["known_planets"] == [] and body["known_planets_note"] == lab.NOTE_ARCHIVE_DOWN
    archive.down = False
    body = client.get(f"/stars/{WASP_121}/lab").json()
    assert body["known_planets_note"] is None
    assert services.storage.get_known_planets(WASP_121).fetched_at > T


def test_archive_text_is_kept_honest(client, services):
    services.archive.rows[9] = [{"pl_name": "X b", "hostname": "The new planet host"}]
    body = client.get("/stars/9/lab").json()  # HonestClient scans the response
    assert body["name"] == "The planet candidate host"


# the SPECTRA index ---------------------------------------------------------------------------


def test_spectra_index_tolerates_missing_and_bad_files(tmp_path, spectra_file):
    assert SpectraIndex(None).for_star(WASP_121).index_available is False
    assert SpectraIndex(str(tmp_path / "nope.json")).for_star(WASP_121).index_available is False
    bad = tmp_path / "bad.json"
    bad.write_text("[not json")
    assert SpectraIndex(str(bad)).for_star(1).index_available is False
    idx = SpectraIndex(str(spectra_file))
    only_xp = idx.for_star(42)
    assert only_xp.gaia_xp and not only_xp.abundances and only_xp.planet_atmospheres == []
    assert idx.star_name(WASP_121) == "WASP-121"
    spectra_file.write_text("{broken")  # a later bad read keeps the last good copy
    idx._read_at = -1e9
    assert idx.for_star(WASP_121).gaia_xp is True


def test_spectra_index_from_url(spectra_file):
    import http.server
    import threading

    body = spectra_file.read_bytes()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}/data/spectra/index.json"
        got = SpectraIndex(url).for_star(WASP_121)
        assert got.index_available and got.planet_atmospheres == ["wasp-121-b"]
    finally:
        srv.shutdown()


def test_lab_mass_prefers_archive_then_tic(client, services):
    services.analyzer.star_extra[4242] = {"mass_msun": 0.81, "distance_pc": 12.5, "tmag": 9.0}
    services.analyzer.star_extra[WASP_121] = {"mass_msun": 1.36}  # TIC's value
    analyze(client, 4242)
    analyze(client, WASP_121)
    lone = client.get("/stars/4242/lab").json()  # not an archive host: TIC's mass
    assert lone["mass"] == 0.81 and lone["distance"] == 12.5 and lone["tmag"] == 9.0
    assert client.get(f"/stars/{WASP_121}/lab").json()["mass"] == 1.33  # pscomppars st_mass


def test_analyze_accepts_and_ignores_target(client, services):
    r = client.post("/analyze", json={"tic_id": TIC, "target": {"from": "lab", "x": [1]}})
    assert r.status_code == 202, r.text
    wait_job(client, r.json()["job_id"])
    r = client.post("/analyze", json={"name": "WASP-18", "target": "WASP-18 b"})
    assert r.status_code == 202 and "target" not in r.json()
    assert client.post("/analyze", json={"target": "x"}).status_code == 422  # still needs a star
    assert client.post("/analyze", json={"tic_id": TIC, "other": 1}).status_code == 422
