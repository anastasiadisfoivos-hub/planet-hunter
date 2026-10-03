"""python -m api.remote_ingest against the app itself: chunking, the final chunk, and the pixel
checks run client-side through the pixel queue. SQLite and Postgres."""

from __future__ import annotations

import json

from api import remote_ingest
from api.fakes.finder import FakePixelVetter
from tests.test_finder import candidate
from tests.test_monitor import AUTH, TOKEN, star


class ClientApi:
    """remote_ingest.Api over a TestClient instead of the network."""

    def __init__(self, client) -> None:
        self.client = client
        self.calls: list[str] = []

    def call(self, method, path, body=None):
        self.calls.append(f"{method} {path}")
        r = self.client.request(method, path, json=body, headers=AUTH)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()


def test_chunks_split_by_size_and_mark_the_last_final():
    cands = [(f"{i}_1", candidate(i)) for i in range(1, 6)]
    stars = [star(i, i) for i in range(10, 16)]
    bodies = remote_ingest.chunks(cands, stars, {"summary": {"a": 1}}, max_bytes=3000)
    assert len(bodies) > 2
    assert bodies[0]["summary"] == {"a": 1} and all("summary" not in b for b in bodies[1:])
    assert [b.get("final", False) for b in bodies] == [False] * (len(bodies) - 1) + [True]
    assert sum(len(b["candidates"]) for b in bodies) == 5
    assert sum(len(b["monitor"]) for b in bodies) == 6
    # nothing to send is still one final chunk: it closes the run
    assert remote_ingest.chunks([], [], {}, 1000) == [
        {"candidates": [], "monitor": [], "final": True}
    ]


def test_a_night_over_http(make_client, storage, tmp_path):
    c = make_client(ingest_token=TOKEN)
    api = ClientApi(c)
    folder = tmp_path / "candidates"
    folder.mkdir()
    for tic in (100, 200):
        (folder / f"{tic}_1.json").write_text(json.dumps(candidate(tic)))
    (folder / "300_s1.json").write_text(json.dumps(candidate(300, period_d=None)))
    monitor = tmp_path / "monitor"
    monitor.mkdir()
    for tic in (100, 200, 300, 400):
        (monitor / f"{tic}.json").write_text(json.dumps(star(tic, tic)))

    cands = remote_ingest._items(folder, remote_ingest.CANDIDATE_ID)
    stars = [s for _, s in remote_ingest._items(monitor, remote_ingest.STAR_FILE)]
    sent = remote_ingest.send(api, remote_ingest.chunks(cands, stars, {}, 4000), "oracle-1", None)
    assert sent["created"] == 3 and sent["monitor_stars"] == 4 and not sent["invalid"]
    assert storage.get_monitor_run("oracle-1")["state"] == "done"

    vetter = FakePixelVetter()
    vetter.fail.add(200)
    px = remote_ingest.pixel_checks(api, vetter, limit=20, deadline=float("inf"))
    assert px == {"vetted": 1, "failed": 1, "stale": 0, "skipped_for_time": 0}
    assert c.get("/finder/candidates/100_1").json()["pixel_vet"]["verdict"] == "on target"
    # the failure is queued again for the next night; the single dip never is
    assert [i["id"] for i in c.get("/finder/pixel-queue", headers=AUTH).json()["items"]] == [
        "200_1"
    ]


def test_pixel_checks_stop_at_the_deadline(make_client):
    c = make_client(ingest_token=TOKEN)
    api = ClientApi(c)
    cands = [(f"{i}_1", candidate(i)) for i in (1, 2)]
    remote_ingest.send(api, remote_ingest.chunks(cands, [], {}, 10**6), "oracle-2", None)
    px = remote_ingest.pixel_checks(api, FakePixelVetter(), limit=20, deadline=0.0)
    assert px["vetted"] == 0 and px["skipped_for_time"] == 1
