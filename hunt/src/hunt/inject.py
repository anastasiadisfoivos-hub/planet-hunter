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

Three grids (the first is HUNT's, unchanged; the other two cover the deep search):
  grid         radius 1-15 R_earth x period 0.5-15 d (42 bins)
  long_period  the same radii x period 30, 60, 120, 240, 400 d (28 bins). A long-period injection counts as
               recovered as "periodic" (a periodic candidate within 1% of P, in phase), "duo" (a duo candidate
               whose surviving aliases include P within 1% and whose dips are injected transits) or "single"
               (a single candidate on an injected transit whose period range contains P). The kind is recorded.
  single       one transit only, of a planet with a period drawn in 100-300 or 300-1000 d (radius bins x 2
               period bins = 14 bins), placed at a random time with data. Recovered = a single (or duo)
               candidate on it; "period_in_range" says whether the reported range contains the true period.
All injections go into the star's stitched curve (every sector), which is what the sweep searches. A star is
used only if it is quiet: no periodic signal passing SNR >= 10, SDE >= 9, >= 3 transits, and no single or duo
candidate of its own.
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
LONG_PERIOD_EDGES = [30.0, 60.0, 120.0, 240.0, 400.0]  # days
SINGLE_PERIOD_EDGES = [100.0, 300.0, 1000.0]  # days (only one transit is injected)
GRIDS = {"grid": PERIOD_EDGES, "long_period": LONG_PERIOD_EDGES, "single": SINGLE_PERIOD_EDGES}
REARTH_PER_RSUN = 109.076
MAX_IMPACT = 0.7
STAR_TIMEOUT_S = 7200  # every injection re-runs the whole stitched search (8 searches per star)


def bins(grid: str = "grid") -> list[tuple[int, int]]:
    edges = GRIDS[grid]
    return [(i, j) for i in range(len(RADIUS_EDGES) - 1) for j in range(len(edges) - 1)]


def all_bins() -> list[tuple[str, int, int]]:
    """Every bin of every grid, cycled over the stars (so each grid gets injections in proportion to its bins)."""
    return [(g, i, j) for g in GRIDS for i, j in bins(g)]


def inject(lc: StarLC, period: float, t0: float, duration: float, depth: float, single: bool = False) -> StarLC:
    """Box transits multiplied into the flux; single=True: only the one at t0."""
    if single:
        model = np.where(np.abs(lc.time - t0) < duration / 2, 1 - depth, 1.0)
    else:
        phase = (lc.time - t0 + 0.5 * period) % period - 0.5 * period
        model = np.where(np.abs(phase) < duration / 2, 1 - depth, 1.0)
    return replace(lc, flux=lc.flux * model)


def is_quiet(result) -> bool:
    periodic = any(s["snr"] >= MIN_SNR and s["sde"] >= MIN_SDE and s["n_transits"] >= MIN_TRANSITS
                   for s in result.signals)
    dips = any(d["failed_stage"] is None for d in getattr(result, "dips", []))
    return not periodic and not dips


def matches(sig: dict, period: float, t0: float, duration: float) -> bool:
    if abs(sig["period_d"] - period) / period > 0.01:
        return False
    off = ((sig["t0_btjd"] - t0) / period + 0.5) % 1.0 - 0.5
    return abs(off) * period < max(duration, sig["duration_h"] / 24)


def draw(rng: np.random.Generator, bin_ij: tuple[int, int], grid: str = "grid") -> tuple[float, float]:
    i, j = bin_ij
    edges = GRIDS[grid]
    r = math.exp(rng.uniform(math.log(RADIUS_EDGES[i]), math.log(RADIUS_EDGES[i + 1])))
    p = math.exp(rng.uniform(math.log(edges[j]), math.log(edges[j + 1])))
    return r, p


def _on(times: list[float], t: float, dur: float) -> bool:
    return any(abs(x - t) < max(dur, 1 / 24) for x in times)


def dip_match(res, grid: str, period: float, t0: float, dur: float, lc: StarLC) -> dict | None:
    """The single / duo candidate (or rejected dip) that sits on injected transits, with what it says about P."""
    injected = [t0] if grid == "single" else list(t0 + period * np.arange(
        math.floor((lc.time.min() - t0) / period), math.ceil((lc.time.max() - t0) / period) + 1))
    for d in getattr(res, "dips", []):
        if not all(any(abs(m - x) < max(dur, 1 / 24) for x in injected) for m in d["mid_times_btjd"]):
            continue
        pr = d.get("period_range_d")
        in_range = pr is not None and pr[0] <= period <= pr[1]
        alias = None
        if d["kind"] == "duo":
            cand = next((c for c in res.candidates if c.get("kind") == "duo" and c["id"].endswith(f"d{d['n']}")),
                        None)
            aliases = (cand or {}).get("period_aliases_d") or []
            alias = any(abs(a - period) / period < 0.01 for a in aliases) if cand else None
        return {**d, "period_in_range": in_range, "alias_matches": alias}
    return None


def star_injections(star: stars.Star, lc: StarLC, bin_list: list, seed: int, check_quiet: bool = True) -> dict:
    """bin_list items: (i, j) for HUNT's grid, or (grid, i, j)."""
    rng = np.random.default_rng(seed)
    out = {"tic": star.tic, "quiet": True, "injections": [], "stitch": lc.stitch_info()}
    if check_quiet:
        base = analyse(star, lc, None, "A", check_known=False)
        if not is_quiet(base):
            out["quiet"] = False
            return out
    rho, _ = star.density_solar()
    t_lo, t_hi = float(lc.time.min()), float(lc.time.max())
    for b in bin_list:
        grid, bij = (b[0], (b[1], b[2])) if len(b) == 3 else ("grid", tuple(b))
        r_e, period = draw(rng, bij, grid)
        depth = (r_e / REARTH_PER_RSUN / star.rad) ** 2
        imp = rng.uniform(0, MAX_IMPACT)
        dur = max_duration_days(period, rho, math.sqrt(depth)) * math.sqrt(1 - imp**2)
        single = grid == "single"
        if single:  # one transit, at a random time with data (not within a duration of an edge)
            t0 = float(rng.choice(lc.time[(lc.time > t_lo + dur) & (lc.time < t_hi - dur)]))
        else:
            t0 = t_lo + rng.uniform(0, period)
        res = analyse(star, inject(lc, period, t0, dur, depth, single), None, "A", check_known=False)
        hit = None if single else next((s for s in res.signals if matches(s, period, t0, dur)), None)
        dip = None if grid == "grid" else dip_match(res, grid, period, t0, dur, lc)
        periodic_ok = hit is not None and hit["failed_stage"] is None
        dip_ok = dip is not None and dip["failed_stage"] is None
        if dip_ok and dip["kind"] == "duo":
            dip_ok = bool(dip["alias_matches"])
        recovered_as = "periodic" if periodic_ok else (dip["kind"] if dip_ok else None)
        n_in = int(np.sum(np.abs(((lc.time - t0 + 0.5 * period) % period) - 0.5 * period) < dur / 2)) if not single \
            else int(np.sum(np.abs(lc.time - t0) < dur / 2))
        epochs = 1 if single else len(np.unique(np.round((lc.time[np.abs(((lc.time - t0 + 0.5 * period) % period)
                                                                         - 0.5 * period) < dur / 2] - t0) / period)))
        out["injections"].append({
            "grid": grid, "bin": list(bij), "radius_rearth": round(r_e, 3), "period_d": round(period, 5),
            "t0_btjd": round(t0, 5), "duration_h": round(dur * 24, 3), "depth_ppm": round(depth * 1e6, 1),
            "impact": round(imp, 3), "transits_in_data": epochs, "points_in_transit": n_in,
            "detected": hit is not None or dip is not None,
            "recovered": recovered_as is not None, "recovered_as": recovered_as,
            "period_in_range": None if dip is None or dip["kind"] != "single" else dip["period_in_range"],
            "found": hit, "found_dip": dip, "n_signals": len(res.signals)})
    return out


def _worker(tic: int, row: dict, bin_list, seed: int, max_sectors: int) -> dict:
    socket.setdefaulttimeout(120)
    t = time.perf_counter()
    try:
        star = stars.Star.from_row(row) if row.get("tmag") not in (None, "") else stars.star(tic)
        if not star.rad or star.density_solar()[0] is None:
            return {"tic": tic, "skipped": "no stellar radius"}
        lc = lightcurve.stitch(tic, max_sectors=max_sectors)
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


def _table(inj: list[dict], grid: str) -> dict:
    edges = GRIDS[grid]
    sel_g = [x for x in inj if x.get("grid", "grid") == grid]
    table = []
    for i, j in bins(grid):
        sel = [x for x in sel_g if x["bin"] == [i, j]]
        n, det, rec = len(sel), sum(x["detected"] for x in sel), sum(x["recovered"] for x in sel)
        row = {"radius_rearth": [RADIUS_EDGES[i], RADIUS_EDGES[i + 1]], "period_d": [edges[j], edges[j + 1]],
               "n_injected": n, "n_detected": det, "n_recovered": rec,
               "recovery_fraction": round(rec / n, 3) if n else None,
               "detection_fraction": round(det / n, 3) if n else None}
        if grid != "grid":
            row["recovered_as"] = {k: sum(1 for x in sel if x.get("recovered_as") == k)
                                   for k in ("periodic", "duo", "single")}
        table.append(row)

    def marginal(idx: int, e: list[float]) -> list[dict]:
        rows = []
        for k in range(len(e) - 1):
            sel = [x for x in sel_g if x["bin"][idx] == k]
            n = len(sel)
            rows.append({"range": [e[k], e[k + 1]], "n_injected": n,
                         "recovery_fraction": round(sum(x["recovered"] for x in sel) / n, 3) if n else None,
                         "detection_fraction": round(sum(x["detected"] for x in sel) / n, 3) if n else None})
        return rows

    out = {"n_injections": len(sel_g),
           "overall_recovery_fraction": round(sum(x["recovered"] for x in sel_g) / len(sel_g), 3) if sel_g else None,
           "bins": table, "by_radius": marginal(0, RADIUS_EDGES), "by_period": marginal(1, edges),
           "grid": {"radius_edges_rearth": RADIUS_EDGES, "period_edges_d": edges}}
    if grid != "grid":
        out["recovered_as"] = {k: sum(1 for x in sel_g if x.get("recovered_as") == k)
                               for k in ("periodic", "duo", "single")}
    if grid == "single":
        singles = [x for x in sel_g if x.get("recovered_as") == "single"]
        out["period_in_range_fraction"] = (round(sum(bool(x["period_in_range"]) for x in singles) / len(singles), 3)
                                           if singles else None)
    return out


def summarise(star_outputs: list[dict]) -> dict:
    inj = [i for s in star_outputs for i in s.get("injections", [])]
    base = _table(inj, "grid")
    used = [s for s in star_outputs if s.get("injections")]
    return {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "definition": {
            "detected": "the search returned a signal within 1% of the injected period, in phase with it (long "
                        "periods and singles: or a single / duo dip on the injected transits)",
            "recovered": "detected, and the signal passed every cut (SNR >= 10, SDE >= 9, >= 3 transits) and every "
                         "vetting check, so it would have become a candidate (single / duo: the dip cuts and checks; "
                         "a duo must list the injected period among its surviving aliases)",
            "injection": "box-shaped transit multiplied into the real, stitched light curve before detrending; radius "
                         "and period log-uniform within each bin; impact parameter uniform 0-0.7; duration from the "
                         "star's TIC density",
            "quiet_star": "its own search found no signal passing SNR >= 10, SDE >= 9 and >= 3 transits, and no "
                          "single or duo candidate",
            "grids": {"grid": "HUNT's periodic grid, 0.5-15 d", "long_period": "30-400 d, every transit injected",
                      "single": "one transit of a 100-1000 d planet"},
        },
        # HUNT's fields, unchanged in meaning (the short-period grid):
        "grid": base["grid"],
        "n_stars": len(used),
        "n_injections": base["n_injections"],
        "overall_recovery_fraction": base["overall_recovery_fraction"],
        "bins": base["bins"],
        "by_radius": base["by_radius"],
        "by_period": base["by_period"],
        # Added by DEEPHUNT:
        "long_period": _table(inj, "long_period"),
        "single_transit": _table(inj, "single"),
        "n_injections_all_grids": len(inj),
        "stars": [{"tic": s["tic"], "n_injections": len(s["injections"]),
                   "n_sectors": s.get("stitch", {}).get("n_sectors"),
                   "baseline_d": s.get("stitch", {}).get("baseline_d")} for s in used],
        "skipped_stars": [{"tic": s["tic"], "why": s.get("skipped") or "not quiet"} for s in star_outputs
                          if not s.get("injections")],
    }


def run(tic_file: Path, out_path: Path, n_stars: int = 200, per_star: int = 10, workers: int | None = None,
        max_sectors: int = lightcurve.ALL_SECTORS, seed: int = 1, log=print) -> dict:
    """Use the first quiet stars of tic_file (in order) until n_stars have been injected."""
    rows = targets.read(tic_file)
    every = all_bins()
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
            bl = [every[(k + j) % len(every)] for j in range(per_star)]
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
