"""POST /analyze, GET /jobs/{id}, GET /stars/{tic}/analysis (deploy/HOSTING.md R1-R5)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from api.app import create_app
from api.fakes.tess import STEPS
from api.models import JobRecord
from tests.conftest import TIC, HonestClient, wait_job, wait_until


def analyze(client, **body):
    return client.post("/analyze", json=body)


def first_run(client, tic=TIC) -> dict:
    r = analyze(client, tic_id=tic)
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    return job


def age_marker_check(storage, tic, hours):
    rec = storage.get_star_analysis(tic)
    storage.touch_star_analysis(tic, rec.marker_checked_at - timedelta(hours=hours))


def test_first_request_queues_a_job_with_progress(client, services):
    r = analyze(client, tic_id=TIC)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and body["tic_id"] == TIC and body["result"] is None
    job = wait_job(client, body["job_id"])
    names = [s["name"] for s in job["steps"]]
    assert names[:2] == ["queued", "started"]
    assert names[2 : 2 + len(STEPS)] == list(STEPS)
    assert names[-1].startswith("stored result (data sector-")
    result = job["result"]
    assert result["tic_id"] == TIC and result["data_marker"].startswith("sector-")
    assert result["analysis"]["summary"].startswith("We searched TESS sector")
    for sig in result["analysis"]["signals"]:
        assert 0 < len(sig["folded"]["phase"]) <= 1000
        assert len(sig["folded"]["phase"]) == len(sig["folded"]["flux"])
    assert services.analyzer.hunt_calls == [TIC]


def test_cache_hit_returns_immediately_without_a_hunt(client, services):
    first = first_run(client)
    hunter = services.analyzer
    hunter.hunt_calls.clear()
    hunter.marker_calls.clear()
    r = analyze(client, tic_id=TIC)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done" and body["cached"] is True and body["job_id"] is None
    assert body["result"] == first["result"]
    assert hunter.hunt_calls == []
    assert hunter.marker_calls == []  # within PH_MARKER_TTL_S: MAST isn't even asked
    stored = client.get(f"/stars/{TIC}/analysis")
    assert stored.status_code == 200 and stored.json()["analysis"] == first["result"]["analysis"]


def test_same_marker_after_ttl_asks_mast_once_and_serves_stored(client, services):
    first_run(client)
    age_marker_check(services.storage, TIC, hours=7)
    hunter = services.analyzer
    hunter.hunt_calls.clear()
    hunter.marker_calls.clear()
    r = analyze(client, tic_id=TIC)
    assert r.status_code == 200 and r.json()["cached"] is True
    assert hunter.marker_calls == [TIC] and hunter.hunt_calls == []
    checked = datetime.fromisoformat(r.json()["result"]["marker_checked_at"])
    assert datetime.now(UTC) - checked < timedelta(minutes=1)  # touched
    analyze(client, tic_id=TIC)
    assert hunter.marker_calls == [TIC]  # fresh again


def test_marker_change_rehunts_once(client, services):
    first = first_run(client)
    hunter = services.analyzer
    hunter.markers[TIC] = "sector-99"
    age_marker_check(services.storage, TIC, hours=7)
    hunter.hunt_calls.clear()
    r = analyze(client, tic_id=TIC)
    assert r.status_code == 202
    job = wait_job(client, r.json()["job_id"])
    assert job["result"]["data_marker"] == "sector-99"
    assert job["result"]["analyzed_at"] > first["result"]["analyzed_at"]
    assert hunter.hunt_calls == [TIC]
    # The new result is now the stored one; asking again is a cache hit.
    again = analyze(client, tic_id=TIC)
    assert again.status_code == 200 and again.json()["result"]["data_marker"] == "sector-99"
    assert hunter.hunt_calls == [TIC]


def test_concurrent_requests_for_one_star_share_one_hunt(make_client, services):
    hunter = services.analyzer
    hunter.gate = threading.Event()
    client = make_client()
    with ThreadPoolExecutor(8) as pool:
        responses = list(pool.map(lambda _: analyze(client, tic_id=TIC), range(8)))
    assert {r.status_code for r in responses} == {202}
    assert len({r.json()["job_id"] for r in responses}) == 1
    hunter.gate.set()
    job = wait_job(client, responses[0].json()["job_id"])
    assert job["status"] == "done"
    assert hunter.hunt_calls == [TIC]
    assert analyze(client, tic_id=TIC).status_code == 200


def test_at_most_two_analyses_at_once(make_client, services):
    hunter = services.analyzer
    hunter.gate = threading.Event()
    client = make_client()
    jobs = [analyze(client, tic_id=100 + i).json()["job_id"] for i in range(4)]
    wait_until(lambda: hunter.running == 2)
    views = [client.get(f"/jobs/{j}").json() for j in jobs]
    assert [v["status"] for v in views] == ["running", "running", "queued", "queued"]
    assert [v["queue_position"] for v in views] == [None, None, 1, 2]
    hunter.gate.set()
    for j in jobs:
        assert wait_job(client, j)["status"] == "done"
    assert hunter.max_running_seen == 2


def test_queue_full_is_503(make_client, services):
    services.analyzer.gate = threading.Event()
    client = make_client(max_queued_jobs=2)
    assert analyze(client, tic_id=1).status_code == 202
    assert analyze(client, tic_id=2).status_code == 202
    r = analyze(client, tic_id=3)
    assert r.status_code == 503 and r.headers["Retry-After"]
    assert analyze(client, tic_id=1).status_code == 202  # same star: joins its job
    services.analyzer.gate.set()


def test_mast_down_serves_stored_with_note(client, services):
    first_run(client)
    age_marker_check(services.storage, TIC, hours=7)
    services.analyzer.marker_down = True
    services.analyzer.hunt_calls.clear()
    r = analyze(client, tic_id=TIC)
    assert r.status_code == 200
    assert r.json()["note"] == "data check unavailable: showing stored result"
    assert services.analyzer.hunt_calls == []


def test_mast_down_without_stored_result_still_analyzes(client, services):
    services.analyzer.marker_down = True
    r = analyze(client, tic_id=TIC)
    assert r.status_code == 202
    job = wait_job(client, r.json()["job_id"])
    assert job["status"] == "done" and job["result"]["data_marker"] is None
    services.analyzer.marker_down = False
    # Unknown marker: the next check (once the TTL passes) re-analyzes on real data.
    age_marker_check(services.storage, TIC, hours=7)
    assert analyze(client, tic_id=TIC).status_code == 202


def test_no_tess_data_is_404(client, services):
    services.analyzer.markers[42] = None
    r = analyze(client, tic_id=42)
    assert r.status_code == 404 and "no TESS light curve" in r.json()["detail"]
    assert services.analyzer.hunt_calls == []


def test_none_marker_with_stored_result_serves_it(client, services):
    first_run(client)
    age_marker_check(services.storage, TIC, hours=7)
    services.analyzer.markers[TIC] = None
    services.analyzer.hunt_calls.clear()
    assert analyze(client, tic_id=TIC).status_code == 200
    assert services.analyzer.hunt_calls == []


def test_failed_analysis(client, services):
    services.analyzer.fail_for.add(TIC)
    job = wait_job(client, analyze(client, tic_id=TIC).json()["job_id"])
    assert job["status"] == "failed" and "no usable light curve" in job["error"]
    assert job["result"] is None
    assert client.get(f"/stars/{TIC}/analysis").status_code == 404


def test_timeout(make_client, services):
    services.analyzer.gate = threading.Event()
    client = make_client(hunt_timeout_s=0.05)
    job = wait_job(client, analyze(client, tic_id=TIC).json()["job_id"])
    services.analyzer.gate.set()
    assert job["status"] == "failed" and job["error"] == "analysis timed out"


def test_names(client, services):
    hunter = services.analyzer
    r = analyze(client, name="wasp 18 b")  # a Known system: no catalogue lookup
    assert r.json()["tic_id"] == 100100827 and hunter.resolve_calls == []
    r = analyze(client, name="TIC 12345")
    assert r.json()["tic_id"] == 12345 and hunter.resolve_calls == []
    r = analyze(client, name="Fake Star 777")
    assert r.json()["tic_id"] == 777 and hunter.resolve_calls == ["Fake Star 777"]
    analyze(client, name="fake-star 777")  # remembered: same key
    assert hunter.resolve_calls == ["Fake Star 777"]
    r = analyze(client, name="Nothing Here")
    assert r.status_code == 404 and "No star called" in r.json()["detail"]


def test_validation(client):
    for body in (
        {},
        {"name": "WASP-18", "tic_id": 100100827},
        {"tic_id": 0},
        {"tic_id": "12x"},
        {"tic_id": True},
        {"tic_id": 10**11},
        {"name": ""},
        {"name": "x" * 81},
        {"name": "<script>"},
        {"name": "WASP-18", "extra": 1},
    ):
        assert client.post("/analyze", json=body).status_code == 422, body
    assert client.get("/jobs/nope").status_code == 404
    assert client.get("/stars/0/analysis").status_code == 422
    assert client.get("/stars/123/analysis").status_code == 404


def test_honesty_of_stored_results(client, services):
    services.analyzer.extra_text = " A new planet was discovered here."
    job = first_run(client)
    for sig in job["result"]["analysis"]["signals"]:
        assert sig["explanation"].endswith("A planet candidate was detected here.")


def test_restart_fails_unfinished_jobs(services, settings):
    now = datetime.now(UTC)
    services.storage.create_job(JobRecord(id="stale", tic_id=1, status="running", created_at=now))
    with HonestClient(create_app(settings, services)):
        job = services.storage.get_job("stale")
    assert job.status == "failed" and "restart" in job.error
