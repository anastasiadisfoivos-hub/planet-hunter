"""Storage-port behaviour both backends must share."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.fakes.tess import FakeAnalyzer
from api.models import JobRecord, JobStep, StoredAnalysis
from api.settings import Settings
from api.storage.sqlite import SqliteStorage
from api.wiring import build_storage

T = datetime(2026, 9, 20, 3, 4, 5, 123456, tzinfo=UTC)


def _analysis(tic: int, marker: str = "sector-1") -> StoredAnalysis:
    return StoredAnalysis(
        tic_id=tic,
        data_marker=marker,
        analyzed_at=T,
        marker_checked_at=T,
        # The light curve travels apart (star_lightcurves), never inside the stored result.
        analysis=FakeAnalyzer()._result(tic, marker).model_copy(update={"lightcurve": None}),
    )


def test_migrations_are_recorded(storage, backend):
    if backend == "sqlite":
        versions = [r[0] for r in storage._all("SELECT version FROM schema_migrations")]
        assert versions == ["0002_events", "0003_analyze", "0004_stardata"]
        assert storage.migrate() == []  # idempotent
    else:
        rows = storage._all("SELECT version FROM schema_migrations ORDER BY version")
        assert [r["version"] for r in rows] == [
            "0001_init", "0002_events", "0003_analyze", "0004_stardata"
        ]  # fmt: skip


def test_star_analysis_round_trip(storage):
    assert storage.get_star_analysis(1) is None
    rec = _analysis(1)
    storage.put_star_analysis(rec)
    got = storage.get_star_analysis(1)
    assert got == rec and got.analyzed_at.utcoffset() == timedelta(0)
    storage.touch_star_analysis(1, T + timedelta(hours=1))
    assert storage.get_star_analysis(1).marker_checked_at == T + timedelta(hours=1)
    storage.put_star_analysis(_analysis(1, "sector-2"))  # replaces the row
    assert storage.get_star_analysis(1).data_marker == "sector-2"


def test_star_names(storage):
    assert storage.get_star_name("wasp18") is None
    storage.put_star_name("wasp18", 100100827, T)
    storage.put_star_name("wasp18", 100100827, T)
    assert storage.get_star_name("wasp18") == 100100827


def test_jobs(storage):
    a = JobRecord(id="a", tic_id=1, status="queued", steps=[JobStep(name="queued", at=T)],
                  created_at=T)  # fmt: skip
    b = JobRecord(id="b", tic_id=2, status="queued", data_marker="sector-3", created_at=T)
    storage.create_job(a)
    storage.create_job(b)
    assert storage.queue_position("a") == 1 and storage.queue_position("b") == 2
    storage.set_job_status("a", "running", at=T)
    storage.append_job_step("a", JobStep(name="started", at=T))
    assert storage.queue_position("a") is None and storage.queue_position("b") == 1
    got = storage.get_job("a")
    assert got.status == "running" and got.started_at == T
    assert [s.name for s in got.steps] == ["queued", "started"]
    assert storage.get_job("b").data_marker == "sector-3"
    storage.set_job_status("a", "failed", at=T, error="boom")
    assert storage.get_job("a").error == "boom" and storage.get_job("a").finished_at == T
    assert storage.fail_unfinished_jobs("restart", T) == 1
    assert storage.get_job("b").status == "failed"
    assert storage.queue_position("missing") is None and storage.get_job("missing") is None


def test_atomic_rolls_back_and_nests(storage):
    with pytest.raises(RuntimeError), storage.atomic():
        storage.put_star_name("a", 1, T)
        with storage.atomic():
            storage.put_star_name("b", 2, T)
        raise RuntimeError
    assert storage.get_star_name("a") is None and storage.get_star_name("b") is None
    with storage.atomic(), storage.atomic():
        storage.put_star_name("a", 1, T)
    assert storage.get_star_name("a") == 1


def test_status_rows(storage):
    storage.put_status("run", {"n": 1}, T)
    storage.put_status("run", {"n": 2}, T)
    storage.put_status("source:tns", {"state": "live"}, T)
    assert storage.get_status() == {"run": {"n": 2}, "source:tns": {"state": "live"}}


def test_sqlite_file_survives_reopen(tmp_path):
    path = str(tmp_path / "x.db")
    s = SqliteStorage(path)
    s.put_star_analysis(_analysis(5))
    s.close()
    s = build_storage(Settings(db_path=path))
    assert s.get_star_analysis(5).tic_id == 5
    s.close()
