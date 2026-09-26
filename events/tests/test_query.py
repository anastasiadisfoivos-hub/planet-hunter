from __future__ import annotations

import json

import pytest

from skyevents import query
from skyevents.dedup import dedup
from skyevents.util import make_event, sky


def ev(source, sid, type, t, loc=None, conf=0.5):
    return make_event(
        source=source, source_id=sid, type=type, title=sid, summary="x.", source_url="https://e.org",
        observed_at=t, reported_at=t, location=loc or sky(10, 20, 0.001), confidence=conf,
        confidence_basis="machine_guess",
    )


EVENTS = dedup([
    ev("rubin", "sn1", "supernova", "2026-09-20T00:00:00Z", conf=0.9),
    ev("ztf", "sn2", "supernova", "2026-09-24T00:00:00Z", sky(200, -30, 0.001), conf=0.3),
    ev("mpc", "neo", "near_earth_object", "2026-09-23T00:00:00Z", sky(15, 22, 0.05), conf=1.0),
    ev("donki", "flr", "solar_flare", "2026-09-22T00:00:00Z", {"frame": "sun"}, conf=1.0),
    ev("cneos", "fb", "fireball", "2026-09-21T00:00:00Z", {"frame": "earth", "lat_deg": 1, "lon_deg": 2, "alt_km": 30}, 1.0),
    ev("gcn", "grb", "gamma_ray_burst", "2026-09-25T00:00:00Z", sky(11, 20, 0.01), conf=1.0),
    ev("gcn", "ep", "unknown", "2026-09-19T00:00:00Z", sky(300, 60, 0.05), conf=1.0),
])


def ids(fs):
    return [e["id"].split(":")[1] for e in query(fs, EVENTS)]


def test_default_is_everything_newest_first():
    assert ids({}) == ["grb", "sn2", "neo", "flr", "fb", "sn1", "ep"]


def test_types_and_categories():
    assert ids({"types": ["supernova"]}) == ["sn2", "sn1"]
    assert ids({"categories": ["solar_system"]}) == ["neo"]
    assert ids({"categories": ["sun_space_weather", "earth_atmosphere"]}) == ["flr", "fb"]
    assert ids({"categories": ["high_energy"]}) == ["grb"]
    assert ids({"categories": ["transients"]}) == ["sn2", "sn1"]
    assert ids({"categories": ["other"]}) == ["ep"]


def test_time_window():
    assert ids({"since": "2026-09-22T00:00:00Z", "until": "2026-09-24T00:00:00Z"}) == ["sn2", "neo", "flr"]


def test_sources_frame_confidence():
    assert ids({"sources": ["gcn"]}) == ["grb", "ep"]
    assert ids({"frame": "earth"}) == ["fb"]
    assert ids({"frame": "sun"}) == ["flr"]
    assert ids({"min_confidence": 0.95}) == ["grb", "neo", "flr", "fb", "ep"]


def test_sky_region():
    assert ids({"region": {"ra_deg": 10, "dec_deg": 20, "radius_deg": 2}}) == ["grb", "sn1"]
    assert ids({"region": {"ra_deg": 10, "dec_deg": 20, "radius_deg": 6}}) == ["grb", "neo", "sn1"]
    assert "flr" not in ids({"region": {"ra_deg": 0, "dec_deg": 0, "radius_deg": 180}})


def test_paging():
    assert ids({"limit": 2}) == ["grb", "sn2"]
    assert ids({"limit": 2, "offset": 2}) == ["neo", "flr"]
    assert ids({"offset": 100}) == []


def test_merged_event_matches_any_member_source():
    a = ev("tns", "x", "supernova", "2026-09-20T00:00:00Z")
    a["raw"]["names"] = ["ZTFq"]
    b = ev("ztf", "ZTFq", "supernova", "2026-09-21T00:00:00Z")
    b["raw"]["names"] = ["ZTFq"]
    merged = dedup([a, b])
    assert len(query({"sources": ["ztf"]}, merged)) == 1


@pytest.mark.parametrize("bad", [
    {"types": ["planet"]}, {"categories": ["weather"]}, {"frame": "moon"},
    {"region": {"ra_deg": 400, "dec_deg": 0, "radius_deg": 1}}, {"min_confidence": 2},
    {"frame": "sun", "region": {"ra_deg": 1, "dec_deg": 0, "radius_deg": 1}},
])
def test_bad_filters(bad):
    with pytest.raises(ValueError):
        query(bad, EVENTS)


def test_loads_events_json(tmp_path, monkeypatch):
    p = tmp_path / "events.json"
    p.write_text(json.dumps({"events": EVENTS}))
    monkeypatch.setenv("SKYEVENTS_FILE", str(p))
    assert len(query({})) == len(EVENTS)
