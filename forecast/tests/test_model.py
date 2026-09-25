import math
from dataclasses import dataclass
from datetime import timedelta

import pytest
from conftest import NOW, TONIGHT

from skyforecast import (
    CatchType,
    Exposure,
    ForecastConfig,
    Pointing,
    Providers,
    SkybotObject,
    Sphere,
    forecast,
)
from skyforecast.fakes import Broken
from skyforecast.geometry import cap_area_deg2, parse_grid, pixel_area_deg2

T0 = TONIGHT.start + timedelta(hours=2)
NSIDE = 4
NPIX = 12 * NSIDE**2
AREA = pixel_area_deg2(parse_grid(f"healpix nside={NSIDE}"))


@dataclass
class UniformSky:
    """Every pixel: 100 visits in 100 days, 100 variable stars -> 1 per pixel-area per visit."""

    def heatmap(self):
        return {"generated_at": "2026-09-01T00:00:00Z", "grid": f"healpix nside={NSIDE}",
                "cells": [{"pix": p, "counts": {"variable_star": 100}} for p in range(NPIX)]}

    def exposure(self):
        return Exposure(f"healpix nside={NSIDE}", {p: 100.0 for p in range(NPIX)}, 100.0)


@dataclass
class ListSchedule:
    items: list

    def pointings(self, window):
        return list(self.items)


@dataclass
class ListSkybot:
    rows: list

    def cone(self, ra, dec, radius, epoch):
        return list(self.rows)


SKY = UniformSky()
S = Sphere(30, -10, 0.5)
RATE = 1.0 / AREA  # variable stars per deg^2 per visit


def vs(f):
    return f.mean_count(CatchType.variable_star)


def test_visit_probability_and_expected_counts_by_hand():
    sched = ListSchedule([Pointing(T0, 30, -10, "r", 0.5), Pointing(T0, 30, -10, "g", 0.3)])
    f = forecast(S, TONIGHT, Providers(schedule=sched, heatmap=SKY, exposure=SKY), now=NOW)
    assert f.rubin_visit_probability == pytest.approx(1 - 0.5 * 0.7)
    V = 0.5 + 0.3
    assert vs(f) == pytest.approx(RATE * cap_area_deg2(0.5) * V, rel=1e-3)
    assert [v.band for v in f.visits] == ["r", "g"]


def test_default_p_exec_and_partial_overlap():
    # Footprint edge cuts through the sphere centre -> roughly half covered.
    edge = 30 + ForecastConfig().fov_radius_deg / math.cos(math.radians(10))
    sched = ListSchedule([Pointing(T0, edge, -10, "i")])
    f = forecast(S, TONIGHT, Providers(schedule=sched, heatmap=SKY, exposure=SKY), now=NOW)
    assert f.rubin_visit_probability == pytest.approx(0.8)
    # Flat two-circle lens (r=0.5, R=fov, d=R): the curved edge covers a bit under half.
    r, R = 0.5, ForecastConfig().fov_radius_deg
    d = R
    lens = (r**2 * math.acos((d**2 + r**2 - R**2) / (2 * d * r))
            + R**2 * math.acos((d**2 + R**2 - r**2) / (2 * d * R))
            - 0.5 * math.sqrt((-d + r + R) * (d + r - R) * (d - r + R) * (d + r + R)))
    frac = lens / (math.pi * r**2)
    assert 0.45 < frac < 0.5
    assert vs(f) == pytest.approx(RATE * cap_area_deg2(0.5) * 0.8 * frac, rel=0.03)


def test_pointings_outside_window_or_far_away_are_ignored():
    sched = ListSchedule([
        Pointing(TONIGHT.end + timedelta(minutes=1), 30, -10, "r"),
        Pointing(TONIGHT.start - timedelta(minutes=1), 30, -10, "r"),
        Pointing(T0, 40, -10, "r"),
    ])
    f = forecast(S, TONIGHT, Providers(schedule=sched, heatmap=SKY), now=NOW)
    assert f.rubin_visit_probability == 0.0
    assert f.visits == []
    assert all(e.mean_count == 0 for e in f.expected)
    assert "rubin_schedule(0 of 3 pointings overlap)" in f.inputs_used


def test_outside_schedule_still_lists_known_objects_with_zero_catch_probability():
    rows = [SkybotObject("(1) Ceres", "MB>Outer", 30.1, -10.1, 8.0)]
    f = forecast(S, TONIGHT, Providers(schedule=ListSchedule([]), heatmap=SKY,
                                       skybot=ListSkybot(rows)), now=NOW)
    assert [o.name for o in f.known_solar_system_objects] == ["(1) Ceres"]
    assert f.mean_count(CatchType.asteroid) == 0


