"""Per-IP limits (ingest and votes apart from reads), proxies, CORS."""

from __future__ import annotations

from api.ratelimit import RateLimiter


def test_ingest_posts_have_their_own_bucket(make_client, clock):
    client = make_client(ingest_token="t" * 32, rate_ingest_per_min=2, rate_read_per_min=5)
    h = {"Authorization": "Bearer " + "t" * 32}
    body = {"run_id": "1", "done": 0, "total": 10}
    assert [client.post("/monitor/progress", json=body, headers=h).status_code
            for _ in range(3)] == [200, 200, 429]  # fmt: skip
    # Reads have their own bucket.
    assert [client.get("/monitor/now").status_code for _ in range(6)] == [200] * 5 + [429]
    clock.t += 30  # refills one ingest token at 2/min
    assert client.post("/monitor/progress", json=body, headers=h).status_code == 200


def test_limits_are_per_ip_behind_a_trusted_proxy(make_client):
    client = make_client(rate_read_per_min=2, trusted_proxy_hops=1)

    def get(xff):
        return client.get("/monitor/stats", headers={"X-Forwarded-For": xff}).status_code

    assert [get("1.1.1.1"), get("1.1.1.1"), get("1.1.1.1")] == [200, 200, 429]
    assert get("2.2.2.2") == 200
    # A client can prepend anything; only the entry the proxy added counts.
    assert get("9.9.9.9, 1.1.1.1") == 429


def test_forwarded_for_is_ignored_without_trusted_proxy(make_client):
    client = make_client(rate_read_per_min=2)
    codes = [client.get("/monitor/stats", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
             for i in range(3)]  # fmt: skip
    assert codes == [200, 200, 429]


def test_cors_for_the_web_origin(make_client):
    client = make_client(web_origins=("https://spotter.example",))
    pre = client.options(
        "/finder/candidates/1_1/vote",
        headers={
            "Origin": "https://spotter.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-voter-key",
        },
    )
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == "https://spotter.example"
    assert "x-voter-key" in pre.headers["access-control-allow-headers"].lower()
    ok = client.get("/monitor/now", headers={"Origin": "https://spotter.example"})
    assert ok.headers["access-control-allow-origin"] == "https://spotter.example"
    other = client.get("/monitor/now", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_bucket_math():
    t = [0.0]
    rl = RateLimiter(clock=lambda: t[0])
    assert rl.hit("b", "k", 60) == 0
    for _ in range(59):
        rl.hit("b", "k", 60)
    assert rl.hit("b", "k", 60) > 0
    t[0] += 1.0
    assert rl.hit("b", "k", 60) == 0
