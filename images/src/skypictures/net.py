"""HTTP for this package: cached text fetches (listings, JSON) and cached image probes.

A probe GETs the image (several hosts answer HEAD with 405), decodes it with Pillow, and
records whether it is a real picture: HTTP 200, an image content type, decodable, and not a
single flat colour (hips2fits returns an all-white frame outside a survey's footprint).

Tests replace `Net._fetch` and `Net._probe_uncached`; nothing else touches the network.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image as PILImage
from PIL import ImageStat

USER_AGENT = "planet-hunter-skypictures/0.1 (+https://github.com/anastasiadisfoivos-hub/planet-hunter)"
MAX_IMAGE_BYTES = 8_000_000
PROBE_OK_TTL = 7 * 86400.0
PROBE_FAIL_TTL = 3600.0
BLANK_STDDEV = 1.5  # grey levels; a real sky/Sun frame is far noisier than this

# Seconds between requests to one host.
HOST_MIN_INTERVAL = {
    "api.lsst.fink-portal.org": 0.5,
    "api.ztf.fink-portal.org": 0.5,
    "alasky.cds.unistra.fr": 0.3,
    "api.helioviewer.org": 0.5,
}
DEFAULT_MIN_INTERVAL = 0.2


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Probe:
    ok: bool
    status: int
    content_type: str = ""
    width: int | None = None
    height: int | None = None
    reason: str = ""  # why not ok

    def to_json(self) -> dict:
        return asdict(self)


def cache_dir() -> Path:
    return Path(os.environ.get("SKYPICTURES_CACHE", Path.home() / ".cache" / "skypictures"))


def _key(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]


def inspect_image(status: int, content_type: str, body: bytes) -> Probe:
    """Judge a downloaded response: is it a real, non-blank picture?"""
    ctype = content_type.split(";")[0].strip().lower()
    if status != 200:
        return Probe(False, status, ctype, reason=f"HTTP {status}")
    if not ctype.startswith("image/"):
        return Probe(False, status, ctype, reason=f"not an image ({ctype or 'no content type'})")
    try:
        img = PILImage.open(io.BytesIO(body))
        img.load()
    except Exception as exc:  # noqa: BLE001 -- truncated or not really an image
        return Probe(False, status, ctype, reason=f"undecodable: {exc}")
    w, h = img.size
    stddev = max(ImageStat.Stat(img.convert("L")).stddev)
    if stddev < BLANK_STDDEV:
        return Probe(False, status, ctype, w, h, reason="blank (one flat colour)")
    return Probe(True, status, ctype, w, h)


class Net:
    def __init__(self, timeout: float = 90.0) -> None:
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

    def _fetch(self, url: str, params: dict | None) -> tuple[int, str, bytes]:
        """One GET with two retries on network errors / 5xx / 429. Returns (status, type, body)."""
        last: Exception | None = None
        for attempt in range(3):
            self._wait(url)
            try:
                resp = self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last = FetchError(f"HTTP {resp.status_code}")
                time.sleep(1.5 * (attempt + 1))
                continue
            return resp.status_code, resp.headers.get("content-type", ""), resp.content[:MAX_IMAGE_BYTES]
        raise FetchError(f"{urlsplit(url).netloc}: {last}")

    def _probe_uncached(self, url: str) -> Probe:
        try:
            status, ctype, body = self._fetch(url, None)
        except FetchError as exc:
            return Probe(False, 0, reason=str(exc))
        return inspect_image(status, ctype, body)

    # -- cached API -----------------------------------------------------------------------------

    def text(self, url: str, params: dict | None = None, ttl: float = 3600.0) -> str:
        """GET a text/JSON/HTML resource, cached on disk. Raises FetchError on HTTP >= 400."""
        path = cache_dir() / "text" / f"{_key(url, params)}.json"
        if ttl > 0 and path.exists():
            entry = json.loads(path.read_text())
            if time.time() - entry["at"] < ttl:
                return entry["text"]
        status, _ctype, body = self._fetch(url, params)
        if status >= 400:
            raise FetchError(f"{urlsplit(url).netloc}: HTTP {status}")
        text = body.decode("utf-8", errors="replace")
        if ttl > 0:
            _write_json(path, {"at": time.time(), "url": url, "params": params, "text": text})
        return text

    def json(self, url: str, params: dict | None = None, ttl: float = 3600.0):
        return json.loads(self.text(url, params, ttl))

    def probe(self, url: str) -> Probe:
        """Is this URL a working, non-blank image? Cached: good answers 7 days, bad ones 1 hour."""
        path = cache_dir() / "probes" / f"{_key(url)}.json"
        if path.exists():
            entry = json.loads(path.read_text())
            ttl = PROBE_OK_TTL if entry["probe"]["ok"] else PROBE_FAIL_TTL
            if time.time() - entry["at"] < ttl:
                return Probe(**entry["probe"])
        probe = self._probe_uncached(url)
        _write_json(path, {"at": time.time(), "url": url, "probe": probe.to_json()})
        return probe


def _write_json(path: Path, doc: dict) -> None:
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
