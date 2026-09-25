"""GET /events: every filter, paging, validation, GET /events/{id} and GET /status."""

from __future__ import annotations

import pytest

from api.ingest import store_events, store_status
from tests.sample_events import NOW, sample


@pytest.fixture
def loaded(storage):
    summary = store_events(storage, sample(), now=NOW)
    status = {
        "window": {"since": "2026-09-18T12:00:00Z", "until": "2026-09-25T12:00:00Z"},
        "sources": {
            "tns": {"state": "live", "live": True, "last_event_at": "2026-09-25T10:00:00Z",
                    "events": 1, "events_fetched": 1, "error": None},
            "gcn": {"state": "unknown", "live": None, "last_event_at": None, "events": 0,
                    "events_fetched": 0, "error": "fetch: timeout"},
        },
    }  # fmt: skip
    stream = {"is_live": False, "last_alert_at": "2026-09-10T03:00:00Z"}
    store_status(storage, status, summary, now=NOW, rubin_stream=stream)
    return storage


def ids(client, **params) -> list[str]:
    r = client.get("/events", params=params)
    assert r.status_code == 200, r.text
    return [e["id"] for e in r.json()["items"]]


def test_default_is_newest_first_without_latest_window(loaded, client):
    got = ids(client)
    assert "rubin:1001" not in got  # from Rubin's latest observed window: opt-in only
    assert got[:3] == ["gcn:GRB260925A", "tns:2026abc", "donki:FLR-1"]
    assert len(got) == len(sample()) - 1


def test_include_latest_window(loaded, client):
    assert "rubin:1001" in ids(client, include_latest_window=True)


def test_types(loaded, client):
    assert ids(client, types="supernova") == ["tns:2026abc"]
    both = ids(client, types=["supernova", "comet"], include_latest_window=True)
    assert set(both) == {"tns:2026abc", "rubin:1001", "jpl:C2026A1"}
    assert set(ids(client, types="comet,fireball")) == {"jpl:C2026A1", "cneos:fb1"}


def test_categories(loaded, client):
    assert set(ids(client, categories="high_energy")) == {
        "gcn:GRB260925A", "gracedb:S260920x", "icecube:IC260921A"
    }  # fmt: skip
    assert set(ids(client, categories="sun_space_weather")) == {"donki:FLR-1", "donki:GST-1"}
    assert ids(client, categories="other") == ["ztf:ZTF26bbb"]
    assert set(ids(client, categories="solar_system,earth_atmosphere")) == {
        "mpc:LS123", "jpl:C2026A1", "cneos:fb1"
    }  # fmt: skip


def test_since_and_until_on_observed_at(loaded, client):
    since = ids(client, since="2026-09-25T06:00:00Z")
    assert set(since) == {"gcn:GRB260925A", "tns:2026abc", "donki:FLR-1", "ztf:ZTF26aaa"}
    until = ids(client, until="2026-09-10T00:00:00Z")
    assert until == ["jpl:C2026A1"]
    window = ids(client, since="2026-09-24T00:00:00Z", until="2026-09-25T05:00:00Z")
    assert set(window) == {"donki:GST-1", "mpc:LS123", "ztf:ZTF26bbb"}


def test_sources_match_any_member(loaded, client):
    # tns:2026abc was merged with a ZTF alert, so it matches "ztf" too.
    assert set(ids(client, sources="ztf")) == {"tns:2026abc", "ztf:ZTF26aaa", "ztf:ZTF26bbb"}
    assert set(ids(client, sources=["donki", "cneos"])) == {
        "donki:FLR-1", "donki:GST-1", "cneos:fb1"
    }  # fmt: skip


def test_frame(loaded, client):
    assert ids(client, frame="sun") == ["donki:FLR-1"]
    assert set(ids(client, frame="earth")) == {"donki:GST-1", "cneos:fb1"}
    assert len(ids(client, frame="sky")) == 8


def test_region(loaded, client):
    near = ids(client, ra=150.0, dec=-20.0, radius=2)
    assert set(near) == {"tns:2026abc", "ztf:ZTF26aaa", "ztf:ZTF26bbb"}
    # Across RA 0/360.
    wrap = ids(client, ra=0.0, dec=0.0, radius=1, include_latest_window=True)
    assert set(wrap) == {"rubin:1001", "mpc:LS123"}
    # Around the pole, where RA means little.
    assert ids(client, ra=180.0, dec=-90.0, radius=1) == ["gcn:GRB260925A"]
    tight = ids(client, ra=80.0, dec=30.0, radius=0.3)
    assert tight == ["gracedb:S260920x"]


def test_min_confidence(loaded, client):
    got = ids(client, min_confidence=0.9)
    assert "icecube:IC260921A" not in got and "ztf:ZTF26aaa" not in got
    assert "cneos:fb1" in got and "gracedb:S260920x" in got
    assert ids(client, min_confidence=1) == ["cneos:fb1"]


def test_has_images(loaded, client):
    assert set(ids(client, has_images=True)) == {"tns:2026abc", "donki:FLR-1"}
    assert "tns:2026abc" not in ids(client, has_images=False)


def test_filters_combine(loaded, client):
    got = ids(client, categories="transients", sources="ztf", min_confidence=0.5)
    assert got == ["tns:2026abc"]


def test_cursor_paging(loaded, client):
    everything = ids(client, include_latest_window=True, limit=200)
    seen, cursor = [], None
    while True:
        params = {"include_latest_window": True, "limit": 5}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/events", params=params).json()
        seen += [e["id"] for e in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert seen == everything and len(seen) == len(sample())


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 201},
        {"limit": 0},
        {"types": "planet"},
        {"categories": "weather"},
        {"sources": "nope"},
        {"frame": "moon"},
        {"ra": 10, "dec": 10},
        {"ra": 10, "dec": 10, "radius": 1, "frame": "sun"},
        {"ra": 400, "dec": 10, "radius": 1},
        {"min_confidence": 2},
        {"since": "yesterday-ish"},
        {"since": "2026-09-25", "until": "2026-09-01"},
        {"cursor": "not-a-cursor"},
    ],
)
def test_bad_filters_are_422(loaded, client, params):
    assert client.get("/events", params=params).status_code == 422


def test_relative_since(loaded, client):
    # Relative ages count back from the real clock; the sample is dated 2026-09-25.
    assert client.get("/events", params={"since": "36500d"}).status_code == 200


def test_event_by_id(loaded, client):
    r = client.get("/events/tns:2026abc")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "tns:2026abc" and body["images"][0]["thumb_url"].endswith("?thumb")
    assert body == next(e for e in sample() if e["id"] == "tns:2026abc")
    assert client.get("/events/gcn:GRB260925A").json()["type"] == "gamma_ray_burst"
    assert client.get("/events/tns:nope").status_code == 404


def test_status(loaded, client):
    body = client.get("/status").json()
    assert body["ingested_at"].startswith("2026-09-25T12:00:00")
    assert body["events_stored"] == len(sample())
    assert body["sources"]["tns"]["state"] == "live"
    assert body["sources"]["gcn"]["error"] == "fetch: timeout"
    assert body["rubin_stream"] == {"is_live": False, "last_alert_at": "2026-09-10T03:00:00Z"}
    assert body["ingest"]["created"] == len(sample())


def test_status_before_any_ingest(client):
    body = client.get("/status").json()
    assert body["ingested_at"] is None and body["events_stored"] == 0 and body["sources"] == {}
