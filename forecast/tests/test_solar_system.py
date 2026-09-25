from datetime import UTC, datetime, timedelta

import pytest

from skyforecast import CatchType, ForecastConfig, SkybotObject, Sphere
from skyforecast.solar_system import (
    PlannedVisit,
    _epochs,
    classify,
    known_objects_scheduled,
    known_objects_unscheduled,
)

T = datetime(2026, 9, 26, 3, tzinfo=UTC)
CFG = ForecastConfig()
S = Sphere(0, 0, 1)


@pytest.mark.parametrize("cls,t", [
    ("MB>Middle", CatchType.asteroid), ("Hungaria", CatchType.asteroid),
    ("Trojan", CatchType.asteroid), ("Mars-Crosser", CatchType.asteroid),
    ("NEA>Apollo", CatchType.near_earth_object), ("NEA>Atira", CatchType.near_earth_object),
    ("KBO>Classical", CatchType.trans_neptunian_object),
    ("Centaur", CatchType.trans_neptunian_object),
    ("Comet>JFc", CatchType.comet), ("Interstellar", CatchType.interstellar_object),
])
def test_classify(cls, t):
    assert classify(cls) == t


class Rows:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def cone(self, ra, dec, radius, epoch):
        self.calls += 1
        return self.rows


def test_catch_probability_combines_visits_and_depth_cut():
    rows = [
        SkybotObject("bright", "MB", 0.2, 0.0, 20.0),
        SkybotObject("g-only", "MB", 0.2, 0.1, 24.9),     # g depth 25.0, r depth 24.7
        SkybotObject("faint", "MB", 0.2, 0.2, 26.0),
        SkybotObject("nomag", "NEA>Aten", 0.2, 0.3, None),
        SkybotObject("outside", "MB", 5.0, 0.0, 15.0),    # outside the sphere: dropped
    ]
    visits = [PlannedVisit(T, 0, 0, "r", 0.8), PlannedVisit(T + timedelta(minutes=33), 0, 0,
                                                            "g", 0.5)]
    res = known_objects_scheduled(S, visits, Rows(rows), CFG, T)
    assert [o.name for o in res.objects] == ["bright", "faint", "g-only", "nomag"]
    # bright: 1 - 0.2*0.5 = 0.9; g-only: 0.5; faint: 0
    assert res.expected[CatchType.asteroid] == pytest.approx(0.9 + 0.5)
    assert res.expected[CatchType.near_earth_object] == pytest.approx(0.9)


def test_object_in_sphere_but_outside_footprint_is_listed_not_expected():
    rows = [SkybotObject("edge", "MB", 0.0, 0.9, 18)]
    visits = [PlannedVisit(T, 0, -2.0, "r", 1.0)]  # footprint reaches dec -0.25 only
    res = known_objects_scheduled(S, visits, Rows(rows), CFG, T)
    assert [o.name for o in res.objects] == ["edge"]
    assert res.expected.get(CatchType.asteroid, 0) == 0


def test_epochs_bucketed_and_capped():
    visits = [PlannedVisit(T + timedelta(minutes=m), 0, 0, "r", 0.8) for m in range(0, 600, 2)]
    ep = _epochs(visits, CFG)
    assert len(ep) == CFG.skybot_max_queries
    few = _epochs(visits[:10], CFG)  # 0..18 min -> buckets at 0 and 10
    assert len(few) == 2
    sb = Rows([])
    known_objects_scheduled(S, visits, sb, CFG, T)
    assert sb.calls == CFG.skybot_max_queries


def test_unscheduled_uses_given_catch_probability_and_depth():
    rows = [SkybotObject("a", "MB", 0.1, 0, 20), SkybotObject("b", "MB", 0.1, 0.1, 25.5)]
    res = known_objects_unscheduled(S, T, Rows(rows), 0.3, CFG)
    assert res.expected[CatchType.asteroid] == pytest.approx(0.3)
    assert len(res.objects) == 2
