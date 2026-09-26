"""api.ingest: upsert only what changed, keep checked pictures, prune after 90 days."""

from __future__ import annotations

import json
from datetime import timedelta

from api import ingest
from api.ports import EventQuery
from tests.sample_events import NOW, event, image, sample


class CountingEnricher:
    """Stands in for skypictures: one real-looking picture per event, counting calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, e: dict) -> list[dict]:
        self.calls.append(e["id"])
        return [*e.get("images", []), image(f"https://pics.example/{e['id']}.jpg")]


def all_rows(storage) -> dict[str, dict]:
    rows = storage.query_events(EventQuery(include_latest_window=True, limit=1000))
    return {r["id"]: r for r, _ in rows}


def test_second_run_rewrites_nothing(storage):
    enrich = CountingEnricher()
    first = ingest.store_events(storage, sample(), now=NOW, enrich=enrich)
    assert (first.created, first.updated, first.unchanged) == (len(sample()), 0, 0)
    assert first.pictures_checked == len(sample())
    before = storage.event_meta([e["id"] for e in sample()])

    enrich.calls.clear()
    later = NOW + timedelta(hours=1)
    second = ingest.store_events(storage, sample(), now=later, enrich=enrich)
    assert (second.created, second.updated, second.unchanged) == (0, 0, len(sample()))
    assert enrich.calls == []  # pictures reused: event unchanged and checked < 24 h ago
    assert second.pictures_reused == len(sample())
    after = storage.event_meta([e["id"] for e in sample()])
    assert {k: v.content_hash for k, v in after.items()} == {
        k: v.content_hash for k, v in before.items()
    }
    assert storage.count_events() == len(sample())


def test_unchanged_rows_keep_updated_at(storage, backend, request):
    ingest.store_events(storage, sample(), now=NOW)
    ingest.store_events(storage, sample(), now=NOW + timedelta(hours=2))
    if backend == "sqlite":
        rows = storage._all("SELECT updated_at FROM events")
        assert {r[0] for r in rows} == {"2026-09-25T12:00:00.000000+00:00"}
    else:
        rows = storage._all("SELECT DISTINCT updated_at FROM events")
        assert [r["updated_at"] for r in rows] == [NOW]


def test_changed_event_is_updated(storage):
    ingest.store_events(storage, sample(), now=NOW)
    changed = sample()
    changed[1]["confidence"] = 0.99
    changed[1]["type"] = "supernova"
    s = ingest.store_events(storage, changed, now=NOW + timedelta(hours=1))
    assert (s.created, s.updated, s.unchanged) == (0, 1, len(sample()) - 1)
    row = storage.get_event(changed[1]["id"])
    assert row["confidence"] == 0.99 and row["type"] == "supernova"
    got = storage.query_events(EventQuery(types=["supernova"], min_confidence=0.95))
    assert [r["id"] for r, _ in got] == [changed[1]["id"]]


def test_merged_sources_update_with_the_event(storage):
    ingest.store_events(storage, sample(), now=NOW)
    changed = sample()
    changed[0]["raw"]["sources"] = [{"source": "tns", "url": "u"}]  # ZTF no longer merged in
    ingest.store_events(storage, changed, now=NOW)
    ztf = storage.query_events(EventQuery(sources=["ztf"]))
    assert "tns:2026abc" not in {r["id"] for r, _ in ztf}


def test_pictures_rechecked_after_ttl_or_change(storage):
    enrich = CountingEnricher()
    ingest.store_events(storage, sample(), now=NOW, enrich=enrich)
    enrich.calls.clear()
    changed = sample()
    changed[2]["summary"] = "Brighter now."
    ingest.store_events(storage, changed, now=NOW + timedelta(hours=1), enrich=enrich)
    assert enrich.calls == [changed[2]["id"]]

    enrich.calls.clear()
    s = ingest.store_events(storage, changed, now=NOW + timedelta(hours=30), enrich=enrich)
    assert len(enrich.calls) == len(sample())  # older than 24 h: checked again
    assert s.unchanged == len(sample())  # same pictures, so the records didn't change
    meta = storage.event_meta([changed[0]["id"]])[changed[0]["id"]]
    assert meta.images_checked_at == NOW + timedelta(hours=30)


def test_pictures_are_stored_and_failures_keep_the_event(storage):
    def flaky(e):
        if e["id"] == "tns:2026abc":
            raise RuntimeError("hips2fits down")
        return [image(f"https://pics.example/{e['id']}.jpg")]

    ingest.store_events(storage, sample(), now=NOW, enrich=flaky)
    rows = all_rows(storage)
    assert rows["tns:2026abc"]["images"] == sample()[0]["images"]  # its own picture kept
    assert rows["cneos:fb1"]["images"][0]["url"] == "https://pics.example/cneos:fb1.jpg"
    assert len(rows) == len(sample())


def test_prune_and_too_old(storage):
    ingest.store_events(storage, sample(), now=NOW)
    old = event("tns:2026old", "supernova", hours_ago=24 * 100)
    s = ingest.store_events(storage, [old], now=NOW)
    assert s.too_old == 1 and storage.get_event("tns:2026old") is None
    # 81 days on, the 20-day-old comet is past 90 days and goes; its sources rows go with it.
    s = ingest.store_events(storage, [], now=NOW + timedelta(days=71))
    assert s.pruned == 1 and storage.get_event("jpl:C2026A1") is None
    assert storage.query_events(EventQuery(sources=["jpl"])) == []
    s = ingest.store_events(storage, [], now=NOW + timedelta(days=200))
    assert storage.count_events() == 0


def test_malformed_events_are_rejected(storage):
    bad = [
        {"id": "x:1"},
        {**sample()[0], "id": "x:2", "location": {"frame": "moon"}},
        {**sample()[0], "id": "x:3", "location": {"frame": "sky"}},
        {**sample()[0], "id": "x:4", "observed_at": "soon"},
        "not an event",
    ]
    s = ingest.store_events(storage, [*bad, sample()[0]], now=NOW)
    assert len(s.rejected) == 5 and s.created == 1


def test_honesty_rewrites_text_but_not_urls_or_raw(storage):
    e = event("tns:2026h", "supernova", hours_ago=1,
              summary="A supernova discovered last night near a new planet host.",
              raw={"note": "discovered by ATLAS"})  # fmt: skip
    e["source_url"] = "https://example.org/discovered/2026h"
    ingest.store_events(storage, [e], now=NOW)
    got = storage.get_event("tns:2026h")
    assert got["summary"] == "A supernova detected last night near a planet candidate host."
    assert got["source_url"] == "https://example.org/discovered/2026h"
    assert got["raw"]["note"] == "discovered by ATLAS"


def test_cli_from_file(tmp_path, capsys):
    events_file = tmp_path / "events.json"
    events_file.write_text(json.dumps({"events": sample()}))
    status_file = tmp_path / "status.json"
    status_file.write_text(
        json.dumps({"window": {"since": "a", "until": "b"}, "sources": {"tns": {"state": "live"}}})
    )
    db = str(tmp_path / "spotter.db")
    args = ["--from-file", str(events_file), "--status-file", str(status_file), "--no-pictures"]
    # Old events against the real clock: keep them all.
    assert ingest.main([*args, "--db", db, "--keep-days", "36500"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["created"] == len(sample()) and first["sources"]["tns"]["state"] == "live"
    assert ingest.main([*args, "--db", db, "--keep-days", "36500"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["created"] == 0 and second["unchanged"] == len(sample())
