"""Injection-recovery: how sensitive is the search?

Box-shaped transits are multiplied into the real (normalised, un-detrended) light curves of quiet stars and
the very same search, checks and cuts are run. A star is "quiet" when its own search found no signal passing
the detection cuts (SNR >= 10, SDE >= 9, >= 3 transits).

Each injection: planet radius R (Earth radii) and period P drawn log-uniformly inside a grid bin (bins are
cycled so every bin gets the same number), depth = (R / R_star)^2, impact parameter uniform in [0, 0.7],
duration = central duration for the star's density x sqrt(1 - b^2), epoch uniform in the first orbit.

detected  = the search returned a signal within 1% of P whose transits line up with the injected ones
recovered = detected AND that signal passed every cut and check (it would have become a candidate; the
            known-list stages do not apply to fake planets)
"""

from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import socket
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import lightcurve, stars, targets
from .analyse import MIN_SDE, MIN_SNR, MIN_TRANSITS, analyse
from .checks import max_duration_days
from .lightcurve import StarLC

RADIUS_EDGES = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 11.0, 15.0]  # Earth radii
PERIOD_EDGES = [0.5, 1.0, 2.0, 4.0, 7.0, 10.0, 15.0]  # days
REARTH_PER_RSUN = 109.076
MAX_IMPACT = 0.7
STAR_TIMEOUT_S = 1200


def bins() -> list[tuple[int, int]]:
    return [(i, j) for i in range(len(RADIUS_EDGES) - 1) for j in range(len(PERIOD_EDGES) - 1)]


def inject(lc: StarLC, period: float, t0: float, duration: float, depth: float) -> StarLC:
    phase = (lc.time - t0 + 0.5 * period) % period - 0.5 * period
    model = np.where(np.abs(phase) < duration / 2, 1 - depth, 1.0)
    return replace(lc, flux=lc.flux * model)


def is_quiet(result) -> bool:
    return not any(s["snr"] >= MIN_SNR and s["sde"] >= MIN_SDE and s["n_transits"] >= MIN_TRANSITS
                   for s in result.signals)


def matches(sig: dict, period: float, t0: float, duration: float) -> bool:
    if abs(sig["period_d"] - period) / period > 0.01:
        return False
    off = ((sig["t0_btjd"] - t0) / period + 0.5) % 1.0 - 0.5
    return abs(off) * period < max(duration, sig["duration_h"] / 24)


def draw(rng: np.random.Generator, bin_ij: tuple[int, int]) -> tuple[float, float]:
    i, j = bin_ij
    r = math.exp(rng.uniform(math.log(RADIUS_EDGES[i]), math.log(RADIUS_EDGES[i + 1])))
    p = math.exp(rng.uniform(math.log(PERIOD_EDGES[j]), math.log(PERIOD_EDGES[j + 1])))
    return r, p


def star_injections(star: stars.Star, lc: StarLC, bin_list: list[tuple[int, int]], seed: int,
                    check_quiet: bool = True) -> dict:
    rng = np.random.default_rng(seed)
    out = {"tic": star.tic, "quiet": True, "injections": []}
    if check_quiet:
        base = analyse(star, lc, None, "A", check_known=False)
        if not is_quiet(base):
            out["quiet"] = False
            return out
    rho, _ = star.density_solar()
    for b in bin_list:
        r_e, period = draw(rng, b)
        depth = (r_e / REARTH_PER_RSUN / star.rad) ** 2
        imp = rng.uniform(0, MAX_IMPACT)
        dur = max_duration_days(period, rho, math.sqrt(depth)) * math.sqrt(1 - imp**2)
        t0 = float(lc.time.min()) + rng.uniform(0, period)
        res = analyse(star, inject(lc, period, t0, dur, depth), None, "A", check_known=False)
        hit = next((s for s in res.signals if matches(s, period, t0, dur)), None)
        out["injections"].append({
            "bin": list(b), "radius_rearth": round(r_e, 3), "period_d": round(period, 5), "t0_btjd": round(t0, 5),
            "duration_h": round(dur * 24, 3), "depth_ppm": round(depth * 1e6, 1), "impact": round(imp, 3),
            "detected": hit is not None, "recovered": hit is not None and hit["failed_stage"] is None,
            "found": hit, "n_signals": len(res.signals)})
    return out


def _worker(tic: int, row: dict, bin_list, seed: int, max_sectors: int) -> dict:
    socket.setdefaulttimeout(120)
    t = time.perf_counter()
    try:
        star = stars.Star.from_row(row) if row.get("tmag") not in (None, "") else stars.star(tic)
        if not star.rad or star.density_solar()[0] is None:
            return {"tic": tic, "skipped": "no stellar radius"}
        lc = lightcurve.fetch(tic, max_sectors=max_sectors)
        out = star_injections(star, lc, bin_list, seed)
    except Exception as exc:
        return {"tic": tic, "skipped": f"{type(exc).__name__}: {exc}"[:200]}
    out["elapsed_s"] = round(time.perf_counter() - t, 1)
    return out


def _child(tic: int, row: dict, bin_list, seed: int, max_sectors: int, path: str) -> None:
    import warnings

    warnings.filterwarnings("ignore")
    res = _worker(tic, row, bin_list, seed, max_sectors)
    Path(path + ".part").write_text(json.dumps(res))
    Path(path + ".part").replace(path)


