"""One on-disk cache for every network call.

Root: $SKYVET_CACHE_DIR, else ~/.cache/planet-hunter/vet. Entries never expire: everything cached here is a
published, versioned product (TIC 8.2, Gaia DR3, VSX, TESS light curves and FFI cutouts, TESS PRF models).
Delete the directory to refresh.

$SKYVET_OFFLINE=1 turns a cache miss into an OfflineMiss error instead of a download. The offline tests run
that way against tests/data/cache.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import pickle
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

FORMATS = {"json": ".json", "pickle": ".pkl.gz"}


class OfflineMiss(RuntimeError):
    """A network call was needed while $SKYVET_OFFLINE=1."""


def root() -> Path:
    return Path(os.environ.get("SKYVET_CACHE_DIR") or Path.home() / ".cache" / "planet-hunter" / "vet")


def work_root() -> Path:
    """Scratch space for large raw downloads that are not cache entries themselves (TESScut FFI cutouts,
    ~100 MB each, kept only to avoid downloading them twice): $SKYVET_WORK_DIR, else
    ~/.cache/planet-hunter/vet-work. Never inside the fixtures."""
    return Path(os.environ.get("SKYVET_WORK_DIR") or Path.home() / ".cache" / "planet-hunter" / "vet-work")


def offline() -> bool:
    return os.environ.get("SKYVET_OFFLINE", "") not in ("", "0")


def path_for(ns: str, key: str, fmt: str = "json") -> Path:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", key)[:80]
    digest = hashlib.sha1(key.encode()).hexdigest()[:10]
    return root() / ns / f"{slug}-{digest}{FORMATS[fmt]}"


def cached(ns: str, key: str, fetch: Callable[[], Any], fmt: str = "json", tries: int = 4) -> Any:
    """Return the cached value for (ns, key), calling fetch() and storing its result on a miss.

    Network errors (OSError, which includes requests' and urllib's) are retried: `tries` attempts, backoff 5, 15,
    45 s. Anything else, including LookupError ("not there"), is raised at once.
    """
    path = path_for(ns, key, fmt)
    if path.exists():
        if fmt == "json":
            return json.loads(path.read_text())
        with gzip.open(path, "rb") as f:
            return pickle.load(f)
    if offline():
        raise OfflineMiss(f"{ns} '{key}' is not cached ({path}) and SKYVET_OFFLINE is set")
    value = _retry(fetch, tries)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if fmt == "json":
        tmp.write_text(json.dumps(value, default=_jsonable))
    else:
        with gzip.open(tmp, "wb") as f:
            pickle.dump(value, f, pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)
    return value


def _retry(fetch: Callable[[], Any], tries: int) -> Any:
    for attempt in range(tries):
        try:
            return fetch()
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(5 * 3**attempt)
    raise AssertionError("unreachable")


def _jsonable(x):
    try:
        import numpy as np

        if isinstance(x, np.generic):
            return x.item()
        if isinstance(x, np.ndarray):
            return x.tolist()
    except ImportError:
        pass
    raise TypeError(f"not JSON serialisable: {type(x)}")
