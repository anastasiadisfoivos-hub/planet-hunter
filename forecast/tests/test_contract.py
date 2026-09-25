from datetime import UTC, datetime

import pytest
from conftest import NOW, TONIGHT

from skyforecast import CatchType, Forecast, Sphere, Window, forecast

CONTRACT_KEYS = {"sphere", "window", "rubin_visit_probability", "visits", "expected",
                 "known_solar_system_objects", "generated_at", "inputs_used"}


@pytest.mark.parametrize("r", [0.049, 10.01, -1])
def test_sphere_radius_bounds(r):
    with pytest.raises(ValueError):
        Sphere(0, 0, r)


def test_sphere_bounds_inclusive_and_ra_wraps():
    assert Sphere(-10, 0, 0.05).ra_deg == 350
    Sphere(0, 90, 10)


def test_window_rejects_naive_and_reversed():
    with pytest.raises(ValueError):
        Window(datetime(2026, 1, 1), datetime(2026, 1, 2))
    with pytest.raises(ValueError):
        Window(datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))


def test_forecast_dict_matches_contract_and_round_trips(full):
    f = forecast(Sphere(5, 2.2, 0.5), TONIGHT, full, now=NOW)
    d = f.to_dict()
    assert set(d) == CONTRACT_KEYS
    assert set(d["sphere"]) == {"ra_deg", "dec_deg", "radius_deg"}
    assert set(d["window"]) == {"start", "end"}
    assert all(set(v) == {"time", "band"} for v in d["visits"])
    assert [e["type"] for e in d["expected"]] == [t.value for t in CatchType]
    assert all(set(e) == {"type", "mean_count"} for e in d["expected"])
    assert all(set(o) == {"name", "type", "ra_deg", "dec_deg"}
               for o in d["known_solar_system_objects"])
    assert d["generated_at"] == "2026-09-25T18:00:00Z"
    assert all(isinstance(s, str) for s in d["inputs_used"])
    assert Forecast.from_dict(d).to_dict() == d


def test_accepts_dict_inputs(full):
    f = forecast({"ra_deg": 5, "dec_deg": 2.2, "radius_deg": 0.5},
                 {"start": "2026-09-26T00:00:00Z", "end": "2026-09-26T10:00:00Z"}, full, now=NOW)
    assert f.window == TONIGHT
