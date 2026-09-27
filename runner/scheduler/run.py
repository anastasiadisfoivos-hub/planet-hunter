"""One search day, start to finish (the systemd service runs `python3 -m scheduler run` once a day, and at boot).

  run id      "oracle-YYYYMMDD": the day whose PH_RUN_START_UTC (00:15) last passed. Starting again the same day
              (reboot, crash, `systemctl restart`) resumes that run: same id, same deadline, the ledger skips what
              finished, and stars cut off mid-search are retried without costing an attempt.
  prepare     target lists (rebuilt when older than PH_TARGETS_MAX_AGE_DAYS), one known-list snapshot per run.
  search      until PH_SEARCH_HOURS after the day's start: PH_WORKERS processes, queue policy in queues.py,
              every finished star recorded in the ledger and posted to the monitor, every candidate vetted.
  wrap-up     vets still pending get the rest of the workers for up to half of PH_WRAP_HOURS, then merge and
              ingest (ingest.py). The run is then `done`; the service exits until the next day.
"""

from __future__ import annotations

import json
import signal
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scheduler import disk, ingest, jobs, queues
from scheduler.config import QUEUES, Config
from scheduler.ledger import Ledger
from scheduler.poster import Poster

JANITOR_EVERY_S = 600
KILL_GRACE_S = 900  # running stars get this long past the search window before they are cut off


def log(msg: str) -> None:
    print(f"{datetime.now(UTC):%H:%M:%S} {msg}", flush=True)


def run_day(cfg: Config, now: datetime | None = None) -> tuple[str, datetime]:
    now = now or datetime.now(UTC)
    hh, mm = (int(x) for x in cfg.run_start_utc.split(":"))
    start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < start:
        start -= timedelta(days=1)
    return f"oracle-{start:%Y%m%d}", start


def pipeline_version(cfg: Config) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(cfg.repo), "rev-parse", "--short=12", "HEAD"], capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def capabilities(cfg: Config) -> dict[str, dict]:
    """Which queues can run with what is installed. A queue that can't says why (shown by `status`)."""
    out: dict[str, dict] = {}
    hunt_py = cfg.venv_python("hunt")
    has_hunt = hunt_py.exists()
    deep_ok = False
    if has_hunt:
        probe = subprocess.run(
            [str(hunt_py), "-c", "import inspect, hunt.analyse as a; "
             "print('deep_search' in inspect.signature(a.analyse).parameters)"],
            capture_output=True, text=True, timeout=300, env=jobs.child_env(cfg))
        deep_ok = probe.stdout.strip().endswith("True")
    out["fast"] = {"enabled": has_hunt, "why": None if has_hunt else "hunt venv missing"}
    out["deep"] = {"enabled": deep_ok, "why": None if deep_ok else
                   "hunt on this ref has no deep search (DEEPHUNT not merged)" if has_hunt else "hunt venv missing"}
    faint_ok = has_hunt and (cfg.repo / "faint").is_dir() and subprocess.run(
        [str(hunt_py), "-c", "import skyfaint.tglc"], capture_output=True, timeout=300,
        env=jobs.child_env(cfg)).returncode == 0
    out["faint"] = {"enabled": faint_ok, "why": None if faint_ok else
                    "faint/ not on this ref" if not (cfg.repo / "faint").is_dir() else "skyfaint not in hunt's venv"}
    vet_ok = cfg.vet and cfg.venv_python("vet").exists()
    out["vet"] = {"enabled": vet_ok, "why": None if vet_ok else
                  "PH_VET=0" if not cfg.vet else "vet/ not on this ref"}
    api_ok = cfg.venv_python("api").exists()
    out["ingest"] = {"enabled": api_ok, "why": None if api_ok else "api venv missing"}
    return out


