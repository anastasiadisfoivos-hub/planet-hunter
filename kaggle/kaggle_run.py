"""One Planet Finder search day inside a Kaggle notebook session, with RUNNER's scheduler (runner/scheduler).

The notebook (planet_hunter_nightly.ipynb) clones the public repository at PH_REPO_REF and runs this file from
the clone. Standard library only; any Python >= 3.10 (the scheduler itself then runs in hunt's venv).

  restore   the previous run's state from the notebook's own output, attached as an input (/kaggle/input/..):
            the ledger (ledger.sqlite), hunt's ranked list (targets/, rebuilt weekly), the small JSON caches,
            and the candidate files of vets still pending. The newest `ph-state/manifest.json` found wins.
  guard     the API's /monitor/coverage/queues holds the ledger's counts from the last heartbeat. If the
            restored ledger has fewer finished stars, the state was lost: stop before searching anything twice
            and write no output (so this failed version never replaces the last good state).
  install   uv, then runner/sync-venvs.sh (venvs for hunt, faint, vet, api; locks frozen).
  search    `python -m scheduler run` with PH_RUN_PREFIX=kaggle, the day starting now and the search window
            sized to the session: it stops starting stars so that grace + vetting + merge + ingest end before
            PH_SESSION_HOURS; a watchdog sends SIGTERM at that time if anything overran (the scheduler then
            stops cleanly and the stars it cut off are retried next run).
  save      the same state to /kaggle/working/ph-state/: this version's output, the next run's input. It is
            saved even when the install or the search fails, so the chain of ledgers never breaks.

Secrets (PH_INGEST_TOKEN, PH_API_URL) come from the environment; the notebook reads them from Kaggle Secrets.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc
STATE = "ph-state"
# The session after the search window: running stars' grace (scheduler.run.KILL_GRACE_S, 15 min), then the
# wrap-up (vets for half of PH_WRAP_HOURS, then merge and ingest).
GRACE_H = 0.25
# Small caches worth carrying between sessions (answers, file indexes, TIC rows); FITS / TGLC files are not.
CACHE_KEEP = ("hunt/json", "pipeline/json", "faint/json", "vet/json")
CACHE_KEEP_MAX_MB = 1500
GZIP_OVER_MB = 5  # target lists bigger than this are saved gzipped (hunt's targets.csv is ~135 MB)


def log(msg: str) -> None:
    print(f"{datetime.now(UTC):%H:%M:%S} [kaggle] {msg}", flush=True)


# ---- settings ----------------------------------------------------------------------------------------------

class Settings:
    def __init__(self, env: dict[str, str]):
        self.env = env
        self.t0 = float(env.get("PH_SESSION_STARTED_AT") or time.time())
        self.session_h = float(env.get("PH_SESSION_HOURS") or 11.5)
        self.wrap_h = float(env.get("PH_WRAP_HOURS") or 1.0)
        root = Path(env.get("PH_KAGGLE_ROOT") or "/tmp/planet-hunter")
        self.home = Path(env.get("PH_HOME") or root / "home")
        self.data = Path(env.get("PH_DATA") or root / "data")
        self.repo = Path(env.get("PH_REPO_DIR") or self.home / "repo")
        self.inputs = Path(env.get("PH_KAGGLE_IN") or "/kaggle/input")
        self.out = Path(env.get("PH_KAGGLE_OUT") or "/kaggle/working") / STATE
        self.api_url = (env.get("PH_API_URL") or "").rstrip("/") or None
        self.allow_fresh = env.get("PH_ALLOW_FRESH_LEDGER") == "1"

    @property
    def hard_stop(self) -> float:
        return self.t0 + self.session_h * 3600


def cpu_count() -> int:
    """Cores this container may use: the affinity mask, capped by a cgroup CPU quota (docker --cpus)."""
    n = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    for path in ("/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"):
        try:
            text = Path(path).read_text().split()
        except OSError:
            continue
        if path.endswith("cpu.max") and text and text[0] != "max":
            n = min(n, max(1, math.floor(int(text[0]) / int(text[1]))))
        elif path.endswith("quota_us") and text and int(text[0]) > 0:
            period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
            n = min(n, max(1, math.floor(int(text[0]) / period)))
        break
    return n


def memory_gb() -> float | None:
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            raw = Path(path).read_text().strip()
        except OSError:
            continue
        if raw.isdigit() and int(raw) < 1 << 60:
            return int(raw) / 1024 ** 3
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024 ** 2
    except OSError:
        pass
    return None


def workers() -> int:
    """One worker per core (the scheduler runs one BLAS thread per star), at most one per 1.5 GB of memory."""
    n = cpu_count()
    mem = memory_gb()
    if mem:
        n = min(n, max(1, int(mem / 1.5)))
    return n


# ---- state: restore and save -------------------------------------------------------------------------------

def find_state(*roots: Path, max_depth: int = 5) -> Path | None:
    """The newest ph-state/ (by its manifest's saved_at) under the given roots."""
    best, best_at = None, ""
    for root in roots:
        if not root.is_dir():
            continue
        base = len(root.parts)
        for dirpath, dirs, files in os.walk(root, followlinks=True):
            here = Path(dirpath)
            if len(here.parts) - base >= max_depth:
                dirs[:] = []
            if here.name == STATE and "manifest.json" in files:
                try:
                    at = json.loads((here / "manifest.json").read_text()).get("saved_at") or ""
                except (OSError, ValueError):
                    continue
                if at > best_at:
                    best, best_at = here, at
                dirs[:] = []
    return best


def ledger_counts(path: Path) -> dict[str, dict[str, int]]:
    if not path.exists():
        return {}
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        out: dict[str, dict[str, int]] = {}
        for q, s, n in db.execute("SELECT queue, status, COUNT(*) FROM stars GROUP BY queue, status"):
            out.setdefault(q, {})[s] = n
        return out
    except sqlite3.DatabaseError:
        return {}
    finally:
        db.close()


def done_total(counts: dict[str, dict[str, int]]) -> int:
    return sum(v.get("done", 0) for v in counts.values())


def _gzip(src: Path, dest: Path) -> None:
    with open(src, "rb") as fi, gzip.open(dest, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo, 1 << 20)
    st = src.stat()
    os.utime(dest, (st.st_atime, st.st_mtime))


def _gunzip(src: Path, dest: Path) -> None:
    with gzip.open(src, "rb") as fi, open(dest, "wb") as fo:
        shutil.copyfileobj(fi, fo, 1 << 20)
    st = src.stat()
    os.utime(dest, (st.st_atime, st.st_mtime))
    src.unlink()


def restore(s: Settings) -> dict:
    """Copy the newest saved state into PH_DATA. Returns what was restored (for the log and the manifest)."""
    s.data.mkdir(parents=True, exist_ok=True)
    src = find_state(s.out.parent, s.inputs)  # an earlier save in this same session (a re-run) counts too
    if src is None:
        log(f"no saved state under {s.inputs} or {s.out.parent}: starting a new ledger")
        return {"from": None, "counts": {}}
    manifest = json.loads((src / "manifest.json").read_text())
    ledger = src / "ledger.sqlite"
    if not ledger.exists():
        raise RuntimeError(f"{src} has a manifest but no ledger.sqlite")
    if hashlib.sha256(ledger.read_bytes()).hexdigest() != manifest.get("ledger_sha256"):
        raise RuntimeError(f"{ledger}: checksum does not match its manifest (truncated or edited)")
    dest = s.data / "ledger.sqlite"
    for extra in ("-wal", "-shm"):
        Path(str(dest) + extra).unlink(missing_ok=True)
    shutil.copy2(ledger, dest)
    for sub in ("targets", "cache", "runs"):  # copy2 keeps mtimes: the targets list's age decides its rebuild
        if (src / sub).is_dir():
            shutil.copytree(src / sub, s.data / sub, dirs_exist_ok=True, copy_function=shutil.copy2)
    for gz in (s.data / "targets").glob("*.csv.gz.saved"):
        _gunzip(gz, gz.with_name(gz.name.removesuffix(".gz.saved")))
    counts = ledger_counts(dest)
    log(f"restored {src} (saved {manifest.get('saved_at')} by {manifest.get('run_id')}): "
        f"{done_total(counts)} stars done in the ledger {json.dumps(counts)}")
    return {"from": str(src), "saved_at": manifest.get("saved_at"), "run_id": manifest.get("run_id"),
            "counts": counts}


def api_done(s: Settings) -> int | None:
    """Stars done per the API's last heartbeat from a runner (GET /monitor/coverage/queues, public)."""
    if not s.api_url:
        return None
    try:
        with urllib.request.urlopen(s.api_url + "/monitor/coverage/queues", timeout=60) as r:
            body = json.loads(r.read())
    except (OSError, ValueError) as exc:
        log(f"guard: could not read {s.api_url}/monitor/coverage/queues ({exc}); skipping the check")
        return None
    return sum(int((v or {}).get("done") or 0) for v in (body.get("queues") or {}).values())


def guard(s: Settings, restored: dict) -> None:
    have = done_total(restored["counts"])
    seen = api_done(s)
    if seen is None:
        return
    log(f"guard: the API last heard {seen} stars done; the restored ledger has {have}")
    if have < seen and not s.allow_fresh:
        raise SystemExit(
            f"STOP: the restored ledger has {have} finished stars, but the API last heard {seen}. The "
            "previous run's output is not attached (Add Input > this notebook's output), so searching now "
            "would repeat stars. Attach it and run again (kaggle/README.md, 'If a run stops'); set "
            "PH_ALLOW_FRESH_LEDGER=1 only to start over on purpose.")


def _referenced_files(ledger: Path) -> list[Path]:
    """Candidate files of vets still to run, vetted files of vets done: the ledger points at them by path."""
    db = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT source, vetted_path, status FROM vets "
                          "WHERE status != 'failed' OR attempts < 3")
        out = []
        for source, vetted, status in rows:
            if status in ("pending", "running", "failed") and source:
                out.append(Path(source))
            if vetted:
                out.append(Path(vetted))
        return out
    finally:
        db.close()


