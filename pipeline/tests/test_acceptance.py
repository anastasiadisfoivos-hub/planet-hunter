"""Acceptance on real TESS data (network). Run with: uv run pytest --run-network -m network

Each target is hunted twice: cold (empty temporary cache) and cached. Timings go to reports/runtime.json;
result.json and folded PNGs for each target go to reports/<slug>/.
"""

import json
import os
import time
from pathlib import Path

import pytest

import hunter
from hunter import known
from hunter.__main__ import main as cli_main
from hunter.core import run
from hunter.models import CatchType
from test_contract import assert_raw_fields

pytestmark = pytest.mark.network

REPORTS = Path(__file__).resolve().parent.parent / "reports"

PLANETS = {"WASP-18": "WASP-18 b", "WASP-121": "WASP-121 b", "WASP-43": "WASP-43 b"}
# TESS Eclipsing Binary catalogue, Prsa et al. 2022, ApJS 258, 16 (VizieR J/ApJS/258/16), P = 4.5070860 d.
EB_TARGET = "TIC 219707463"
# Extra EBs from the same catalogue that exercise the odd/even and secondary-eclipse tests on real data.
EXTRA_EBS = {"TIC 144539611": "odd_even", "TIC 231010756": "secondary_eclipse"}
TARGETS = [*PLANETS, EB_TARGET, *EXTRA_EBS]


def _slug(target: str) -> str:
    return target.replace(" ", "").lower()


@pytest.fixture(scope="session")
def results(tmp_path_factory):
    REPORTS.mkdir(exist_ok=True)
    out, timings = {}, {}
    old = os.environ.get("HUNTER_CACHE_DIR")
    for target in TARGETS:
        os.environ["HUNTER_CACHE_DIR"] = str(tmp_path_factory.mktemp(_slug(target)))
        t0 = time.perf_counter()
        run(target)
        cold = time.perf_counter() - t0
        t0 = time.perf_counter()
        res = run(target)
        cached = time.perf_counter() - t0
        cli_main([target, "--out", str(REPORTS / _slug(target))])
        out[target] = res
        timings[target] = {"cold_s": round(cold, 1), "cached_s": round(cached, 1),
                           "sectors": [p["sector"] for p in res.products]}
    if old is None:
        os.environ.pop("HUNTER_CACHE_DIR", None)
    else:
        os.environ["HUNTER_CACHE_DIR"] = old
    (REPORTS / "runtime.json").write_text(json.dumps(timings, indent=2))
    return out, timings


def _primary(res):
    return next(d for d in res.discoveries if d.id == f"tess:{res.star.tic_id}:sig:1")


@pytest.mark.parametrize("star,planet", PLANETS.items())
def test_known_hot_jupiters(results, star, planet):
    res = results[0][star]
    d = _primary(res)
    archive = {p["name"]: p for p in known.confirmed_planets(res.star.tic_id)}[planet]
    assert d.type == CatchType.planet_candidate, d.explanation
    assert abs(d.raw["signal"]["period"] - archive["period"]) / archive["period"] < 0.01
    assert d.known_status == "known"
    assert d.name_if_known == planet
    size_vet = next(v for v in d.raw["vetting"] if v["name"] == "size")
    assert size_vet["passed"] is True  # WASP-43 b is deliberately deep; it must NOT fail the size test


def test_catalogue_eclipsing_binary(results):
    d = _primary(results[0][EB_TARGET])
    assert d.type == CatchType.eclipsing_binary
    assert d.known_status == "known"
    assert abs(d.raw["signal"]["period"] - 4.5070860) / 4.5070860 < 0.01


@pytest.mark.parametrize("star,failing_test", EXTRA_EBS.items())
def test_extra_eclipsing_binaries_fail_the_right_test(results, star, failing_test):
    d = _primary(results[0][star])
    assert d.type == CatchType.eclipsing_binary
    vet = next(v for v in d.raw["vetting"] if v["name"] == failing_test)
    assert vet["passed"] is False


def test_raw_fields_on_every_discovery(results):
    for target, res in results[0].items():
        assert res.discoveries, target
        for d in res.discoveries:
            assert_raw_fields(d.to_dict())
    for path in REPORTS.glob("*/result.json"):
        for d in json.loads(path.read_text())["discoveries"]:
            assert_raw_fields(d)


def test_cached_run_is_faster(results):
    for target, t in results[1].items():
        assert t["cached_s"] < t["cold_s"], target


def test_latest_data_marker_live():
    marker = hunter.latest_data_marker(36734222)  # WASP-43
    assert marker is not None and marker.startswith("sector-")
    assert int(marker.split("-")[1]) >= 100
