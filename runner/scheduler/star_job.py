"""Search one star. Runs inside hunt's venv (every queue; skyfaint is installed there for faint stars), as its own
process, so a stuck MAST read or a crash only ever costs that star (the scheduler kills it at its timeout).

    python -m scheduler.star_job --queue deep --row '{"tic": 123, ...}' --out RUN/deep --catalogue RUN/catalogue.json

Writes, like hunt's sweep.process_star:
  OUT/results/<tic>.json            hunt's per-star result (every signal and dip, the stage each failed at)
  OUT/candidates/<tic>_<n>.json     each candidate (n = signal number, s<m> / d<m> for a single / duo)
  OUT/monitor/<tic>.json            the monitor's star record (monitor_record.py), when the star had data
and prints one JSON line: {tic, outcome, n_sectors, n_signals, n_candidates, best_snr, best_score, promising,
candidates: [stems], error, elapsed_s}. outcome is none | rejected | known | candidate | no_data | error.

Pass settings per queue (QUEUE_MODES). A hunt without DEEPHUNT's deep_search / dip_search switches (v2's HUNT)
runs its only search; the result says which switches were honoured.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import socket
import sys
import time
import traceback
import warnings
from pathlib import Path

QUEUE_MODES = {
    "fast": {"max_sectors": 3, "deep_search": False, "dip_search": False, "source": "spoc"},
    "deep": {"max_sectors": 999, "deep_search": True, "dip_search": True, "source": "spoc"},
    "faint": {"max_sectors": 999, "deep_search": True, "dip_search": True, "source": "tglc"},
}


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.part")
    tmp.write_text(json.dumps(obj, allow_nan=False))
    tmp.replace(path)


def run(queue: str, row: dict, out: Path, catalogue_path: Path | None, pipeline: str | None = None) -> dict:
    from hunt import analyse as an
    from hunt import catalogs, lightcurve, stars

    from scheduler import monitor_record as mr

    t_start = time.perf_counter()
    mode = QUEUE_MODES[queue]
    tic = int(row["tic"])
    kind = row.get("list") or "A"
    result: dict = {"tic": tic, "queue": queue, "pipeline": pipeline, "candidates": []}
    try:
        cat = catalogs.Catalogue.from_json(catalogue_path) if catalogue_path else catalogs.load()
        if row.get("ra") not in (None, "") and row.get("tmag") not in (None, ""):
            star = stars.Star.from_row({k: v for k, v in row.items() if isinstance(v, str | int | float)})
        else:
            star = stars.star(tic)
        if mode["source"] == "tglc":
            from skyfaint.tglc import get_lightcurves

            lc = get_lightcurves(tic).to_hunt()
        else:
            fetch = getattr(lightcurve, "stitch", None) or lightcurve.fetch
            lc = fetch(tic, max_sectors=mode["max_sectors"])
        t_fetch = time.perf_counter()
        params = inspect.signature(an.analyse).parameters
        switches = {k: mode[k] for k in ("deep_search", "dip_search") if k in params}
        res = an.analyse(star, lc, cat, kind, **switches)
        summary = res.summary()
        summary["timings_s"] = {"fetch": round(t_fetch - t_start, 2), **summary.get("timings_s", {})}
        summary["runner"] = {"queue": queue, "switches": switches, "pipeline": pipeline}
        stems = []
        for cand in res.candidates:
            stem = f"{tic}_{cand['id'].rsplit(':', 1)[1]}"
            cand.setdefault("search_pass", queue)
            _write(out / "candidates" / f"{stem}.json", mr.clean(cand))
            stems.append(stem)
        durations = {e.name: e.duration_h for e in cat.on_star(tic)} if hasattr(cat, "on_star") else {}
        record = mr.build(summary, lc.time, lc.flux, lc.sector, queue=queue, listed_durations=durations)
        _write(out / "monitor" / f"{tic}.json", record)
        sigs = summary.get("signals") or []
        result.update({
            "outcome": record["outcome"],
            "n_sectors": len(summary.get("sectors") or []),
            "n_signals": len(sigs) + len(summary.get("dips") or []),
            "n_candidates": len(stems),
            "best_snr": max((s.get("snr") or 0 for s in sigs), default=None),
            "best_score": max((s.get("score") or 0 for s in sigs), default=None),
            "promising": mr.promising(summary),
            "candidates": stems,
        })
    except LookupError as exc:
        if isinstance(exc, IndexError | KeyError):  # bugs or bad files, not "no data"
            summary, result["outcome"] = _error(tic, kind, exc), "error"
        else:
            summary = {"tic": tic, "list": kind, "error": f"no_data: {exc}"[:300], "signals": []}
            result["outcome"] = "no_data"
        result["error"] = summary["error"]
    except Exception as exc:  # network, MAST, numerical: retried by the ledger (at most 3 attempts)
        summary = _error(tic, kind, exc)
        result["outcome"], result["error"] = "error", summary["error"]
    elapsed = round(time.perf_counter() - t_start, 2)
    summary["elapsed_s"] = result["elapsed_s"] = elapsed
    from scheduler.monitor_record import clean

    _write(out / "results" / f"{tic}.json", clean(summary))
    return result


def _error(tic: int, kind: str, exc: Exception) -> dict:
    return {"tic": tic, "list": kind, "error": f"{type(exc).__name__}: {exc}"[:300], "signals": [],
            "traceback": traceback.format_exc()[-1500:]}


def main(argv: list[str] | None = None) -> int:
    warnings.filterwarnings("ignore")
    socket.setdefaulttimeout(120)
    p = argparse.ArgumentParser(prog="star_job")
    p.add_argument("--queue", required=True, choices=sorted(QUEUE_MODES))
    p.add_argument("--row", required=True, help="the target row as JSON")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--catalogue", type=Path, default=None)
    p.add_argument("--pipeline", default=os.environ.get("PH_PIPELINE_VERSION"))
    a = p.parse_args(argv)
    result = run(a.queue, json.loads(a.row), a.out, a.catalogue, a.pipeline)
    sys.stdout.write("\n@@RESULT " + json.dumps(result, allow_nan=False, default=str) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