def summarise(star_outputs: list[dict]) -> dict:
    inj = [i for s in star_outputs for i in s.get("injections", [])]
    table = []
    for i, j in bins():
        sel = [x for x in inj if x["bin"] == [i, j]]
        n, det, rec = len(sel), sum(x["detected"] for x in sel), sum(x["recovered"] for x in sel)
        table.append({"radius_rearth": [RADIUS_EDGES[i], RADIUS_EDGES[i + 1]],
                      "period_d": [PERIOD_EDGES[j], PERIOD_EDGES[j + 1]], "n_injected": n,
                      "n_detected": det, "n_recovered": rec,
                      "recovery_fraction": round(rec / n, 3) if n else None,
                      "detection_fraction": round(det / n, 3) if n else None})

    def marginal(key: str, edges: list[float]) -> list[dict]:
        idx = 0 if key == "radius" else 1
        rows = []
        for k in range(len(edges) - 1):
            sel = [x for x in inj if x["bin"][idx] == k]
            n = len(sel)
            rows.append({"range": [edges[k], edges[k + 1]], "n_injected": n,
                         "recovery_fraction": round(sum(x["recovered"] for x in sel) / n, 3) if n else None,
                         "detection_fraction": round(sum(x["detected"] for x in sel) / n, 3) if n else None})
        return rows

    used = [s for s in star_outputs if s.get("injections")]
    return {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "definition": {
            "detected": "the search returned a signal within 1% of the injected period, in phase with it",
            "recovered": "detected, and the signal passed every cut (SNR >= 10, SDE >= 9, >= 3 transits) and every "
                         "vetting check, so it would have become a candidate",
            "injection": "box-shaped transit multiplied into the real light curve before detrending; radius and "
                         "period log-uniform within each bin; impact parameter uniform 0-0.7; duration from the "
                         "star's TIC density",
            "quiet_star": "its own search found no signal passing SNR >= 10, SDE >= 9 and >= 3 transits",
        },
        "grid": {"radius_edges_rearth": RADIUS_EDGES, "period_edges_d": PERIOD_EDGES},
        "n_stars": len(used),
        "n_injections": len(inj),
        "overall_recovery_fraction": round(sum(x["recovered"] for x in inj) / len(inj), 3) if inj else None,
        "bins": table,
        "by_radius": marginal("radius", RADIUS_EDGES),
        "by_period": marginal("period", PERIOD_EDGES),
        "stars": [{"tic": s["tic"], "n_injections": len(s["injections"])} for s in used],
        "skipped_stars": [{"tic": s["tic"], "why": s.get("skipped") or "not quiet"} for s in star_outputs
                          if not s.get("injections")],
    }


def run(tic_file: Path, out_path: Path, n_stars: int = 200, per_star: int = 10, workers: int | None = None,
        max_sectors: int = 3, seed: int = 1, log=print) -> dict:
    """Use the first quiet stars of tic_file (in order) until n_stars have been injected."""
    rows = targets.read(tic_file)
    all_bins = bins()
    workers = workers or os.cpu_count() or 1
    outputs: list[dict] = []
    raw_path = out_path.with_name(out_path.stem + "_injections.jsonl")
    raw_path.write_text("")
    k = 0
    tmp = out_path.with_name(out_path.stem + "_work")
    tmp.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    queue = iter(enumerate(rows))
    running: dict[int, tuple] = {}

    def n_used() -> int:
        return sum(1 for o in outputs if o.get("injections"))

    while True:
        # Each star in its own process, killed after STAR_TIMEOUT_S (MAST can hang; see sweep.py).
        while len(running) < workers and n_used() + len(running) < n_stars:
            nxt = next(queue, None)
            if nxt is None:
                break
            idx, row = nxt
            bl = [all_bins[(k + j) % len(all_bins)] for j in range(per_star)]
            k += per_star
            path = tmp / f"{int(row['tic'])}.json"
            path.unlink(missing_ok=True)
            p = ctx.Process(target=_child, args=(int(row["tic"]), row, bl, seed + idx, max_sectors, str(path)),
                            daemon=True)
            p.start()
            running[int(row["tic"])] = (p, time.time(), path)
        if not running:
            break
        time.sleep(0.5)
        for tic, (p, t0, path) in list(running.items()):
            if p.is_alive() and time.time() - t0 < STAR_TIMEOUT_S:
                continue
            if p.is_alive():
                p.kill()
            p.join(2)
            res = json.loads(path.read_text()) if path.exists() else {"tic": tic, "skipped": "timeout or crash"}
            del running[tic]
            outputs.append(res)
            with open(raw_path, "a") as fh:
                fh.write(json.dumps(res) + "\n")
            if len(outputs) % 20 == 0:
                log(f"  {len(outputs)} stars tried, {n_used()} quiet stars injected")
    # Keep exactly the first n_stars quiet stars in target order so reruns are comparable.
    order = {int(r["tic"]): i for i, r in enumerate(rows)}
    used = sorted((o for o in outputs if o.get("injections")), key=lambda o: order[o["tic"]])[:n_stars]
    rest = [o for o in outputs if not o.get("injections")]
    summary = summarise(used + rest)
    out_path.write_text(json.dumps(summary, indent=1))
    return summary
