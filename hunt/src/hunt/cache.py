"""Disk cache for the hunt package: downloaded files and JSON answers, each with a time-to-live."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from hunter.cache import retry

DAY = 86400.0
TIMEOUT = 300


def cache_dir() -> Path:
    root = os.environ.get("HUNT_CACHE_DIR") or Path.home() / ".cache" / "planet-hunter" / "hunt"
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fresh(path: Path, ttl_s: float) -> bool:
    return path.exists() and path.stat().st_size > 0 and time.time() - path.stat().st_mtime < ttl_s


def cached_file(name: str, ttl_s: float, produce: Callable[[Path], None], refresh: bool = False) -> Path:
    """Path of cache file `name`; (re)made by produce(tmp_path) when missing, stale or refresh=True."""
    path = cache_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if refresh or not _fresh(path, ttl_s):
        tmp = path.with_name(path.name + ".part")
        produce(tmp)
        tmp.replace(path)
    return path


def download(url: str, name: str, ttl_s: float, refresh: bool = False, params: dict | None = None) -> Path:
    def produce(tmp: Path) -> None:
        def call() -> None:
            with requests.get(url, params=params, timeout=TIMEOUT, stream=True) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
        retry(call)
    return cached_file(name, ttl_s, produce, refresh)


def cached_json(name: str, ttl_s: float, compute: Callable[[], Any], refresh: bool = False) -> Any:
    path = cache_dir() / "json" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not refresh and _fresh(path, ttl_s):
        return json.loads(path.read_text())
    value = compute()
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(value))
    tmp.replace(path)
    return value
