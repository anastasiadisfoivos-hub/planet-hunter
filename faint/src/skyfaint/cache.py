"""Disk cache: downloaded files and JSON answers, each with a time-to-live.

Root: ~/.cache/planet-hunter/faint (override with FAINT_CACHE_DIR).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")
DAY = 86400.0
FOREVER = 3650 * DAY


def cache_dir() -> Path:
    root = os.environ.get("FAINT_CACHE_DIR") or Path.home() / ".cache" / "planet-hunter" / "faint"
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def retry(fn: Callable[[], T], tries: int = 4, backoff_s: float = 3.0) -> T:
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(backoff_s * (2**i))
    raise AssertionError("unreachable")


def fresh(path: Path, ttl_s: float) -> bool:
    return path.exists() and path.stat().st_size > 0 and time.time() - path.stat().st_mtime < ttl_s


def cached_json(name: str, ttl_s: float, compute: Callable[[], Any], refresh: bool = False) -> Any:
    path = cache_dir() / "json" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not refresh and fresh(path, ttl_s):
        return json.loads(path.read_text())
    value = compute()
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(value))
    tmp.replace(path)
    return value
