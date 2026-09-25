"""Offline end-to-end: hunt() on a synthetic star with network calls stubbed. Checks contract shape, IDs,
honesty wording, known-list matching and latest_data_marker."""

import json
import re

import numpy as np
import pytest

import hunter
from conftest import box, make_time
from hunter import fetch as fetch_mod
from hunter import core as hunt_mod
from hunter import known
from hunter.fetch import LightCurveData, choose_products
from hunter.models import CatchType
from hunter.resolve import StarInfo

CONTRACT_KEYS = {"id", "type", "confidence", "source", "origin", "ra_deg", "dec_deg", "detected_at",
                 "name_if_known", "known_status", "cutouts", "light_curve", "explanation", "links", "raw"}
TIC = 123456789


@pytest.fixture
def synthetic(monkeypatch, rng):
    t, g = make_time()
    flux = 1 + box(t, 2.2, 2000.4, 0.1, 0.006) + rng.normal(0, 8e-4, len(t))
    k = int(np.searchsorted(t, 2010.0))
    flux[k:k + 25] += 0.03 * np.exp(-np.arange(25) / 6.0)
    lc = LightCurveData(t, flux, np.full(len(t), 8e-4), g,
                        [{"sector": 1, "author": "SPOC", "exptime": 120.0, "flux_column": "pdcsap_flux"},
                         {"sector": 2, "author": "SPOC", "exptime": 120.0, "flux_column": "pdcsap_flux"}])
    star = StarInfo(TIC, 10.0, -20.0, 1.0, 5800.0, 9.0, f"TIC {TIC}")
    monkeypatch.setattr(hunt_mod, "resolve", lambda target, refresh=False: star)
    monkeypatch.setattr(hunt_mod, "fetch", lambda tic, max_sectors=2, refresh=False: lc)
    monkeypatch.setattr(known, "confirmed_planets", lambda tic: [])
    monkeypatch.setattr(known, "tois", lambda tic: [{"name": "TOI-9999.01", "period": 2.2 * 2,
                                                     "list": "TESS Objects of Interest", "extra": {}}])
    monkeypatch.setattr(known, "ctois", lambda tic: [])
    monkeypatch.setattr(known, "eclipsing_binaries", lambda tic: [])
    return t[k]


def test_discoveries_follow_contract(synthetic):
    discoveries = hunter.hunt(hunter.StarTarget(TIC))
    assert discoveries
    for d in discoveries:
        data = d.to_dict()
        assert set(data) == CONTRACT_KEYS
        assert data["type"] in {c.value for c in CatchType}
        assert 0 <= data["confidence"] <= 1
        assert data["source"] == "tess"
        assert data["known_status"] in {"known", "not_on_lists", "unchecked"}
        assert set(data["cutouts"]) == {"before", "now", "difference"}
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", data["detected_at"])
        assert all(set(link) == {"label", "url"} for link in data["links"])
        if data["light_curve"] is not None:
            assert set(data["light_curve"]) == {"time_btjd", "flux"}
            assert len(data["light_curve"]["flux"]) <= 2000
        json.dumps(data, allow_nan=False)  # strict JSON: no NaN/Infinity


def test_ids_and_alias_match(synthetic):
    flare_peak = synthetic
    discoveries = {d.id: d for d in hunter.hunt(TIC)}
    sig = discoveries[f"tess:{TIC}:sig:1"]
    assert sig.type == CatchType.planet_candidate
    assert sig.known_status == "known" and sig.name_if_known == "TOI-9999.01"
    assert "half the listed one" in sig.explanation
    flare_id = f"tess:{TIC}:flare:{round(flare_peak, 2):.2f}"
    assert flare_id in discoveries
    assert discoveries[flare_id].type == CatchType.flare


def test_honesty_wording(synthetic):
    text = json.dumps([d.to_dict() for d in hunter.hunt(TIC)]).lower()
    assert "discovered" not in text
    assert "new planet" not in text


def test_known_status_unchecked_when_lists_fail(monkeypatch):
    def boom(tic):
        raise ConnectionError("down")
    monkeypatch.setattr(known, "confirmed_planets", boom)
    monkeypatch.setattr(known, "tois", lambda tic: [])
    monkeypatch.setattr(known, "ctois", lambda tic: [])
    assert known.check(1, 3.0).status == "unchecked"
    monkeypatch.setattr(known, "confirmed_planets", lambda tic: [])
    assert known.check(1, 3.0).status == "not_on_lists"


@pytest.mark.parametrize("found,listed,expected", [
    (1.0, 1.005, "same period"), (1.0, 1.02, None), (2.0, 1.0, "our period is twice the listed one"),
    (0.5, 1.0, "our period is half the listed one"), (3.0, 1.0, "our period is 3x the listed one"),
])
def test_period_matching(found, listed, expected):
    assert known.match_period(found, listed) == expected


ROWS = [
    {"sector": 10, "author": "QLP", "exptime": 1800.0, "uri": "a", "filename": "a"},
    {"sector": 37, "author": "SPOC", "exptime": 120.0, "uri": "b", "filename": "b"},
    {"sector": 37, "author": "SPOC", "exptime": 20.0, "uri": "c", "filename": "c"},
    {"sector": 64, "author": "TESS-SPOC", "exptime": 200.0, "uri": "d", "filename": "d"},
    {"sector": 64, "author": "QLP", "exptime": 200.0, "uri": "e", "filename": "e"},
    {"sector": 90, "author": "SPOC", "exptime": 20.0, "uri": "f", "filename": "f"},
]


def test_product_preference():
    chosen = choose_products(ROWS, 2)
    assert [(r["sector"], r["author"], r["exptime"]) for r in chosen] == [(37, "SPOC", 120.0), (64, "TESS-SPOC", 200.0)]
    assert len(choose_products(ROWS, 10)) == 3  # sector 90 has only 20-s data, which we do not use


def test_latest_data_marker(monkeypatch):
    monkeypatch.setattr(fetch_mod, "search_products", lambda tic, refresh=False: ROWS)
    assert hunter.latest_data_marker(1) == "sector-64"
    monkeypatch.setattr(fetch_mod, "search_products", lambda tic, refresh=False: [])
    assert hunter.latest_data_marker(1) is None
