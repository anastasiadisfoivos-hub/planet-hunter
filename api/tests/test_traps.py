from __future__ import annotations

import time
from datetime import datetime

import pytest

from api.contract import Discovery
from api.geometry import angular_distance_deg
from tests.conftest import SKY, TIC, wait_job


def test_sky_trap_gets_instant_catches(client, alice, services):
    r = client.post("/traps", json={"sphere": SKY}, headers=alice)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trap"]["kind"] == "sky"
    assert body["trap"]["sphere"] == SKY
    assert body["sweep"]["status"] == "ok"
    assert body["job_id"] is None
    catches = [Discovery.model_validate(d) for d in body["catches"]]
    assert catches, "the fake sky patch should have objects"
    since = datetime.fromisoformat(body["sweep"]["since"])
    until = datetime.fromisoformat(body["sweep"]["until"])
    assert (until - since).days == 7
    for d in catches:
        assert d.source == "rubin"
        assert d.id.startswith(("rubin:obj:", "rubin:ss:"))
        assert since <= d.detected_at < until
        dist = angular_distance_deg(d.ra_deg, d.dec_deg, SKY["ra_deg"], SKY["dec_deg"])
        assert dist <= SKY["radius_deg"]
    assert body["trap"]["last_checked_at"] == body["sweep"]["until"]

    mine = client.get("/discoveries", headers=alice).json()["items"]
    assert {d["id"] for d in mine} == {d.id for d in catches}


def test_star_trap_queues_a_hunt(client, alice, services):
    r = client.post("/traps", json={"star": {"tic_id": TIC}}, headers=alice)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sweep"]["status"] == "queued"
    assert body["catches"] == []
    job = wait_job(client, body["job_id"], alice)
    assert job["status"] == "done"
    assert job["trap_id"] == body["trap"]["id"]
    assert job["result"]
    assert all(d["id"].startswith(f"tess:{TIC}:") for d in job["result"])

    trap = client.get("/traps", headers=alice).json()[0]
    assert trap["last_tess_marker"] == services.hunter.latest_data_marker(TIC)
    assert trap["star"] == {"tic_id": TIC}


def test_star_trap_accepts_digit_string(client, alice):
    r = client.post("/traps", json={"star": {"tic_id": " 123456 "}}, headers=alice)
    assert r.status_code == 201
    assert r.json()["trap"]["star"] == {"tic_id": 123456}


@pytest.mark.parametrize(
    "sphere",
    [
        {"ra_deg": 0, "dec_deg": 0, "radius_deg": 0.05},
        {"ra_deg": 359.999, "dec_deg": 90, "radius_deg": 10},
        {"ra_deg": 10, "dec_deg": -90, "radius_deg": 1},
    ],
)
def test_sphere_edges_accepted(client, alice, sphere):
    assert client.post("/traps", json={"sphere": sphere}, headers=alice).status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        {"sphere": {"ra_deg": 10, "dec_deg": 0, "radius_deg": 0.049}},
        {"sphere": {"ra_deg": 10, "dec_deg": 0, "radius_deg": 10.01}},
        {"sphere": {"ra_deg": 10, "dec_deg": 90.1, "radius_deg": 1}},
        {"sphere": {"ra_deg": 10, "dec_deg": -90.1, "radius_deg": 1}},
        {"sphere": {"ra_deg": 360, "dec_deg": 0, "radius_deg": 1}},
        {"sphere": {"ra_deg": -0.1, "dec_deg": 0, "radius_deg": 1}},
        {"sphere": {"ra_deg": "nan", "dec_deg": 0, "radius_deg": 1}},
        {"sphere": {"ra_deg": 10, "dec_deg": 0}},
        {"sphere": {"ra_deg": 10, "dec_deg": 0, "radius_deg": 1, "extra": 1}},
        {"star": {"tic_id": "abc"}},
        {"star": {"tic_id": 0}},
        {"star": {"tic_id": -5}},
        {"star": {"tic_id": True}},
        {"star": {"tic_id": 1.5}},
        {"sphere": {"ra_deg": 10, "dec_deg": 0, "radius_deg": 1}, "star": {"tic_id": 1}},
        {},
    ],
)
def test_invalid_traps_rejected(client, alice, payload):
    r = client.post("/traps", json=payload, headers=alice)
    assert r.status_code == 422, r.text
    assert client.get("/traps", headers=alice).json() == []


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Player-Id": "not-a-uuid"}, {"X-Player-Id": ""}],
)
def test_player_id_required(client, headers):
    for method, path in [("get", "/traps"), ("get", "/discoveries"), ("delete", "/traps/x")]:
        assert getattr(client, method)(path, headers=headers).status_code == 400
    r = client.post("/traps", json={"sphere": SKY}, headers=headers)
    assert r.status_code == 400


