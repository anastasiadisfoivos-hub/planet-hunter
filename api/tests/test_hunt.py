from __future__ import annotations

import threading
from datetime import UTC, datetime

from api.app import create_app
from api.contract import Discovery
from api.fakes.tess import STEPS
from api.models import JobRecord
from tests.conftest import TIC, HonestClient, player, wait_job, wait_until


def test_hunt_runs_and_reports_steps(client, alice):
    r = client.post("/hunt", json={"star": {"tic_id": TIC}}, headers=alice)
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["job_id"], alice)
    assert job["status"] == "done"
    assert job["error"] is None
    names = [s["name"] for s in job["steps"]]
    assert names[:2] == ["queued", "started"]
    assert names[2 : 2 + len(STEPS)] == list(STEPS)
    assert names[-1].startswith("stored")
    results = [Discovery.model_validate(d) for d in job["result"]]
    assert results and all(d.source == "tess" for d in results)
    assert job["started_at"] and job["finished_at"]
    mine = {d["id"] for d in client.get("/discoveries", headers=alice).json()["items"]}
    assert mine == {d.id for d in results}


def test_hunt_validation(client, alice):
    assert client.post("/hunt", json={"star": {"tic_id": "x"}}, headers=alice).status_code == 422
    assert client.post("/hunt", json={}, headers=alice).status_code == 422
    assert client.post("/hunt", json={"star": {"tic_id": 1}}).status_code == 400


def test_jobs_are_private(client, alice, bob):
    job_id = client.post("/hunt", json={"star": {"tic_id": TIC}}, headers=alice).json()["job_id"]
    assert client.get(f"/jobs/{job_id}", headers=bob).status_code == 404
    assert client.get("/jobs/nope", headers=alice).status_code == 404


def test_at_most_two_hunts_at_once(make_client, services):
    hunter = services.hunter
    hunter.gate = threading.Event()
    client = make_client()
    players = [player() for _ in range(4)]
    jobs = [
        client.post("/hunt", json={"star": {"tic_id": 100 + i}}, headers=p).json()["job_id"]
        for i, p in enumerate(players)
    ]

    def status(i):
        return client.get(f"/jobs/{jobs[i]}", headers=players[i]).json()

    wait_until(lambda: hunter.running == 2)
    views = [status(i) for i in range(4)]
    assert [v["status"] for v in views] == ["running", "running", "queued", "queued"]
    assert [v["queue_position"] for v in views] == [None, None, 1, 2]

    hunter.gate.set()
    for i, p in enumerate(players):
        assert wait_job(client, jobs[i], p)["status"] == "done"
    assert hunter.max_running_seen == 2


def test_pending_hunt_cap(make_client, alice, services):
    services.hunter.gate = threading.Event()
    client = make_client(max_pending_jobs_per_player=2)
    for tic in (1, 2):
        r = client.post("/hunt", json={"star": {"tic_id": tic}}, headers=alice)
        assert r.status_code == 202
    assert client.post("/hunt", json={"star": {"tic_id": 3}}, headers=alice).status_code == 429
    assert client.post("/traps", json={"star": {"tic_id": 3}}, headers=alice).status_code == 429
    services.hunter.gate.set()


def test_failed_hunt(client, alice, services):
    services.hunter.fail_for.add(TIC)
    job_id = client.post("/hunt", json={"star": {"tic_id": TIC}}, headers=alice).json()["job_id"]
    job = wait_job(client, job_id, alice)
    assert job["status"] == "failed"
    assert "no usable light curve" in job["error"]
    assert job["result"] is None


def test_hunt_timeout(make_client, alice, services):
    services.hunter.gate = threading.Event()
    client = make_client(hunt_timeout_s=0.05)
    job_id = client.post("/hunt", json={"star": {"tic_id": TIC}}, headers=alice).json()["job_id"]
    job = wait_job(client, job_id, alice)
    services.hunter.gate.set()
    assert job["status"] == "failed" and job["error"] == "hunt timed out"


def test_rehunt_updates_instead_of_duplicating(client, alice, services):
    first = wait_job(
        client,
        client.post("/hunt", json={"star": {"tic_id": TIC}}, headers=alice).json()["job_id"],
        alice,
    )
    services.hunter.markers[TIC] = "sector-99"  # new data: periods shift slightly
    second = wait_job(
        client,
        client.post("/hunt", json={"star": {"tic_id": TIC}}, headers=alice).json()["job_id"],
        alice,
    )
    first_sigs = {d["id"] for d in first["result"] if ":sig:" in d["id"]}
    second_sigs = {d["id"] for d in second["result"] if ":sig:" in d["id"]}
    assert first_sigs == second_sigs
    updated = [d for d in second["result"] if ":sig:" in d["id"]]
    assert all("updated_at" in d["raw"] for d in updated)
    stored = services.storage.discoveries_with_prefix(f"tess:{TIC}:sig:")
    assert len(stored) == len(first_sigs)
    items = client.get("/discoveries", headers=alice).json()["items"]
    assert len(items) == len({d["id"] for d in items})


def test_restart_fails_unfinished_jobs(services, settings):
    now = datetime.now(UTC)
    services.storage.create_job(
        JobRecord(id="stale", player_id="p", tic_id=1, status="running", created_at=now)
    )
    with HonestClient(create_app(settings, services)):
        job = services.storage.get_job("stale")
    assert job.status == "failed" and "restart" in job.error
