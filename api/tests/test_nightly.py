from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from api.contract import Cutouts, Discovery, Sphere, StarTarget
from api.models import TrapRecord
from api.nightly import main, run_nightly
from api.storage.sqlite import SqliteStorage
from tests.conftest import SKY, TIC, wait_job, wipe_postgres

T0 = datetime(2026, 9, 20, tzinfo=UTC)


class ScriptedAlerts:
    """Objects with fixed detection times; returns those detected in [since, until)."""

    def __init__(self):
        self.detections: list[tuple[str, datetime]] = []
        self.fail = False

    def alerts_in_sphere(self, sphere, since, until):
        if self.fail:
            raise ConnectionError("broker down")
        out = {}
        for oid, t in sorted(self.detections, key=lambda x: x[1]):
            if since <= t < until and oid not in out:
                out[oid] = Discovery(
                    id=oid,
                    type="supernova",
                    confidence=0.6,
                    source="rubin",
                    origin="scripted",
                    ra_deg=sphere.ra_deg,
                    dec_deg=sphere.dec_deg,
                    detected_at=t,
                    known_status="not_on_lists",
                    cutouts=Cutouts(),
                    explanation="Best guess: supernova.",
                    raw={"brightness": 18.0},
                )
        return list(out.values())


def _sky_trap(storage, player_id: str, checked: datetime) -> TrapRecord:
    trap = TrapRecord(
        id=str(uuid.uuid4()),
        player_id=player_id,
        kind="sky",
        sphere=Sphere(**SKY),
        created_at=checked,
        last_checked_at=checked,
    )
    storage.create_trap(trap)
    return trap


def test_sky_trap_gets_only_new_alerts_and_is_idempotent(services):
    alerts = services.alerts = ScriptedAlerts()
    storage = services.storage
    alerts.detections = [
        ("rubin:obj:1", T0 - timedelta(days=1)),  # before the last check: not new
        ("rubin:obj:2", T0 + timedelta(hours=5)),
        ("rubin:obj:3", T0 + timedelta(hours=20)),
        ("rubin:obj:3", T0 + timedelta(hours=22)),  # a second alert, same object
    ]
    trap = _sky_trap(storage, "p1", T0)
    run1 = T0 + timedelta(days=1)

    s = run_nightly(services, now=run1)
    assert (s.sky_checked, s.new_catches, s.created, s.updated) == (1, 2, 2, 0)
    assert storage.get_trap(trap.id).last_checked_at == run1

    again = run_nightly(services, now=run1)
    assert (again.new_catches, again.created, again.updated) == (0, 0, 0)
    assert storage.count_catches() == 2

    # Next night: object 3 fires again (update, no new catch) and object 4 is new.
    alerts.detections += [
        ("rubin:obj:3", run1 + timedelta(hours=3)),
        ("rubin:obj:4", run1 + timedelta(hours=4)),
    ]
    s3 = run_nightly(services, now=run1 + timedelta(days=1))
    assert (s3.new_catches, s3.created) == (1, 1)
    assert storage.count_catches() == 3
    # The re-seen object keeps its first detection time.
    assert storage.get_discovery("rubin:obj:3").detected_at == T0 + timedelta(hours=20)


def test_changed_object_is_updated_not_duplicated(services):
    alerts = services.alerts = ScriptedAlerts()
    storage = services.storage
    alerts.detections = [("rubin:obj:9", T0 + timedelta(hours=1))]
    _sky_trap(storage, "p1", T0)
    run_nightly(services, now=T0 + timedelta(days=1))

    class Brighter(ScriptedAlerts):
        def alerts_in_sphere(self, sphere, since, until):
            return [
                d.model_copy(update={"raw": {"brightness": 17.0}, "confidence": 0.8})
                for d in super().alerts_in_sphere(sphere, since, until)
            ]

    services.alerts = Brighter()
    services.alerts.detections = [("rubin:obj:9", T0 + timedelta(days=1, hours=2))]
    s = run_nightly(services, now=T0 + timedelta(days=2))
    assert (s.new_catches, s.created, s.updated) == (0, 0, 1)
    d = storage.get_discovery("rubin:obj:9")
    assert d.confidence == 0.8
    assert d.raw["updated_at"] == (T0 + timedelta(days=2)).isoformat(timespec="microseconds")
    assert d.detected_at == T0 + timedelta(hours=1)
    assert storage.count_catches() == 1


