"""Storage-level behaviour both backends must share, plus the Postgres-only guarantees."""

from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from api import catalog
from api.models import TrapRecord
from api.settings import Settings
from api.storage.sqlite import SqliteStorage
from api.wiring import build_storage
from tests.conftest import BACKENDS, TIC, wipe_postgres
from tests.test_conventions import d

T = datetime(2026, 9, 20, tzinfo=UTC)


def _trap(player_id: str = "p") -> TrapRecord:
    return TrapRecord(
        id=str(uuid.uuid4()), player_id=player_id, kind="star", star={"tic_id": TIC}, created_at=T
    )


def test_atomic_rolls_back_and_nests(storage):
    a, b = _trap(), _trap()
    with pytest.raises(RuntimeError), storage.atomic():
        storage.create_trap(a)
        with storage.atomic():  # joins the outer transaction
            storage.create_trap(b)
        raise RuntimeError
    assert storage.get_trap(a.id) is None and storage.get_trap(b.id) is None

    with storage.atomic(), storage.atomic():
        storage.create_trap(a)
    assert storage.get_trap(a.id) == a


def test_insert_or_ignore_and_timestamps_round_trip(storage):
    storage.put_discovery(d("rubin:obj:1", source="rubin"))
    at = datetime(2026, 9, 21, 3, 4, 5, 123456, tzinfo=UTC)
    assert storage.add_catch("p", "rubin:obj:1", None, at)
    assert not storage.add_catch("p", "rubin:obj:1", "t", T)  # same key: ignored
    [(disc, caught_at)] = storage.list_catches("p", 10, None)
    assert disc.id == "rubin:obj:1" and caught_at == "2026-09-21T03:04:05.123456+00:00"
    trap = _trap()
    storage.create_trap(trap)
    storage.set_trap_checked(trap.id, last_checked_at=at, marker="sector-1")
    got = storage.get_trap(trap.id)
    assert got.last_checked_at == at and got.last_checked_at.utcoffset().total_seconds() == 0


def test_forged_cursor_is_not_a_server_error(client, alice):
    cursor = base64.urlsafe_b64encode(json.dumps(["not a time", "x"]).encode()).decode()
    assert client.get(f"/discoveries?cursor={cursor}", headers=alice).status_code == 200


def test_sqlite_is_the_default():
    storage = build_storage(Settings(db_path=":memory:"))
    assert isinstance(storage, SqliteStorage)


# Postgres only -------------------------------------------------------------------------------


@pytest.fixture
def pg(request):
    if "postgres" not in BACKENDS:
        pytest.skip("PH_TEST_BACKENDS excludes postgres")
    storage = request.getfixturevalue("pg_storage")
    wipe_postgres(request.getfixturevalue("pg_url"))
    return storage


def test_database_url_selects_postgres(pg, pg_url):
    from api.storage.postgres import PostgresStorage

    other = build_storage(replace(Settings(), database_url=pg_url))
    try:
        assert isinstance(other, PostgresStorage)
        trap = _trap()
        other.create_trap(trap)
        assert pg.get_trap(trap.id) == trap  # same database
    finally:
        other.close()


def test_migrations_are_idempotent(pg, pg_url):
    import psycopg

    from api.storage.postgres import migrate, migration_files

    with psycopg.connect(pg_url, autocommit=True) as conn:
        assert migrate(conn) == []
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations")]
    assert versions == [v for v, _ in migration_files()] and "0001_init" in versions


def test_concurrent_hunts_of_one_star_get_distinct_signal_ids(pg, pg_url):
    """The API's hunt and the nightly re-hunt, as two processes, finding different signals."""
    from api.storage.postgres import PostgresStorage

    api, nightly = PostgresStorage(pg_url), PostgresStorage(pg_url)
    try:
        for attempt in range(5):
            tic = TIC + attempt
            gate = threading.Barrier(2)
            errors = []

            def hunt(storage, player, period, tic=tic, gate=gate, errors=errors):
                found = [d(f"tess:{tic}:sig:1", period_days=period)]
                try:
                    gate.wait()
                    catalog.ingest_hunt(storage, player, None, tic, found, T)
                except Exception as e:  # pragma: no cover - reported below
                    errors.append(e)

            threads = [
                threading.Thread(target=hunt, args=(api, "alice", 1.3)),
                threading.Thread(target=hunt, args=(nightly, "bob", 3.7)),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert not errors
            stored = pg.discoveries_with_prefix(f"tess:{tic}:sig:")
            assert sorted(s.raw["period_days"] for s in stored) == [1.3, 3.7]
            assert len({s.id for s in stored}) == 2
    finally:
        api.close()
        nightly.close()


def test_open_nightly_transaction_does_not_block_the_api(pg, pg_url):
    """SQLite has one writer; on Postgres a long nightly transaction leaves other rows writable."""
    from api.storage.postgres import PostgresStorage

    nightly = PostgresStorage(pg_url)
    inside, release = threading.Event(), threading.Event()

    def long_transaction():
        with nightly.atomic():
            nightly.create_trap(_trap("nightly-player"))
            nightly.put_discovery(d("rubin:obj:7", source="rubin"))
            inside.set()
            release.wait(10)

    t = threading.Thread(target=long_transaction)
    t.start()
    try:
        assert inside.wait(5)
        start = time.monotonic()
        mine = _trap("api-player")
        pg.create_trap(mine)
        pg.put_discovery(d("rubin:obj:8", source="rubin"))
        assert pg.add_catch("api-player", "rubin:obj:8", mine.id, T)
        assert [x.id for x in pg.list_traps("api-player")] == [mine.id]
        assert pg.get_discovery("rubin:obj:7") is None  # uncommitted work stays invisible
        assert time.monotonic() - start < 1.0
    finally:
        release.set()
        t.join()
        nightly.close()
    assert pg.get_discovery("rubin:obj:7") is not None
