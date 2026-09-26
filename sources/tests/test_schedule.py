
import pytest
from fixtures import scenarios as sc

from skysources.schedule import LSSTCAM_FOV_DEG, _box_predicate, band_from_em, schedule
from skysources.util import sep_deg


def test_past_window_has_performed_visits(replay):
    replay("schedule")
    visits = schedule(sc.SCHEDULE_SPHERE, *sc.SCHEDULE_PAST)
    assert len(visits) == 41
    reach = sc.SCHEDULE_SPHERE["radius_deg"] + LSSTCAM_FOV_DEG / 2
    for v in visits:
        assert v["status"] == "performed"
        assert v["band"] in "ugrizy"
        assert sc.SCHEDULE_PAST[0][:10] <= v["time"][:10] <= sc.SCHEDULE_PAST[1][:10]
        assert sep_deg(193.0, 14.0, v["ra_deg"], v["dec_deg"]) <= reach
    assert [v["time"] for v in visits] == sorted(v["time"] for v in visits)


def test_future_window_is_empty_while_feed_is_stale(replay):
    replay("schedule")
    assert schedule(sc.SCHEDULE_SPHERE, *sc.SCHEDULE_FUTURE) == []


def test_band_from_wavelengths():
    assert band_from_em(5.52e-07, 6.91e-07) == "r"
    assert band_from_em(8.18e-07, 9.22e-07) == "z"
    assert band_from_em(1e-6, 2e-6) is None


def test_box_predicate_drops_ra_when_wrapping_or_polar():
    assert "s_ra" in _box_predicate({"ra_deg": 180, "dec_deg": 0, "radius_deg": 1}, 2.75)
    assert "s_ra" not in _box_predicate({"ra_deg": 1, "dec_deg": 0, "radius_deg": 1}, 2.75)
    assert "s_ra" not in _box_predicate({"ra_deg": 180, "dec_deg": -88, "radius_deg": 1}, 2.75)


def test_rejects_bad_window():
    with pytest.raises(ValueError):
        schedule(sc.SCHEDULE_SPHERE, sc.SCHEDULE_PAST[1], sc.SCHEDULE_PAST[0])
