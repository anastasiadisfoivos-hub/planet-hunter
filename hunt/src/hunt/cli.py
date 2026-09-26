"""hunt CLI: targets | run | merge | inject."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import warnings
from pathlib import Path


def _log(msg: str) -> None:
    print(msg, flush=True)


def _shard(text: str) -> tuple[int, int]:
    i, n = text.split("/")
    return int(i), int(n)


def cmd_targets(a) -> int:
    from . import targets

    result = targets.build(n_sectors=a.sectors, max_tmag=a.max_tmag, refresh=a.refresh, log=_log)
    if a.limit:
        result["A"], result["B"] = result["A"][:a.limit], result["B"][:a.limit]
    paths = targets.write(result, Path(a.out))
    combined = Path(a.out) / "targets.csv"
    # One ranked file for the sweep: siblings (few, high value) interleaved with the new-star list.
    rows = []
    a_rows, b_rows = result["A"], result["B"]
    for i in range(max(len(a_rows), len(b_rows))):
        if i < len(b_rows):
            rows.append(b_rows[i])
        if i < len(a_rows):
            rows.append(a_rows[i])
    import csv
    with open(combined, "w", newline="") as fh:
        w = csv.DictWriter(fh, targets.CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r.to_csv())
    _log(json.dumps(result["summary"], indent=1))
    _log(f"wrote {paths['A']}, {paths['B']}, {combined}")
    return 0


def cmd_run(a) -> int:
    from . import sweep

    i, n = _shard(a.shard)
    info = sweep.run(Path(a.tic_file), Path(a.out), i, n, a.time_budget_min, a.workers, a.max_sectors, a.limit,
                     not a.no_plots, Path(a.catalogue) if a.catalogue else None, log=_log)
    _log(json.dumps(info, indent=1))
    return 0


def cmd_merge(a) -> int:
    from . import sweep, targets

    assigned = len(targets.read(Path(a.tic_file))) if a.tic_file else None
    out = sweep.merge([Path(d) for d in a.shard_dirs], Path(a.out), assigned,
                      Path(a.sensitivity) if a.sensitivity else None)
    _log(json.dumps(out["funnel"], indent=1))
    _log(f"{len(out['candidates'])} candidates -> {a.out}/candidates.json")
    return 0


def cmd_inject(a) -> int:
    from . import inject

    s = inject.run(Path(a.tic_file), Path(a.out), a.n_stars, a.per_star, a.workers, a.max_sectors, a.seed, log=_log)
    _log(json.dumps({k: s[k] for k in ("n_stars", "n_injections", "overall_recovery_fraction", "by_radius",
                                       "by_period")}, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    warnings.filterwarnings("ignore")
    socket.setdefaulttimeout(120)
    p = argparse.ArgumentParser(prog="hunt", description="Systematic TESS search for planet candidates.")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("targets", help="build ranked target lists")
    t.add_argument("--out", default="targets")
    t.add_argument("--sectors", type=int, default=1, help="newest N public sectors of each kind (2-min, FFI)")
    t.add_argument("--max-tmag", type=float, default=13.0)
    t.add_argument("--limit", type=int, default=None, help="keep only the top N of each list")
    t.add_argument("--refresh", action="store_true")
    t.set_defaults(fn=cmd_targets)

    r = sub.add_parser("run", help="search one shard of a target file")
    r.add_argument("--tic-file", required=True, help="targets CSV, or one TIC per line")
    r.add_argument("--shard", default="0/1", help="i/N, 0-based: rows i, i+N, i+2N, ...")
    r.add_argument("--time-budget-min", type=float, default=350.0)
    r.add_argument("--out", default="out/shard")
    r.add_argument("--workers", type=int, default=None)
    r.add_argument("--max-sectors", type=int, default=3)
    r.add_argument("--limit", type=int, default=None, help="only the first N stars of this shard")
    r.add_argument("--catalogue", default=None, help="known-signal snapshot JSON (default: download)")
    r.add_argument("--no-plots", action="store_true")
    r.set_defaults(fn=cmd_run)

    m = sub.add_parser("merge", help="merge shard outputs into ranked candidates + funnel")
    m.add_argument("shard_dirs", nargs="+")
    m.add_argument("--out", default="out/merged")
    m.add_argument("--tic-file", default=None, help="the target file, to report how many stars were listed")
    m.add_argument("--sensitivity", default=None, help="sensitivity.json to ship next to the candidates")
    m.set_defaults(fn=cmd_merge)

    i = sub.add_parser("inject", help="injection-recovery on quiet stars -> sensitivity.json")
    i.add_argument("--tic-file", required=True)
    i.add_argument("--out", default="out/sensitivity.json")
    i.add_argument("--n-stars", type=int, default=200)
    i.add_argument("--per-star", type=int, default=10)
    i.add_argument("--workers", type=int, default=None)
    i.add_argument("--max-sectors", type=int, default=3)
    i.add_argument("--seed", type=int, default=1)
    i.set_defaults(fn=cmd_inject)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
