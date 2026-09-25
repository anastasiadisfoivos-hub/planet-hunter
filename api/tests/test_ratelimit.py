from __future__ import annotations

from api.ratelimit import RateLimiter
from tests.conftest import SKY, TIC, player


def test_trap_create_limit_per_player(make_client, alice, bob, clock):
    client = make_client(rate_trap_create_per_min=2)
    for _ in range(2):
        assert client.post("/traps", json={"sphere": SKY}, headers=alice).status_code == 201
    r = client.post("/traps", json={"sphere": SKY}, headers=alice)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    # Other players and other routes are unaffected.
    assert client.post("/traps", json={"sphere": SKY}, headers=bob).status_code == 201
    assert client.get("/traps", headers=alice).status_code == 200
    clock.t += 30  # refills one token at 2/min
    assert client.post("/traps", json={"sphere": SKY}, headers=alice).status_code == 201


def test_hunt_limit(make_client, alice):
    client = make_client(rate_hunt_per_min=1)
    assert client.post("/hunt", json={"star": {"tic_id": TIC}}, headers=alice).status_code == 202
    assert client.post("/hunt", json={"star": {"tic_id": TIC}}, headers=alice).status_code == 429


def test_overall_limit_per_player(make_client, alice):
    client = make_client(rate_all_per_min=3)
    codes = [client.get("/traps", headers=alice).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_ip_backstop_stops_uuid_rotation(make_client):
    client = make_client(rate_ip_per_min=5)
    codes = [client.get("/traps", headers=player()).status_code for _ in range(6)]
    assert codes[-1] == 429


def test_bucket_math():
    t = [0.0]
    rl = RateLimiter(clock=lambda: t[0])
    assert rl.hit("b", "k", 60) == 0
    for _ in range(59):
        rl.hit("b", "k", 60)
    assert rl.hit("b", "k", 60) > 0
    t[0] += 1.0
    assert rl.hit("b", "k", 60) == 0
