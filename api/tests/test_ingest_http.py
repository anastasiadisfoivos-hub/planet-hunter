"""The search server's HTTP side: chunked ingest, the pixel queue and its results, the
heartbeat (runner block, per-queue coverage) and the search label. SQLite and Postgres."""

from __future__ import annotations

import json
from datetime import timedelta

import api.routes.monitor as monitor_routes
from api.fakes.finder import FakePixelVetter
from api.finder import normalize_vet
from tests.test_finder import candidate
from tests.test_monitor import AUTH, NIGHT, TOKEN, star


def chunk(**over) -> dict:
    body = {"run_id": "oracle-20260927", "run_started_at": "2026-09-27T00:15:00Z"}
    body.update(over)
    return body


def test_ingest_is_token_only(make_client):
    assert make_client().post("/finder/ingest", json=chunk()).status_code == 404
    on = make_client(ingest_token=TOKEN)
    assert on.post("/finder/ingest", json=chunk()).status_code == 403
    assert on.get("/finder/pixel-queue").status_code == 403
    assert on.post("/monitor/heartbeat", json={"state": "idle"}).status_code == 403
    assert "/finder/ingest" not in on.get("/openapi.json").text


def test_chunks_store_candidates_and_monitor_and_final_closes_the_run(make_client, storage):
    c = make_client(ingest_token=TOKEN)
    first = c.post("/finder/ingest", headers=AUTH, json=chunk(
        candidates=[{"id": "100_1", "candidate": candidate(100)},
                    {"id": "200_s1", "candidate": candidate(200, period_d=None)},
                    {"id": "bad id", "candidate": candidate(300)},
                    {"id": "300_1", "candidate": {"tic": 300}}],
        monitor=[star(100, 1), {"tic": "x"}],
        summary={"funnel": {"stars_searched": 2, "candidates": 2}},
    ))  # fmt: skip
    assert first.status_code == 200, first.text
    out = first.json()
    assert out["candidates"] == {"created": 2, "updated": 0, "unchanged": 0}
    assert [i["file"] for i in out["invalid"]] == ["bad id", "300_1", "monitor[1] tic x"]
    assert out["summary_stored"] and out["monitor_stars"] == 1 and not out["final"]
    assert storage.get_monitor_run("oracle-20260927")["state"] == "running"

    last = chunk(candidates=[{"id": "100_1", "candidate": candidate(100)}], monitor=[star(101, 2)])
    again = c.post("/finder/ingest", headers=AUTH, json={**last, "final": True}).json()
    assert again["candidates"]["unchanged"] == 1 and again["final"]
    assert storage.get_monitor_run("oracle-20260927")["state"] == "done"
    assert {i["id"] for i in c.get("/finder/candidates").json()["items"]} == {"100_1", "200_s1"}
    assert c.get("/finder/funnel").json()["sweep_at"] is not None
    assert c.get("/monitor/now").json()["star"]["tic"] in (100, 101)


def test_chunk_dismisses_from_its_own_known_lists(make_client):
    c = make_client(ingest_token=TOKEN)
    known = candidate(100, known_lists=[{"list": "toi", "name": "TOI-9.01"}])
    out = c.post("/finder/ingest", headers=AUTH,
                 json=chunk(candidates=[{"id": "100_1", "candidate": known}])).json()  # fmt: skip
    assert [d["id"] for d in out["dismissed"]] == ["100_1"]


def test_chunk_size_limit(make_client):
    c = make_client(ingest_token=TOKEN, ingest_max_bytes=2000)
    big = chunk(monitor=[star(100, 1, lightcurve={"t": [1.0] * 300, "f": [1.0] * 300})])
    assert c.post("/finder/ingest", headers=AUTH, json=big).status_code == 413
    assert c.post("/finder/ingest", headers=AUTH, content=b"{nope",
                  ).status_code == 422  # fmt: skip


