"""Bring the read-only clone to the tip of PH_REPO_REF and refresh the venvs whose locks changed.

Runs before every run (systemd ExecStartPre) when PH_AUTO_UPDATE=1, and by hand through `planet-hunter update`.
The clone is fetched anonymously over HTTPS and never pushed from; `git reset --hard` makes it exactly the
remote ref, whatever happened to it locally. A failed fetch keeps the current checkout (the night still runs).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scheduler.config import Config


def _git(cfg: Config, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cfg.repo), *args], capture_output=True, text=True, timeout=timeout)


def update(cfg: Config, log=print, force_sync: bool = False) -> int:
    before = _git(cfg, "rev-parse", "HEAD").stdout.strip()
    fetch = _git(cfg, "fetch", "--depth=1", "--prune", "origin", f"+refs/heads/{cfg.repo_ref}:refs/remotes/origin/{cfg.repo_ref}")
    if fetch.returncode != 0:
        log(f"update: fetch of {cfg.repo_ref} failed; keeping {before[:12]}. {fetch.stderr.strip()[-400:]}")
        return 0
    reset = _git(cfg, "reset", "--hard", f"origin/{cfg.repo_ref}")
    if reset.returncode != 0:
        log(f"update: reset failed: {reset.stderr.strip()[-400:]}")
        return 1
    _git(cfg, "clean", "-fdq")
    after = _git(cfg, "rev-parse", "HEAD").stdout.strip()
    log(f"update: {cfg.repo_ref} {before[:12]} -> {after[:12]}" if before != after else
        f"update: {cfg.repo_ref} unchanged at {after[:12]}")
    script = Path(cfg.repo) / "runner" / "sync-venvs.sh"
    p = subprocess.run(["bash", str(script), *(["--force"] if force_sync else [])], text=True, capture_output=True,
                       timeout=3600)
    for line in (p.stdout or "").splitlines():
        log(line)
    if p.returncode != 0:
        log(f"update: sync-venvs failed ({p.returncode}): {(p.stderr or '')[-1500:]}")
        return p.returncode
    return 0
