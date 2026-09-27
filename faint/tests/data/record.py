"""Record the real TGLC data the offline tests run on (needs the network; run from faint/).

    uv run python tests/data/record.py

Writes tests/data/<tic>.npz (the stitched FaintLC from get_lightcurves, with its products and download metadata),
tests/data/<tic>.json (the TIC row), one raw TGLC FITS file for the reader tests, and facts.json (the catalogue
numbers the recovery tests compare against, with their sources).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from skyfaint import tglc, tic

HERE = Path(__file__).parent
FIXTURES = {
    # Two known planets around faint M dwarfs (Tmag > 13), chosen before any search was run:
    "toi5688": 193634953,  # TOI-5688 A b: Tmag 14.21, R* 0.58, P 2.948 d, 10.3 R_earth; 7 TGLC sectors; has a companion (B)
    "toi1680": 259168516,  # TOI-1680 b: Tmag 13.31, R* 0.21, P 4.803 d, 1.47 R_earth; 24 TGLC sectors (small planet)
    # A faint M dwarf with no known planet: the first star of the random noise sample (scripts/fit_noise.py, seed 7)
    # with Tmag 14-15 and >= 3 TGLC sectors.
    "quiet": 0,  # filled in by --quiet TIC
}
RAW_FITS = (193634953, 25)  # one raw TGLC file (TOI-5688, sector 25, 30-min cadence) for the reader tests

FACTS = {
    "toi5688": {
        "name": "TOI-5688 A b", "tic": 193634953, "period_d": 2.948155, "ratror": 0.164,
        "depth_ppm_from_ratror": round(0.164**2 * 1e6), "exofop_depth_ppm": 24090, "rade": 10.3, "st_rad": 0.57,
        "source": "NASA Exoplanet Archive ps table, default solution Reji et al. 2025 (AJ 169, 187); the ExoFOP TOI "
                  "depth (24090 ppm) is from the TESS pipelines' undiluted-by-companion fit",
    },
    "toi1680": {
        "name": "TOI-1680 b", "tic": 259168516, "period_d": 4.8026345, "t0_btjd": 2459013.84254 - 2457000,
        "duration_h": 1.186, "ratror": 0.0638, "depth_ppm": 4070, "rade": 1.466, "st_rad": 0.2106,
        "source": "NASA Exoplanet Archive ps table, default solution (Ghachoui et al. 2023)",
    },
}


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", type=int, required=True, help="TIC of the quiet star (see FIXTURES)")
    a = ap.parse_args()
    FIXTURES["quiet"] = a.quiet
    for role, t in FIXTURES.items():
        lc = tglc.get_lightcurves(t)
        lc.save(HERE / f"{t}.npz")
        (HERE / f"{t}.json").write_text(json.dumps({"role": role, "star": tic.star(t)}, indent=1))
        print(role, t, lc.sectors, len(lc.time), "points", (HERE / f"{t}.npz").stat().st_size, "bytes")
    idx = tglc.resolve(RAW_FITS[0])
    f = next(x for x in idx["files"] if x["sector"] == RAW_FITS[1])
    shutil.copy(tglc.download(f), HERE / f["url"].rsplit("/", 1)[1])
    (HERE / "facts.json").write_text(json.dumps({**FACTS, "quiet": {"tic": a.quiet}}, indent=1))


if __name__ == "__main__":
    main()
