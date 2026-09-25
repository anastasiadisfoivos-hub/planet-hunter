"""The whole pipeline on a recorded real week (fixtures/http/live_week.json), offline."""

from __future__ import annotations

import json
import re
from datetime import datetime

import httpx
import pytest
from recording import install_replay, meta

from skyevents.adapters import ADAPTERS
from skyevents.ingest import ingest
from skyevents.models import CATEGORIES, CATEGORY_OF, DISTANCE_BASES, EVENT_TYPES
from skyevents.query import query

M = meta("live_week")
NOW, SINCE, UNTIL = (datetime.fromisoformat(M[k].replace("Z", "+00:00")) for k in ("now", "since", "until"))
ISO_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
IMAGE_KINDS = {"cutout_reference", "cutout_new", "cutout_difference", "sky_context", "solar", "light_curve"}


@pytest.fixture(scope="module")
def week(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SKYSOURCES_CACHE", str(tmp_path_factory.mktemp("cache")))
        mp.setattr(httpx.Client, "send", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
        install_replay(mp, "live_week", "distances_week")
        events, status = ingest(SINCE, UNTIL, now=NOW)
    return events, status


def test_every_source_contributes_or_reports_why(week):
    events, status = week
    assert set(status["sources"]) == set(ADAPTERS)
    by_source = {s["source"] for e in events for s in e["raw"]["sources"]}
    for name, st in status["sources"].items():
        assert st["error"] is None, (name, st["error"])
        assert st["state"] in ("live", "paused")
        assert st["last_event_at"] is None or ISO_Z.match(st["last_event_at"])
        if st["events"]:
            assert name in by_source


def test_status_flags(week):
    _, status = week
    s = status["sources"]
    assert s["rubin"]["state"] == "paused"  # Rubin's alert stream quiet since 2026-07-14
    assert s["rubin"]["last_event_at"].startswith("2026-07-14")
    assert s["rubin"]["window"]["end"] <= "2026-07-15T00:00:00Z"
    assert s["rubin"]["note"]
    assert s["gracedb"]["state"] == "paused"  # LVK between observing runs
    for live in ("ztf", "tns", "mpc", "donki", "gcn"):
        assert s[live]["state"] == "live", live


@pytest.mark.parametrize("field", ["id", "type", "title", "summary", "source", "source_url", "observed_at",
                                   "reported_at", "location", "confidence", "confidence_basis",
                                   "brightness_mag", "images", "raw"])
def test_contract_fields_present(week, field):
    events, _ = week
    assert all(field in e for e in events)


def test_contract_values(week):
    events, _ = week
    assert len({e["id"] for e in events}) == len(events), "ids must be unique"
    for e in events:
        assert list(e) == ["id", "type", "title", "summary", "source", "source_url", "observed_at", "reported_at",
                           "location", "confidence", "confidence_basis", "brightness_mag", "images", "raw"]
        assert e["id"].startswith(e["source"] + ":") and len(e["id"]) > len(e["source"]) + 1
        assert e["type"] in EVENT_TYPES and e["type"] in CATEGORY_OF
        assert ISO_Z.match(e["observed_at"]) and ISO_Z.match(e["reported_at"])
        assert 0.0 <= e["confidence"] <= 1.0
        assert e["confidence_basis"] in ("official_report", "catalogue_match", "machine_guess")
        assert e["source_url"].startswith("https://")
        assert e["brightness_mag"] is None or -30 < e["brightness_mag"] < 35
        loc = e["location"]
        if loc["frame"] == "sky":
            assert {"frame", "ra_deg", "dec_deg", "error_deg"} <= set(loc) <= {
                "frame", "ra_deg", "dec_deg", "error_deg", "distance", "ephemeris"}
            assert 0 <= loc["ra_deg"] < 360 and -90 <= loc["dec_deg"] <= 90 and loc["error_deg"] > 0
        elif loc["frame"] == "earth":
            assert set(loc) == {"frame", "lat_deg", "lon_deg", "alt_km"}
            assert -90 <= loc["lat_deg"] <= 90 and -180 <= loc["lon_deg"] <= 180
        else:
            assert loc == {"frame": "sun"}
        for img in e["images"]:
            assert set(img) == {"url", "kind", "caption", "credit", "license", "width", "height"}
            assert img["kind"] in IMAGE_KINDS and img["url"].startswith("https://")
        assert len(json.dumps(e["raw"])) < 4000, f"raw must stay small: {e['id']}"
        assert all(s["source_url"].startswith("https://") for s in e["raw"]["sources"])


def test_honest_wording(week):
    events, _ = week
    for e in events:
        text = f"{e['title']} {e['summary']}"
        assert not re.search(r"discover", text, re.IGNORECASE), e["id"]
        sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", e["summary"].strip()) if s]
        assert 1 <= len(sentences) <= 3, (e["id"], e["summary"])  # a trailing brightness note may add one
        if e["confidence_basis"] == "machine_guess" and e["source"] in ("rubin", "ztf") and e["type"] != "unknown":
            assert "guess" in e["summary"], e["id"]


def test_every_source_has_a_real_example(week):
    events, status = week
    have = {e["source"] for e in events}
    for name, st in status["sources"].items():
        if st["events"]:
            assert name in have or any(name == s["source"] for e in events for s in e["raw"]["sources"])


def test_rubin_uses_latest_observed_nights_with_true_dates(week):
    events, _ = week
    rubin = [e for e in events if e["source"] == "rubin"]
    assert rubin
    assert all(e["observed_at"] < "2026-07-15" for e in rubin)  # real dates, not relabelled as "now"
    e = rubin[0]
    assert {i["kind"] for i in e["images"]} == {"cutout_reference", "cutout_new", "cutout_difference"}
    assert e["source_url"] == f"https://lsst.fink-portal.org/{e['raw']['diaObjectId']}"


def test_tns_and_ztf_join(week):
    events, _ = week
    joined = [e for e in events if {s["source"] for s in e["raw"]["sources"]} >= {"tns", "ztf"}]
    assert joined, "at least one TNS supernova should carry its ZTF internal name"
    e = joined[0]
    assert e["id"].startswith("tns:") and e["confidence_basis"] == "official_report"
    assert any(s["id"].startswith("ztf:ZTF") for s in e["raw"]["sources"])
    assert e["raw"]["first_observed_at"] <= e["observed_at"]


def test_gcn_burst_position_prefers_the_tightest_report(week):
    events, _ = week
    grbs = [e for e in events if e["source"] == "gcn" and e["type"] == "gamma_ray_burst"]
    assert grbs
    for e in grbs:
        assert e["location"]["error_deg"] < 20
        assert e["raw"]["time_precision"] in ("second", "day")


def test_status_counts_only_events_observed_in_the_window(week):
    events, status = week
    rubin = status["sources"]["rubin"]
    assert rubin["events"] == 0  # paused: nothing observed this week
    assert rubin["events_fetched"] > 0  # but its latest nights are in the feed
    for name, st in status["sources"].items():
        assert st["events"] <= st["events_fetched"], name
    in_window = [e for e in events if SINCE <= datetime.fromisoformat(e["observed_at"].replace("Z", "+00:00")) <= UNTIL]
    assert status["events_in_window"] == len(in_window) < status["events"]


def test_rubin_latest_nights_are_flagged_and_query_since_drops_them(week):
    events, _ = week
    rubin = [e for e in events if e["source"] == "rubin"]
    assert rubin and all(e["raw"]["from_latest_observed_window"] is True for e in rubin)
    recent = query({"since": SINCE, "limit": 1000}, events)
    assert recent and all(e["observed_at"] >= M["since"] for e in recent)
    assert not any(e["source"] == "rubin" for e in recent)  # July is not "recent"
    toggle = query({"sources": ["rubin"], "limit": 1000}, events)
    toggle += query({"sources": ["rubin"], "limit": 1000, "offset": 1000}, events)  # paging
    assert len(toggle) == len(rubin) and all(e["observed_at"] < "2026-07-15" for e in toggle)


# ------------------------------------------------------------------ distances


def _sky(events):
    return [e for e in events if e["location"]["frame"] == "sky"]


def test_every_sky_event_has_a_distance_or_an_ephemeris(week):
    events, _ = week
    for e in _sky(events):
        loc = e["location"]
        if e["type"] in CATEGORIES["solar_system"]:
            assert "ephemeris" in loc and "distance" not in loc, e["id"]
        else:
            assert "distance" in loc and "ephemeris" not in loc, e["id"]
    for e in events:
        if e["location"]["frame"] != "sky":
            assert "distance" not in e["location"] and "ephemeris" not in e["location"]


def test_distance_values_are_consistent(week):
    events, _ = week
    for e in _sky(events):
        d = e["location"].get("distance")
        if not d:
            continue
        assert list(d) == ["pc", "pc_low", "pc_high", "redshift", "basis"] and d["basis"] in DISTANCE_BASES
        if d["basis"] == "unknown":
            assert d == {"pc": None, "pc_low": None, "pc_high": None, "redshift": None, "basis": "unknown"}
            continue
        assert d["pc"] > 0 and e["raw"]["distance_from"]
        if d["pc_low"] is not None:
            assert d["pc_low"] <= d["pc"] <= d["pc_high"]
        if d["basis"] in ("redshift", "catalogue"):
            assert d["redshift"] > 0 and d["pc"] > 1e5  # beyond the Milky Way
        if d["basis"] == "parallax":
            assert e["raw"]["distance_from"].startswith("Gaia DR3") and d["pc"] < 1e5
            plx, err = (float(x) for x in re.findall(r"([\d.]+)(?: ±| mas)", e["raw"]["distance_from"]))
            assert plx / err > 5
    assert all(e["location"]["distance"]["basis"] == "unknown" for e in events if e["type"] == "neutrino")


def test_solar_system_positions(week):
    events, _ = week
    ss = [e for e in _sky(events) if e["type"] in CATEGORIES["solar_system"]]
    assert len(ss) == 39
    for e in ss:
        eph = e["location"]["ephemeris"]
        assert list(eph) == ["helio_xyz_au", "earth_distance_au", "sun_distance_au", "epoch"]
        assert eph["epoch"] == e["observed_at"]  # at the observation, not at ingest time
        assert sum(c * c for c in eph["helio_xyz_au"]) ** 0.5 == pytest.approx(eph["sun_distance_au"], abs=1e-6)
        assert 0 < eph["earth_distance_au"] < 60 and 0.05 < eph["sun_distance_au"] < 60
        # the Earth-object-Sun triangle closes
        assert abs(eph["sun_distance_au"] - eph["earth_distance_au"]) <= 1.02
    by_id = {e["id"]: e for e in ss}
    assert by_id["jpl:P/2026_R1"]["raw"]["distance_from"] == "JPL Horizons vectors for 2026 R1"
    neo = [e for e in ss if e["source"] == "mpc"]
    assert all(e["raw"]["ephemeris_spread"]["orbits"] == 50 for e in neo)


def test_one_real_example_per_basis(week):
    events, _ = week
    by_id = {e["id"]: e for e in events}
    sn = by_id["tns:2026abvs"]["location"]["distance"]
    assert (sn["basis"], sn["redshift"], sn["pc"]) == ("redshift", 0.029, pytest.approx(1.3132e8))
    grb = by_id["gcn:GRB_260924A"]
    assert grb["location"]["distance"]["redshift"] == 3.51 and grb["raw"]["distance_from"].startswith("GCN Circular 45740")
    ep = by_id["gcn:GRB_260920B"]  # GRB 260920B = EP260920b; the VLT spectrum's circular wins
    assert ep["location"]["distance"]["redshift"] == 3.582
    cat = by_id["ztf:ZTF26abwqnbk"]
    assert cat["location"]["distance"]["basis"] == "catalogue" and cat["raw"]["distance_from"].startswith("SIMBAD LEDA 1471594")
    star = by_id["rubin:170059273359851523"]["location"]["distance"]
    assert star["basis"] == "parallax" and star["pc"] == pytest.approx(779.0, abs=0.5)
    comet = by_id["mpc:A11H8ut"]["location"]["ephemeris"]
    assert comet["sun_distance_au"] == pytest.approx(4.806, abs=1e-3)


def test_status_reports_distance_coverage(week):
    events, status = week
    d = status["distances"]
    assert d["cosmology"].startswith("Planck18")
    assert all(v["ok"] for v in d["lookups"].values()), d["lookups"]
    assert d["by_type"]["near_earth_object"]["share"] == 1.0
    assert d["by_type"]["neutrino"] == {"events": 1, "with_distance": 0, "share": 0.0, "basis": {"unknown": 1}}
    s = status["sources"]
    assert s["mpc"]["distance"]["share"] == 1.0 and s["tns"]["distance"]["share"] > 0.9
    assert s["donki"]["distance"] == {"sky_events": 0, "with_distance": 0, "share": None}
    for name, st in s.items():
        cov = st["distance"]
        assert cov["with_distance"] <= cov["sky_events"], name
    assert sum(v["with_distance"] for v in d["by_type"].values()) == sum(
        e["location"]["frame"] == "sky" and ("ephemeris" in e["location"] or e["location"]["distance"]["pc"] is not None)
        for e in events)
