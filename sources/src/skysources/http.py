"""Small shared HTTP layer: on-disk cache, per-host rate limit, polite retries.

Every client in this package goes through `get_client()`. Nothing here knows about astronomy.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

USER_AGENT = "planet-hunter-skysources/0.1 (+https://github.com/anastasiadisfoivos-hub/planet-hunter)"

# Minimum seconds between requests to one host. Conservative defaults; brokers publish few hard numbers.
DEFAULT_MIN_INTERVAL = 1.0
HOST_MIN_INTERVAL: dict[str, float] = {}


# dict, or a list of (key, value) pairs when a key repeats (ALeRCE ranges: lastmjd=a&lastmjd=b).
Params = dict[str, Any] | list[tuple[str, Any]] | None


class UpstreamError(RuntimeError):
    """An upstream service failed, refused us, or needs a login we don't have."""


def cache_dir() -> Path:
    return Path(os.environ.get("SKYSOURCES_CACHE", Path.home() / ".cache" / "skysources"))


def cache_disabled() -> bool:
    return os.environ.get("SKYSOURCES_NO_CACHE", "") not in ("", "0")


@dataclass
class RateLimiter:
    min_interval: dict[str, float] = field(default_factory=lambda: HOST_MIN_INTERVAL)
    _last: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def wait(self, host: str) -> None:
        interval = self.min_interval.get(host, DEFAULT_MIN_INTERVAL)
        with self._lock:
            now = time.monotonic()
            ready = self._last.get(host, 0.0) + interval
            delay = max(0.0, ready - now)
            self._last[host] = now + delay
        if delay:
            time.sleep(delay)


class CachedClient:
    """httpx wrapper returning decoded bodies, cached on disk by (method, url, params, body)."""

    def __init__(self, timeout: float = 180.0, retries: int = 3) -> None:
        self._http = httpx.Client(
            timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        self._limiter = RateLimiter()
        self._retries = retries

    def request_text(
        self,
        method: str,
        url: str,
        *,
        params: Params = None,
        json_body: Any = None,
        data: dict[str, Any] | None = None,
        ttl: float = 3600.0,
    ) -> str:
        key = _cache_key(method, url, params, json_body, data)
        path = cache_dir() / f"{key}.json"
        if not cache_disabled() and ttl > 0 and path.exists():
            entry = json.loads(path.read_text())
            if time.time() - entry["at"] < ttl:
                return entry["text"]

        host = urlsplit(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            self._limiter.wait(host)
            try:
                resp = self._http.request(method, url, params=params, json=json_body, data=data)
            except httpx.HTTPError as exc:  # network trouble: retry
                last_exc = exc
                time.sleep(2**attempt)
                continue
            if resp.status_code in (401, 403):
                raise UpstreamError(f"{host} refused access (HTTP {resp.status_code}): needs login?")
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = UpstreamError(f"{host} HTTP {resp.status_code}: {resp.text[:200]}")
                retry_after = resp.headers.get("Retry-After", "")
                time.sleep(float(retry_after) if retry_after.isdigit() else 2**attempt)
                continue
            if resp.status_code >= 400:
                raise UpstreamError(f"{host} HTTP {resp.status_code}: {resp.text[:300]}")
            text = resp.text
            if not cache_disabled() and ttl > 0:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps({"at": time.time(), "url": str(resp.url), "text": text}))
                tmp.replace(path)
            return text
        raise UpstreamError(f"{host} unavailable after {self._retries + 1} tries: {last_exc}")

    def get_json(self, url: str, *, params: Params = None, ttl: float = 3600.0) -> Any:
        return json.loads(self.request_text("GET", url, params=params, ttl=ttl))

    def post_json(self, url: str, *, json_body: Any = None, ttl: float = 3600.0) -> Any:
        return json.loads(self.request_text("POST", url, json_body=json_body, ttl=ttl))


    def download(self, url: str, name: str, *, json_body: Any = None, ttl: float = 86400.0) -> Path:
        """POST/GET a binary file into the cache dir (e.g. a Parquet bulk file) and return its path."""
        path = cache_dir() / "files" / name
        if path.exists() and time.time() - path.stat().st_mtime < ttl:
            return path
        host = urlsplit(url).netloc
        self._limiter.wait(host)
        method = "POST" if json_body is not None else "GET"
        try:
            with self._http.stream(method, url, json=json_body, timeout=600) as resp:
                if resp.status_code >= 400:
                    raise UpstreamError(f"{host} HTTP {resp.status_code} downloading {name}")
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(path.suffix + ".tmp")
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_bytes():
                        fh.write(chunk)
        except httpx.HTTPError as exc:
            if path.exists():  # stale copy beats nothing
                return path
            raise UpstreamError(f"{host} download failed: {exc}") from exc
        tmp.replace(path)
        return path


def _cache_key(method: str, url: str, params: Any, json_body: Any, data: Any) -> str:
    blob = json.dumps([method.upper(), url, params, json_body, data], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


_client: CachedClient | None = None


def get_client() -> CachedClient:
    global _client
    if _client is None:
        _client = CachedClient()
    return _client
