"""Measure TGLC noise and download cost on a random sample of faint M dwarfs, and fit the Tmag noise model.

    uv run python scripts/fit_noise.py --n 60 --out results/noise_sample.json

Stars are drawn at random from cached TIC strips (tic.strip), stratified in Tmag (13-14, 14-15, 15-16), skipping
known stars. Every light curve is fetched with an empty per-run cache (FAINT_CACHE_DIR is pointed at a fresh
directory for the TGLC files), so the download sizes and times are what a nightly run pays for a new star.
Writes each star's CDPP (1 h, 2 h), days with data, sectors, bytes and seconds, and a fit of
log10(CDPP_1h) = a + b (T - 14) + c (T - 14)^2 to paste into noise.NOISE_MODEL.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import tempfile
import time
from pathlib import Path

import numpy as np


def fit(rows: list[dict], bins) -> dict:
    ok = [x for x in rows if x.get("cdpp_1h_ppm")]
    tm = np.array([x["tmag"] for x in ok]) - 14
    y = np.log10([x["cdpp_1h_ppm"] for x in ok])
    use = np.ones(len(y), bool)
    for _ in range(5):  # clip variables and broken curves (3 sigma, iterated)
        c, b, a = np.polyfit(tm[use], y[use], 2)
        resid = y - (a + b * tm + c * tm**2)
        s = 1.4826 * np.median(np.abs(resid[use]))
        use = np.abs(resid) < 3 * s
    resid = resid[use]
    dl = [x["download"] for x in ok]
    summary = {
        "n_stars": len(rows), "n_with_tglc": len(ok),
        "fit": {"a": round(float(a), 4), "b": round(float(b), 4), "c": round(float(c), 4),
                "rms_dex": round(float(np.std(resid)), 3), "clipped": int((~use).sum())},
        "median_alpha": round(float(np.median([x["alpha"] for x in ok])), 3),
        "median_days_per_sector": round(float(np.median([x["days_per_sector"] for x in ok])), 2),
        "per_star": {
            "sectors_median": float(np.median([len(x["sectors"]) for x in ok])),
            "bytes_median": int(np.median([d["bytes"] for d in dl])), "bytes_p90": int(np.percentile([d["bytes"] for d in dl], 90)),
            "bytes_per_sector_median": int(np.median([d["bytes"] / max(d["files"], 1) for d in dl])),
            "seconds_median": round(float(np.median([x["wall_s"] for x in ok])), 2),
            "seconds_p90": round(float(np.percentile([x["wall_s"] for x in ok], 90)), 2),
            "resolve_s_median": round(float(np.median([d["resolve_s"] for d in dl])), 2),
            "download_s_median": round(float(np.median([d["download_s"] for d in dl])), 2)},
        "cdpp_1h_by_tmag": {f"{lo}-{hi}": round(float(np.median([x["cdpp_1h_ppm"] for x in ok if lo <= x["tmag"] < hi])))
                            for lo, hi in bins if any(lo <= x["tmag"] < hi for x in ok)},
    }
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path("results/noise_sample.json"))
    ap.add_argument("--refit", action="store_true", help="only redo the fit on an existing --out file")
    ap.add_argument("--remeasure", type=Path, help="cold-cache directory of an earlier run: re-read each star's "
                    "files from there (no downloads) with the current loader defaults, keep the download stats")
    args = ap.parse_args()
    bins = [(13, 14), (14, 15), (15, 16)]
    if args.refit or args.remeasure:
        rows = json.loads(args.out.read_text())["stars"]
        if args.remeasure:
            from skyfaint import noise, tglc

            for r in rows:
                if "error" in r:
                    continue
                os.environ["FAINT_CACHE_DIR"] = str(args.remeasure / str(r["tic"]))
                lc = tglc.get_lightcurves(r["tic"])
                assert lc.meta["download"]["from_cache"] == lc.meta["download"]["files"]
                star = json.loads((args.remeasure / str(r["tic"]) / "json" / "tic" / f"{r['tic']}.json").read_text())
                n = noise.star_noise(lc, star)
                r.update({"cdpp_1h_ppm": n["cdpp_1h_ppm"], "cdpp_2h_ppm": n["cdpp_2h_ppm"],
                          "alpha": n["detectable"]["noise_slope_alpha"],
                          "days_with_data": n["detectable"]["days_with_data"],
                          "days_per_sector": round(n["detectable"]["days_with_data"] / len(lc.sectors), 2),
                          "rmin_p5": n["detectable"]["by_period"]["5"],
                          "scattered_light_cut": sum(p["n_scattered_light"] for p in lc.products)})
        summary = fit(rows, bins)
        args.out.write_text(json.dumps({"summary": summary, "stars": rows}, indent=1))
        print(json.dumps(summary, indent=1))
        return

    from skyfaint import cache, known, noise, tglc

    strips = sorted((cache.cache_dir() / "json" / "tic-strips").glob("*/*.json"))
    rng = random.Random(args.seed)
    known_any = set().union(*known.load().values())
    pool = [r for p in rng.sample(strips, min(12, len(strips))) for r in json.loads(p.read_text())]
    pool = [r for r in pool if r["tic"] not in known_any and r["rad"] and (r["contratio"] or 0) <= 1]
    picks = []
    for lo, hi in bins:
        sel = [r for r in pool if lo <= r["tmag"] < hi]
        picks += rng.sample(sel, min(len(sel), args.n // len(bins)))

    fresh = Path(tempfile.mkdtemp(prefix="faint-cold-"))
    rows = []
    for r in picks:
        # cold TGLC cache per star (the TIC row / Gaia id lookups are part of the cost too: cleared as well)
        os.environ["FAINT_CACHE_DIR"] = str(fresh / str(r["tic"]))
        (fresh / str(r["tic"]) / "json" / "tic").mkdir(parents=True, exist_ok=True)
        (fresh / str(r["tic"]) / "json" / "tic" / f"{r['tic']}.json").write_text(json.dumps(r))  # TIC row known
        t0 = time.time()
        try:
            lc = tglc.get_lightcurves(r["tic"])
        except LookupError as e:
            rows.append({"tic": r["tic"], "tmag": r["tmag"], "error": str(e)[:200]})
            continue
        n = noise.star_noise(lc, r)
        rows.append({"tic": r["tic"], "tmag": r["tmag"], "rad": r["rad"], "contratio": r["contratio"],
                     "sectors": lc.sectors, "cdpp_1h_ppm": n["cdpp_1h_ppm"], "cdpp_2h_ppm": n["cdpp_2h_ppm"],
                     "alpha": n["detectable"]["noise_slope_alpha"], "days_with_data": n["detectable"]["days_with_data"],
                     "days_per_sector": round(n["detectable"]["days_with_data"] / len(lc.sectors), 2),
                     "rmin_p5": n["detectable"]["by_period"]["5"], "download": lc.meta["download"],
                     "wall_s": round(time.time() - t0, 2), "scattered_light_cut": sum(p["n_scattered_light"] for p in lc.products)})
        print(rows[-1]["tic"], rows[-1]["tmag"], rows[-1]["cdpp_1h_ppm"], len(lc.sectors), lc.meta["download"], flush=True)

    summary = fit(rows, bins)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, "stars": rows}, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
