"""Live monitor: /monitor/now (live and replay), log, coverage, stats, shard progress posts and
the ingest of a run's monitor/*.json. Every storage-touching test runs on SQLite and Postgres."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import api.routes.monitor as monitor_routes
from api import finder_ingest

TOKEN = "ingest-token-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
NIGHT = datetime(2026, 9, 26, 2, 17, tzinfo=UTC)


def star(tic: int, minutes: int, **over) -> dict:
    rec = {
        "tic": tic,
        "tmag": 10.2,
        "teff": 5600,
        "radius_rsun": 0.95,
        "ra": 84.3,
        "dec": -12.6,
        "sectors": [6, 33],
        "observed_from": "2018-12-15T00:00:00Z",
        "observed_to": "2021-01-13T00:00:00Z",
        "lightcurve": {"t": [1468.3, 1468.4, 1468.5], "f": [1.0, 0.9991, 1.0]},
        "detections": [
            {"t0": 1468.4, "duration_h": 2.1, "depth_ppm": 900.0, "period_d": 3.2,
             "kind": "periodic", "outcome": "candidate", "reason": None},
            {"t0": 1470.1, "duration_h": 5.0, "depth_ppm": 300.0, "period_d": None,
             "kind": "single", "outcome": "rejected", "reason": "odd-even depth mismatch"},
        ],
        "outcome": "candidate",
        "searched_at": (NIGHT + timedelta(minutes=minutes)).isoformat(),
    }  # fmt: skip
    rec.update(over)
    return rec


@pytest.fixture
def at(monkeypatch):
    """Set the server clock the monitor routes read."""
    now = [NIGHT + timedelta(hours=10)]
    monkeypatch.setattr(monitor_routes, "utcnow", lambda: now[0])
    return now


def write_monitor(root: Path, stars: list[dict]) -> Path:
    folder = root / "monitor"
    folder.mkdir(parents=True, exist_ok=True)
    for s in stars:
        (folder / f"{s['tic']}.json").write_text(json.dumps(s))
    return folder


def ingest(storage, root: Path, run_id: str = "18000000001", **kw) -> dict:
    return finder_ingest.ingest(storage, root / "candidates", vetter=None, known=None,
                                run_id=run_id, run_started_at=NIGHT, **kw)  # fmt: skip


def test_empty_monitor(client):
    now = client.get("/monitor/now").json()
    assert now == {"mode": "replay", "run_id": None, "run_started_at": None,
                   "progress": {"done": 0, "total": 0}, "star": None, "next_at": None}  # fmt: skip
    assert client.get("/monitor/log").json() == {"items": []}
    assert client.get("/monitor/coverage").json() == {
        "stars_searched_total": 0, "by_sector": [], "cell_deg": 5, "sky_cells": []
    }  # fmt: skip
    assert client.get("/monitor/stats").json() == {
        "stars_searched": 0, "signals": 0, "candidates": 0, "rejected_by_reason": {},
        "last_run_at": None,
    }  # fmt: skip


def test_replay_cycles_last_nights_stars_by_server_time(client, storage, tmp_path, at):
    write_monitor(tmp_path, [star(300, 2), star(100, 0), star(200, 1)])
    out = ingest(storage, tmp_path)
    assert out["monitor"] == {"run_id": "18000000001", "stars": 3, "pruned_runs": 0}
    at[0] = datetime.fromtimestamp(1_790_000_000 // 60 * 60, UTC)  # a multiple of 20 s
    start = int(at[0].timestamp()) // 20 % 3
    seen = []
    for _ in range(4):
        body = client.get("/monitor/now").json()
        assert body["mode"] == "replay" and body["run_id"] == "18000000001"
        assert body["run_started_at"].startswith("2026-09-26T02:17")
        assert body["progress"] == {"done": 3, "total": 3}
        assert datetime.fromisoformat(body["next_at"]) == at[0] + timedelta(seconds=20)
        seen.append(body["star"]["tic"])
        at[0] += timedelta(seconds=19)
        assert client.get("/monitor/now").json()["star"]["tic"] == seen[-1]  # same slot
        at[0] += timedelta(seconds=1)
    # In search order (searched_at), wrapping around.
    order = [100, 200, 300]
    assert seen == [order[(start + i) % 3] for i in range(4)]
    full = client.get("/monitor/now").json()["star"]
    assert full["lightcurve"]["f"] == [1.0, 0.9991, 1.0] and len(full["detections"]) == 2


def test_live_while_shards_post_then_replay(client, make_client, storage, tmp_path, at):
    live = make_client(ingest_token=TOKEN)
    body = {"run_id": "18000000002", "run_started_at": "2026-09-27T02:17:00Z", "shard": 0,
            "done": 1, "total": 50, "star": star(400, 600)}  # fmt: skip
    r = live.post("/monitor/progress", json=body, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json() == {"run_id": "18000000002", "state": "running",
                        "progress": {"done": 1, "total": 50}}  # fmt: skip
    live.post("/monitor/progress", headers=AUTH,
              json={"run_id": "18000000002", "shard": 1, "done": 3, "total": 40,
                    "star": star(500, 601)})  # fmt: skip
    live.post("/monitor/progress", headers=AUTH,
              json={"run_id": "18000000002", "shard": 0, "done": 2, "total": 50})  # fmt: skip
    now = live.get("/monitor/now").json()
    assert now["mode"] == "live" and now["run_id"] == "18000000002"
    assert now["run_started_at"].startswith("2026-09-27T02:17")
    assert now["progress"] == {"done": 5, "total": 90}  # summed over shards
    assert now["star"]["tic"] == 500 and now["next_at"] is None
    assert [i["tic"] for i in live.get("/monitor/log").json()["items"]] == [500, 400]

    # The shards go quiet (a dead sweep): replay what was searched.
    at[0] += timedelta(minutes=16)
    stale = live.get("/monitor/now").json()
    assert stale["mode"] == "replay" and stale["star"]["tic"] in (400, 500)

    # The ingest loads the whole run and closes it: replay, never live again.
    write_monitor(tmp_path, [star(400, 600), star(500, 601), star(600, 602)])
    ingest(storage, tmp_path, run_id="18000000002")
    at[0] -= timedelta(minutes=16)
    after = live.get("/monitor/now").json()
    # Shards reported 5 done; the ingest found 3 files: the larger count stands.
    assert after["mode"] == "replay" and after["progress"] == {"done": 5, "total": 90}
    late = live.post("/monitor/progress", headers=AUTH,
                     json={"run_id": "18000000002", "shard": 2, "done": 1, "total": 1})  # fmt: skip
    assert late.json()["state"] == "done"
    assert live.get("/monitor/now").json()["mode"] == "replay"


def test_progress_auth_and_validation(make_client):
    off = make_client()
    body = {"run_id": "1", "done": 0, "total": 1}
    assert off.post("/monitor/progress", json=body, headers=AUTH).status_code == 404
    on = make_client(ingest_token=TOKEN)
    assert on.post("/monitor/progress", json=body).status_code == 403
    assert on.post("/monitor/progress", json=body,
                   headers={"Authorization": f"Bearer {TOKEN}x"}).status_code == 403  # fmt: skip
    assert on.post("/monitor/progress", json={**body, "done": 2}, headers=AUTH).status_code == 422
    assert on.post("/monitor/progress", json={**body, "run_id": "a b"},
                   headers=AUTH).status_code == 422  # fmt: skip
    assert on.post("/monitor/progress", json={**body, "star": {"tic": "x"}},
                   headers=AUTH).status_code == 422  # fmt: skip
    assert on.post("/monitor/progress", json={**body, "star": {"tic": 5, "detections": {}}},
                   headers=AUTH).status_code == 422  # fmt: skip
    assert "/monitor/progress" not in on.get("/openapi.json").text


def test_log_coverage_and_stats(client, storage, tmp_path):
    write_monitor(tmp_path, [
        star(100, 0),
        star(200, 1, ra=359.9, dec=89.9, sectors=[33, 60], detections=[], outcome="nothing"),
        star(300, 2, ra=None, dec=None, sectors=[],
             detections=[{"t0": 1.0, "duration_h": 1.0, "depth_ppm": 50.0, "period_d": 1.5,
                          "kind": "periodic", "outcome": "rejected",
                          "reason": "odd-even depth mismatch"},
                         {"t0": 2.0, "duration_h": 1.0, "depth_ppm": 70.0, "period_d": 2.5,
                          "kind": "periodic", "outcome": "known", "reason": None}]),
    ])  # fmt: skip
    ingest(storage, tmp_path)
    log = client.get("/monitor/log?limit=2").json()["items"]
    assert [(i["tic"], i["outcome"], i["detections_count"]) for i in log] == [
        (300, "candidate", 2), (200, "nothing", 0)
    ]  # fmt: skip
    assert log[0]["searched_at"].startswith("2026-09-26T02:19")
    assert client.get("/monitor/log?limit=0").status_code == 422
    assert client.get("/monitor/log?limit=201").status_code == 422

    cov = client.get("/monitor/coverage").json()
    assert cov["stars_searched_total"] == 3
    assert cov["by_sector"] == [{"sector": 6, "stars": 1}, {"sector": 33, "stars": 2},
                                {"sector": 60, "stars": 1}]  # fmt: skip
    assert cov["sky_cells"] == [
        {"ra": 82.5, "dec": -12.5, "stars": 1},  # 84.3, -12.6
        {"ra": 357.5, "dec": 87.5, "stars": 1},  # 359.9, 89.9
    ]  # fmt: skip

    stats = client.get("/monitor/stats").json()
    assert stats == {
        "stars_searched": 3, "signals": 4, "candidates": 1,
        "rejected_by_reason": {"known": 1, "odd-even depth mismatch": 2},
        "last_run_at": stats["last_run_at"],
    }  # fmt: skip
    assert stats["last_run_at"].startswith("2026-09-26T02:17")


def test_ingest_reports_bad_monitor_files_and_prunes(storage, tmp_path, capsys):
    folder = write_monitor(tmp_path, [star(100, 0)])
    (folder / "200.json").write_text(json.dumps(star(201, 1)))  # tic != file name
    (folder / "300.json").write_text("{nope")
    (folder / "index.json").write_text("{}")  # not <tic>.json: ignored
    out = ingest(storage, tmp_path)
    assert sorted(i["file"] for i in out["invalid"]) == ["monitor/200.json", "monitor/300.json"]
    assert out["monitor"]["stars"] == 1
    for n in range(3, 7):
        ingest(storage, tmp_path, run_id=f"run-{n}", keep_runs=2)
    assert storage.get_monitor_run("run-6") and storage.get_monitor_run("run-5")
    assert storage.get_monitor_run("run-4") is None
    assert storage.get_monitor_run("18000000001") is None

    db = str(tmp_path / "m.db")
    args = ["--dir", str(tmp_path / "candidates"), "--db", db, "--run-id", "42"]
    code = finder_ingest.main([*args, "--run-started-at", "2026-09-26T02:17:00Z"])
    assert code == 1  # the bad monitor files
    assert json.loads(capsys.readouterr().out)["monitor"]["run_id"] == "42"
    with pytest.raises(SystemExit):
        finder_ingest.main(["--dir", str(tmp_path), "--db", db, "--run-id", "a b"])


def test_monitor_text_follows_the_honesty_rule(client, storage, tmp_path):
    write_monitor(tmp_path, [star(100, 0, outcome="new planet discovered", detections=[
        {"t0": 1.0, "duration_h": 1.0, "depth_ppm": 50.0, "period_d": None, "kind": "single",
         "outcome": "rejected", "reason": "not a new planet"}])])  # fmt: skip
    ingest(storage, tmp_path)
    # HonestClient fails the test on any violation.
    assert client.get("/monitor/now").json()["star"]["outcome"] == "planet candidate detected"
    assert client.get("/monitor/log").json()["items"][0]["outcome"] == "planet candidate detected"
    assert client.get("/monitor/stats").json()["rejected_by_reason"] == {
        "not a planet candidate": 1
    }  # fmt: skip