def test_no_schedule_uses_exposure_climatology():
    f = forecast(S, TONIGHT, Providers(heatmap=SKY, exposure=SKY), now=NOW)
    V = 1.0 * TONIGHT.days  # 100 visits / 100 days
    assert f.rubin_visit_probability == pytest.approx(1 - math.exp(-V), rel=1e-3)
    assert vs(f) == pytest.approx(RATE * cap_area_deg2(0.5) * V, rel=1e-3)
    assert f.visits == []
    assert any(s.startswith("no:rubin_schedule (not provided) - base rates only; visits from "
                            "exposure climatology") for s in f.inputs_used)


def test_no_schedule_no_exposure_is_per_visit_and_probability_unknown():
    f = forecast(S, TONIGHT, Providers(heatmap=SKY), now=NOW)
    assert f.rubin_visit_probability is None
    assert vs(f) == pytest.approx(RATE * cap_area_deg2(0.5) * 100, rel=1e-3)  # 100 counts/1 visit
    assert any("PER SINGLE VISIT" in s for s in f.inputs_used)
    assert any(s.startswith("no:exposure") for s in f.inputs_used)


def test_broken_providers_degrade_and_say_error():
    f = forecast(S, TONIGHT, Providers(schedule=Broken(), heatmap=SKY, exposure=Broken(),
                                       skybot=Broken()), now=NOW)
    assert f.rubin_visit_probability is None
    joined = " | ".join(f.inputs_used)
    for name in ("rubin_schedule", "exposure", "skybot"):
        assert f"no:{name} (error)" in joined


def test_incompatible_exposure_does_not_kill_heatmap():
    bad = ListExposure(Exposure("healpix nside=8", {}, 10))
    f = forecast(S, TONIGHT, Providers(heatmap=SKY, exposure=bad), now=NOW)
    assert vs(f) > 0
    assert any(s.startswith("heatmap(") for s in f.inputs_used)


@dataclass
class ListExposure:
    e: Exposure

    def exposure(self):
        return self.e


def test_no_inputs_at_all_still_returns_a_valid_forecast():
    f = forecast(S, TONIGHT, None, now=NOW)
    assert f.rubin_visit_probability is None
    assert len(f.expected) == 15 and all(e.mean_count == 0 for e in f.expected)
    assert {s.split(" ")[0] for s in f.inputs_used} == {
        "no:heatmap", "no:rubin_schedule", "no:skybot"}


def test_known_asteroids_raise_asteroid_expectation():
    sched = ListSchedule([Pointing(T0, 30, -10, "r", 0.8),
                          Pointing(T0 + timedelta(minutes=33), 30, -10, "r", 0.8)])
    rows = [SkybotObject(f"a{i}", "MB>Middle", 30.0 + 0.01 * i, -10, 20.0) for i in range(5)]
    base = forecast(S, TONIGHT, Providers(schedule=sched, heatmap=SKY), now=NOW)
    with_sb = forecast(S, TONIGHT, Providers(schedule=sched, heatmap=SKY,
                                             skybot=ListSkybot(rows)), now=NOW)
    b = base.mean_count(CatchType.asteroid)
    expected = 5 * (1 - 0.2 * 0.2) + 0.5 * b
    assert with_sb.mean_count(CatchType.asteroid) == pytest.approx(expected, rel=1e-3)
    assert with_sb.mean_count(CatchType.asteroid) > b
    # Non-solar types untouched.
    assert vs(with_sb) == vs(base)


def test_generated_at_defaults_to_now_utc():
    f = forecast(S, TONIGHT, None)
    assert f.generated_at.tzinfo is not None


def test_worked_example_ordering(full):
    """Asteroid density: ecliptic >> high galactic latitude; empty schedule -> zero."""
    eclip = forecast(Sphere(5, 2.2, 0.5), TONIGHT, full, now=NOW)
    sgp = forecast(Sphere(12.86, -27.13, 8), TONIGHT, full, now=NOW)
    outside = forecast(Sphere(150, -40, 2), TONIGHT, full, now=NOW)
    per_area = lambda f: f.mean_count(CatchType.asteroid) / cap_area_deg2(f.sphere.radius_deg)  # noqa: E731
    assert per_area(eclip) > 10 * per_area(sgp)
    assert sgp.mean_count(CatchType.active_galaxy) > eclip.mean_count(CatchType.active_galaxy)
    assert outside.rubin_visit_probability == 0
    assert sum(e.mean_count for e in outside.expected) == 0


def test_sliver_overlap_counts_as_a_visit_even_if_grid_misses_it():
    # Footprint edge 0.001 deg inside the sphere: exact geometry says overlap.
    R = ForecastConfig().fov_radius_deg
    sched = ListSchedule([Pointing(T0, 30, -10 - 0.5 - R + 0.001, "y")])
    f = forecast(S, TONIGHT, Providers(schedule=sched, heatmap=SKY, exposure=SKY), now=NOW)
    assert f.rubin_visit_probability == pytest.approx(0.8)
    assert len(f.visits) == 1
    assert vs(f) < 1e-3
