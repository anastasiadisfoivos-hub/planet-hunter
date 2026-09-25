"""skyspectra CLI: build the "Chemical fingerprints" data set for the planet-hunter LAB.

    uv run skyspectra build --out DIR [--tic-file FILE]

Writes elements.json, sun_spectrum.json, stars/<tic>.abundances.json, stars/<tic>.gaia_xp.json,
planets/<slug>.atmosphere.json and index.json. Every answer is cached (SKYSPECTRA_CACHE,
default ~/.cache/skyspectra), so reruns are fast and gentle on the services.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .build import PARTS, build
from .hosts import read_tic_file
from .net import get_net


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skyspectra", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="fetch, reduce and write the data set")
    b.add_argument("--out", type=Path, required=True, help="output directory")
    b.add_argument("--tic-file", type=Path,
                   help="hosts to build for: the map's hosts.json, a JSON list of TICs, or one TIC per line "
                        "(default: every NASA Exoplanet Archive host)")
    b.add_argument("--only", nargs="+", choices=PARTS, default=list(PARTS), help="build only these parts")
    b.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    tics = read_tic_file(args.tic_file) if args.tic_file else None
    index = build(args.out, get_net(), tics, tuple(args.only))
    c = index["counts"]
    print(f"{args.out}: {c['stars_with_abundances']} stars with abundances, {c['stars_with_gaia_xp']} with "
          f"Gaia XP, {c['planets']} planets with atmosphere data ({c['planets_with_spectrum']} with a "
          f"spectrum); {index['total_bytes'] / 1e6:.1f} MB")
    return 0
