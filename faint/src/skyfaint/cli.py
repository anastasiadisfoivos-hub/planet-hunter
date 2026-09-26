"""skyfaint command line.

    skyfaint targets --out targets            ranked faint-star list (TIC M dwarfs, Tmag 13-16, TGLC-covered)
    skyfaint lc 259168516 [--save x.npz]      fetch and stitch every TGLC sector; print what was used
    skyfaint noise 259168516                  CDPP (1 h, 2 h) and smallest detectable planet at P = 1, 5, 10 d
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _targets(a) -> None:
    from . import targets

    res = targets.build(workers=a.workers)
    paths = targets.write(res, a.out, top=a.top)
    print(json.dumps(res["summary"], indent=2))
    print("wrote", ", ".join(str(p) for p in paths.values()))


def _lc(a) -> None:
    from . import tglc

    lc = tglc.get_lightcurves(a.tic, flux=a.flux)
    print(json.dumps({"points": len(lc.time), "sectors": lc.sectors, **lc.meta,
                      "products": [{k: p[k] for k in ("sector", "exptime", "flux_column", "n_good", "n_scattered_light")}
                                   for p in lc.products]}, indent=1))
    if a.save:
        lc.save(a.save)


def _noise(a) -> None:
    from . import noise, tglc, tic

    lc = tglc.get_lightcurves(a.tic, flux=a.flux)
    print(json.dumps(noise.star_noise(lc, tic.star(a.tic)), indent=1))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="skyfaint", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("targets", help="build the ranked faint-star target list")
    t.add_argument("--out", type=Path, default=Path("targets"))
    t.add_argument("--top", type=int, default=5000, help="rows in targets_faint_top.csv")
    t.add_argument("--workers", type=int, default=6, help="parallel MAST queries")
    t.set_defaults(fn=_targets)
    for name, fn in (("lc", _lc), ("noise", _noise)):
        p = sub.add_parser(name)
        p.add_argument("tic", type=int)
        p.add_argument("--flux", choices=("aper", "psf"), default="aper")
        if name == "lc":
            p.add_argument("--save", type=Path)
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
