from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.contract import Forecast
from api.routes.forecast import parse_window

Q = {"ra": 150.0, "dec": -20.0, "radius": 2.0}


def test_forecast_default_window(client, alice):
    r = client.get("/forecast", params=Q, headers=alice)
    assert r.status_code == 200, r.text
    f = Forecast.model_validate(r.json())
    assert f.sphere.ra_deg == 150.0 and f.sphere.radius_deg == 2.0
    assert f.window.end - f.window.start == timedelta(days=7)
    assert 0 <= f.rubin_visit_probability <= 1
    assert all(f.window.start <= v.time < f.window.end for v in f.visits)
    assert f.inputs_used


def test_forecast_iso_interval(client, alice):
    window = "2026-10-01T00:00:00Z/2026-10-03T12:00:00Z"
    r = client.get("/forecast", params={**Q, "window": window}, headers=alice)
    assert r.status_code == 200, r.text
    f = Forecast.model_validate(r.json())
    assert f.window.start == datetime(2026, 10, 1, tzinfo=UTC)
    assert f.window.end == datetime(2026, 10, 3, 12, tzinfo=UTC)


@pytest.mark.parametrize("window", ["1h", "12h", "1d", "30d", "720h"])
def test_forecast_duration_windows(client, alice, window):
    assert client.get("/forecast", params={**Q, "window": window}, headers=alice).status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {**Q, "window": "31d"},
        {**Q, "window": "0h"},
        {**Q, "window": "7w"},
        {**Q, "window": "soon"},
        {**Q, "window": "2026-10-03T00:00:00Z/2026-10-01T00:00:00Z"},
        {**Q, "window": "2026-10-01T00:00:00Z/2026-11-15T00:00:00Z"},
        {**Q, "window": "yesterday/today"},
        {**Q, "ra": 360},
        {**Q, "dec": -91},
        {**Q, "radius": 0.01},
        {**Q, "radius": 11},
        {"ra": 1, "dec": 1},
        {**Q, "ra": "east"},
    ],
)
def test_forecast_validation(client, alice, params):
    assert client.get("/forecast", params=params, headers=alice).status_code == 422


def test_forecast_needs_player(client):
    assert client.get("/forecast", params=Q).status_code == 400


def test_parse_window_naive_times_are_utc():
    now = datetime(2026, 9, 25, tzinfo=UTC)
    start, end = parse_window("2026-10-01T00:00:00/2026-10-02T00:00:00", now)
    assert start.tzinfo is not None and end - start == timedelta(days=1)
