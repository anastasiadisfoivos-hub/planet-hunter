"""Results of run_dryrun.sh: per-session ledgers and manifests, repeats between sessions, the monitor as polled,
measured stars per hour, and what that means for one Kaggle session. Prints JSON."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

SPLIT = {"fast": 0.45, "deep": 0.40, "faint": 0.15}
KAGGLE_CORES, KAGGLE_SESSION_H, GRACE_H, WRAP_H = 4, 11.5, 0.25, 1.0


def rows(ledger: Path) -> list[dict]:
    db = sqlite3.connect(ledger)
    db.row_factory = sqlite3.Row
    out = [dict(r) for r in db.execute("SELECT queue, tic, status, run_id, attempts, outcome, elapsed_s FROM stars")]
    db.close()
    return out


def notebook_log(path: Path) -> str:
    nb = json.loads(path.read_text())
    text = []
    for c in nb["cells"]:
        for o in c.get("outputs", []):
            text.append("".join(o.get("text", "")) if "text" in o else json.dumps(o.get("data", {}))[:2000])
    return "".join(text)


def ts(log: str, pattern: str) -> str | None:
    m = re.search(r"^(\d\d:\d\d:\d\d) .*" + pattern, log, re.M)
    return m.group(1) if m else None


def minutes(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    d = (datetime.strptime(b, "%H:%M:%S") - datetime.strptime(a, "%H:%M:%S")).total_seconds()
    return round((d + 86400 if d < 0 else d) / 60, 1)


def main(out: Path) -> dict:
    res: dict = {"sessions": {}}
    ledgers = {}
    for name in ("s1", "s2", "s3"):
        w = out / name / "working"
        man = w / "ph-state" / "manifest.json"
        info: dict = {"output_written": man.exists()}
        if (w / "executed.ipynb").exists():
            log = notebook_log(w / "executed.ipynb")
            (out / name / "notebook_log.txt").write_text(log)
            info["install_min"] = minutes(ts(log, r"session started"), ts(log, r"workers \d+; disk cap"))
            info["session_min"] = minutes(ts(log, r"session started"), ts(log, r"done: scheduler exit"))
            m = re.search(r"STOP: [^\n]*", log)
            if m:
                info["stopped_with"] = m.group(0)
        if man.exists():
            m = json.loads(man.read_text())
            last = m.get("last_run") or {}
            info.update({k: m.get(k) for k in ("run_id", "state", "scheduler_exit", "done_total", "counts",
                                                "restored_done_total", "restored_from", "cache_mb", "error")})
            info["stars_per_hour"] = last.get("stars_per_hour")
            info["poster"] = last.get("poster")
            info["ingest"] = (last.get("ingest") or {}).get("summary") or last.get("ingest")
            info["merge"] = last.get("merge")
            ledgers[name] = rows(w / "ph-state" / "ledger.sqlite")
        res["sessions"][name] = info

    if "s1" in ledgers and "s2" in ledgers:
        s1_id = res["sessions"]["s1"]["run_id"]
        s2_id = res["sessions"]["s2"]["run_id"]
        done1 = {(r["queue"], r["tic"]) for r in ledgers["s1"] if r["status"] == "done"}
        s2_new = [(r["queue"], r["tic"]) for r in ledgers["s2"] if r["run_id"] == s2_id]
        res["reload"] = {
            "s1_rows": len(ledgers["s1"]), "s2_rows": len(ledgers["s2"]),
            "s1_rows_kept_in_s2": sum(1 for r in ledgers["s2"] if r["run_id"] == s1_id),
            "searched_in_s2": sorted(s2_new),
            "repeats": sorted(set(s2_new) & done1),
        }

    polls = [json.loads(ln) for ln in (out / "monitor_polls.jsonl").read_text().splitlines() if ln.strip()]
    s1_id = res["sessions"].get("s1", {}).get("run_id")
    live = [p for p in polls if (p["now"] or {}).get("mode") == "live"]
    res["monitor"] = {
        "polls": len(polls), "live_polls": len(live),
        "live_run_ids": sorted({p["now"].get("run_id") for p in live}),
        "first_live": live[0]["at"] if live else None, "last_live": live[-1]["at"] if live else None,
        "runner_states": sorted({((p["now"] or {}).get("runner") or {}).get("state") or "none" for p in polls}),
        "final": {k: (polls[-1]["now"] or {}).get(k) for k in ("mode", "run_id", "progress")} if polls else None,
        "s1_run_id": s1_id,
    }

    # measured seconds per star (s1: cold caches), projected onto one Kaggle session
    rates = res["sessions"].get("s1", {}).get("stars_per_hour") or {}
    install_h = (res["sessions"].get("s1", {}).get("install_min") or 15) / 60
    search_h = KAGGLE_SESSION_H - GRACE_H - WRAP_H - install_h
    proj = {}
    for q, share in SPLIT.items():
        if q in rates:
            mean = rates[q]["mean_s_per_star"]
            proj[q] = {"mean_s_per_star": mean, "stars_per_hour_4_cores": round(3600 * KAGGLE_CORES / mean, 1),
                       "per_session_at_split": int(KAGGLE_CORES * search_h * 3600 * share / mean)}
    res["kaggle_projection"] = {"cores": KAGGLE_CORES, "session_h": KAGGLE_SESSION_H,
                                "search_h": round(search_h, 2), "split": SPLIT, "queues": proj,
                                "total": sum(v["per_session_at_split"] for v in proj.values())}
    return res


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), indent=1, default=str))
