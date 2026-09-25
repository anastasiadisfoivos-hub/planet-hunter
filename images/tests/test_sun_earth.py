import json
from datetime import UTC, datetime, timedelta

import pytest
from recording import FIXTURES

from skypictures import earth, pictures_for, sun

EVENTS = {e["type"]: e for e in json.loads((FIXTURES / "example_events.json").read_text())}
NOAA = json.loads((FIXTURES / "noaa_event.json").read_text())


def test_flare_uses_131_at_peak_with_region(replay):
    replay("examples")
    [img] = sun.solar_images(EVENTS["solar_flare"])
    assert img["url"].endswith("_1024_0131.jpg") and img["url"].startswith(sun.SDO_BROWSE)
    assert "2 min before the flare peak (18:17 UTC)" in img["caption"]
    assert "N14E90 (NOAA active region 14535): on the left (east) edge of the disk" in img["caption"]
    assert img["credit"] == "Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams"


def test_cme_gets_sdo_193_and_lasco(replay):
    replay("examples")
    sdo, lasco = sun.solar_images(EVENTS["coronal_mass_ejection"])
    assert sdo["url"].endswith("_1024_0193.jpg")
    assert lasco["url"].startswith(sun.HELIOVIEWER + "/downloadImage/") and "LASCO C2" in lasco["caption"]
    assert "after the reported time" in lasco["caption"]


def test_sdo_listing_pick_is_nearest_1024(replay):
    replay("examples")
    t = datetime(2026, 9, 19, 18, 17, tzinfo=UTC)
    it, stem = sun.sdo_nearest(t, "131")
    assert stem == "20260919_181456" and abs(it - t) < timedelta(minutes=10)
    assert sun.sdo_url(stem, "131", 512).endswith("/2026/09/19/20260919_181456_512_0131.jpg")


def test_falls_back_to_helioviewer_when_sdo_has_nothing(monkeypatch):
    monkeypatch.setattr(sun, "sdo_nearest", lambda t, wl: None)
    monkeypatch.setattr(sun, "helioviewer_nearest",
                        lambda t, src: (t, "777") if src == "131" else None)
    [img] = sun.solar_images(EVENTS["solar_flare"])
    assert img["url"] == sun.helioviewer_url("777") and "Helioviewer" in img["credit"]


def test_lasco_frame_before_the_cme_is_refused(monkeypatch):
    monkeypatch.setattr(sun, "sdo_nearest", lambda t, wl: None)
    monkeypatch.setattr(sun, "helioviewer_nearest",
                        lambda t, src: (t - timedelta(hours=1), "1") if src.startswith("LASCO") else None)
    assert sun.solar_images(EVENTS["coronal_mass_ejection"]) == []


def test_lasco_c3_used_when_c2_has_a_gap(monkeypatch):
    monkeypatch.setattr(sun, "sdo_nearest", lambda t, wl: None)
    frames = {"LASCO C2": None, "LASCO C3": "33"}
    monkeypatch.setattr(sun, "helioviewer_nearest",
                        lambda t, src: (t, frames[src]) if frames.get(src) else None)
    [img] = sun.solar_images(EVENTS["coronal_mass_ejection"])
    assert "LASCO C3" in img["caption"] and "about 30 solar radii" in img["caption"]


@pytest.mark.parametrize("loc,words", [
    ("N14E90", "on the left (east) edge of the disk, 14° north of the equator"),
    ("S35W70", "near the right (west) edge of the disk, 35° south of the equator"),
    ("N03W05", "near the centre of the disk, near the solar equator"),
    ("S20E30", "left of centre, 20° south of the equator"),
])
def test_describe_location(loc, words):
    assert sun.describe_location(loc) == words


def test_region_found_in_summary_when_raw_lacks_it():
    e = {**EVENTS["solar_flare"], "raw": {}, "summary": "M1 flare from S12W40 today"}
    assert sun.flare_region(e) == ("S12W40", None)


# -- Earth ----------------------------------------------------------------------------------------

def at(iso):
    return lambda: datetime.fromisoformat(iso)


def test_fireball_gets_nothing():
    assert pictures_for(EVENTS["fireball"], check=False) == []


def test_old_storm_gets_nothing_rather_than_a_wrong_time():
    assert earth.earth_images(EVENTS["geomagnetic_storm"]) == []  # 2026-08-08, far beyond 24 h


def test_current_storm_gets_noaa_latest_maps(replay, monkeypatch):
    replay("noaa")
    monkeypatch.setattr(earth, "_now", at(NOAA["now"]))
    got = pictures_for(NOAA["event"])
    assert got == NOAA["pictures"]
    assert [i["url"] for i in got] == [earth.LATEST["north"], earth.LATEST["south"]]
    for img in got:
        assert img["kind"] == "forecast_map"
        assert img["caption"].startswith("NOAA aurora forecast, latest (model)")
        assert "not a photograph" in img["caption"] and "Public domain" in img["license"]
        assert img["thumb_url"] == img["url"]


def test_24_hour_limit(monkeypatch):
    storm = {**NOAA["event"], "observed_at": "2026-09-25T00:00:00Z"}
    monkeypatch.setattr(earth, "_now", at("2026-09-25T23:59:00Z"))
    assert earth.is_current(storm)
    monkeypatch.setattr(earth, "_now", at("2026-09-26T00:01:00Z"))
    assert not earth.is_current(storm) and earth.earth_images(storm) == []
    monkeypatch.setattr(earth, "_now", at("2026-09-24T23:00:00Z"))  # forecast start ahead: ongoing
    assert earth.is_current(storm)


def test_hemisphere_follows_latitude(monkeypatch):
    monkeypatch.setattr(earth, "_now", at(NOAA["now"]))
    south = {**NOAA["event"], "location": {"frame": "earth", "lat_deg": -45.0, "lon_deg": 170.0, "alt_km": None}}
    [img] = earth.earth_images(south)
    assert img["url"] == earth.LATEST["south"]
    assert earth._hemispheres(NOAA["event"]) == ["north", "south"]  # no latitude given: both