def test_list_traps_only_mine(client, alice, bob):
    client.post("/traps", json={"sphere": SKY}, headers=alice)
    client.post("/traps", json={"star": {"tic_id": TIC}}, headers=alice)
    client.post("/traps", json={"sphere": SKY}, headers=bob)
    mine = client.get("/traps", headers=alice).json()
    assert len(mine) == 2
    assert {t["kind"] for t in mine} == {"sky", "star"}
    assert all("player_id" not in t for t in mine)
    assert len(client.get("/traps", headers=bob).json()) == 1


def test_delete_trap(client, alice, bob):
    created = client.post("/traps", json={"sphere": SKY}, headers=alice).json()
    trap_id = created["trap"]["id"]
    assert client.delete(f"/traps/{trap_id}", headers=bob).status_code == 404
    assert client.delete(f"/traps/{trap_id}", headers=alice).status_code == 204
    assert client.delete(f"/traps/{trap_id}", headers=alice).status_code == 404
    assert client.get("/traps", headers=alice).json() == []
    # Catches stay after the trap is gone.
    kept = client.get("/discoveries", headers=alice).json()["items"]
    assert len(kept) == len(created["catches"])


def test_trap_cap(make_client, alice):
    client = make_client(max_traps_per_player=2)
    for _ in range(2):
        assert client.post("/traps", json={"sphere": SKY}, headers=alice).status_code == 201
    assert client.post("/traps", json={"sphere": SKY}, headers=alice).status_code == 409


def test_sweep_timeout_keeps_trap_and_retries_later(make_client, alice, services):
    class Slow:
        def alerts_in_sphere(self, sphere, since, until):
            time.sleep(0.5)
            return []

    services.alerts = Slow()
    client = make_client(sweep_timeout_s=0.05)
    body = client.post("/traps", json={"sphere": SKY}, headers=alice).json()
    assert body["sweep"]["status"] == "timeout"
    assert body["catches"] == []
    # The nightly check will cover the whole missed window.
    assert body["trap"]["last_checked_at"] == body["sweep"]["since"]


def test_sweep_error_is_reported(make_client, alice, services):
    class Broken:
        def alerts_in_sphere(self, sphere, since, until):
            raise ConnectionError("broker down")

    services.alerts = Broken()
    body = make_client().post("/traps", json={"sphere": SKY}, headers=alice).json()
    assert body["sweep"]["status"] == "error"
    assert body["trap"]["id"]


def test_sweep_drops_ids_that_break_conventions(make_client, alice, services):
    real = services.alerts

    class Mixed:
        def alerts_in_sphere(self, sphere, since, until):
            found = real.alerts_in_sphere(sphere, since, until)
            bad = found[0].model_copy(update={"id": "rubin:alert:123"})
            return [bad, *found]

    services.alerts = Mixed()
    body = make_client().post("/traps", json={"sphere": SKY}, headers=alice).json()
    assert body["sweep"]["rejected"] == 1
    assert "rubin:alert:123" not in {d["id"] for d in body["catches"]}


def test_upstream_text_is_made_honest(make_client, alice, services):
    real = services.alerts

    class Boastful:
        def alerts_in_sphere(self, sphere, since, until):
            d = real.alerts_in_sphere(sphere, since, until)[0]
            return [d.model_copy(update={"explanation": "We discovered a New Planet here!"})]

    services.alerts = Boastful()
    body = make_client().post("/traps", json={"sphere": SKY}, headers=alice).json()
    assert body["catches"][0]["explanation"] == "We detected a planet candidate here!"
