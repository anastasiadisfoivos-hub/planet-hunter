"""Distances and ephemerides, on recorded real responses (offline)."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timedelta

import numpy as np
import pytest
from recording import HTTP_DIR, meta

from skyevents import distance, ephemeris
from skyevents.adapters import gcn, gracedb
from skyevents.catalogues import gcn_redshift
from skyevents.dedup import dedup


def _recorded(name: str, url_part: str) -> list[dict]:
    doc = json.loads((HTTP_DIR / f"{name}.json").read_text())
    return [v for v in doc["responses"].values() if url_part in v["url"]]


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ------------------------------------------------------------------ conversions


def test_redshift_uses_planck18_luminosity_distance():
    d = distance.from_redshift(0.029)
    assert d["basis"] == "redshift" and d["redshift"] == 0.029
    assert d["pc"] == pytest.approx(131.3e6, rel=2e-3)  # Planck18 D_L(0.029) ≈ 131.3 Mpc
    assert d["pc_low"] is None and d["pc_high"] is None
    assert distance.from_redshift(0.5, "catalogue")["basis"] == "catalogue"


def test_parallax_needs_signal_to_noise_above_five():
    d = distance.from_parallax(1.284, 0.028)
    assert d == {"pc": pytest.approx(778.82, rel=1e-4), "pc_low": pytest.approx(762.2, rel=1e-3),
                 "pc_high": pytest.approx(796.2, rel=1e-3), "redshift": None, "basis": "parallax"}
    assert d["pc_low"] < d["pc"] < d["pc_high"]
    assert distance.from_parallax(1.0, 0.2) is None  # exactly 5: not above
    assert distance.from_parallax(1.0, 0.19) is not None
    assert distance.from_parallax(-0.5, 0.01) is None


def test_gw_mean_and_std():
    d = distance.from_gw(2698.7, 860.3)
    assert (d["pc"], d["pc_low"], d["pc_high"], d["basis"]) == (2.6987e9, 1.8384e9, 3.559e9, "gw_estimate")
    assert distance.from_gw(100.0, 300.0)["pc_low"] == 0.0


# ------------------------------------------------------------------ gravitational waves (GraceDB)


def test_gracedb_distance_from_the_sky_map(replay):
    replay("gracedb_S251117dq")
    [e] = gracedb.fetch(_t(meta("gracedb_S251117dq")["since"]), _t(meta("gracedb_S251117dq")["until"]))
    assert e["raw"]["distance_mpc"] == {"mean": 2698.7, "std": 860.3}  # sky-map DISTMEAN, DISTSTD
    [e] = dedup([e])
    status = distance.enrich([e])
    d = e["location"]["distance"]
    assert d["basis"] == "gw_estimate" and d["pc"] == pytest.approx(2.6987e9)
    assert d["pc_low"] == pytest.approx(1.8384e9) and d["pc_high"] == pytest.approx(3.559e9)
    assert "DISTMEAN" in e["raw"]["distance_from"]
    assert status["by_type"]["gravitational_wave"]["share"] == 1.0


def test_gracedb_map_without_distance():
    alert = json.loads(_recorded("gracedb_S251117dq", "-update.json")[0]["text"])
    fits_bytes = base64.b64decode(alert["event"]["skymap"])
    assert gracedb.skymap_distance(fits_bytes) == {"mean": 2698.7, "std": 860.3}
    e = gracedb.alert_to_event(alert)
    e["raw"]["distance_mpc"] = None  # a burst-search map: no distance published
    distance.enrich([e])
    assert e["location"]["distance"]["basis"] == "unknown"


# ------------------------------------------------------------------ ephemerides


def test_earth_position_matches_horizons():
    m = meta("distance_checks")
    earth = [v for v in _recorded("distance_checks", "horizons") if v["params"]["COMMAND"] == "'399'"]
    horizons = ephemeris.parse_vectors(json.loads(earth[0]["text"])["result"])
    assert np.linalg.norm(horizons - ephemeris.earth_helio_ecliptic(_t(m["t0"]))) < 1e-6  # au, ~150 km


def test_kepler_propagation_matches_horizons():
    """Horizons osculating elements of comet P/2026 R1 at t0, moved with our two-body code, land
    where Horizons' own vectors put the comet 5 and 30 days later."""
    m = meta("distance_checks")
    resp = _recorded("distance_checks", "horizons")
    elements = next(json.loads(v["text"])["result"] for v in resp if v["params"]["EPHEM_TYPE"] == "ELEMENTS")
    row = [c.strip() for c in re.search(r"\$\$SOE\s*\n(.*?)\n", elements)[1].split(",")]
    ec, qr, inc, om, w, tp = (float(row[i]) for i in (2, 3, 4, 5, 6, 7))
    from astropy.time import Time

    for days, tol in zip(m["later_days"], (1e-6, 1e-5), strict=True):
        t = _t(m["t0"]) + timedelta(days=days)
        vec = next(v for v in resp if v["params"]["EPHEM_TYPE"] == "VECTORS" and "R1" in v["params"]["COMMAND"]
                   and v["params"]["TLIST"] == f"'{Time(t).utc.jd:.6f}'")
        horizons = ephemeris.parse_vectors(json.loads(vec["text"])["result"])
        ours = ephemeris.kepler_xyz(qr, ec, tp, om, w, inc, Time(t).tdb.jd)
        assert np.linalg.norm(ours - horizons) < tol, days


