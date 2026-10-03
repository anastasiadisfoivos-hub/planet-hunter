"""Storage-port behaviour both backends must share."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.finder import candidate_row, parse_candidate
from api.monitor import parse_star
from api.settings import Settings
from api.storage.sqlite import SqliteStorage
from api.wiring import build_storage
from tests.conftest import BACKENDS, wipe_postgres

T = datetime(2026, 9, 20, 3, 4, 5, 123456, tzinfo=UTC)
GONE = ("events", "star_analyses", "analyze_jobs", "star_lightcurves", "known_planets")


def _row(tic: int = 5, n: str = "1", **over):
    rec = {"tic": tic, "period_d": 2.0, "t0_btjd": 2000.0, "duration_h": 2.0, **over}
    return candidate_row(f"{tic}_{n}", parse_candidate(f"{tic}_{n}", rec), T)


def test_migrations_are_recorded(storage, backend):
    if backend == "sqlite":
        versions = [r[0] for r in storage._all("SELECT version FROM schema_migrations")]
        assert versions == [
            "0002_events", "0003_analyze", "0004_stardata", "0005_finder", "0006_finder_only",
            "0007_monitor_detail", "0008_runner",
        ]  # fmt: skip
        assert storage.migrate() == []  # idempotent
        tables = {r[0] for r in storage._all("SELECT name FROM sqlite_master WHERE type='table'")}
    else:
        rows = storage._all("SELECT version FROM schema_migrations ORDER BY version")
        assert [r["version"] for r in rows] == [
            "0001_init", "0002_events", "0003_analyze", "0004_stardata", "0005_finder",
            "0006_finder_only", "0007_monitor_detail", "0008_runner",
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


# 0007 backfills known_count/rejected_count from the latest search's record, where it is kept.
_OLD_ROWS = [
    "INSERT INTO monitor_runs (run_id, state, updated_at) VALUES ('r1', 'done', '{t}')",
    "INSERT INTO monitor_stars (run_id, tic, searched_at, detections_count, record) VALUES"
    ' (\'r1\', 1, \'{t}\', 4, \'{{"tic": 1, "detections": [{{"outcome": "known"}},'
    ' {{"outcome": "rejected"}}, {{"outcome": "rejected"}}, {{"outcome": "candidate"}}]}}\')',
    "INSERT INTO monitor_stars (run_id, tic, searched_at, record) VALUES"
    " ('r1', 2, '{t}', '{{\"tic\": 2, \"detections\": []}}')",
    "INSERT INTO monitor_seen (tic, run_id, searched_at, detections_count)"
    " VALUES (1, 'r1', '{t}', 4)",
    "INSERT INTO monitor_seen (tic, run_id, searched_at) VALUES (2, 'r1', '{t}')",
    # 3's run was pruned: nothing to backfill from.
    "INSERT INTO monitor_seen (tic, run_id, searched_at, detections_count)"
    " VALUES (3, 'r0', '{t}', 2)",
]


def _check_backfill(s) -> None:
    rows = s._all("SELECT tic, known_count, rejected_count FROM monitor_seen ORDER BY tic")
    assert [(r["tic"], r["known_count"], r["rejected_count"]) for r in rows] == [
        (1, 1, 2), (2, 0, 0), (3, 0, 0)
    ]  # fmt: skip
    stats = s.monitor_stats()
    assert (stats["known"], stats["rejected"]) == (1, 2)


def test_0007_backfills_sqlite(monkeypatch):
    from api.storage import sqlite

    files = sqlite.migration_files()
    i = [v for v, _ in files].index("0007_monitor_detail")
    files = files[: i + 1]  # up to 0007: later migrations are not what this test is about
    monkeypatch.setattr(sqlite, "migration_files", lambda: files[:-1])
    s = SqliteStorage(":memory:")
    try:
        for sql in _OLD_ROWS:
            s._exec(sql.format(t=T.isoformat()))
        monkeypatch.setattr(sqlite, "migration_files", lambda: files)
        assert s.migrate() == ["0007_monitor_detail"]
        _check_backfill(s)
    finally:
        s.close()


@pytest.mark.skipif("postgres" not in BACKENDS, reason="PH_TEST_BACKENDS excludes postgres")
def test_0007_backfills_postgres(pg_url, pg_storage, monkeypatch):
    import psycopg

    from api.storage import postgres
    from tests.conftest import OLD_TABLES, TABLES

    every = postgres.migration_files()
    files = every
    i = [v for v, _ in files].index("0007_monitor_detail")
    files = files[: i + 1]  # up to 0007: later migrations are not what this test is about
    with psycopg.connect(pg_url, autocommit=True) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {TABLES}, {OLD_TABLES}, schema_migrations CASCADE")
        monkeypatch.setattr(postgres, "migration_files", lambda: files[:-1])
        postgres.migrate(conn)
        for sql in _OLD_ROWS:
            conn.execute(sql.format(t=T.isoformat()))
        monkeypatch.setattr(postgres, "migration_files", lambda: files)
        assert postgres.migrate(conn) == ["0007_monitor_detail"]
        monkeypatch.setattr(postgres, "migration_files", lambda: every)
        postgres.migrate(conn)  # back to the current schema, which the shared wipe expects
    try:
        _check_backfill(pg_storage)
    finally:
        wipe_postgres(pg_url)