def _age_days(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 86400 if path.exists() else float("inf")


def prepare_targets(cfg: Config, caps: dict) -> tuple[Path | None, Path | None]:
    bright = cfg.targets_file
    if bright is None:
        bright = cfg.targets_dir / "targets.csv"
        if caps["fast"]["enabled"] and _age_days(bright) > cfg.targets_max_age_days:
            log("targets: building hunt's ranked list (hunt targets)")
            tmp = cfg.targets_dir / "building"
            p = subprocess.run([str(cfg.venv_python("hunt")), "-m", "hunt", "targets", "--out", str(tmp)],
                               env=jobs.child_env(cfg), capture_output=True, text=True, timeout=4 * 3600)
            if p.returncode == 0 and (tmp / "targets.csv").exists():
                for f in tmp.iterdir():
                    f.replace(cfg.targets_dir / f.name)
                tmp.rmdir()
                log(f"targets: {sum(1 for _ in open(bright)) - 1} stars")
            else:
                log(f"targets: build failed ({p.returncode}); keeping the old list. {(p.stderr or '')[-800:]}")
    faint = cfg.faint_file
    if faint is None:
        built = cfg.targets_dir / "targets_faint.csv.gz"
        faint = built if built.exists() else cfg.repo / "faint" / "results" / "targets_faint_top.csv"
    return (bright if bright.exists() else None), (faint if faint.exists() else None)


def snapshot_catalogue(cfg: Config, run_dir: Path) -> Path | None:
    path = run_dir / "catalogue.json"
    if path.exists():
        return path
    code = ("from pathlib import Path; from hunt import catalogs; "
            f"catalogs.load().to_json(Path({str(path)!r}))")
    p = subprocess.run([str(cfg.venv_python("hunt")), "-c", code], env=jobs.child_env(cfg), capture_output=True,
                       text=True, timeout=1800)
    if p.returncode != 0:
        log(f"catalogue snapshot failed; each star loads the lists itself. {(p.stderr or '')[-500:]}")
        return None
    return path


class Runner:
    def __init__(self, cfg: Config, now: datetime | None = None):
        self.cfg = cfg
        self.run_id, self.day_start = run_day(cfg, now)
        self.ledger = Ledger(cfg.ledger_path)
        self.run_dir = cfg.runs_dir / self.run_id
        self.stop_requested = False
        self.running: dict[str, jobs.Job] = {}
        self.used_s = {q: 0.0 for q in QUEUES}
        self.done = {q: 0 for q in QUEUES}
        self.total = {q: 0 for q in QUEUES}
        self.disk: dict = {}
        self.caps: dict = {}
        self.poster: Poster | None = None
        self.state = "starting"

    # ---- bookkeeping ----------------------------------------------------------------------------------------

    def heartbeat_file(self, extra: dict | None = None) -> None:
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        running: dict[str, int] = {}
        for j in self.running.values():
            running[j.queue] = running.get(j.queue, 0) + 1
        hb = {"run_id": self.run_id, "state": self.state, "at": datetime.now(UTC).isoformat(timespec="seconds"),
              "day_start": self.day_start.isoformat(), "queues": {q: {"done": self.done[q], "total": self.total[q],
                                                                      "running": running.get(q, 0)} for q in QUEUES},
              "vets_running": running.get("vet", 0), "vets_pending": self.ledger.pending_vets(),
              "poster": self.poster.stats if self.poster else None, "disk": self.disk,
              "capabilities": self.caps, **(extra or {})}
        tmp = self.cfg.state_dir / ".heartbeat.json.part"
        tmp.write_text(json.dumps(hb, indent=1, default=str))
        tmp.replace(self.cfg.state_dir / "heartbeat.json")

    def _progress(self, q: str) -> None:
        running = sum(1 for j in self.running.values() if j.queue == q)
        self.total[q] = max(self.total[q], self.done[q] + running)
        if self.poster:
            self.poster.set_progress(q, self.done[q], self.total[q])

    # ---- jobs -----------------------------------------------------------------------------------------------

    def _reap(self) -> None:
        for key, job in list(self.running.items()):
            code = job.poll()
            timed_out = code is None and job.over_time()
            if code is None and not timed_out:
                continue
            if timed_out:
                job.kill()
            del self.running[key]
            if job.kind == "star":
                self._finish_star(job, timed_out)
            else:
                self._finish_vet(job, timed_out)

    def _finish_star(self, job: jobs.Job, timed_out: bool) -> None:
        q, tic = job.queue, int(job.key)
        res = None if timed_out else job.result()
        if res is None:
            outcome = "timeout" if timed_out else "crash"
            res = {"outcome": outcome, "error": f"{outcome} after {job.elapsed:.0f} s; exit {job.proc.returncode}: "
                                                f"{job.tail(400)}", "elapsed_s": round(job.elapsed, 1)}
        status = self.ledger.finish(q, tic, res)
        self.used_s[q] += job.elapsed
        self.done[q] += 1
        self._progress(q)
        job.cleanup(keep=status != "done" or res.get("outcome") == "error")
        mon = self.run_dir / q / "monitor" / f"{tic}.json"
        if res.get("outcome") not in ("timeout", "crash", "error", "no_data") and mon.exists() and self.poster:
            try:
                self.poster.star(q, json.loads(mon.read_text()))
            except ValueError:
                pass
        stems = res.get("candidates") or []
        if stems:
            self.ledger.add_vets(self.run_id, [(s, tic, str(self.run_dir / q / "candidates" / f"{s}.json"))
                                               for s in stems])
        if q == "fast" and res.get("promising") and "deep" in self.queues:
            self.queues["deep"].reset()  # let the deep queue see the newly promoted star first
        log(f"{q:5s} TIC {tic}: {res.get('outcome')} in {job.elapsed:.0f} s"
            + (f", {len(stems)} candidate(s)" if stems else "") + (f" [{status}]" if status != "done" else ""))

    def _finish_vet(self, job: jobs.Job, timed_out: bool) -> None:
        vetted = Path(job.meta["vetted"])
        current = self.ledger.get_vet(job.key)
        if current is None or current["source"] != job.meta["source"]:
            # The same candidate was found again (the deep pass after the fast one) while this vet ran: the
            # newer file is queued and its vet is the one that counts.
            job.cleanup(keep=False)
            log(f"vet   {job.key}: superseded by a newer search of the star")
            return
        verdict, ok, err = None, False, None
        if not timed_out and job.proc.returncode == 0 and vetted.exists():
            try:
                block = json.loads(vetted.read_text()).get("vetting") or {}
                verdict, ok = (block.get("summary") or {}).get("verdict"), True
            except ValueError as exc:
                err = f"unreadable vetted file: {exc}"
        else:
            err = "timeout" if timed_out else f"exit {job.proc.returncode}: {job.tail(400)}"
        self.ledger.finish_vet(job.key, ok=ok, verdict=verdict, vetted_path=str(vetted) if ok else None,
                               elapsed_s=round(job.elapsed, 1), error=err)
        job.cleanup(keep=not ok)
        log(f"vet   {job.key}: {verdict if ok else 'failed'} in {job.elapsed:.0f} s")

    def _start_vet(self) -> bool:
        v = self.ledger.next_vet()
        if v is None:
            return False
        src = Path(v["source"])
        try:
            cand = json.loads(src.read_text())
        except (OSError, ValueError) as exc:
            self.ledger.finish_vet(v["stem"], ok=False, error=f"candidate file unreadable: {exc}")
            return True
        if cand.get("period_d") is None:  # a single dip: skyvet needs a period
            self.ledger.finish_vet(v["stem"], ok=True, verdict="not run (single dip, no period)")
            return True
        job = jobs.start_vet(self.cfg, v["stem"], src, self.run_dir / "vetted" / src.parent.parent.name)
        self.running[f"vet:{v['stem']}"] = job
        return True

    def _start_star(self) -> bool:
        running = {q: sum(1 for j in self.running.values() if j.queue == q) for q in QUEUES}
        expected = {q: queues.expected_s(self.ledger, q) for q in QUEUES}
        while True:
            name = queues.pick_queue(self.queues, self.cfg.split, self.used_s, running, expected)
            if name is None:
                return False
            row = self.queues[name].next(self.run_id)
            if row is None:
                continue  # that queue just ran out; pick again
            job = jobs.start_star(self.cfg, name, row, self.run_dir / name, self.catalogue, self.pipeline)
            self.running[f"{name}:{row['tic']}"] = job
            self._progress(name)
            return True

    # ---- the day --------------------------------------------------------------------------------------------

    def _on_signal(self, signum, _frame) -> None:
        log(f"signal {signum}: stopping (running stars are retried on the next start)")
        self.stop_requested = True

    def execute(self) -> int:
        cfg = self.cfg
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        search_until = self.day_start + timedelta(hours=cfg.search_hours)
        run = self.ledger.start_run(self.run_id, self.day_start.timestamp(), search_until.timestamp())
        if run["state"] == "done":
            log(f"{self.run_id} is already done; next run starts {self.day_start + timedelta(days=1):%Y-%m-%d %H:%M} UTC")
            self.state = "idle"
            self.heartbeat_file({"last_run": run})
            return 0
        recovered = self.ledger.recover()
        if recovered:
            log(f"resuming {self.run_id}: {recovered} star(s) cut off last time will be retried")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.pipeline = pipeline_version(cfg)
        self.caps = capabilities(cfg)
        log(f"{self.run_id}: pipeline {self.pipeline}; search until {search_until:%Y-%m-%d %H:%M} UTC; "
            f"{cfg.workers} workers; split {cfg.split}; queues "
            + ", ".join(f"{k}={'on' if v['enabled'] else 'off (' + str(v['why']) + ')'}" for k, v in self.caps.items()))
        self.state = "preparing"
        self.heartbeat_file()
        targets, faint = prepare_targets(cfg, self.caps)
        self.catalogue = snapshot_catalogue(cfg, self.run_dir) if self.caps["fast"]["enabled"] else None
        enabled = {q: self.caps[q]["enabled"] for q in QUEUES}
        self.queues = queues.build_queues(self.ledger, targets, faint, enabled, cfg.star_limit)
        search_s = max(0.0, search_until.timestamp() - time.time())
        expected = {q: queues.expected_s(self.ledger, q) for q in QUEUES}
        plan = queues.plan(cfg.split, cfg.workers, search_s, expected, list(self.queues))
        for q, rows in self.ledger.counts(self.run_id).items():
            if q in self.done:
                self.done[q] = sum(n for s, n in rows.items() if s != "running")
        for q in self.queues:
            cap = cfg.star_limit if cfg.star_limit is not None else plan.get(q, 0)
            self.total[q] = max(self.done[q], min(plan.get(q, 0), cap) if cfg.star_limit else plan.get(q, 0))
        log(f"plan for tonight (stars): {plan}; targets {targets}; faint {faint}")
        self.poster = Poster(cfg.api_url, cfg.ingest_token, self.run_id, self.day_start, log=log)
        self.poster.start()
        for q in self.queues:
            self._progress(q)

        self.state = "searching" if run["state"] == "searching" else "wrapping"
        last_janitor = last_beat = 0.0
        vet_until = search_until.timestamp() + cfg.wrap_hours * 3600 / 2
        while not self.stop_requested:
            now = time.time()
            if now - last_janitor > JANITOR_EVERY_S:
                self.disk = disk.janitor(cfg.data, cfg.cache_dir, cfg.runs_dir, cfg.disk_cap_gb, self.run_id, log)
                last_janitor = now
            if now - last_beat > cfg.heartbeat_s:
                self.poster.heartbeat()
                self.heartbeat_file()
                last_beat = now
            self._reap()
            searching = self.state == "searching" and now < search_until.timestamp()
            if self.state == "searching" and not searching:
                self.state = "wrapping"
                self.ledger.set_run(self.run_id, "wrapping")
                log("search window closed; finishing running stars, then vetting and ingest")
            if self.state == "wrapping":
                for key, job in list(self.running.items()):
                    if job.kind == "star" and now > search_until.timestamp() + KILL_GRACE_S:
                        job.kill()
                        del self.running[key]
                        log(f"{job.queue} TIC {job.key}: cut off at the end of the night; retried next run")
                        self.ledger.recover()
            paused = bool(self.disk.get("paused"))
            vets_running = sum(1 for j in self.running.values() if j.kind == "vet")
            while len(self.running) < cfg.workers and not paused:
                vet_room = self.caps["vet"]["enabled"] and (
                    vets_running < cfg.vet_slots or (self.state == "wrapping" and now < vet_until))
                if vet_room and self._start_vet():
                    vets_running += 1
                    continue
                if not searching or not self._start_star():
                    break
            if not self.running:
                idle_search = not searching or all(q.exhausted for q in self.queues.values())
                more_vets = self.caps["vet"]["enabled"] and self.ledger.pending_vets() and time.time() < vet_until
                if idle_search and not more_vets:
                    break
                if idle_search and self.state == "searching":
                    self.state = "wrapping"
                    self.ledger.set_run(self.run_id, "wrapping")
                    log("every queue is empty for tonight; vetting what is left, then ingest")
            time.sleep(0.5)

        if self.stop_requested:
            for job in self.running.values():
                job.kill()
            self.running.clear()
            self.ledger.recover()
            self.state = "stopped"
            self.heartbeat_file()
            self.poster.close(5)
            return 0
        return self.wrap_up()

    def wrap_up(self) -> int:
        cfg = self.cfg
        self.state = "ingesting"
        self.heartbeat_file()
        self.poster.heartbeat()
        summary: dict = {"run_id": self.run_id, "counts": self.ledger.counts(self.run_id),
                         "stars_per_hour": self.rates()}
        code = 0
        try:
            m = ingest.merge(cfg, self.run_dir, log)
            merged = self.run_dir / "merged"
            summary["merge"] = {k: m[k] for k in ("dirs", "candidates")} | {"rejected_at_merge": len(m["rejected_at_merge"])}
            summary["vetting"] = ingest.attach_vetting(merged, self.ledger.vetted())
            summary["monitor_stars"] = ingest.collect_monitor(self.run_dir, merged, m["rejected_at_merge"])
            if self.caps["ingest"]["enabled"]:
                res = ingest.finder_ingest(cfg, merged, self.run_id, self.day_start.isoformat(), log)
                summary["ingest"] = res
                code = 0 if res["exit_code"] in (0, 1) else res["exit_code"]  # 1 = some invalid files, rest stored
                log(f"ingest exit {res['exit_code']}: {json.dumps(res['summary'])[:600] if res['summary'] else res['output_tail']}")
            else:
                summary["ingest"] = {"skipped": self.caps["ingest"]["why"]}
        except Exception as exc:  # the run stays 'wrapping' and the next start retries the wrap-up
            log(f"wrap-up failed: {type(exc).__name__}: {exc}")
            summary["error"] = f"{type(exc).__name__}: {exc}"
            code = 1
        summary["poster"] = self.poster.close(30)
        if code == 0:
            self.ledger.set_run(self.run_id, "done", summary)
            self.state = "done"
        (self.run_dir / "run_summary.json").write_text(json.dumps(summary, indent=1, default=str))
        self.heartbeat_file({"last_run": summary})
        log(f"{self.run_id} {self.state}: {json.dumps(summary['stars_per_hour'])}")
        return code

    def rates(self) -> dict:
        """Measured throughput this run: stars finished per wall-clock hour of the queue's worker time, scaled
        to the whole machine (stars per hour if every worker served that queue), and seconds per star."""
        out = {}
        for q in QUEUES:
            rows = [r for r in self.ledger.run_rows(self.run_id) if r["queue"] == q and r["status"] == "done"]
            secs = [r["elapsed_s"] for r in rows if r["elapsed_s"]]
            if not secs:
                continue
            mean = sum(secs) / len(secs)
            out[q] = {"stars": len(rows), "mean_s_per_star": round(mean, 1),
                      "median_s_per_star": round(sorted(secs)[len(secs) // 2], 1),
                      "stars_per_hour_all_workers": round(3600 * self.cfg.workers / mean, 1),
                      "no_data": sum(1 for r in rows if r["outcome"] == "no_data")}
        return out
