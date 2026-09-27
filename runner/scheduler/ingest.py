"""The night's wrap-up, after the search window closes:

1. merge   `hunt merge RUN/fast RUN/faint RUN/deep --out RUN/merged` (hunt's venv): ranked candidates, the funnel,
           summary.json, and the merge-only test that drops single / duo dips seen at the same time in 2+ nearby
           stars. A star searched by two queues in one night keeps its deep result (deep is listed last).
2. vetting every merged candidate gets skyvet's `vetting` block from its vet (vets.vetted_path) when one ran; a
           candidate whose vet did not finish is ingested without it and vetted first on the next night, then
           re-ingested (the API upserts; an unchanged file is not rewritten).
3. monitor every star's monitor record goes to RUN/merged/monitor (deep's wins over fast's); a dip the merge
           rejected is marked rejected there too.
4. ingest  `python -m api.finder_ingest --dir RUN/merged/candidates --monitor-dir RUN/merged/monitor --run-id RUN
           --run-started-at T --summary RUN/merged/summary.json --sensitivity hunt/results/sensitivity.json`
           in api's venv (extra `finder`: pixels/ and the known lists), with PH_DATABASE_URL and PH_ADAPTERS=real.
           This stores the candidates, runs the pixel checks and marks the monitor run done.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from scheduler.config import Config
from scheduler.jobs import child_env

MERGE_ORDER = ("fast", "faint", "deep")


def _run(cmd: list[str], env: dict, timeout_s: float, log, cwd: Path | None = None) -> tuple[int, str]:
    log("$ " + " ".join(cmd[:6]) + (" ..." if len(cmd) > 6 else ""))
    try:
        p = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        return 124, f"timeout after {timeout_s:.0f} s: {(exc.stdout or '')[-2000:]}"
    return p.returncode, (p.stdout or "")[-6000:] + (p.stderr or "")[-3000:]


def merge(cfg: Config, run_dir: Path, log=print) -> dict:
    dirs = [run_dir / q for q in MERGE_ORDER if (run_dir / q / "results").is_dir()]
    merged = run_dir / "merged"
    if merged.exists():
        shutil.rmtree(merged)
    merged.mkdir(parents=True)
    if not dirs:
        (merged / "candidates").mkdir()
        return {"dirs": [], "candidates": 0, "rejected_at_merge": {}}
    cmd = [str(cfg.venv_python("hunt")), "-m", "hunt", "merge", *map(str, dirs), "--out", str(merged)]
    sens = cfg.repo / "hunt" / "results" / "sensitivity.json"
    if sens.exists():
        cmd += ["--sensitivity", str(sens)]
    code, out = _run(cmd, child_env(cfg), 1800, log)
    if code != 0:
        raise RuntimeError(f"hunt merge failed ({code}): {out[-1500:]}")
    index = json.loads((merged / "candidates.json").read_text())
    return {"dirs": [d.name for d in dirs], "candidates": len(index["candidates"]),
            "rejected_at_merge": index.get("rejected_at_merge", {}), "funnel": index.get("funnel")}


def attach_vetting(merged: Path, vetted: dict[str, dict]) -> dict:
    """Copy skyvet's block into each merged candidate that has a finished vet. Returns counts."""
    n_with = n_without = 0
    verdicts: dict[str, int] = {}
    for path in sorted((merged / "candidates").glob("*.json")):
        v = vetted.get(path.stem)
        vpath = Path(v["vetted_path"]) if v and v.get("vetted_path") else None
        if vpath is None or not vpath.exists():
            n_without += 1
            continue
        block = json.loads(vpath.read_text()).get("vetting")
        if not isinstance(block, dict):
            n_without += 1
            continue
        cand = json.loads(path.read_text())
        cand["vetting"] = block
        path.write_text(json.dumps(cand, indent=1))
        n_with += 1
        verdict = str((block.get("summary") or {}).get("verdict"))
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
    return {"with_vetting": n_with, "without_vetting": n_without, "verdicts": verdicts}


def collect_monitor(run_dir: Path, merged: Path, rejected: dict[str, str]) -> int:
    out = merged / "monitor"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for q in MERGE_ORDER:  # later queues overwrite earlier ones: deep's record wins
        for p in sorted((run_dir / q / "monitor").glob("*.json")) if (run_dir / q / "monitor").is_dir() else []:
            rec = json.loads(p.read_text())
            changed = False
            for d in rec.get("detections", []):
                why = rejected.get(f"{rec['tic']}:{d.get('id')}")
                if why and d.get("outcome") == "candidate":
                    d["outcome"], d["reason"] = "rejected", why
                    changed = True
            if changed:
                order = ("candidate", "known", "rejected")
                kinds = {d["outcome"] for d in rec["detections"]}
                rec["outcome"] = next((o for o in order if o in kinds), "none")
            (out / p.name).write_text(json.dumps(rec))
            n += 1
    return n


def finder_ingest(cfg: Config, merged: Path, run_id: str, run_started_iso: str, log=print) -> dict:
    cmd = [str(cfg.venv_python("api")), "-m", "api.finder_ingest", "--dir", str(merged / "candidates"),
           "--monitor-dir", str(merged / "monitor"), "--run-id", run_id, "--run-started-at", run_started_iso]
    if (merged / "summary.json").exists():
        cmd += ["--summary", str(merged / "summary.json")]
    if (merged / "sensitivity.json").exists():
        cmd += ["--sensitivity", str(merged / "sensitivity.json")]
    if cfg.db_path and not cfg.database_url:
        cmd += ["--db", cfg.db_path]
    env = child_env(cfg, {"PH_ADAPTERS": os.environ.get("PH_ADAPTERS", "real")})
    if cfg.database_url:
        env["PH_DATABASE_URL"] = cfg.database_url  # only this child sees it
    code, out = _run(cmd, env, cfg.wrap_hours * 3600, log, cwd=cfg.repo / "api")
    summary = None
    start = out.find("{")
    if start >= 0:
        try:
            summary = json.loads(out[start:out.rfind("}") + 1])
        except ValueError:
            summary = None
    return {"exit_code": code, "summary": summary, "output_tail": None if summary else out[-2000:]}
