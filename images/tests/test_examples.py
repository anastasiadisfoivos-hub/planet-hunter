"""The 20 real example events, replayed from recorded answers."""

import json

import pytest
from recording import FIXTURES

from skypictures import Stats, net, pictures_for
from skypictures.models import EVENT_TYPES, IMAGE_KINDS

EVENTS = json.loads((FIXTURES / "example_events.json").read_text())
EXPECTED = json.loads((FIXTURES / "example_pictures.json").read_text())["pictures"]
BY_TYPE = {e["type"]: e for e in EVENTS}
REQUIRED = {"url", "kind", "caption", "credit", "license", "width", "height"}


def test_one_real_example_per_event_type():
    assert sorted(BY_TYPE) == sorted(EVENT_TYPES)
    assert len(EVENTS) == len(EVENT_TYPES)


@pytest.mark.parametrize("event", EVENTS, ids=[e["type"] for e in EVENTS])
def test_replay_matches_recording(replay, event):
    replay("examples")
    assert pictures_for(event) == EXPECTED[event["id"]]


@pytest.mark.parametrize("event", EVENTS, ids=[e["type"] for e in EVENTS])
def test_every_image_follows_the_contract(event):
    for img in EXPECTED[event["id"]]:
        assert set(img) == REQUIRED
        assert img["kind"] in IMAGE_KINDS
        assert img["caption"].strip() and img["credit"].strip() and img["license"].strip()
        assert isinstance(img["width"], int) and isinstance(img["height"], int)
        assert img["url"].startswith("https://")


def test_what_each_frame_gets():
    kinds = {t: [i["kind"] for i in EXPECTED[e["id"]]] for t, e in BY_TYPE.items()}
    triplet = ["sky_context", "cutout_reference", "cutout_new", "cutout_difference"]
    for t in ("supernova", "tidal_disruption_event", "nova", "active_galaxy_flare", "variable_star",
              "stellar_flare", "microlensing", "asteroid", "unknown"):
        assert kinds[t] == triplet, t
    for t in ("kilonova", "near_earth_object", "comet", "interstellar_object", "gamma_ray_burst", "neutrino",
              "gravitational_wave"):
        assert kinds[t] == ["sky_context"], t
    assert kinds["solar_flare"] == ["solar"]
    assert kinds["coronal_mass_ejection"] == ["solar", "solar"]
    assert kinds["fireball"] == []
    assert kinds["geomagnetic_storm"] == []  # older than SWPC's 24-hour archive: no image rather than a wrong one


def test_rubin_and_ztf_cutouts_both_exercised():
    sn = EXPECTED[BY_TYPE["supernova"]["id"]]
    tde = EXPECTED[BY_TYPE["tidal_disruption_event"]["id"]]
    assert all("api.lsst.fink-portal.org" in i["url"] for i in sn[1:])
    assert all("api.ztf.fink-portal.org" in i["url"] for i in tde[1:])
    assert "new light only" in sn[3]["caption"] and "new light only" in tde[3]["caption"]


def test_dead_links_are_dropped_and_counted(replay, monkeypatch):
    replay("examples")
    event = BY_TYPE["supernova"]
    recorded = net.Net.probe
    dead = EXPECTED[event["id"]][2]["url"]

    def probe(self, url):
        return net.Probe(False, 404, "text/html", reason="HTTP 404") if url == dead else recorded(self, url)

    monkeypatch.setattr(net.Net, "probe", probe)
    stats = Stats()
    got = pictures_for(event, stats=stats)
    assert [i["url"] for i in got] == [i["url"] for i in EXPECTED[event["id"]] if i["url"] != dead]
    assert stats.candidates == 4 and stats.kept == 3 and stats.dropped == [(dead, "HTTP 404")]


def test_unchecked_mode_makes_no_probes(replay, monkeypatch):
    replay("examples")
    monkeypatch.setattr(net.Net, "probe", lambda self, url: pytest.fail("probed"))
    got = pictures_for(BY_TYPE["tidal_disruption_event"], check=False)
    assert [i["kind"] for i in got] == ["sky_context", "cutout_reference", "cutout_new", "cutout_difference"]
    assert got[1]["width"] is None  # unknown until fetched


def test_one_failing_source_keeps_the_others(replay, monkeypatch):
    replay("examples")
    from skypictures import core, cutouts

    def boom(event):
        raise RuntimeError("Fink down")

    monkeypatch.setitem(core.PROVIDERS, "sky", [core.context.sky_context, boom])
    stats = Stats()
    got = pictures_for(BY_TYPE["supernova"], stats=stats)
    assert [i["kind"] for i in got] == ["sky_context"]
    assert "Fink down" in stats.provider_errors[0]
    assert cutouts  # imported module still intact
