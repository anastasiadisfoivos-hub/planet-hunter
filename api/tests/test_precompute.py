"""api.precompute: sharding, idempotency, --force, failures, the CLI."""

from __future__ import annotations

import argparse
import json

import pytest

from api import precompute
from api.fakes.tess import FakeAnalyzer
from api.known_systems import KNOWN_SYSTEMS
from api.storage.sqlite import SqliteStorage

TICS = list(range(1000, 1047)) + [1003, 1010]  # duplicates are ignored


def test_shards_cover_the_list_exactly_once():
    for n in (1, 3, 20, 60):
        parts = [precompute.shard(TICS, i, n) for i in range(n)]
        flat = [t for p in parts for t in p]
        assert sorted(flat) == sorted(set(TICS)) and len(flat) == len(set(flat))
        sizes = [len(p) for p in parts]
        assert max(sizes) - min(sizes) <= 1


def test_parse_shard():
    assert precompute.parse_shard("3/20") == (3, 20)
    for bad in ("20/20", "-1/3", "1", "a/b", "0/0"):
        with pytest.raises(argparse.ArgumentTypeError):
            precompute.parse_shard(bad)


def test_read_tics(tmp_path):
    hosts = tmp_path / "hosts.json"
    hosts.write_text(json.dumps({"count": 3, "name": ["a", "b", "c"], "tic": [5, 6, 7]}))
    assert precompute.read_tics(hosts) == [5, 6, 7]
    lst = tmp_path / "list.json"
    lst.write_text(json.dumps([1, "TIC 2", {"tic_id": 3}, {"tic": "4"}, None, "x"]))
    assert precompute.read_tics(lst) == [1, 2, 3, 4]
    txt = tmp_path / "tics.txt"
    txt.write_text("# known systems\nTIC 100100827\n22529346  # WASP-121\n\n")
    assert precompute.read_tics(txt) == [100100827, 22529346]


def test_second_run_skips_everything(storage):
    hunter = FakeAnalyzer()
    tics = precompute.shard(TICS, 1, 4)
    first = precompute.run(storage, hunter, tics)
    assert sorted(first.analyzed) == tics and first.failed == []
    assert sorted(hunter.hunt_calls) == tics
    hunter.hunt_calls.clear()
    second = precompute.run(storage, hunter, tics)
    assert second.analyzed == [] and sorted(second.skipped) == tics
    assert hunter.hunt_calls == []


def test_force_and_marker_change(storage):
    hunter = FakeAnalyzer()
    precompute.run(storage, hunter, [1, 2, 3])
    hunter.hunt_calls.clear()
    assert precompute.run(storage, hunter, [1, 2, 3], force=True).analyzed == [1, 2, 3]
    hunter.hunt_calls.clear()
    hunter.markers[2] = "sector-200"
    again = precompute.run(storage, hunter, [1, 2, 3])
    assert again.analyzed == [2] and again.skipped == [1, 3] and hunter.hunt_calls == [2]
    assert storage.get_star_analysis(2).data_marker == "sector-200"


def test_failures_and_no_data_dont_stop_the_shard(storage):
    hunter = FakeAnalyzer()
    hunter.markers[11] = None  # no TESS data
    hunter.fail_for.add(12)  # the search finds no usable light curve

    class Broken(FakeAnalyzer):
        def analyze(self, tic_id, progress):
            if tic_id == 13:
                raise RuntimeError("MAST download failed")
            return super().analyze(tic_id, progress)

    broken = Broken()
    broken.markers, broken.fail_for = hunter.markers, hunter.fail_for
    s = precompute.run(storage, broken, [10, 11, 12, 13, 14])
    assert s.analyzed == [10, 14] and s.no_data == [11, 12]
    assert s.failed == [{"tic_id": 13, "error": "MAST download failed"}]
    assert storage.get_star_analysis(13) is None


def test_mast_down_skips_stored_and_analyzes_new(storage):
    hunter = FakeAnalyzer()
    precompute.run(storage, hunter, [1])
    hunter.marker_down = True
    hunter.hunt_calls.clear()
    s = precompute.run(storage, hunter, [1, 2])
    assert s.skipped == [1] and s.analyzed == [2] and hunter.hunt_calls == [2]


def test_time_budget(storage):
    s = precompute.run(storage, FakeAnalyzer(), [1, 2, 3], time_budget_s=-1)
    assert s.not_reached == [1, 2, 3] and s.analyzed == []


def test_cli(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PH_ADAPTERS", "fake")
    monkeypatch.delenv("PH_DATABASE_URL", raising=False)
    db = str(tmp_path / "spotter.db")
    tic_file = tmp_path / "hosts.json"
    tic_file.write_text(json.dumps({"tic": TICS}))
    outs = []
    for i in range(3):
        assert precompute.main(["--tic-file", str(tic_file), "--shard", f"{i}/3", "--db", db]) == 0
        outs.append(json.loads(capsys.readouterr().out))
    assert sum(o["counts"]["analyzed"] for o in outs) == len(set(TICS))
    assert all(o["stars_in_list"] == len(set(TICS)) for o in outs)
    assert precompute.main(["--tic-file", str(tic_file), "--shard", "0/3", "--db", db]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["counts"]["skipped"] == again["stars_in_shard"]

    assert precompute.main(["--known-systems", "--db", db]) == 0
    known = json.loads(capsys.readouterr().out)
    assert sorted(known["analyzed"]) == sorted(KNOWN_SYSTEMS.values())
    storage = SqliteStorage(db)
    assert storage.get_star_analysis(100100827).analysis.star.name == "WASP-18"
    storage.close()


def test_cli_exit_code_on_failures(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PH_ADAPTERS", "fake")
    db = str(tmp_path / "spotter.db")

    def broken_analyze(self, tic_id, progress):
        raise RuntimeError("boom")

    monkeypatch.setattr(FakeAnalyzer, "analyze", broken_analyze)
    assert precompute.main(["--stars", "1,2", "--db", db]) == 1
    capsys.readouterr()
    assert precompute.main(["--stars", "1,2", "--db", db, "--max-failed-fraction", "1"]) == 0
