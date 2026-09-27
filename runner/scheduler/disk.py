"""Disk cap. Everything the runner writes lives under PH_DATA (ledger, runs, targets, every package's cache).

- Measure: bytes actually allocated under PH_DATA.
- Prune when over PRUNE_AT (85 % of PH_DISK_CAP_GB, default 150 GB) down to PRUNE_TO (70 %): first run folders
  older than KEEP_RUNS nights (their candidates and monitor records are in the database by then), then the bulky
  re-downloadable caches, least recently used file first:
    cache/pipeline/fits   MAST light-curve FITS (SPOC / TESS-SPOC / QLP)
    cache/faint           TGLC light curves
    cache/vet-work        TESScut cutouts (~100 MB each)
    cache/pixels          pixels/'s cutouts
    cache/xdg, cache/lightkurve   astropy / astroquery / lightkurve downloads
  Small JSON caches (catalogues, TIC rows, file indexes) and the ledger are never pruned.
- Pause: if still over the cap, or the filesystem has less than MIN_FREE_GB free, no new star starts until
  pruning makes room (running stars finish).
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

PRUNE_AT = 0.85
PRUNE_TO = 0.70
MIN_FREE_GB = 5.0
KEEP_RUNS = 14
GB = 1024 ** 3
PRUNABLE = ("pipeline/fits", "faint", "vet-work", "pixels", "xdg", "lightkurve")
KEEP_SUFFIXES = (".sqlite", ".sqlite-wal", ".sqlite-shm")


def usage_bytes(root: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            try:
                st = os.lstat(os.path.join(dirpath, f))
            except OSError:
                continue
            total += getattr(st, "st_blocks", 0) * 512 or st.st_size
    return total


def _files(root: Path) -> list[tuple[float, int, str]]:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(KEEP_SUFFIXES):
                continue
            p = os.path.join(dirpath, f)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            out.append((max(st.st_atime, st.st_mtime), getattr(st, "st_blocks", 0) * 512 or st.st_size, p))
    return out


def old_runs(runs_dir: Path, keep: int, current: str | None) -> list[Path]:
    if not runs_dir.is_dir():
        return []
    runs = sorted(p for p in runs_dir.iterdir() if p.is_dir() and p.name != current)
    return runs[:-keep] if keep and len(runs) > keep else ([] if keep else runs)


def janitor(data: Path, cache: Path, runs_dir: Path, cap_gb: float, current_run: str | None = None,
            log=print) -> dict:
    """Prune if needed. Returns {used_gb, cap_gb, free_gb, pruned_gb, pruned_files, paused}."""
    cap = cap_gb * GB
    used = usage_bytes(data)
    pruned = files = 0
    if used > PRUNE_AT * cap:
        target = PRUNE_TO * cap
        for run in old_runs(runs_dir, KEEP_RUNS, current_run):
            if used - pruned <= target:
                break
            size = usage_bytes(run)
            shutil.rmtree(run, ignore_errors=True)
            pruned += size
            files += 1
            log(f"janitor: removed old run folder {run.name} ({size / GB:.2f} GB)")
        if used - pruned > target:
            cands = []
            for sub in PRUNABLE:
                d = cache / sub
                if d.is_dir():
                    cands += _files(d)
            cands.sort()  # least recently used first
            for _t, size, path in cands:
                if used - pruned <= target:
                    break
                try:
                    os.unlink(path)
                except OSError:
                    continue
                pruned += size
                files += 1
        log(f"janitor: {used / GB:.1f} GB used of a {cap_gb:.0f} GB cap; pruned {pruned / GB:.2f} GB "
            f"({files} files)")
    used_after = used - pruned
    try:
        free = shutil.disk_usage(data).free
    except OSError:
        free = 0
    paused = used_after > cap or free < MIN_FREE_GB * GB
    return {"used_gb": round(used_after / GB, 2), "cap_gb": cap_gb, "free_gb": round(free / GB, 1),
            "pruned_gb": round(pruned / GB, 2), "pruned_files": files, "paused": paused, "at": time.time()}
