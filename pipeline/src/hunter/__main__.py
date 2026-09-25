"""CLI: python -m hunter <name or TIC> [--max-sectors N] [--out DIR]"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

from .core import run
from .plot import plot_folded, plot_raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hunter", description="Hunt a TESS star for transits and flares.")
    parser.add_argument("target", nargs="+", help='star name ("WASP-18"), "TIC 100100827" or 100100827')
    parser.add_argument("--max-sectors", type=int, default=2, help="how many sectors to use (default 2)")
    parser.add_argument("--max-signals", type=int, default=3, help="how many transit signals to look for")
    parser.add_argument("--out", type=Path, default=Path("."), help="output folder (default: current folder)")
    parser.add_argument("--refresh", action="store_true", help="ignore cached searches and star lookups")
    args = parser.parse_args(argv)

    warnings.filterwarnings("ignore")
    target = " ".join(args.target)
    result = run(target, max_sectors=args.max_sectors, max_signals=args.max_signals, refresh=args.refresh)
    tic = result.star.tic_id
    args.out.mkdir(parents=True, exist_ok=True)

    pngs = []
    kept_t, kept_f = result.lc.time[result.keep], result.flat[result.keep]
    for n, (sig, record) in enumerate(zip(result.signal_objs, result.signals), start=1):
        kind = record["type"] or "no convincing signal"
        title = f"TIC {tic} signal {n}: {kind}, P = {sig.period:.5f} d, depth {sig.depth * 100:.3f}%"
        pngs.append(str(plot_folded(kept_t, kept_f, sig, args.out / f"tic{tic}_sig{n}_folded.png", title)))
    if not pngs:
        pngs.append(str(plot_raw(kept_t, kept_f, args.out / f"tic{tic}_flattened.png",
                                 f"TIC {tic}: no transit-like signal found")))

    payload = result.to_dict()
    payload["plots"] = [Path(p).name for p in pngs]  # relative to result.json
    (args.out / "result.json").write_text(json.dumps(payload, indent=2))

    print(f"TIC {tic} ({target}); sectors {[p['sector'] for p in result.products]}; "
          f"{result.timings_s['total']:.1f} s")
    for d in result.discoveries:
        print(f"  {d.id}  {d.type}  conf={d.confidence:.2f}  {d.known_status}  {d.name_if_known or ''}")
    if not result.discoveries:
        print("  no discoveries")
    print(f"wrote {args.out / 'result.json'} and {', '.join(pngs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
