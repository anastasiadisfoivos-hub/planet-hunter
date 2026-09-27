"""Build the go-live data (docs/DEPLOY.md, B6): what the site shows until the daily search runs. Real data only.

    cd hunt && uv run python ../docs/ship/dayone/make_dayone.py --out ../docs/ship/dayone \
        --sweep-results ~/ph-hunt/hunt/out/sweep_final/results \
        --sweep-summary results/sweep_2026-09-26_top200_summary.json \
        --leads-results <final deep search of the lead stars>/results \
        --leads ../docs/ship/dayone/leads.json

- The 26 Sep 2026 sweep (hunt's fast search, 200 stars): one monitor record per star from hunt's result, built with
  runner's monitor_record (the records the daily search posts). hunt's result files hold no light curve, so a star
  gets MONITOR-UI's real binned curve when web/public/data/monitor/stars has it, else none.
- The two leads from DEEPHUNT's calibration run, searched again by the final deep search: one monitor record each,
  with the star's stitched curve, labelled "deep". leads.json holds each lead's vetting verdict: a lead that
  survives is written to candidates/ with its vetting block (the API then pixel-checks it); one that does not is
  rejected in its monitor record, with the reasons.
- summary.json: the 26 Sep sweep's summary (the funnel).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "runner"))

from scheduler import monitor_record as mr  # noqa: E402

UI_STARS = REPO / "web" / "public" / "data" / "monitor" / "stars"


def sweep_record(path: Path) -> dict:
    res = json.loads(path.read_text())
    searched = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    empty = np.array([], float)
    rec = mr.build(res, empty, empty, np.array([], int), queue="fast", searched_at=searched)
    ui = UI_STARS / f"{res['tic']}.json"
    if ui.exists() and (u := json.loads(ui.read_text())).get("lightcurve"):
        rec.update(lightcurve=u["lightcurve"], observed_from=u.get("observed_from"), observed_to=u.get("observed_to"),
                   bin_minutes=10)
    rec["label"] = "fast"
    return rec


def lead_record(path: Path, lead: dict) -> dict:
    from hunt import lightcurve

    res = json.loads(path.read_text())
    searched = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    fetch = getattr(lightcurve, "stitch", None) or lightcurve.fetch
    lc = fetch(int(res["tic"]))  # every sector, as the deep search read them
    rec = mr.build(res, lc.time, lc.flux, lc.sector, queue="deep", searched_at=searched)
    rec["label"] = "deep"
    for d in rec["detections"]:
        if d.get("period_d") and abs(d["period_d"] / lead["period_d"] - 1) < 1e-3:
            if lead["verdict"] == "candidate":
                d["outcome"], d["reason"] = "candidate", lead["summary"]
            else:
                d["outcome"], d["reason"] = "rejected", lead["summary"]
    kinds = {d["outcome"] for d in rec["detections"]}
    rec["outcome"] = next((o for o in ("candidate", "known", "rejected") if o in kinds), "none")
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sweep-results", type=Path, required=True)
    ap.add_argument("--sweep-summary", type=Path, required=True)
    ap.add_argument("--leads-results", type=Path, required=True)
    ap.add_argument("--leads", type=Path, required=True)
    a = ap.parse_args()
    mon, cands = a.out / "monitor", a.out / "candidates"
    for d in (mon, cands):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    n = 0
    for p in sorted(a.sweep_results.glob("*.json")):
        rec = sweep_record(p)
        (mon / f"{rec['tic']}.json").write_text(json.dumps(rec, allow_nan=False, separators=(",", ":")))
        n += 1
    leads = json.loads(a.leads.read_text())["leads"]
    for lead in leads:
        rec = lead_record(a.leads_results / f"{lead['tic']}.json", lead)
        (mon / f"{rec['tic']}.json").write_text(json.dumps(rec, allow_nan=False, separators=(",", ":")))
        if lead["verdict"] == "candidate":
            shutil.copy(REPO / lead["candidate_file"], cands / Path(lead["candidate_file"]).name)
    shutil.copy(a.sweep_summary, a.out / "summary.json")
    print(json.dumps({"sweep_stars": n, "leads": {x["tic"]: x["verdict"] for x in leads},
                      "candidates": sorted(p.name for p in cands.glob("*.json"))}))


if __name__ == "__main__":
    main()