def test_asteroid_names_to_horizons_commands():
    assert ephemeris.horizons_command("180274 (2003 WC63)") == "180274;"
    assert ephemeris.horizons_command("(2026 AB12)") == "DES=2026 AB12;"


def test_kepler_hyperbolic_orbit_is_continuous():
    # e > 1 (an interstellar object): perihelion at tp, distance grows both ways.
    at_peri = ephemeris.kepler_xyz(1.36, 6.14, 2460970.0, 322.0, 128.0, 175.1, 2460970.0)
    later = ephemeris.kepler_xyz(1.36, 6.14, 2460970.0, 322.0, 128.0, 175.1, 2461070.0)
    assert np.linalg.norm(at_peri) == pytest.approx(1.36, abs=1e-9)
    assert np.linalg.norm(later) > 1.36


# ------------------------------------------------------------------ GCN


def test_gcn_redshift_circulars_ranked_from_subjects():
    subjects = [
        {"circularId": 45683, "subject": "EP260920b: 2.2m CAHA optical afterglow detection and 10.4m GTC redshift confirmation"},
        {"circularId": 45678, "subject": "Swift GRB 260921A: MASTER OT J094129.58+025052.5 possible optical counterpart detection with host galaxy (z=1.3)"},
        {"circularId": 45675, "subject": "EP260920b: VLT/X-shooter spectroscopic redshift z = 3.582"},
    ]
    ranked = gcn.redshift_circulars(subjects)
    assert [c["id"] for c in ranked] == [45675, 45683]  # spectroscopic first; no "redshift" -> ignored
    assert gcn_redshift(ranked) == (3.582, 45675, subjects[2]["subject"])  # read from the subject


def test_gcn_redshift_from_the_body(replay):
    replay("distance_checks")
    only_body = [{"id": 45683, "subject": "EP260920b: 2.2m CAHA optical afterglow detection and 10.4m GTC redshift confirmation", "rank": 1}]
    # the body also says "z > 20.5" (a z-band magnitude), which must not be read as a redshift
    assert gcn_redshift(only_body)[0] == 3.58


# ------------------------------------------------------------------ fail-soft


def _adapter_events() -> list:
    """Plain adapter output from the recorded week: records without distance fields."""
    from skyevents.adapters import comets, mpc

    m = meta("live_week")
    since, until = _t(m["since"]), _t(m["until"])
    return dedup(mpc.fetch(since, until) + comets.fetch(since, until))


def test_failed_lookups_leave_unknown_and_are_reported(replay):
    replay("live_week")  # the adapters' answers only: every distance lookup fails
    events = _adapter_events()
    assert events
    status = distance.enrich(events)
    assert status["lookups"]["scout"]["failed_objects"] == sum(e["source"] == "mpc" for e in events)
    assert status["lookups"]["horizons"]["failed_objects"] == sum(e["source"] == "jpl" for e in events)
    assert all(e["location"]["distance"]["basis"] == "unknown" and "ephemeris" not in e["location"] for e in events)


def test_records_without_distance_stay_valid(replay):
    from skyevents.query import query

    replay("live_week")
    old = _adapter_events()
    assert all(set(e["location"]) == {"frame", "ra_deg", "dec_deg", "error_deg"} for e in old)
    assert len(query({"limit": 1000}, old)) == len(old)
    assert all(not distance.has_distance(e) for e in old)
