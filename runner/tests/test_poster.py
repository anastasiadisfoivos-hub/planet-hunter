"""Posting to the real API (api/, served locally): progress and stars make the monitor "live"; a wrong token or
an API that is down is counted and never blocks the caller."""

import time
from datetime import UTC, datetime

from conftest import TOKEN
from scheduler.poster import Poster


def star(tic):
    return {"tic": tic, "tmag": 10.1, "teff": 3400, "radius_rsun": 0.4, "ra": 10.0, "dec": -20.0, "sectors": [10, 11],
            "observed_from": "2025-01-01T00:00:00Z", "observed_to": "2025-02-01T00:00:00Z",
            "lightcurve": {"t": [1.0, 2.0], "f": [1.0, 0.999]},
            "detections": [{"t0": 1.5, "duration_h": 2, "depth_ppm": 900, "period_d": 3.5, "kind": "periodic",
                            "outcome": "rejected", "reason": "Too faint."}],
            "outcome": "rejected", "searched_at": datetime.now(UTC).isoformat()}


def wait_sent(p, n, timeout=10):
    t = time.time()
    while p.stats["sent"] + p.stats["failed"] < n and time.time() - t < timeout:
        time.sleep(0.05)


def test_progress_and_star_make_the_monitor_live(api):
    p = Poster(api.url, TOKEN, "oracle-20260927", datetime(2026, 9, 27, 0, 15, tzinfo=UTC), log=lambda m: None)
    p.start()
    p.set_progress("fast", 1, 10)
    p.set_progress("deep", 0, 3)
    p.star("fast", star(111))
    p.heartbeat("searching", {"fast": {"done": 1, "listed": 400, "running": 1}})
    wait_sent(p, 4)  # the star, both queues' progress, the heartbeat
    stats = p.close()
    assert stats["failed"] == 0 and stats["stars_sent"] == 1
    now = api.get("/monitor/now")
    assert now["mode"] == "live"
    assert now["run_id"] == "oracle-20260927"
    assert now["progress"] == {"done": 1, "total": 13}  # summed over the queues' shards
    assert now["star"]["tic"] == 111
    assert api.get("/monitor/log")["items"][0]["tic"] == 111
    assert now["label"] == "fast", "the queue that searched the star"
    assert now["runner"]["state"] == "searching" and now["runner"]["responding"]
    assert api.get("/monitor/coverage/queues")["queues"]["fast"] == {"done": 1, "listed": 400, "running": 1}


def test_idle_heartbeat_says_when_the_next_run_starts(api):
    p = Poster(api.url, TOKEN, "oracle-20260927", datetime(2026, 9, 27, 0, 15, tzinfo=UTC), log=lambda m: None)
    p.start()
    p.heartbeat("idle", {}, next_run_at="2099-01-01T00:15:00+00:00")
    wait_sent(p, 1)
    assert p.close()["failed"] == 0
    runner = api.get("/monitor/now")["runner"]
    assert runner["state"] == "idle" and runner["next_run_at"].startswith("2099-01-01")
    assert runner["responding"], "idle until its next run, which is announced"


def test_wrong_token_is_counted(api):
    logs = []
    p = Poster(api.url, "wrong", "r-bad", datetime.now(UTC), log=logs.append)
    p.start()
    p.set_progress("fast", 0, 1)
    p.heartbeat("searching")
    wait_sent(p, 2)
    stats = p.close()
    assert stats["failed"] == 2 and stats["sent"] == 0
    assert "403" in stats["last_error"]
    assert any("dropping and counting" in m for m in logs)


def test_api_down_never_blocks():
    p = Poster("http://127.0.0.1:9", TOKEN, "r-down", datetime.now(UTC), log=lambda m: None)
    p.start()
    t = time.time()
    for i in range(1000):  # more than the queue holds
        p.star("fast", star(i + 1))
    assert time.time() - t < 1.0, "posting is fire-and-forget"
    stats = p.close(timeout_s=2)
    assert stats["dropped"] > 0


def test_disabled_without_token():
    p = Poster(None, None, "r", datetime.now(UTC), log=lambda m: None)
    p.start()
    p.star("fast", star(1))
    assert p.close() == {"sent": 0, "failed": 0, "dropped": 0, "stars_sent": 0, "last_ok_at": None,
                         "last_error": None}