def test_star_trap_rehunts_only_on_new_data(client, alice, services):
    hunter = services.hunter
    job_id = client.post("/traps", json={"star": {"tic_id": TIC}}, headers=alice).json()["job_id"]
    wait_job(client, job_id, alice)
    calls = len(hunter.hunt_calls)
    before = {d.id for d in services.storage.discoveries_with_prefix(f"tess:{TIC}:")}

    s = run_nightly(services)
    assert (s.star_checked, s.star_rehunted, s.star_skipped_no_new_data) == (1, 0, 1)
    assert len(hunter.hunt_calls) == calls

    hunter.markers[TIC] = "sector-200"
    s = run_nightly(services)
    assert s.star_rehunted == 1 and s.new_catches == 0 and s.created == 0 and s.updated >= 1
    assert len(hunter.hunt_calls) == calls + 1
    after = {d.id for d in services.storage.discoveries_with_prefix(f"tess:{TIC}:")}
    assert after == before

    s = run_nightly(services)
    assert s.star_rehunted == 0
    assert len(hunter.hunt_calls) == calls + 1


def test_star_without_tess_data_is_skipped(services):
    services.hunter.markers[42] = None
    services.storage.create_trap(
        TrapRecord(id="t", player_id="p", kind="star", star=StarTarget(tic_id=42), created_at=T0)
    )
    s = run_nightly(services, now=T0 + timedelta(days=1))
    assert s.star_skipped_no_new_data == 1 and not services.hunter.hunt_calls


def test_one_failing_trap_does_not_stop_the_rest(services):
    services.hunter.fail_for.add(7)
    services.storage.create_trap(
        TrapRecord(id="bad", player_id="p", kind="star", star=StarTarget(tic_id=7), created_at=T0)
    )
    services.storage.create_trap(
        TrapRecord(id="good", player_id="p", kind="star", star=StarTarget(tic_id=8), created_at=T0)
    )
    s = run_nightly(services, now=T0 + timedelta(days=1))
    assert [f["trap_id"] for f in s.failures] == ["bad"]
    assert s.star_rehunted == 2 and s.created > 0
    # The failed trap keeps its old marker, so it is retried next night.
    assert services.storage.get_trap("bad").last_tess_marker is None


def test_failed_sky_check_keeps_window(services):
    alerts = services.alerts = ScriptedAlerts()
    alerts.fail = True
    trap = _sky_trap(services.storage, "p", T0)
    s = run_nightly(services, now=T0 + timedelta(days=1))
    assert len(s.failures) == 1
    assert services.storage.get_trap(trap.id).last_checked_at == T0


def test_dry_run_writes_nothing(services):
    alerts = services.alerts = ScriptedAlerts()
    alerts.detections = [("rubin:obj:5", T0 + timedelta(hours=2))]
    trap = _sky_trap(services.storage, "p", T0)
    s = run_nightly(services, now=T0 + timedelta(days=1), dry_run=True)
    assert s.new_catches == 1
    assert services.storage.count_catches() == 0
    assert services.storage.get_trap(trap.id).last_checked_at == T0


@pytest.fixture
def cli_db(backend, tmp_path, monkeypatch, request):
    """A fresh database the CLI can reach: (open a Storage on it, CLI args). Postgres goes
    through PH_DATABASE_URL, so the env-var selection is what gets exercised."""
    if backend == "sqlite":
        monkeypatch.delenv("PH_DATABASE_URL", raising=False)
        path = str(tmp_path / "traps.db")
        return (lambda: SqliteStorage(path)), ["--db", path]
    from api.storage.postgres import PostgresStorage

    request.getfixturevalue("pg_storage")  # schema in place
    url = request.getfixturevalue("pg_url")
    wipe_postgres(url)
    monkeypatch.setenv("PH_DATABASE_URL", url)
    return (lambda: PostgresStorage(url)), []


def _seed_db(open_storage) -> None:
    storage = open_storage()
    checked = datetime.now(UTC) - timedelta(days=3)
    _sky_trap(storage, "p1", checked)
    storage.create_trap(
        TrapRecord(
            id="star", player_id="p1", kind="star", star=StarTarget(tic_id=TIC), created_at=checked
        )
    )
    storage.close()


def test_cli_main_twice(cli_db, capsys):
    open_storage, args = cli_db
    _seed_db(open_storage)
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["sky_checked"] == 1 and first["star_rehunted"] == 1
    assert first["new_catches"] > 0
    assert main(args) == 0
    second = json.loads(capsys.readouterr().out)
    assert (second["new_catches"], second["created"], second["star_rehunted"]) == (0, 0, 0)


def test_python_dash_m_entrypoint(cli_db):
    open_storage, args = cli_db
    _seed_db(open_storage)
    out = subprocess.run(
        [sys.executable, "-m", "api.nightly", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(out.stdout)["sky_checked"] == 1
