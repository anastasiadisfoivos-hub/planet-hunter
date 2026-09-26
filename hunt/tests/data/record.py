"""Record the real TESS data the offline tests run on (needs the network; run from hunt/).

    uv run python tests/data/record.py [--only-stitched]

Writes tests/data/<tic>.npz (light curve incl. momentum-dump / flagged-cadence times + TIC row) and
tests/data/catalogue.json (the known-signal entries on and around these stars).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from hunt import catalogs, lightcurve, stars

HERE = Path(__file__).parent
FIXTURES = {  # role: (TIC, sectors)
    "toi": (415739607, 2),  # TOI-7303.01: TOI (PC), not a confirmed planet -> the "already known" filter
    "eb": (408512382, 2),  # detached EB in the TESS EB catalogue (Prsa+ 2022) -> rejected by the checks
    "quiet": (175516858, 2),  # M dwarf with no detection -> injection-recovery
    # Sibling-search hosts whose known planets leaked through the first masking (sweep, 2026-09-26):
    "ttv_host": (254113311, 3),  # TOI-1130: strong TTVs; the confirmed ephemeris is off by hours in S67-S104
    "rounded_host": (76923707, 3),  # TOI-181: the confirmed period is rounded (4.532 d) with a tiny error bar
}
# DEEPHUNT: every sector, stitched and binned to 10 min exactly as the sweep does (lightcurve.stitch), with the
# background and quality-flag times the dip checks need.
FIXTURES_TICS = {tic for tic, _ in FIXTURES.values()}
STITCHED = {
    "toi813": 55525572,  # TOI-813 b, ~84 d, found by Planet Hunters TESS volunteers (Eisner et al. 2020)
    "toi2180": 298663873,  # TOI-2180 b, ~261 d, one TESS transit in year 2 (Dalba et al. 2022)
}


def main() -> None:
    import sys

    cat = catalogs.load()
    keep: set[int] = set(FIXTURES_TICS)
    for role, (tic, n_sectors) in ({} if "--only-stitched" in sys.argv else FIXTURES).items():
        s = stars.star(tic)
        lc = lightcurve.fetch(tic, max_sectors=n_sectors)
        # Trim to float32 and drop flux_err precision; plenty for the tests, keeps the files small.
        lc.save(HERE / f"{tic}.npz", role=role, star=s.to_row())
        keep.add(tic)
        keep |= {e.tic for e, _ in cat.near(s.ra, s.dec)}
        print(role, tic, lc.sectors, len(lc.time), "points,", len(lc.dumps), "dump cadences")
    for role, tic in STITCHED.items():
        s = stars.star(tic)
        lc = lightcurve.stitch(tic)
        lc.save(HERE / f"{tic}.npz", role=role, star=s.to_row())
        keep.add(tic)
        keep |= {e.tic for e, _ in cat.near(s.ra, s.dec)}
        print(role, tic, lc.stitch_info())
    if "--only-stitched" in sys.argv:  # keep the recorded entries HUNT's tests rely on; add the new stars' ones
        old = json.loads((HERE / "catalogue.json").read_text())
        have = {(e["tic"], e["name"]) for e in old["entries"]}
        new = [e for e in (asdict(x) for x in cat.entries if x.tic in keep - FIXTURES_TICS)
               if (e["tic"], e["name"]) not in have]
        old["entries"] += new
        (HERE / "catalogue.json").write_text(json.dumps(old, indent=0))
    else:
        cat.to_json(HERE / "catalogue.json", keep)
    print("catalogue entries:", len(json.loads((HERE / "catalogue.json").read_text())["entries"]),
          "sizes:", {p.name: p.stat().st_size for p in HERE.glob("*.npz")}, np.__version__)


if __name__ == "__main__":
    main()
