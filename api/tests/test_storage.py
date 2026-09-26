"""Storage-port behaviour both backends must share."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.finder import candidate_row, parse_candidate
from api.monitor import parse_star
from api.settings import Settings
from api.storage.sqlite import SqliteStorage
from api.wiring import build_storage

T = datetime(2026, 9, 20, 3, 4, 5, 123456, tzinfo=UTC)
GONE = ("events", "star_analyses", "analyze_jobs", "star_lightcurves", "known_planets")


def _row(tic: int = 5, n: str = "1", **over):
    rec = {"tic": tic, "period_d": 2.0, "t0_btjd": 2000.0, "duration_h": 2.0, **over}
    return candidate_row(f"{tic}_{n}", parse_candidate(f"{tic}_{n}", rec), T)


def test_migrations_are_recorded(storage, backend):
    if backend == "sqlite":
        versions = [r[0] for r in storage._all("SELECT version FROM schema_migrations")]
        assert versions == [
            "0002_events", "0003_analyze", "0004_stardata", "0005_finder", "0006_finder_only"
        ]  # fmt: skip
        assert storage.migrate() == []  # idempotent
        tables = {r[0] for r in storage._all("SELECT name FROM sqlite_master WHERE type='table'")}
    else:
        rows = storage._all("SELECT version FROM schema_migrations ORDER BY version")
        assert [r["version"] for r in rows] == [
            "0001_init", "0002_events", "0003_analyze", "0004_stardata", "0005_finder",
            "0006_finder_only",
        ]  # fmt: skip
        tables = {
            r["tablename"]
            for r in storage._all("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        }
        assert not storage._all("SELECT 1 FROM pg_proc WHERE proname = 'ph_sep_deg'")
    assert not tables & set(GONE)
    assert {"candidates", "votes", "monitor_runs", "monitor_seen"} <= tables


def test_vetting_round_trip(storage):
    storage.upsert_candidate(_row(vetting={"verdict": "pass", "tests": [{"name": "odd_even"}]}))
    assert storage.get_candidate("5_1")["vetting"]["tests"][0]["name"] == "odd_even"
    storage.upsert_candidate(_row(6))
    assert storage.get_candidate("6_1")["vetting"] is None


def test_single_dip_without_period(storage):
    row = _row(7, "s1", period_d=None)
    assert row.period_d is None
    assert storage.upsert_candidate(row) == "created"
    assert storage.get_candidate("7_s1")["record"]["period_d"] is None
    assert storage.candidates_to_vet(10, 3) == []  # no period: no pixel check


def test_atomic_rolls_back_and_nests(storage):
    with pytest.raises(RuntimeError), storage.atomic():
        storage.upsert_candidate(_row(1))
        with storage.atomic():
            storage.upsert_candidate(_row(2))
        raise RuntimeError
    assert storage.get_candidate("1_1") is None and storage.get_candidate("2_1") is None
    with storage.atomic(), storage.atomic():
        storage.upsert_candidate(_row(1))
    assert storage.get_candidate("1_1") is not None


def _star(tic: int, at: datetime, **over):
    rec = {"tic": tic, "ra": 10.0, "dec": -20.0, "sectors": [1, 2], "detections": [],
           "outcome": "nothing", "searched_at": at.isoformat(), **over}  # fmt: skip
    return parse_star(rec, T)


def test_monitor_latest_search_wins(storage):
    storage.put_monitor_run("r1", T, "running", T)
    storage.put_monitor_star("r1", _star(9, T + timedelta(hours=2), outcome="new"))
    storage.put_monitor_star("r1", _star(9, T, outcome="old", sectors=[3]))  # older: seen stays
    log = storage.monitor_log(10)
    assert log == [{"tic": 9, "outcome": "new", "detections_count": 0,
                    "searched_at": T + timedelta(hours=2)}]  # fmt: skip
    assert storage.monitor_coverage()["by_sector"] == [
        {"sector": 1, "stars": 1}, {"sector": 2, "stars": 1}
    ]  # fmt: skip
    assert storage.get_monitor_star("r1", 9)["outcome"] == "old"  # the run's own copy updates


def test_monitor_runs_prune_keeps_running(storage):
    for i in range(4):
        storage.put_monitor_run(f"r{i}", T + timedelta(days=i), "running", T)
        storage.put_monitor_star(f"r{i}", _star(100 + i, T + timedelta(days=i)))
        if i != 3:
            storage.put_monitor_run(f"r{i}", None, "done", T)
    assert storage.prune_monitor_runs(1) == 2
    assert storage.get_monitor_run("r0") is None and storage.get_monitor_run("r1") is None
    assert storage.get_monitor_run("r2")["state"] == "done"
    assert storage.get_monitor_run("r3")["state"] == "running"
    assert storage.monitor_stats()["stars_searched"] == 4  # the latest searches stay forever
    # A late shard post never reopens a finished run.
    storage.put_monitor_run("r2", None, "running", T)
    assert storage.get_monitor_run("r2")["state"] == "done"


def test_sqlite_file_survives_reopen(tmp_path):
    path = str(tmp_path / "x.db")
    s = SqliteStorage(path)
    s.upsert_candidate(_row(5))
    s.close()
    s = build_storage(Settings(db_path=path))
    assert s.get_candidate("5_1")["tic"] == 5
    s.close()
