"""Record the real-data test fixtures and the report outputs (needs internet).

    uv run python scripts/record_fixtures.py            # all cases
    uv run python scripts/record_fixtures.py wasp18     # one case

For each case: runs the full pipeline once with an empty cache (cold runtime) and once warm, saves the reduced
per-sector images + catalogue answers to tests/data/<case>/ (what the offline tests replay), and the PNG/JSON
outputs to reports/<case>/.  Also saves a small crop of raw WASP-18 pixels so the reduction step is tested on
real frames offline.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data"
REPORTS = ROOT / "reports"


def run_case(name: str, case: dict, cold: bool) -> dict:
    from skypixels.vet import analyze_inputs, gather
    from skypixels.render import write_outputs

    timings: dict[str, float] = {}
    t = time.perf_counter()
    inputs = gather(case["tic"], case["period_d"], case["t0_btjd"], case["duration_h"], case.get("sectors"),
                    timings=timings)
    vet, results = analyze_inputs(inputs, timings)
    out = REPORTS / name
    vet.files = write_outputs(vet, results, out)
    timings["total"] = round(time.perf_counter() - t, 2)
    vet.timings_s = timings
    (out / "pixel_vet.json").write_text(json.dumps(vet.to_dict(), indent=1))
    if not cold:
        inputs.save(DATA / name)
    return {"verdict": vet.verdict, "timings_s": timings, "sectors": [p["sector"] for p in vet.data]}


def record_raw_crop() -> None:
    """First 8 transits of WASP-18 sector 105 (frames within ±2.5 durations of mid-transit), float32."""
    from skypixels import fetch
    from skypixels.catalog import tic_row

    case = CASES["wasp18"]
    tic = tic_row(case["tic"])
    rows = [r for r in fetch.list_products(case["tic"], tic["ra_deg"], tic["dec_deg"]) if r["sector"] == 105]
    series = fetch.read(fetch.download(rows[0], tic["ra_deg"], tic["dec_deg"]), rows[0])
    t0 = case["t0_btjd"]
    P, D = case["period_d"], case["duration_h"] / 24
    phase = (series.time - t0 + 0.5 * P) % P - 0.5 * P
    epoch = np.round((series.time - t0) / P)
    first = np.unique(epoch[np.isfinite(series.time)])[:8]
    keep = (np.abs(phase) < 2.5 * D) & np.isin(epoch, first)
    np.savez_compressed(
        DATA / "wasp18_s105_raw_crop.npz", time=series.time[keep], flux=series.flux[keep].astype(np.float32),
        quality=series.quality[keep].astype(np.int32), wcs_header=series.wcs.to_header_string(relax=True),
    )


CASES = json.loads((DATA / "cases.json").read_text())


def main(names: list[str]) -> None:
    names = names or list(CASES)
    runtime = json.loads((REPORTS / "runtime.json").read_text()) if (REPORTS / "runtime.json").exists() else {}
    for name in names:
        case = CASES[name]
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["SKYPIXELS_CACHE_DIR"] = tmp
            cold = run_case(name, case, cold=True)
        os.environ.pop("SKYPIXELS_CACHE_DIR")
        run_case(name, case, cold=False)  # fills the normal cache
        warm = run_case(name, case, cold=False)
        runtime[name] = {"cold_s": cold["timings_s"], "warm_s": warm["timings_s"], "sectors": warm["sectors"],
                         "verdict": warm["verdict"]}
        print(name, runtime[name], file=sys.stderr)
    if "wasp18" in names:
        record_raw_crop()
    (REPORTS / "runtime.json").write_text(json.dumps(runtime, indent=1))


if __name__ == "__main__":
    warnings.simplefilter("ignore")
    REPORTS.mkdir(exist_ok=True)
    with contextlib.redirect_stdout(sys.stderr):
        main(sys.argv[1:])
