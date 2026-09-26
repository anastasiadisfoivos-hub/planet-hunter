"""Per-IP limits (analyze much tighter than reads), proxies, CORS."""

from __future__ import annotations

from api.ratelimit import RateLimiter
from tests.conftest import TIC


def test_analyze_is_tighter_than_reads(make_client, clock):
    client = make_client(rate_analyze_per_min=2, rate_read_per_min=5)
    assert client.post("/analyze", json={"tic_id": TIC}).status_code == 202
    assert client.post("/analyze", json={"tic_id": TIC}).status_code == 202
    r = client.post("/analyze", json={"tic_id": TIC})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    # Reads have their own bucket.
    assert [client.get("/events").status_code for _ in range(6)] == [200] * 5 + [429]
    clock.t += 30  # refills one analyze token at 2/min
    assert client.post("/analyze", json={"tic_id": TIC}).status_code in (200, 202)


def test_limits_are_per_ip_behind_a_trusted_proxy(make_client):
    client = make_client(rate_read_per_min=2, trusted_proxy_hops=1)

    def get(xff):
        return client.get("/status", headers={"X-Forwarded-For": xff}).status_code

    assert [get("1.1.1.1"), get("1.1.1.1"), get("1.1.1.1")] == [200, 200, 429]
    assert get("2.2.2.2") == 200
    # A client can prepend anything; only the entry the proxy added counts.
    assert get("9.9.9.9, 1.1.1.1") == 429


def test_forwarded_for_is_ignored_without_trusted_proxy(make_client):
    client = make_client(rate_read_per_min=2)
    codes = [client.get("/status", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
             for i in range(3)]  # fmt: skip
    assert codes == [200, 200, 429]


def test_cors_for_the_web_origin(make_client):
    client = make_client(web_origins=("https://spotter.example",))
    pre = client.options(
        "/analyze",
        headers={"Origin": "https://spotter.example", "Access-Control-Request-Method": "POST"},
    )
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == "https://spotter.example"
    ok = client.get("/events", headers={"Origin": "https://spotter.example"})
    assert ok.headers["access-control-allow-origin"] == "https://spotter.example"
    other = client.get("/events", headers={"Origin": "https://evil.example"})
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
