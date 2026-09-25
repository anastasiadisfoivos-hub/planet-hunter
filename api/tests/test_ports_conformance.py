"""Checks any adapter must pass. Add the real adapters to the parameter lists once wired in."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.contract import Forecast, Sphere
from api.conventions import RUBIN_ID, TESS_ID
from api.fakes.forecast import FakeForecaster
from api.fakes.rubin import FakeAlertSource
from api.fakes.tess import FakeStarHunter
from api.geometry import angular_distance_deg

UNTIL = datetime(2026, 9, 25, tzinfo=UTC)
SINCE = UNTIL - timedelta(days=7)

ALERT_SOURCES = [pytest.param(FakeAlertSource, id="fake")]
HUNTERS = [pytest.param(FakeStarHunter, id="fake")]
FORECASTERS = [pytest.param(FakeForecaster, id="fake")]


@pytest.mark.parametrize("make", ALERT_SOURCES)
@pytest.mark.parametrize(
    "sphere",
    [
        Sphere(ra_deg=150, dec_deg=-20, radius_deg=3),
        Sphere(ra_deg=359.9, dec_deg=0, radius_deg=2),  # wraps RA 0
        Sphere(ra_deg=0, dec_deg=-89, radius_deg=5),  # covers the pole
        Sphere(ra_deg=10, dec_deg=10, radius_deg=0.05),
    ],
)
def test_alert_source(make, sphere):
    found = make().alerts_in_sphere(sphere, SINCE, UNTIL)
    ids = [d.id for d in found]
    assert len(ids) == len(set(ids)), "one entry per object"
    for d in found:
        assert d.source == "rubin" and RUBIN_ID.match(d.id)
        assert SINCE <= d.detected_at < UNTIL
        assert angular_distance_deg(d.ra_deg, d.dec_deg, sphere.ra_deg, sphere.dec_deg) <= (
            sphere.radius_deg + 1e-9
        )


def test_fake_sweeps_find_something_across_the_ra_wrap():
    found = FakeAlertSource().alerts_in_sphere(
        Sphere(ra_deg=359.5, dec_deg=-10, radius_deg=4), SINCE, UNTIL
    )
    ras = {d.ra_deg < 180 for d in found}
    assert ras == {True, False}


@pytest.mark.parametrize("make", HUNTERS)
def test_star_hunter(make):
    hunter = make()
    steps: list[str] = []
    found = hunter.hunt(25155310, steps.append)
    assert steps
    assert hunter.latest_data_marker(25155310)
    for d in found:
        m = TESS_ID.match(d.id)
        assert d.source == "tess" and m and m.group(1) == "25155310"
        key = "period_days" if m.group(2) == "sig" else "peak_btjd"
        assert isinstance(d.raw[key], float)
        if d.light_curve:
            assert len(d.light_curve.time_btjd) <= 2000


@pytest.mark.parametrize("make", FORECASTERS)
def test_forecaster(make):
    sphere = Sphere(ra_deg=150, dec_deg=-20, radius_deg=2)
    f = make().forecast(sphere, SINCE, UNTIL)
    assert isinstance(f, Forecast)
    assert f.sphere == sphere
    assert (f.window.start, f.window.end) == (SINCE, UNTIL)
