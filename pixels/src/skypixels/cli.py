"""skypixels vet --tic T --period P --t0 T0 --duration D --out DIR"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skypixels", description="TESS pixel-level vetting of a transit signal")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("vet", help="is the dip on the target star or on a neighbour?")
    v.add_argument("--tic", type=int, required=True, help="TIC ID of the target")
    v.add_argument("--period", type=float, required=True, help="orbital period, days")
    v.add_argument("--t0", type=float, required=True, help="mid-transit time, BTJD (a full BJD is converted)")
    v.add_argument("--duration", type=float, required=True, help="transit duration, hours")
    v.add_argument("--sectors", type=int, nargs="*", help="TESS sectors to use (default: the newest few)")
    v.add_argument("--max-sectors", type=int, default=3, help="how many recent sectors when --sectors is not given")
    v.add_argument("--out", default="out", help="output folder for pixel_vet.json, PNGs and UI JSON")
    v.add_argument("--refresh", action="store_true", help="re-query catalogues and MAST (FITS files stay cached)")
    args = parser.parse_args(argv)

    from .vet import vet_pixels

    # astroquery and lightkurve print progress/notices on stdout; keep stdout for the JSON summary only.
    with contextlib.redirect_stdout(sys.stderr):
        vet = vet_pixels(args.tic, args.period, args.t0, args.duration, sectors=args.sectors, out_dir=args.out,
                         max_sectors=args.max_sectors, refresh=args.refresh)
    summary = {k: getattr(vet, k) for k in ("tic_id", "verdict", "reason", "on_target_probability",
                                             "centroid_offset_arcsec", "offset_sigma", "depth_on_target",
                                             "suspect_neighbours", "timings_s", "files")}
    json.dump(summary, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
