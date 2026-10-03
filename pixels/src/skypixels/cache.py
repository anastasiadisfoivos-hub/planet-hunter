"""Small disk cache: JSON answers with a TTL, plus a directory for downloaded FITS files."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

DAY = 86400.0


def cache_dir() -> Path:
    root = os.environ.get("SKYPIXELS_CACHE_DIR") or Path.home() / ".cache" / "planet-hunter" / "pixels"
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def fits_dir() -> Path:
    path = cache_dir() / "fits"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _json_path(namespace: str, key: str) -> Path:
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    folder = cache_dir() / "json" / namespace
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{digest}.json"


def cached_json(namespace: str, key: str, ttl_s: float, compute: Callable[[], Any], refresh: bool = False) -> Any:
    """Return the cached JSON value for (namespace, key) if younger than ttl_s, else compute and store it."""
    path = _json_path(namespace, key)
    if not refresh and path.exists() and time.time() - path.stat().st_mtime < ttl_s:
        return json.loads(path.read_text())["value"]
    value = compute()
    path.write_text(json.dumps({"key": key, "value": value}))
    return value


def retry(fn: Callable[[], T], tries: int = 3, backoff_s: float = 2.0) -> T:
    """Call fn, retrying on any exception with exponential backoff (MAST and the Gaia archive are flaky)."""
    for attempt in range(tries):
        try:
            return fn()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(backoff_s * 2**attempt)
    raise AssertionError("unreachable")
