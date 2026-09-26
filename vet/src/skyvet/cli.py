"""skyvet <candidate.json>: vet one Planet Finder candidate and print its "vetting" block as JSON."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import warnings

from . import tri
from .core import vet_candidate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skyvet", description=__doc__)
    ap.add_argument("candidate", help="candidate JSON (a HUNT candidates/<tic>_<n>.json, or any dict with tic, "
                                      "period_d, t0_btjd, duration_h and ideally depth_ppm, sectors)")
    ap.add_argument("-o", "--out", help="write the whole candidate with its vetting block here")
    ap.add_argument("--no-triceratops", action="store_true", help="skip TRICERATOPS (reported as not run)")
    ap.add_argument("--tri-budget", type=float, default=tri.DEFAULT_BUDGET_S,
                    help=f"TRICERATOPS wall-clock budget in s (default {tri.DEFAULT_BUDGET_S:.0f})")
    ap.add_argument("--tri-n", type=int, default=tri.DEFAULT_N,
                    help=f"TRICERATOPS Monte Carlo draws per scenario (default {tri.DEFAULT_N})")
    ap.add_argument("--no-pixel", action="store_true", help="skip LEO's pixel-level off-target test")
    ap.add_argument("--max-sectors", type=int, default=3, help="newest sectors to use (default 3)")
    ap.add_argument("--summary", action="store_true", help="print only the summary block")
    a = ap.parse_args(argv)
    with open(a.candidate) as f:
        cand = json.load(f)
    warnings.simplefilter("ignore")
    with _quiet():
        out = vet_candidate(cand, triceratops=not a.no_triceratops, tri_budget_s=a.tri_budget, tri_n=a.tri_n,
                            pixel=not a.no_pixel, max_sectors=a.max_sectors)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)
    block = out["vetting"]["summary"] if a.summary else out["vetting"]
    print(json.dumps(block, indent=1, default=str))
    return 0


@contextlib.contextmanager
def _quiet():
    """The tools print progress (and transitDiffImage shells out to curl/unzip); keep stdout for the JSON."""
    sys.stdout.flush()
    saved = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    try:
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(devnull)
        os.close(saved)


if __name__ == "__main__":
    raise SystemExit(main())
