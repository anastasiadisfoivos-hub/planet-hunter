"""Child processes: one per star (star_job.py in hunt's or faint's venv) and one per candidate vet (skyvet in
vet's venv). Each runs in its own process group with one BLAS thread, so four of them fill four cores without
oversubscribing, and is killed with its whole group at its timeout. Output goes to a log file, not a pipe (a
chatty child can never block on a full pipe); the log is deleted when the job succeeds."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from scheduler.config import Config

RESULT_MARK = "@@RESULT "
THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
               "NUMBA_NUM_THREADS")


def child_env(cfg: Config, extra: dict | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.update(cfg.cache_env())
    env.update({v: "1" for v in THREAD_VARS})
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])  # runner/, for `-m scheduler.star_job`
    env["PYTHONUNBUFFERED"] = "1"
    env["MPLBACKEND"] = "Agg"
    for secret in ("PH_INGEST_TOKEN", "PH_DATABASE_URL"):  # children never need them
        env.pop(secret, None)
    env.update(extra or {})
    return env


@dataclass
class Job:
    kind: str  # "star" | "vet"
    queue: str  # fast | deep | faint | vet
    key: str  # tic or candidate stem
    proc: subprocess.Popen
    log_path: Path
    timeout_s: float
    started: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)

    @property
    def elapsed(self) -> float:
        return time.time() - self.started

    def poll(self) -> int | None:
        return self.proc.poll()

    def over_time(self) -> bool:
        return self.elapsed > self.timeout_s

    def kill(self) -> None:
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.proc.wait(5)

    def tail(self, n: int = 1500) -> str:
        try:
            return self.log_path.read_text(errors="replace")[-n:]
        except OSError:
            return ""

    def result(self) -> dict | None:
        """The @@RESULT line a star job prints last."""
        try:
            text = self.log_path.read_text(errors="replace")
        except OSError:
            return None
        for line in reversed(text.splitlines()):
            if line.startswith(RESULT_MARK):
                try:
                    return json.loads(line[len(RESULT_MARK):])
                except ValueError:
                    return None
        return None

    def cleanup(self, keep: bool) -> None:
        if not keep:
            try:
                self.log_path.unlink()
            except OSError:
                pass


def _spawn(cmd: list[str], env: dict, log_path: Path, cwd: Path | None = None) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log_path, "wb")
    try:
        return subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env,
                                cwd=cwd, start_new_session=True)
    finally:
        fh.close()


def start_star(cfg: Config, queue: str, row: dict, out: Path, catalogue: Path | None,
               pipeline: str | None) -> Job:
    venv = "faint" if queue == "faint" else "hunt"
    clean_row = {k: v for k, v in row.items() if k != "sectors_key" and isinstance(v, str | int | float | bool)}
    cmd = [str(cfg.venv_python(venv)), "-m", "scheduler.star_job", "--queue", queue, "--row",
           json.dumps(clean_row), "--out", str(out)]
    if catalogue is not None:
        cmd += ["--catalogue", str(catalogue)]
    extra = {"PH_PIPELINE_VERSION": pipeline or ""}
    tic = str(row["tic"])
    proc = _spawn(cmd, child_env(cfg, extra), out / "logs" / f"{tic}.log")
    return Job("star", queue, tic, proc, out / "logs" / f"{tic}.log", cfg.timeouts[queue], meta={"row": row})


def start_vet(cfg: Config, stem: str, source: Path, out: Path) -> Job:
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(cfg.venv_python("vet")), "-m", "skyvet.cli", str(source), "-o", str(out / f"{stem}.json"),
           "--tri-budget", str(cfg.tri_budget_s)]
    proc = _spawn(cmd, child_env(cfg), out / "logs" / f"{stem}.log")
    return Job("vet", "vet", stem, proc, out / "logs" / f"{stem}.log", cfg.timeouts["vet"],
               meta={"source": str(source), "vetted": str(out / f"{stem}.json")})
