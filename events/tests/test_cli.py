from __future__ import annotations

import json
from datetime import datetime

import pytest
from recording import meta

from skyevents import cli
from skyevents.util import parse_age


def test_parse_age():
    now = datetime.fromisoformat("2026-09-25T12:00:00+00:00")
    assert parse_age("7d", now).isoformat() == "2026-09-18T12:00:00+00:00"
    assert parse_age("12h", now).isoformat() == "2026-09-25T00:00:00+00:00"
    assert parse_age("2026-09-01", now).isoformat() == "2026-09-01T00:00:00+00:00"


def test_ingest_cli_writes_events_and_status(replay, tmp_path, monkeypatch, capsys):
    replay("cneos_2026-09")
    m = meta("cneos_2026-09")
    out = tmp_path / "out" / "events.json"
    # The fixture holds the fetch window only; the status lookup (latest fireball) is stubbed.
    from skyevents.adapters import cneos

    monkeypatch.setattr(cneos, "last_event_at", lambda now: datetime.fromisoformat("2026-09-15T11:26:13+00:00"))
    assert cli.main(["--since", m["since"], "--until", m["until"], "--sources", "cneos", "--out", str(out)]) == 0
    doc = json.loads(out.read_text())
    status = json.loads((tmp_path / "out" / "status.json").read_text())
    assert doc["count"] == len(doc["events"]) == 4
    assert doc["since"] == "2026-09-01T00:00:00Z" and doc["until"] == "2026-09-25T00:00:00Z"
    st = status["sources"]["cneos"]
    assert st["events"] == 4 and st["last_event_at"] == "2026-09-15T11:26:13Z" and st["error"] is None
    assert "cneos" in capsys.readouterr().err


def test_unknown_source_is_an_error():
    with pytest.raises(ValueError):
        cli.main(["--sources", "nope", "--out", "/dev/null"])