def _copy_under(src_root: Path, path: Path, dest_root: Path) -> int:
    try:
        rel = path.resolve().relative_to(src_root.resolve())
    except ValueError:
        return 0
    if not path.is_file():
        return 0
    target = dest_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return path.stat().st_size


def save(s: Settings, run_id: str | None, extra: dict) -> Path:
    """Write the state to /kaggle/working/ph-state (this version's output). Built in a temporary folder and
    swapped in, so a crash mid-save leaves the old state or the new one, never half of each."""
    ledger = s.data / "ledger.sqlite"
    tmp = s.out.with_name(STATE + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    if ledger.exists():
        src = sqlite3.connect(str(ledger))
        dst = sqlite3.connect(str(tmp / "ledger.sqlite"))
        with dst:
            src.backup(dst)  # a consistent copy, WAL included
        dst.execute("PRAGMA journal_mode=DELETE")
        dst.close()
        src.close()
    if (s.data / "targets").is_dir():
        (tmp / "targets").mkdir()
        for p in (s.data / "targets").iterdir():
            if not p.is_file():
                continue  # "building/": an unfinished `hunt targets`
            if p.suffix == ".csv" and p.stat().st_size > GZIP_OVER_MB * 1024 ** 2:
                _gzip(p, tmp / "targets" / (p.name + ".gz.saved"))  # not *.csv.gz: faint's own list uses that
            else:
                shutil.copy2(p, tmp / "targets" / p.name)
    kept = 0
    budget = CACHE_KEEP_MAX_MB * 1024 ** 2
    for sub in CACHE_KEEP:
        d = s.data / "cache" / sub
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            if p.is_file() and not p.name.endswith(".part") and kept + p.stat().st_size <= budget:
                kept += _copy_under(s.data, p, tmp)
    refs = 0
    if (tmp / "ledger.sqlite").exists():
        for p in _referenced_files(tmp / "ledger.sqlite"):
            refs += bool(_copy_under(s.data, p, tmp))
    counts = ledger_counts(tmp / "ledger.sqlite")
    manifest = {
        "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_id": run_id, "data_dir": str(s.data), "counts": counts, "done_total": done_total(counts),
        "ledger_sha256": hashlib.sha256((tmp / "ledger.sqlite").read_bytes()).hexdigest()
        if (tmp / "ledger.sqlite").exists() else None,
        "cache_mb": round(kept / 1024 ** 2, 1), "vet_files": refs, **extra,
    }
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    old = s.out.with_name(STATE + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if s.out.exists():
        s.out.rename(old)
    tmp.rename(s.out)
    shutil.rmtree(old, ignore_errors=True)
    log(f"saved {s.out}: {manifest['done_total']} stars done, {manifest['cache_mb']} MB of caches, "
        f"{refs} vet file(s)")
    return s.out


# ---- install -----------------------------------------------------------------------------------------------

def sh(cmd: list[str], env: dict | None = None, timeout: float | None = None) -> None:
    log("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True, env=env, timeout=timeout)


def install(s: Settings) -> dict[str, str]:
    """uv, then one venv per package (runner/sync-venvs.sh). Returns the scheduler's environment."""
    env = dict(s.env)
    env.update({"PH_HOME": str(s.home), "PH_DATA": str(s.data)})
    uv = shutil.which("uv")
    if uv is None:
        target = s.home / "uv-bin"
        sh([sys.executable, "-m", "pip", "install", "-q", "--target", str(target), "uv"], timeout=900)
        uv = str(target / "bin" / "uv")
    env["UV"] = uv
    sh(["bash", str(s.repo / "runner" / "sync-venvs.sh")], env=env, timeout=3600)
    return env


def repo_commit(repo: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=30).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


# ---- the search --------------------------------------------------------------------------------------------

def run_prefix(ledger: Path, start: datetime) -> str:
    """"kaggle" (run id kaggle-YYYYMMDD); when that run is already done (a second session the same UTC day),
    "kaggle-2", "kaggle-3", ...: a new run that searches the next stars instead of exiting at once."""
    done: set[str] = set()
    if ledger.exists():
        db = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
        try:
            done = {r[0] for r in db.execute("SELECT run_id FROM runs WHERE state = 'done'")}
        except sqlite3.DatabaseError:
            pass
        finally:
            db.close()
    n = 1
    while f"{'kaggle' if n == 1 else f'kaggle-{n}'}-{start:%Y%m%d}" in done:
        n += 1
    return "kaggle" if n == 1 else f"kaggle-{n}"


def scheduler_env(s: Settings, env: dict[str, str], now: float) -> tuple[dict[str, str], float]:
    """The scheduler's settings for this session. Returns (env, search_until)."""
    start = datetime.fromtimestamp(now, UTC).replace(second=0, microsecond=0)
    search_until = s.hard_stop - (GRACE_H + s.wrap_h) * 3600
    search_h = max(0.0, (search_until - start.timestamp()) / 3600)
    free_gb = shutil.disk_usage(s.data).free / 1024 ** 3
    out = dict(env)
    out.setdefault("PH_WORKERS", str(workers()))
    out.setdefault("PH_DISK_CAP_GB", str(round(max(5.0, min(150.0, 0.7 * free_gb)), 1)))
    out.update({
        "PH_RUN_PREFIX": run_prefix(s.data / "ledger.sqlite", start),
        "PH_RUN_START_UTC": f"{start:%H:%M}",
        "PH_SEARCH_HOURS": f"{search_h:.3f}",
        "PH_WRAP_HOURS": str(s.wrap_h),
        "PH_AUTO_UPDATE": "0",
        "PYTHONPATH": str(s.repo / "runner"),
        "PYTHONUNBUFFERED": "1",
    })
    return out, start.timestamp() + search_h * 3600


def run_scheduler(s: Settings, env: dict[str, str]) -> int:
    py = s.home / "venvs" / "hunt" / "bin" / "python"  # stdlib-only scheduler, on a known Python (>= 3.12)
    proc = subprocess.Popen([str(py), "-m", "scheduler", "run"], cwd=s.repo / "runner", env=env)
    stopped = threading.Event()

    def watchdog() -> None:
        while not stopped.wait(15):
            if time.time() >= s.hard_stop:
                log("session time is up: stopping the scheduler (stars cut off are retried next run)")
                proc.send_signal(signal.SIGTERM)
                if stopped.wait(120):
                    return
                proc.kill()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        return proc.wait()
    except KeyboardInterrupt:  # "Stop" in the notebook editor
        proc.send_signal(signal.SIGTERM)
        return proc.wait()
    finally:
        stopped.set()


def last_run_summary(s: Settings) -> dict | None:
    hb = s.data / "state" / "heartbeat.json"
    try:
        return json.loads(hb.read_text())
    except (OSError, ValueError):
        return None


def main(env: dict[str, str] | None = None) -> int:
    s = Settings(dict(os.environ if env is None else env))
    log(f"session started {datetime.fromtimestamp(s.t0, UTC):%Y-%m-%d %H:%M} UTC; hard stop "
        f"{datetime.fromtimestamp(s.hard_stop, UTC):%H:%M} UTC ({s.session_h} h); {cpu_count()} cores, "
        f"{(memory_gb() or 0):.1f} GB; repo {repo_commit(s.repo)}")
    restored = restore(s)
    guard(s, restored)
    run_id = None
    code = 1
    extra: dict = {"repo_commit": repo_commit(s.repo), "restored_from": restored.get("from"),
                   "restored_done_total": done_total(restored["counts"])}
    try:
        env = install(s)
        sched_env, search_until = scheduler_env(s, env, time.time())
        hours = float(sched_env["PH_SEARCH_HOURS"])
        log(f"workers {sched_env['PH_WORKERS']}; disk cap {sched_env['PH_DISK_CAP_GB']} GB; search until "
            f"{datetime.fromtimestamp(search_until, UTC):%H:%M} UTC ({hours:.2f} h), then {GRACE_H} h grace "
            f"and {s.wrap_h} h wrap-up")
        if search_until - time.time() < 600:
            log("less than 10 minutes left for the search after the install; not starting")
        else:
            code = run_scheduler(s, sched_env)
        hb = last_run_summary(s) or {}
        run_id = hb.get("run_id")
        extra.update({"scheduler_exit": code, "state": hb.get("state"), "last_run": hb.get("last_run")})
    except Exception as exc:  # the state is still saved below, so the next run starts from it
        log(f"failed: {type(exc).__name__}: {exc}")
        extra["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        save(s, run_id, extra)
    log(f"done: scheduler exit {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
