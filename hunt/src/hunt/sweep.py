"""Sharded sweep with a time budget, and the merge of shard outputs into one ranked candidate set.

Shard i of N takes every N-th row of the (ranked) target file starting at row i, so each shard gets a share
of the high-priority stars. Stars already done in the output directory are skipped (resumable). New stars
stop being started once the budget is nearly used; whatever finished is written.

Each star is stitched from every sector it has (lightcurve.stitch) and searched for periodic signals and for
single / double dips (analyse.analyse).

Layout of an output directory:
  results/<tic>.json        every star searched: periodic signals and dips examined, the stage each failed at,
                            its dip events (for the merge's nearby-star test), stitching, runtimes, errors
  candidates/<tic>_<n>.json full candidate record (n = signal number, or s<m> / d<m> for a single / duo);
                            candidates/<tic>_<n>.png plot
  shard.json                shard bookkeeping (assigned, done, stopped by budget, time used)

Merge adds one test the per-star search cannot do: a single or double dip also seen at the same time in 2+
nearby stars' light curves (within NEIGHBOUR_DIPS_DEG, same sector) is a spacecraft or sky artefact, not a
transit, and is dropped (funnel stage "neighbour_dips").
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import socket
import time
import traceback
import warnings
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from . import catalogs, lightcurve, stars, targets
from .analyse import DIP_STAGES, STAGES, analyse, plot_candidate
from .checks import MUST_RUN
from .singles import DUO_MUST_RUN, SINGLE_MUST_RUN

_CATALOGUE = None
SOCKET_TIMEOUT_S = 120
STAR_TIMEOUT_S = 900  # hard wall-clock limit per star; the parent kills the star's process after this
# (a 40-sector continuous-viewing-zone star needs ~150 s to download and ~250 s to search on a CI runner)
NEIGHBOUR_DIPS_DEG = 1.0  # stars this close, in the same sector, see the same scattered light and dumps
NEIGHBOUR_DIPS_MIN_STARS = 2  # one other star with a dip at the same time can be chance; two is an artefact
# Why a process per star: MAST sometimes stops answering mid-read, and requests passes timeout=None, which
# overrides socket defaults; only killing the process reliably frees the slot.


def _load_catalogue(catalogue_path: str | None) -> None:
    global _CATALOGUE
    socket.setdefaulttimeout(SOCKET_TIMEOUT_S)
    _CATALOGUE = catalogs.Catalogue.from_json(Path(catalogue_path)) if catalogue_path else catalogs.load()


def _star_from_row(row: dict) -> stars.Star:
    if row.get("ra") not in (None, "") and row.get("tmag") not in (None, ""):
        return stars.Star.from_row(row)
    return stars.star(int(row["tic"]))


def process_star(row: dict, out_dir: str, max_sectors: int, plots: bool) -> dict:
    t0 = time.perf_counter()
    tic = int(row["tic"])
    kind = row.get("list") or "A"
    out = Path(out_dir)
    try:
        star = _star_from_row(row)
        lc = lightcurve.stitch(tic, max_sectors=max_sectors)
        t1 = time.perf_counter()
        res = analyse(star, lc, _CATALOGUE, kind)
        res.timings_s = {"fetch": t1 - t0, "analyse": time.perf_counter() - t1, **res.timings_s}
        for cand in res.candidates:
            stem = f"{tic}_{cand['id'].rsplit(':', 1)[1]}"
            (out / "candidates" / f"{stem}.json").write_text(json.dumps(cand, indent=1))
            if plots:
                plot_candidate(cand, out / "candidates" / f"{stem}.png")
        summary = res.summary()
    except LookupError as exc:
        if isinstance(exc, (IndexError, KeyError)):  # LookupError subclasses that are bugs or bad files
            summary = _error_summary(tic, kind, exc)
        else:
            summary = {"tic": tic, "list": kind, "error": f"no_data: {exc}"[:300], "signals": []}
    except Exception as exc:
        summary = _error_summary(tic, kind, exc)
    summary["elapsed_s"] = round(time.perf_counter() - t0, 2)
    _write_result(out, tic, summary)
    return summary


def _error_summary(tic: int, kind: str, exc: Exception) -> dict:
    return {"tic": tic, "list": kind, "error": f"{type(exc).__name__}: {exc}"[:300], "signals": [],
            "traceback": traceback.format_exc()[-1500:]}


def _write_result(out: Path, tic: int, summary: dict) -> None:
    tmp = out / "results" / f".{tic}.json.part"
    tmp.write_text(json.dumps(summary))
    tmp.replace(out / "results" / f"{tic}.json")


def _child(row: dict, out_dir: str, max_sectors: int, plots: bool, catalogue_path: str) -> None:
    warnings.filterwarnings("ignore")
    _load_catalogue(catalogue_path)
    process_star(row, out_dir, max_sectors, plots)


def shard_rows(rows: list[dict], shard: int, n_shards: int) -> list[dict]:
    if not 0 <= shard < n_shards:
        raise ValueError(f"shard {shard} is outside 0..{n_shards - 1}")
    return rows[shard::n_shards]


def run(tic_file: Path, out_dir: Path, shard: int = 0, n_shards: int = 1, budget_min: float = 350.0,
        workers: int | None = None, max_sectors: int = lightcurve.ALL_SECTORS, limit: int | None = None, plots: bool = True,
        catalogue_path: Path | None = None, star_timeout_s: float = STAR_TIMEOUT_S, log=print) -> dict:
    start = time.time()
    deadline = start + budget_min * 60
    for sub in ("results", "candidates"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    rows = shard_rows(targets.read(tic_file), shard, n_shards)
    if limit:
        rows = rows[:limit]
    done = {p.stem for p in (out_dir / "results").glob("*.json")}
    todo = [r for r in rows if str(int(r["tic"])) not in done]
    log(f"shard {shard}/{n_shards}: {len(rows)} stars assigned, {len(rows) - len(todo)} already done, "
        f"{len(todo)} to do, budget {budget_min} min")

    if catalogue_path is None:  # one snapshot for the whole shard, so every star is checked against the same lists
        catalogue_path = out_dir / "catalogue_snapshot.json"
        catalogs.load().to_json(catalogue_path)
    workers = workers or os.cpu_count() or 1
    ctx = mp.get_context("spawn")
    durations: list[float] = []
    running: dict[int, tuple] = {}
    finished = timeouts = 0
    stopped = False
    it = iter(todo)
    while True:
        avg = (sum(durations[-50:]) / len(durations[-50:])) if durations else 60.0
        while len(running) < workers and not stopped:
            # Start a star only if it can plausibly finish before the deadline.
            if time.time() + 1.5 * avg + 15 > deadline:
                stopped = True
                break
            row = next(it, None)
            if row is None:
                break
            p = ctx.Process(target=_child, args=(row, str(out_dir), max_sectors, plots, str(catalogue_path)),
                            daemon=True)
            p.start()
            running[int(row["tic"])] = (p, time.time(), row)
        if not running:
            break
        time.sleep(0.5)
        now = time.time()
        for tic, (p, t_start, row) in list(running.items()):
            over = now - t_start > star_timeout_s or now > deadline
            if p.is_alive() and not over:
                continue
            if p.is_alive():
                p.terminate()
                p.join(5)
                if p.is_alive():
                    p.kill()
                why = "timeout" if now - t_start > star_timeout_s else "budget"
                _write_result(out_dir, tic, {"tic": tic, "list": row.get("list") or "A", "signals": [],
                                             "error": f"{why}: stopped after {now - t_start:.0f} s",
                                             "elapsed_s": round(now - t_start, 2)})
                timeouts += why == "timeout"
            elif not (out_dir / "results" / f"{tic}.json").exists():
                _write_result(out_dir, tic, {"tic": tic, "list": row.get("list") or "A", "signals": [],
                                             "error": f"crash: exit code {p.exitcode}",
                                             "elapsed_s": round(now - t_start, 2)})
            p.join(1)
            del running[tic]
            durations.append((now - t_start) / workers)
            finished += 1
            if finished % 25 == 0:
                log(f"  {finished}/{len(todo)} stars, {(now - start) / 60:.1f} min")
        if now > deadline:
            stopped = True

    info = {"shard": shard, "n_shards": n_shards, "assigned": len(rows), "done_before": len(rows) - len(todo),
            "finished_now": finished, "timed_out": timeouts, "stopped_by_budget": stopped,
            "not_started": len(todo) - finished, "budget_min": budget_min,
            "used_min": round((time.time() - start) / 60, 2), "workers": workers, "max_sectors": max_sectors,
            "star_timeout_s": star_timeout_s, "finished_at": datetime.now(UTC).isoformat(timespec="seconds")}
    (out_dir / "shard.json").write_text(json.dumps(info, indent=1))
    return info


def funnel(summaries: list[dict], assigned: int | None = None, merge_rejected: dict | None = None) -> dict:
    """Counts at each stage. Signals are counted once per stage they survived. Periodic signals and single /
    double dips have separate funnels; dips also get rates per 1,000 stars searched."""
    with_data = [s for s in summaries if not s.get("error")]
    errors = Counter((s["error"].split(":")[0]) for s in summaries if s.get("error"))
    signals = [sig for s in with_data for sig in s["signals"]]
    surviving = len(signals)
    stages = {"signals_found": surviving}
    fail_counts = Counter(sig["failed_stage"] for sig in signals)
    for st in STAGES:
        surviving -= fail_counts.get(st, 0)
        stages[f"after_{st}"] = surviving
    check_fails = Counter(c for sig in signals if sig["failed_stage"] == "checks" for c in sig["failed_checks"])
    merge_rejected = merge_rejected or {}
    dips = [{**d, "tic": s["tic"]} for s in with_data for d in s.get("dips", [])]
    for d in dips:  # the merge-time stage
        if d["failed_stage"] is None and f"{d['tic']}:{d['kind'][0]}{d['n']}" in merge_rejected:
            d["failed_stage"] = "neighbour_dips"
    dip_funnel = {}
    n_stars = len(with_data)
    for kind in ("single", "duo"):
        ds = [d for d in dips if d["kind"] == kind]
        fc = Counter(d["failed_stage"] for d in ds)
        left = len(ds)
        row = {"found": left}
        for st in DIP_STAGES:
            left -= fc.get(st, 0)
            row[f"after_{st}"] = left
        row["candidates"] = fc.get(None, 0)
        row["candidates_per_1000_stars"] = round(1000 * fc.get(None, 0) / n_stars, 2) if n_stars else None
        row["check_failures"] = dict(Counter(c for d in ds if d["failed_stage"] == "checks"
                                             for c in d["failed_checks"]).most_common())
        dip_funnel[kind] = row
    events = [e for s in with_data for e in s.get("events", [])]
    return {
        "stars_in_list": assigned,
        "stars_searched": len(summaries),
        "stars_with_data": len(with_data),
        "stars_failed": dict(errors),
        "stars_with_a_signal": sum(1 for s in with_data if s["signals"]),
        **stages,
        "candidates": fail_counts.get(None, 0) + sum(dip_funnel[k]["candidates"] for k in dip_funnel),
        "periodic_candidates": fail_counts.get(None, 0),
        "stars_with_candidates": sum(1 for s in with_data
                                     if any(sig["failed_stage"] is None for sig in s["signals"])
                                     or any(d["failed_stage"] is None for d in s.get("dips", [])
                                            if f"{s['tic']}:{d['kind'][0]}{d['n']}" not in merge_rejected)),
        "failed_at_stage": {st: fail_counts.get(st, 0) for st in STAGES},
        "check_failures_among_signals_rejected_by_checks": dict(check_fails.most_common()),
        "must_run_checks": list(MUST_RUN),
        "dips": dip_funnel,
        "dip_events": {"found": len(events),
                       "rejected_by_a_dip_check": sum(1 for e in events if e.get("failed_checks")),
                       "by_check": dict(Counter(c for e in events for c in e.get("failed_checks", [])).most_common())},
        "dip_must_run_checks": {"single": list(SINGLE_MUST_RUN), "duo": list(DUO_MUST_RUN)},
        "sectors_per_star": _sector_stats(with_data),
    }


def _sector_stats(with_data: list[dict]) -> dict:
    n = sorted(len(s.get("sectors", [])) for s in with_data)
    if not n:
        return {}
    return {"median": n[len(n) // 2], "max": n[-1], "stars_with_5_or_more": sum(1 for x in n if x >= 5)}


def neighbour_dips(cands: dict[str, dict], summaries: dict[int, dict]) -> dict[str, dict]:
    """For each single / duo candidate: nearby stars (<= NEIGHBOUR_DIPS_DEG, same sector) with a dip event at the
    same time (within a quarter of the longer duration, at least 1 h) and a duration within a factor 2. Returns
    {candidate key: check dict}; the candidate is dropped when NEIGHBOUR_DIPS_MIN_STARS or more stars match."""
    import math

    pos = {}
    for tic, s in summaries.items():
        st = s.get("star") or {}
        if st.get("ra") is not None and st.get("dec") is not None and not s.get("error"):
            pos[tic] = (math.radians(float(st["ra"])), math.radians(float(st["dec"])))
    out = {}
    for key, c in cands.items():
        if c.get("kind") not in ("single", "duo"):
            continue
        tic = int(c["tic"])
        if tic not in pos:
            continue
        r0, d0 = pos[tic]
        matches, compared = [], 0
        for other, (r1, d1) in pos.items():
            if other == tic:
                continue
            cosd = math.sin(d0) * math.sin(d1) + math.cos(d0) * math.cos(d1) * math.cos(r0 - r1)
            sep = math.degrees(math.acos(max(-1.0, min(1.0, cosd))))
            if sep > NEIGHBOUR_DIPS_DEG:
                continue
            so = summaries[other]
            for dip in c["dips"]:
                if dip["sector"] not in so.get("sectors", []):
                    continue
                compared += 1
                for ev in so.get("events", []):
                    dt = abs(ev["mid_btjd"] - dip["mid_btjd"]) * 24
                    tol = max(0.25 * max(ev["duration_h"], dip["duration_h"]), 1.0)
                    ratio = max(ev["duration_h"], dip["duration_h"]) / max(min(ev["duration_h"], dip["duration_h"]), 1e-3)
                    if dt < tol and ratio < 2:
                        matches.append({"tic": other, "separation_deg": round(sep, 3), "mid_btjd": ev["mid_btjd"],
                                        "snr": ev["snr"]})
                        break
        n_stars = len({m["tic"] for m in matches})
        if compared == 0:
            chk = {"name": "neighbour_dips", "passed": None, "value": None, "margin": None,
                   "reason": f"No other star within {NEIGHBOUR_DIPS_DEG} deg was searched in the dips' sectors."}
        elif n_stars >= NEIGHBOUR_DIPS_MIN_STARS:
            chk = {"name": "neighbour_dips", "passed": False, "value": n_stars, "margin": 0.0,
                   "reason": f"{n_stars} nearby stars dip at the same time (e.g. TIC {matches[0]['tic']}, "
                             f"{matches[0]['separation_deg']} deg away): a spacecraft or sky artefact, not a transit.",
                   "matches": matches[:5]}
        else:
            chk = {"name": "neighbour_dips", "passed": True, "value": n_stars, "margin": None,
                   "reason": f"Compared with {compared} light curve(s) of stars within {NEIGHBOUR_DIPS_DEG} deg: "
                             f"{'no other star dips' if not n_stars else 'one other star dips (can be chance)'} "
                             f"at the same time.", "matches": matches[:5]}
        out[key] = chk
    return out


def merge(shard_dirs: list[Path], out_dir: Path, assigned: int | None = None,
          sensitivity: Path | None = None) -> dict:
    (out_dir / "candidates").mkdir(parents=True, exist_ok=True)
    summaries: dict[int, dict] = {}
    cands: dict[str, dict] = {}
    for d in shard_dirs:
        for p in sorted((d / "results").glob("*.json")) if (d / "results").exists() else []:
            s = json.loads(p.read_text())
            summaries[int(s["tic"])] = s
        for p in sorted((d / "candidates").glob("*.json")) if (d / "candidates").exists() else []:
            c = json.loads(p.read_text())
            cands[p.stem] = c
            (out_dir / "candidates" / p.name).write_text(p.read_text())
            png = p.with_suffix(".png")
            if png.exists():
                (out_dir / "candidates" / png.name).write_bytes(png.read_bytes())
    nd = neighbour_dips(cands, summaries)
    rejected = {}
    for key, chk in nd.items():
        c = cands[key]
        c["checks"] = [x for x in c["checks"] if x["name"] != "neighbour_dips"] + [chk]
        (out_dir / "candidates" / f"{key}.json").write_text(json.dumps(c, indent=1))
        if chk["passed"] is False:
            rejected[f"{c['tic']}:{c['id'].rsplit(':', 1)[1]}"] = chk["reason"]
            (out_dir / "candidates" / f"{key}.json").unlink()
            (out_dir / "candidates" / f"{key}.png").unlink(missing_ok=True)
    kept = {k: c for k, c in cands.items() if f"{c['tic']}:{c['id'].rsplit(':', 1)[1]}" not in rejected}
    ranked = sorted(kept.items(), key=lambda kv: -kv[1]["score"])
    index = [{"file": f"candidates/{stem}.json", "id": c["id"], "tic": c["tic"], "kind": c.get("kind", "periodic"),
              "score": c["score"], "score_parts": c.get("score_parts"), "period_d": c["period_d"],
              "period_range_d": c.get("period_range_d"), "period_aliases_d": c.get("period_aliases_d"),
              "depth_ppm": c["depth_ppm"], "snr": c["snr"], "sde": c["sde"], "n_transits": c["n_transits"],
              "radius_rjup": c["radius_rjup"], "radius_rearth_best": c["radius_rearth_best"],
              "single_sector_only": c["single_sector_only"], "search_list": c["search_list"],
              "sectors_used": c.get("sectors_used"), "baseline_d": c.get("baseline_d")} for stem, c in ranked]
    fun = funnel(list(summaries.values()), assigned, rejected)
    out = {"created_at": datetime.now(UTC).isoformat(timespec="seconds"), "funnel": fun, "candidates": index,
           "rejected_at_merge": rejected}
    (out_dir / "candidates.json").write_text(json.dumps(out, indent=1))
    (out_dir / "funnel.json").write_text(json.dumps(fun, indent=1))
    # summary.json next to candidates/ is what FINDER-API's ingest reads for GET /finder/funnel.
    shards = [json.loads((d / "shard.json").read_text()) for d in shard_dirs if (d / "shard.json").exists()]
    (out_dir / "summary.json").write_text(json.dumps({"created_at": out["created_at"], "funnel": fun,
                                                      "n_candidates": len(index), "shards": shards}, indent=1))
    if sensitivity is not None and Path(sensitivity).exists():
        (out_dir / "sensitivity.json").write_text(Path(sensitivity).read_text())
    return out
