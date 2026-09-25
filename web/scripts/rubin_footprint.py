"""Build web/public/data/rubin-footprint.json from Rubin's official scheduler footprint.

Source: rubin_scheduler.scheduler.utils.get_current_footprint (lsst/rubin_scheduler),
the survey footprint used by the LSST baseline scheduler (SCOC Phase 3, PSTN-056).

One-off build step (output is committed, so the web build never needs Python):

    python3 -m venv .venv && .venv/bin/pip install rubin-scheduler healpy pandas
    export RUBIN_SIM_DATA_DIR=/some/scratch/dir
    .venv/bin/scheduler_download_data -d scheduler,utils
    .venv/bin/python web/scripts/rubin_footprint.py
"""

import json
import os
from datetime import datetime, timezone
from importlib.metadata import version

import healpy as hp
import numpy as np
from rubin_scheduler.scheduler.utils import get_current_footprint

NSIDE = 64
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "data", "rubin-footprint.json")


def main() -> None:
    _, labels = get_current_footprint(NSIDE)  # RING ordering, one label per pixel
    labels = np.asarray(labels).astype(str)

    # Re-order to NESTED so neighbouring pixels share runs: much smaller run-length output.
    nest_labels = labels[hp.nest2ring(NSIDE, np.arange(hp.nside2npix(NSIDE)))]

    names = sorted({str(x) for x in np.unique(nest_labels) if x})
    code = {name: i + 1 for i, name in enumerate(names)}  # 0 = outside the survey
    codes = np.array([code.get(x, 0) for x in nest_labels], dtype=np.int16)

    # Run-length encode as flat [code, count, code, count, ...].
    runs: list[int] = []
    start = 0
    for i in range(1, len(codes) + 1):
        if i == len(codes) or codes[i] != codes[start]:
            runs += [int(codes[start]), i - start]
            start = i

    out = {
        "source": "Rubin Observatory scheduler footprint, rubin_scheduler.scheduler.utils.get_current_footprint",
        "source_url": "https://github.com/lsst/rubin_scheduler",
        "reference": "SCOC Phase 3 recommendations, PSTN-056 (https://pstn-056.lsst.io)",
        "source_version": f"rubin_scheduler {version('rubin_scheduler')}, data scheduler_2026_07_23",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "nside": NSIDE,
        "order": "nested",
        "labels": ["outside"] + names,
        "rle": runs,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    inside = int((codes > 0).sum())
    print(f"{inside}/{len(codes)} pixels in footprint, {len(runs) // 2} runs -> {os.path.abspath(OUT)}")


if __name__ == "__main__":
    main()
