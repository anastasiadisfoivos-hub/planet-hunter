"""Numbers for the README's Proof section, from the recorded fixtures (offline): hunt's search on each TGLC curve,
the known-ephemeris measurement for TOI-1680 b, and each star's noise.

    uv run python scripts/proof.py > results/proof.json
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "tests"))
from conftest import load  # noqa: E402

from hunt.signals import find_signals  # noqa: E402
from hunter.clean import flatten_for_search, robust_sigma  # noqa: E402
from hunter.search import in_transit  # noqa: E402
from skyfaint import noise  # noqa: E402

facts = json.loads((Path(__file__).parents[1] / "tests" / "data" / "facts.json").read_text())
out = {}
for key, tic in (("toi5688", 193634953), ("toi1680", 259168516), ("quiet", facts["quiet"]["tic"])):
    lc, star = load(tic)
    sigs = find_signals(lc.to_hunt()).signals
    n = noise.star_noise(lc, star)
    n.pop("per_sector")
    rec = {"tic": tic, "tmag": star["tmag"], "rad": star["rad"], "sectors": lc.sectors, "points": len(lc.time),
           "hunt_signals": [{"period_d": round(s.period, 6), "depth_ppm": round(s.depth * 1e6), "depth_err_ppm":
                             round(s.depth_err * 1e6), "snr": round(s.snr, 1), "sde": round(s.sde, 1),
                             "n_transits": s.n_transits, "duration_h": round(s.duration * 24, 2)} for s in sigs],
           "noise": n}
    f = facts.get(key, {})
    if "period_d" in f:
        best = sigs[0]
        rec["catalogue"] = f
        rec["top_signal_period_error_pct"] = round(100 * (best.period / f["period_d"] - 1), 4)
    if key == "toi1680":
        P, T0, D = f["period_d"], f["t0_btjd"], f["duration_h"] / 24
        flat, keep = flatten_for_search(lc.time, lc.flux, 0.9, transit_mask=in_transit(lc.time, P, T0, D, 2))
        t, y = lc.time[keep], flat[keep]
        it = in_transit(t, P, T0, 0.8 * D)
        d = 1 - y[it].mean()
        rec["at_catalogue_ephemeris"] = {"depth_ppm": round(d * 1e6), "in_transit_points": int(it.sum()),
                                         "snr": round(d / (robust_sigma(y[~it]) / np.sqrt(it.sum())), 1)}
    out[key] = rec
print(json.dumps(out, indent=1))
