import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fixtures import scenarios as sc
from recording import HTTP_DIR

from skysources import status


def test_stream_status_from_recorded_services(replay):
    replay("status")
    s = status.stream_status(max_age_s=0)
    assert set(s) == {"last_alert_at", "last_scheduled_visit_at", "is_live", "checked_at"}
    assert s["last_alert_at"] == "2026-07-14T10:03:00+00:00"
    assert s["last_scheduled_visit_at"] == "2026-09-11T09:43:52+00:00"
    assert s["is_live"] is False  # more than 72 h before any real "now"


def test_stream_status_is_cached_for_an_hour(replay, monkeypatch):
    replay("status")
    first = status.stream_status()
    monkeypatch.setattr(status, "last_alert_at", lambda: pytest.fail("should come from cache"))
    assert status.stream_status() == first


def test_live_when_alert_within_72h(monkeypatch):
    recent = datetime.now(UTC) - timedelta(hours=5)
    monkeypatch.setattr(status, "last_alert_at", lambda: recent)
    monkeypatch.setattr(status, "last_scheduled_visit_at", lambda: recent)
    assert status.stream_status(max_age_s=0)["is_live"] is True


def test_services_down_still_gives_a_banner(monkeypatch):
    def down():
        raise status.UpstreamError("down")

    monkeypatch.setattr(status, "last_alert_at", down)
    monkeypatch.setattr(status, "last_scheduled_visit_at", down)
    s = status.stream_status(max_age_s=0)
    assert s["last_alert_at"] is None and s["last_scheduled_visit_at"] is None and s["is_live"] is False


def _recorded_nights():
    doc = json.loads((HTTP_DIR / "status.json").read_text())
    rows = next(json.loads(v["text"]) for v in doc["responses"].values() if v["url"].endswith("/statistics"))
    return sorted(date.fromisoformat(r["f:night"]) for r in rows if int(r["f:alerts"]) > 0)


@pytest.mark.parametrize("n", sc.WINDOW_NIGHTS)
def test_latest_observed_window_holds_n_nights_with_alerts(replay, n):
    replay("status")
    start, end = status.latest_observed_window(n)
    assert end == datetime(2026, 7, 15, tzinfo=UTC)
    inside = [d for d in _recorded_nights() if start.date() <= d < end.date()]
    assert len(inside) == n


def test_window_rejects_zero():
    with pytest.raises(ValueError):
        status.latest_observed_window(0)
