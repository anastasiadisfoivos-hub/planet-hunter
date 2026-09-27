"""A whole run, as systemd starts it (`python -m scheduler run`), with the fake hunt / skyvet and the real API:
the monitor is live while it searches, every star is recorded once, candidates are vetted and ingested, and the
run ends done. Then the same with a power cut in the middle: the restarted run repeats nothing it had finished."""

import csv
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

from conftest import RUNNER, TOKEN

TARGETS = [  # tic, group: 10 / 15 / 20 candidates (10, 20 also promising), 14 / 21 no data, 22 always errors
    (1, "2"), (10, "2"), (14, "0"), (15, "0"), (2, "1"), (20, "2"), (22, "0"), (3, "1"), (21, "2"), (4, "0")]
FAINT = [30, 31, 35]


def setup_env(tmp_path, install, api, **extra):
    t = tmp_path / "targets.csv"
    with open(t, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "list", "tic", "ra", "dec", "tmag", "group", "sectors_2min"])
        for i, (tic, g) in enumerate(TARGETS):
            w.writerow([i + 1, "A", tic, 10 + i, -20, 10.5, g, "10 11 12"])
    f = tmp_path / "faint.csv"
    with open(f, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "tier", "tic", "ra", "dec", "tmag", "sectors"])
        for i, tic in enumerate(FAINT):
            w.writerow([i + 1, 1, tic, 50 + i, 30, 14.2, "1 2 3"])
    start = datetime.now(UTC) - timedelta(minutes=1)
    env = {**os.environ, "PH_HOME": str(install["home"]), "PH_DATA": str(install["data"]), "PH_API_URL": api.url,
           "PH_INGEST_TOKEN": TOKEN, "PH_DB_PATH": str(api.db), "PH_ADAPTERS": "fake",
           "PH_TARGETS_FILE": str(t), "PH_FAINT_FILE": str(f), "PH_RUN_START_UTC": f"{start:%H:%M}",
           "PH_SEARCH_HOURS": "1", "PH_WRAP_HOURS": "0.2", "PH_HEARTBEAT_S": "1", "PH_WORKERS": "4",
           "FAKE_HUNT_DONE_LOG": str(tmp_path / "done.log"), "PYTHONPATH": str(RUNNER), **extra}
    env.pop("PH_DATABASE_URL", None)
    return env, f"oracle-{start:%Y%m%d}"


def start(env, log):
    return subprocess.Popen([sys.executable, "-m", "scheduler", "run"], env=env, cwd=RUNNER,
                            stdout=open(log, "ab"), stderr=subprocess.STDOUT, start_new_session=True)


def ledger_rows(install):
    db = sqlite3.connect(install["data"] / "ledger.sqlite")
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute("SELECT * FROM stars")]
    except sqlite3.OperationalError:  # the scheduler has created the file but not its tables yet
        return []


def test_full_run(tmp_path, install, api):
    env, run_id = setup_env(tmp_path, install, api, FAKE_HUNT_SLEEP="0.4", PH_STAR_LIMIT="6")
    proc = start(env, tmp_path / "run.log")
    seen_live = False
    t0 = time.time()
    while proc.poll() is None and time.time() - t0 < 180:
        now = api.get("/monitor/now")
        if now["mode"] == "live" and now["run_id"] == run_id and now["star"]:
            seen_live = True
        time.sleep(0.3)
    log = (tmp_path / "run.log").read_text()
    assert proc.returncode == 0, log[-3000:]
    assert seen_live, "the monitor showed the run live"

    rows = ledger_rows(install)
    by = {(r["queue"], r["tic"]): r for r in rows}
    assert len(by) == len(rows)
    fast = [r["tic"] for r in rows if r["queue"] == "fast"]
    assert len(fast) == 6 and len(set(fast)) == 6
    # 14 (group 0) went to the deep pass first, so the fast pass skipped it
    assert by[("deep", 14)]["outcome"] == "no_data" and by[("deep", 14)]["status"] == "done"
    assert ("fast", 14) not in by
    assert by[("deep", 22)]["status"] == "failed" and by[("deep", 22)]["outcome"] == "error"
    assert by[("fast", 10)]["promising"] == 1
    deep = [r for r in rows if r["queue"] == "deep"]
    assert deep[0]["tic"] in (10, 20) or any(r["tic"] == 10 for r in deep), "promoted stars reach the deep pass"
    assert {r["tic"] for r in rows if r["queue"] == "faint"} == {30, 31, 35}

    summary = json.loads((install["data"] / "runs" / run_id / "run_summary.json").read_text())
    assert summary["ingest"]["exit_code"] == 0, summary
    assert summary["vetting"]["with_vetting"] >= 1
    assert set(summary["stars_per_hour"]) == {"fast", "deep", "faint"}

    now = api.get("/monitor/now")
    assert now["run_id"] == run_id and now["mode"] == "replay", "ingest marked the run done"
    cands = api.get("/finder/candidates")["items"]
    assert {c["tic"] for c in cands} == {10, 15, 20, 30}
    one = api.get(f"/finder/candidates/{cands[0]['id']}")
    assert one["candidate"]["vetting"]["summary"]["verdict"] == "flag"
    stats = api.get("/monitor/stats")
    assert stats["candidates"] == 4

    # started again the same day: nothing to do
    again = subprocess.run([sys.executable, "-m", "scheduler", "run"], env=env, cwd=RUNNER, capture_output=True,
                           text=True, timeout=60)
    assert again.returncode == 0 and "already done" in again.stdout
    st = subprocess.run([sys.executable, "-m", "scheduler", "status"], env=env, cwd=RUNNER, capture_output=True,
                        text=True, timeout=60)
    assert "Last run " + run_id + ": done" in st.stdout, st.stdout


def test_power_cut_resumes_without_repeats(tmp_path, install, api):
    env, run_id = setup_env(tmp_path, install, api, FAKE_HUNT_SLEEP="1.5")
    proc = start(env, tmp_path / "run1.log")
    t0 = time.time()
    while time.time() - t0 < 120:
        rows = ledger_rows(install) if (install["data"] / "ledger.sqlite").exists() else []
        if sum(r["status"] == "done" for r in rows) >= 5 and any(r["status"] == "running" for r in rows):
            break
        time.sleep(0.2)
    os.killpg(proc.pid, signal.SIGKILL)  # scheduler and every star process, mid-search
    proc.wait()
    rows = ledger_rows(install)
    finished_before = {(r["queue"], r["tic"]) for r in rows if r["status"] == "done"}
    cut_off = {(r["queue"], r["tic"]) for r in rows if r["status"] == "running"}
    assert finished_before and cut_off
    log_pos = len((tmp_path / "done.log").read_text().splitlines())

    env["FAKE_HUNT_SLEEP"] = "0"
    proc = start(env, tmp_path / "run2.log")
    assert proc.wait(180) == 0, (tmp_path / "run2.log").read_text()[-3000:]
    run2 = (tmp_path / "run2.log").read_text()
    assert "will be retried" in run2

    after = [ln.split() for ln in (tmp_path / "done.log").read_text().splitlines()[log_pos:]]
    searched_again = {({"fast": "fast", "deep": "deep"}[p] if int(t) not in FAINT else "faint", int(t))
                      for t, p in after}
    assert not (searched_again & finished_before), "a star finished before the cut was searched again"
    rows = ledger_rows(install)
    for key in cut_off:
        r = next(r for r in rows if (r["queue"], r["tic"]) == key)
        assert r["status"] in ("done", "failed") and r["attempts"] <= 2, r
    assert all(r["status"] != "running" for r in rows)
    assert api.get("/monitor/now")["run_id"] == run_id
