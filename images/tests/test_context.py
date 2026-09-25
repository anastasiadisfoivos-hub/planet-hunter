import json
from urllib.parse import parse_qs, urlsplit

import pytest
from recording import FIXTURES

from skypictures import context, net
from skypictures.net import FetchError, inspect_image

EVENTS = {e["type"]: e for e in json.loads((FIXTURES / "example_events.json").read_text())}
IMAGES = FIXTURES / "images"


def q(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_field_of_view_by_type():
    assert context.field_of_view("supernova", 0) == pytest.approx(2.5 / 60)
    assert context.field_of_view("tidal_disruption_event", 0) == pytest.approx(1.5 / 60)
    assert context.field_of_view("asteroid", 0) > context.field_of_view("supernova", 0) * 5
    assert context.field_of_view("something_new", 0) == context.DEFAULT_FOV_DEG


def test_field_widens_for_error_and_is_capped():
    assert context.field_of_view("neutrino", 16.3 / 60) == 1.0          # default already covers it
    assert context.field_of_view("gamma_ray_burst", 1.0) == pytest.approx(2.4)
    assert context.field_of_view("gravitational_wave", 40.0) == context.MAX_FOV_DEG


def test_survey_choice_follows_the_footprint(replay):
    replay("examples")
    south = EVENTS["supernova"]["location"]  # Dec -49: Legacy Surveys yes, Pan-STARRS no
    assert context.choose_survey(south["ra_deg"], south["dec_deg"], 0.04) is context.LEGACY
    nova = EVENTS["nova"]["location"]
    assert context.choose_survey(nova["ra_deg"], nova["dec_deg"], 0.05) is context.PANSTARRS


def test_wide_fields_use_dss2_without_asking(monkeypatch):
    monkeypatch.setattr(net.Net, "text", lambda *a, **k: pytest.fail("no MocServer call expected"))
    assert context.choose_survey(10, 10, 1.0) is context.DSS2


def test_mocserver_down_falls_back_to_dss2(monkeypatch):
    def down(*a, **k):
        raise FetchError("alasky: HTTP 503")

    monkeypatch.setattr(net.Net, "text", down)
    assert context.choose_survey(10, 10, 0.04) is context.DSS2


def test_url_and_caption_for_supernova(replay):
    replay("examples")
    [img] = context.sky_context(EVENTS["supernova"])
    p = q(img["url"])
    loc = EVENTS["supernova"]["location"]
    assert p["hips"] == context.LEGACY.hips_id and p["width"] == "800" and p["format"] == "jpg"
    assert float(p["ra"]) == pytest.approx(loc["ra_deg"]) and float(p["dec"]) == pytest.approx(loc["dec_deg"])
    assert "Crosshair: the supernova is at the exact centre" in img["caption"]
    assert "not the supernova itself" in img["caption"]
    assert "Legacy" in img["credit"] and "hips2fits" in img["credit"]


def test_moving_object_caption_says_it_is_not_in_the_picture(replay):
    replay("examples")
    [img] = context.sky_context(EVENTS["interstellar_object"])
    assert "The interstellar object itself is not in this picture" in img["caption"]


def test_large_error_caption_for_gravitational_waves(replay):
    replay("examples")
    [img] = context.sky_context(EVENTS["gravitational_wave"])
    assert "most likely position is at the centre" in img["caption"]
    assert q(img["url"])["hips"] == context.DSS2.hips_id


def test_non_sky_events_get_no_context():
    assert context.sky_context(EVENTS["solar_flare"]) == []


# -- image inspection on real bytes ------------------------------------------------------------

def test_real_cutout_passes():
    p = inspect_image(200, "image/png", (IMAGES / "rubin_science_cutout.png").read_bytes())
    assert p.ok and (p.width, p.height) == (30, 30)


def test_blank_frame_outside_footprint_is_rejected():
    p = inspect_image(200, "image/jpeg", (IMAGES / "panstarrs_outside_footprint.jpg").read_bytes())
    assert not p.ok and "blank" in p.reason and p.width == 600


def test_error_page_and_broken_bytes_are_rejected():
    assert inspect_image(404, "text/html", b"<html>") .reason == "HTTP 404"
    assert "not an image" in inspect_image(200, "text/html; charset=utf-8", b"<html>").reason
    png = (IMAGES / "rubin_science_cutout.png").read_bytes()
    assert "undecodable" in inspect_image(200, "image/png", png[:40]).reason