def test_pixel_queue_and_results(make_client):
    c = make_client(ingest_token=TOKEN)
    c.post("/finder/ingest", headers=AUTH, json=chunk(candidates=[
        {"id": "100_1", "candidate": candidate(100)},
        {"id": "200_s1", "candidate": candidate(200, period_d=None)},
    ]))  # fmt: skip
    items = c.get("/finder/pixel-queue", headers=AUTH).json()["items"]
    assert [i["id"] for i in items] == ["100_1"]  # a single dip is never pixel-checked
    key = items[0]["ephemeris_key"]
    assert items[0]["candidate"]["tic"] == 100

    url = "/finder/candidates/100_1/pixel-vet"
    assert c.post(url, headers=AUTH, json={"ephemeris_key": "old"}).status_code == 409
    assert c.post(url, headers=AUTH, json={"ephemeris_key": key}).status_code == 422
    assert c.post("/finder/candidates/9_1/pixel-vet", headers=AUTH,
                  json={"ephemeris_key": key, "error": "x"}).status_code == 404  # fmt: skip
    failed = c.post(url, headers=AUTH, json={"ephemeris_key": key, "error": "TESScut timed out"})
    assert failed.json() == {"id": "100_1", "state": "failed"}
    assert [i["id"] for i in c.get("/finder/pixel-queue", headers=AUTH).json()["items"]] == [
        "100_1"
    ]

    vet = normalize_vet(FakePixelVetter().vet(items[0]["candidate"]))
    done = c.post(url, headers=AUTH, json={"ephemeris_key": key, "vet": vet})
    assert done.json() == {"id": "100_1", "state": "done"}
    assert c.get("/finder/pixel-queue", headers=AUTH).json()["items"] == []
    report = c.get("/finder/candidates/100_1").json()
    assert report["pixel_vet"]["verdict"] == vet["verdict"]
    maybe = {"ephemeris_key": key, "vet": {"verdict": "maybe"}}
    assert c.post(url, headers=AUTH, json=maybe).status_code == 422


def test_heartbeat_runner_block_and_queue_coverage(make_client, monkeypatch):
    now = [NIGHT]
    monkeypatch.setattr(monitor_routes, "utcnow", lambda: now[0])
    c = make_client(ingest_token=TOKEN, runner_stale_s=900)
    assert c.get("/monitor/coverage/queues").json() == {"updated_at": None, "queues": {}}
    beat = {"state": "idle", "next_run_at": "2026-09-27T00:15:00Z",
            "queues": {"fast": {"done": 2300, "listed": 50000, "running": 0},
                       "deep": {"done": 500, "listed": None}}}  # fmt: skip
    assert c.post("/monitor/heartbeat", headers=AUTH, json=beat).status_code == 200
    runner = c.get("/monitor/now").json()["runner"]
    assert runner["state"] == "idle" and runner["responding"] is True
    assert runner["next_run_at"].startswith("2026-09-27T00:15")
    q = c.get("/monitor/coverage/queues").json()
    assert q["queues"]["fast"] == {"done": 2300, "listed": 50000, "running": 0}
    assert q["queues"]["deep"] == {"done": 500, "listed": None, "running": 0}

    now[0] += timedelta(minutes=16)
    assert c.get("/monitor/now").json()["runner"]["responding"] is False

    # A beat while searching keeps that run live, even between stars.
    c.post(
        "/monitor/heartbeat", headers=AUTH, json={"state": "searching", "run_id": "oracle-20260926"}
    )
    now_view = c.get("/monitor/now").json()
    assert now_view["mode"] == "live" and now_view["run_id"] == "oracle-20260926"
    assert now_view["runner"]["responding"] is True
    assert c.post("/monitor/heartbeat", headers=AUTH, json={"state": "asleep"}).status_code == 422
    bad = {"state": "idle", "queues": {"Bad Name": {"done": 1}}}
    assert c.post("/monitor/heartbeat", headers=AUTH, json=bad).status_code == 422


def test_progress_label_shows_on_now_and_in_the_log(make_client, monkeypatch):
    monkeypatch.setattr(monitor_routes, "utcnow", lambda: NIGHT + timedelta(hours=1))
    c = make_client(ingest_token=TOKEN)
    body = {"run_id": "oracle-20260926", "shard": 1, "done": 1, "total": 9, "star": star(400, 30),
            "label": "deep"}  # fmt: skip
    assert c.post("/monitor/progress", headers=AUTH, json=body).status_code == 200
    now = c.get("/monitor/now").json()
    assert now["mode"] == "live" and now["label"] == "deep" and now["star"]["label"] == "deep"
    item = c.get("/monitor/log?detail=true").json()["items"][0]
    assert item["record"]["label"] == "deep"
    bad = {**body, "label": "Deep Pass"}
    assert c.post("/monitor/progress", headers=AUTH, json=bad).status_code == 422
    assert json.dumps(now)  # serialisable
