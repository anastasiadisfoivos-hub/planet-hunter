"""Record the real data the offline tests replay (needs the network; run from vet/).

    uv run python tests/data/record.py

Runs vet_candidate on each proof candidate (tests/data/candidates) with the cache pointed at tests/data/cache,
so every network response it needs is stored there: the TIC rows, the TESS light curves, the difference images
and PRF models for LEO's pixel test, TRICERATOPS' inputs (TIC field, Gaia background, TESScut images), the Gaia
DR3 field and orbits, and VSX. Raw TESScut cutouts stay in $SKYVET_WORK_DIR, outside the repo.

Writes tests/data/expected.json: each candidate's vetting block, which the offline tests reproduce.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
CANDIDATES = ("wasp18b", "toi4257_01", "eb_408512382")


def main() -> None:
    os.environ["SKYVET_CACHE_DIR"] = str(HERE / "cache")
    os.environ.pop("SKYVET_OFFLINE", None)
    from skyvet.cli import _quiet
    from skyvet.core import vet_candidate

    expected = {}
    for name in sys.argv[1:] or CANDIDATES:
        cand = json.loads((HERE / "candidates" / f"{name}.json").read_text())
        with _quiet():
            v = vet_candidate(cand)["vetting"]
        expected[name] = v
        s = v["summary"]
        print(name, s["verdict"], v["triceratops"].get("fpp"), v["triceratops"].get("nfpp"), v["runtime_s"],
              *s["reasons"], sep="\n  ", flush=True)
    path = HERE / "expected.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps({**old, **expected}, indent=1, default=str) + "\n")
    size = sum(p.stat().st_size for p in (HERE / "cache").rglob("*") if p.is_file())
    print(f"cache: {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
