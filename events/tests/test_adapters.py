"""Adapter-level checks on recorded real responses, plus the parsers on real text."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest
from recording import HTTP_DIR, meta

from skyevents.adapters import cneos, donki, gcn, gracedb, icecube, mpc, tns, ztf
from skyevents.adapters.comets import parse_ephemeris
from skyevents.adapters.comets import to_event as comet_event


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _window(name: str) -> tuple[datetime, datetime]:
    m = meta(name)
    return _t(m["since"]), _t(m["until"])


def _recorded(name: str, url_part: str) -> list[str]:
    doc = json.loads((HTTP_DIR / f"{name}.json").read_text())
    return [v["text"] for v in doc["responses"].values() if url_part in v["url"]]


# ------------------------------------------------------------------ historical windows


def test_gracedb_gravitational_wave(replay):
    replay("gracedb_S251117dq")
    [e] = gracedb.fetch(*_window("gracedb_S251117dq"))
    assert e["id"] == "gracedb:S251117dq" and e["type"] == "gravitational_wave"
    assert e["observed_at"] == "2025-11-17T21:38:33Z"
    assert e["confidence_basis"] == "machine_guess" and e["confidence"] > 0.99
    assert "black holes" in e["summary"]
    loc = e["location"]
    assert loc["frame"] == "sky" and 1 < loc["error_deg"] < 60
    assert 100 < e["raw"]["area90_deg2"] < 5000


def test_gracedb_skymap_is_normalised(replay):
    alert = next(json.loads(t) for t in _recorded("gracedb_S251117dq", "-update.json"))
    ra, dec, area = gracedb.skymap_summary(base64.b64decode(alert["event"]["skymap"]))
    assert 0 <= ra < 360 and -90 <= dec <= 90
    assert 0 < area < 41253  # smaller than the whole sky


def test_donki_geomagnetic_storm(replay):
    replay("donki_storm_2026-08")
    events = donki.fetch(*_window("donki_storm_2026-08"))
    [storm] = [e for e in events if e["type"] == "geomagnetic_storm"]
    assert storm["id"] == "donki:2026-08-08T18:00:00-GST-001"
    assert storm["location"] == {"frame": "earth", "lat_deg": 80.8, "lon_deg": -72.7, "alt_km": None}
    assert storm["raw"]["kp_max"] == 5.67 and storm["raw"]["noaa_g_scale"] == "G1 (minor)"
    assert storm["reported_at"] == "2026-08-08T21:02:00Z"
    assert {e["type"] for e in events} <= {"solar_flare", "coronal_mass_ejection", "geomagnetic_storm"}
    assert all(e["location"] == {"frame": "sun"} for e in events if e["type"] != "geomagnetic_storm")


def test_cneos_fireball_signs(replay):
    replay("cneos_2026-09")
    events = cneos.fetch(*_window("cneos_2026-09"))
    e = next(e for e in events if e["id"] == "cneos:2026-09-15T11:26:13")
    assert e["location"] == {"frame": "earth", "lat_deg": -37.6, "lon_deg": -161.6, "alt_km": 37.0}
    assert e["type"] == "fireball" and e["raw"]["impact_energy_kt"] == 0.079
    assert e["raw"]["reported_at_known"] is False


# ------------------------------------------------------------------ parsers on real text


def test_gcn_positions_from_real_circulars():
    bodies = {json.loads(t)["subject"]: json.loads(t)["body"] for t in _recorded("live_week", "gcn.nasa.gov/circulars/4")}
    swift = [b for s, b in bodies.items() if "Swift detection of a burst" in s]
    assert swift
    for body in swift:
        pos = gcn.parse_positions(body)
        assert pos and all(0 <= ra < 360 and -90 <= dec <= 90 and e > 0 for ra, dec, e in pos)


def test_gcn_position_formats():
    xrt = "RA, Dec = 132.45679, +24.91132 which is equivalent to ...\nwith an uncertainty of 2.6 arcsec (radius"
    gbm = "location, using the Fermi GBM trigger data, is RA = 139.9, Dec = 9.7 (J2000 degrees, ...), with a statistical uncertainty of 1.6 degrees."
    ep = "The WXT position of the source is R.A. = 339.0046 deg, DEC = 47.0245 deg (J2000) with an uncertainty of 2.83 arcmin in radius"
    assert gcn.parse_positions(xrt) == [(132.45679, 24.91132, pytest.approx(2.6 / 3600))]
    assert gcn.parse_positions(gbm) == [(139.9, 9.7, 1.6)]
    assert gcn.parse_positions(ep) == [(339.0046, 47.0245, pytest.approx(2.83 / 60))]
    bat = "RA, Dec (145.373, +2.852), which is\n RA(J2000) = 9h 41m 29s\nwith an uncertainty of 3 arcmin (radius"
    assert gcn.parse_positions(bat) == [(145.373, 2.852, 0.05)]
    assert gcn.parse_positions("RA, Dec = 10, 20 and nothing else") == []


def test_gcn_times_and_names():
    day = datetime(2026, 9, 25, tzinfo=UTC)
    assert gcn.parse_time("At 07:13:02 UT, the Swift Burst Alert Telescope", day) == datetime(2026, 9, 25, 7, 13, 2, tzinfo=UTC)
    assert gcn.parse_time("trigger time T0 = 2026-09-25T03:47:56 UTC", day) == datetime(2026, 9, 25, 3, 47, 56, tzinfo=UTC)
    assert gcn.parse_time("no time here", day) is None
    assert gcn.names_in("GRB 260920B/EP260920b: GECAM-B detection") == {"GRB 260920B", "EP260920b"}
    assert gcn.names_in("The EP-WXT trigger 01709319842 is likely a flaring star") == set()


def test_icecube_table_from_real_page():
    [page] = _recorded("live_week", "amon_icecube_gold_bronze")
    rows = icecube.parse_table(page)
    assert rows
    r = next(r for r in rows if r["run_event"] == "143143_38400235")
    assert r["notice_type"] == "GOLD" and r["when"] == datetime(2026, 9, 19, 6, 52, 15, 580000, tzinfo=UTC)
    e = icecube.to_event(r)
    assert e["location"]["ra_deg"] == 111.0499 and e["location"]["dec_deg"] == 6.4299
    assert e["location"]["error_deg"] == pytest.approx(16.30 / 60, abs=1e-4)
    assert e["confidence"] == pytest.approx(0.6704) and e["confidence_basis"] == "machine_guess"


def test_pccp_text_and_neocp_hours():
    line = "C1M0JJP 100 2026 09 21.1  17.8610 +20.9695 21.3 Updated Sept. 25.24 UT           4   0.02 15.5  4.518"
    [r] = mpc.parse_pccp(line)
    e = mpc.pccp_event(r)
    assert e["id"] == "mpc:C1M0JJP" and e["type"] == "comet" and e["confidence"] == 0.5
    assert e["location"]["ra_deg"] == pytest.approx(17.8610 * 15, abs=1e-4)  # MPC RA is in hours
    assert e["reported_at"] == "2026-09-25T05:45:36Z"
    assert e["observed_at"] == "2026-09-20T17:19:40Z"  # update time minus 4.518 days unseen
    assert "not yet a confirmed comet" in e["summary"]


def test_neocp_live_rows_are_machine_guesses():
    [text] = _recorded("live_week", "neocp.json")
    rows = json.loads(text)
    events = [mpc.neocp_event(r) for r in rows]
    assert events and all(e["confidence_basis"] == "machine_guess" and e["type"] == "near_earth_object" for e in events)
    assert all(e["confidence"] == r["Score"] / 100 for e, r in zip(events, rows, strict=True))
    assert any(r["Temp_Desig"].startswith("LS") for r in rows)  # Rubin's own NEOCP submissions


def test_tns_type_mapping():
    assert tns.tns_type("SN Ia") == "supernova"
    assert tns.tns_type("SLSN-II") == "supernova"
    assert tns.tns_type("TDE-H-He") == "tidal_disruption_event"
    assert tns.tns_type("Nova") == "nova"
    assert tns.tns_type("Other") == "unknown"


def test_ztf_old_cv_is_not_news():
    assert "CV/Nova" in ztf.LC_CLASSES and ztf.NEW_DAYS == 30


def test_horizons_line_and_interstellar_rule():
    text = "header\n$$SOE\n 2026-Sep-25 14:24:00.000     344.59019 -13.36849   19.357    n.a.\n$$EOE\n"
    assert parse_ephemeris(text) == (344.59019, -13.36849, 19.357)
    row = {"full_name": "C/2025 N1 (ATLAS)", "pdes": "2025 N1", "prefix": "C", "first_obs": "2025-05-15",
           "last_obs": "2026-02-19", "e": "6.14", "q": "1.36"}
    e = comet_event(row, 108.5, 19.3, None, datetime(2026, 9, 25, tzinfo=UTC))
    assert e["type"] == "interstellar_object" and "3I/ATLAS" in e["title"] and e["id"] == "jpl:C/2025_N1"
