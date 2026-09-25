"""HTTP for this package: cached, rate-limited GET/POST of text resources.

Every network call goes through `Net._fetch`; tests replace it with recorded real answers
(tests/recording.py), so nothing else touches the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

USER_AGENT = "planet-hunter-skyspectra/0.1 (+https://github.com/anastasiadisfoivos-hub/planet-hunter)"

# Seconds between requests to one host. All of these are free public services; be polite.
HOST_MIN_INTERVAL = {
    "physics.nist.gov": 1.0,
    "hypatiacatalog.com": 0.5,
    "gea.esac.esa.int": 1.0,
    "exoplanetarchive.ipac.caltech.edu": 0.5,
    "kurucz.harvard.edu": 1.0,
}
DEFAULT_MIN_INTERVAL = 0.5
DAY = 86400.0


class FetchError(RuntimeError):
    pass


def cache_dir() -> Path:
    return Path(os.environ.get("SKYSPECTRA_CACHE", Path.home() / ".cache" / "skyspectra"))


def key(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]


class Net:
    def __init__(self, timeout: float = 300.0) -> None:
        self._http = httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}

    def _wait(self, url: str) -> None:
        host = urlsplit(url).netloc
        interval = HOST_MIN_INTERVAL.get(host, DEFAULT_MIN_INTERVAL)
        with self._lock:
            now = time.monotonic()
            ready = self._last.get(host, 0.0) + interval
            delay = max(0.0, ready - now)
            self._last[host] = now + delay
        if delay:
            time.sleep(delay)

    # -- raw network (patched in tests) ---------------------------------------------------------

    def _fetch(self, method: str, url: str, params: dict | None, data: dict | None) -> tuple[int, str]:
        """One request with retries on network errors / 5xx / 429. Returns (status, text)."""
        last: Exception | None = None
        for attempt in range(4):
            self._wait(url)
            try:
                resp = self._http.request(method, url, params=params, data=data)
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(2.0 * (attempt + 1))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last = FetchError(f"HTTP {resp.status_code}")
                time.sleep(2.0 * (attempt + 1))
                continue
            return resp.status_code, resp.content.decode("utf-8", errors="replace")
        raise FetchError(f"{urlsplit(url).netloc}: {last}")

    # -- cached API -----------------------------------------------------------------------------

    def text(self, url: str, params: dict | None = None, *, data: dict | None = None,
             ttl: float = 30 * DAY, cache_key: str | None = None) -> str:
        """GET (or POST when `data` is given) a text resource, cached on disk for `ttl` seconds.

        `cache_key` replaces the default (url, params, data) key, for URLs that carry a
        per-session token. Raises FetchError on HTTP >= 400.
        """
        method = "POST" if data is not None else "GET"
        k = cache_key or key(method, url, params, data)
        path = cache_dir() / "http" / f"{k}.json"
        if ttl > 0 and path.exists():
            entry = json.loads(path.read_text())
            if time.time() - entry["at"] < ttl:
                return entry["text"]
        status, text = self._fetch(method, url, params, data)
        if status >= 400:
            raise FetchError(f"{urlsplit(url).netloc}: HTTP {status}")
        if ttl > 0:
            write_json(path, {"at": time.time(), "url": url, "params": params, "text": text})
        return text

    def cached(self, cache_key: str, ttl: float) -> str | None:
        """A fresh cached answer stored under `cache_key`, or None."""
        path = cache_dir() / "http" / f"{cache_key}.json"
        if path.exists():
            entry = json.loads(path.read_text())
            if time.time() - entry["at"] < ttl:
                return entry["text"]
        return None

    def json(self, url: str, params: dict | None = None, **kw):
        return json.loads(self.text(url, params, **kw))


def write_json(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(doc))
    tmp.replace(path)


_net: Net | None = None


def get_net() -> Net:
    global _net
    if _net is None:
        _net = Net()
    return _net
