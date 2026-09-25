"""Record real HTTP answers once, replay them offline in tests.

Every adapter (and skysources, which the Rubin adapter calls) goes through
skysources.http.CachedClient.request_text, so patching that one method covers all network access.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from skysources import http

FIXTURES = Path(__file__).parent / "fixtures"
HTTP_DIR = FIXTURES / "http"


@contextmanager
def recording(name: str, meta: dict | None = None, replay_from: tuple[str, ...] = ()):
    """Run live, saving every response under fixtures/http/<name>.json. Requests already recorded
    in the `replay_from` fixtures are answered from them and not saved again, so a new fixture
    can hold only what a new step adds on top of an old recording."""
    store: dict[str, dict] = {}
    old: dict[str, str] = {}
    for n in replay_from:
        old.update({k: v["text"] for k, v in json.loads((HTTP_DIR / f"{n}.json").read_text())["responses"].items()})
    lock = threading.Lock()
    orig = http.CachedClient.request_text

    def req(self, method, url, *, params=None, json_body=None, data=None, ttl=3600.0):
        key = http._cache_key(method, url, params, json_body, data)
        if key in old:
            return old[key]
        text = orig(self, method, url, params=params, json_body=json_body, data=data, ttl=0)
        with lock:
            store[key] = {"method": method, "url": url, "params": params, "json": json_body, "data": data,
                          "text": text}
        return text

    http.CachedClient.request_text = req
    try:
        yield
    finally:
        http.CachedClient.request_text = orig
    HTTP_DIR.mkdir(parents=True, exist_ok=True)
    doc = {"recorded_at": datetime.now(UTC).isoformat(timespec="seconds"), "meta": meta or {}, "responses": store}
    (HTTP_DIR / f"{name}.json").write_text(json.dumps(doc, indent=0, ensure_ascii=False))


def meta(name: str) -> dict:
    return json.loads((HTTP_DIR / f"{name}.json").read_text())["meta"]


def install_replay(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Serve recorded answers; any unrecorded request fails the test (no network in tests)."""
    store: dict[str, str] = {}
    for n in names:
        doc = json.loads((HTTP_DIR / f"{n}.json").read_text())
        store.update({k: v["text"] for k, v in doc["responses"].items()})

    def req(self, method, url, *, params=None, json_body=None, data=None, ttl=3600.0):
        key = http._cache_key(method, url, params, json_body, data)
        if key not in store:
            raise AssertionError(f"no recorded response for {method} {url} {params or json_body}")
        return store[key]

    def download(self, url, name, *, json_body=None, ttl=86400.0):
        raise AssertionError(f"no recorded download for {url}")

    monkeypatch.setattr(http.CachedClient, "request_text", req)
    monkeypatch.setattr(http.CachedClient, "download", download)
