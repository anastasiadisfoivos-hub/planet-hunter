"""Record real HTTP answers once, replay them offline in tests.

Every client goes through CachedClient.request_text / .download and SkyBoT through
solar_system.fetch_skybot_votable, so patching those three covers all network access.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skysources import http, solar_system

FIXTURES = Path(__file__).parent / "fixtures"
HTTP_DIR = FIXTURES / "http"
SKYBOT_DIR = FIXTURES / "skybot"
SSO_BULK = FIXTURES / "fink_ssobulk_subset.parquet"


def _skybot_key(sphere, epoch) -> str:
    return f"{sphere['ra_deg']:.4f}_{sphere['dec_deg']:.4f}_{sphere['radius_deg']:.4f}_{epoch.jd:.5f}"


@contextmanager
def recording(name: str):
    """Run live, saving every response under fixtures/http/<name>.json."""
    store: dict[str, dict] = {}
    orig_req = http.CachedClient.request_text
    orig_sky = solar_system.fetch_skybot_votable

    def req(self, method, url, *, params=None, json_body=None, data=None, ttl=3600.0):
        text = orig_req(self, method, url, params=params, json_body=json_body, data=data, ttl=0)
        key = http._cache_key(method, url, params, json_body, data)
        store[key] = {"method": method, "url": url, "params": params, "json": json_body, "text": text}
        return text

    def sky(sphere, epoch):
        raw = orig_sky(sphere, epoch)
        SKYBOT_DIR.mkdir(parents=True, exist_ok=True)
        (SKYBOT_DIR / f"{_skybot_key(sphere, epoch)}.xml").write_bytes(raw)
        return raw

    http.CachedClient.request_text = req
    solar_system.fetch_skybot_votable = sky
    try:
        yield
    finally:
        http.CachedClient.request_text = orig_req
        solar_system.fetch_skybot_votable = orig_sky
    HTTP_DIR.mkdir(parents=True, exist_ok=True)
    doc = {"recorded_at": datetime.now(UTC).isoformat(timespec="seconds"), "responses": store}
    (HTTP_DIR / f"{name}.json").write_text(json.dumps(doc, indent=1))


def install_replay(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Serve recorded answers; any unrecorded request fails the test (no network in tests)."""
    store: dict[str, str] = {}
    for n in names:
        store.update({k: v["text"] for k, v in json.loads((HTTP_DIR / f"{n}.json").read_text())["responses"].items()})

    def req(self, method, url, *, params=None, json_body=None, data=None, ttl=3600.0):
        key = http._cache_key(method, url, params, json_body, data)
        if key not in store:
            raise AssertionError(f"no recorded response for {method} {url} {params or json_body}")
        return store[key]

    def download(self, url, name, *, json_body=None, ttl=86400.0):
        if name == "fink_ssobulk.parquet":
            return SSO_BULK
        raise AssertionError(f"no recorded download for {url}")

    def sky(sphere, epoch):
        path = SKYBOT_DIR / f"{_skybot_key(sphere, epoch)}.xml"
        if not path.exists():
            raise AssertionError(f"no recorded SkyBoT answer {path.name}")
        return path.read_bytes()

    monkeypatch.setattr(http.CachedClient, "request_text", req)
    monkeypatch.setattr(http.CachedClient, "download", download)
    monkeypatch.setattr(solar_system, "fetch_skybot_votable", sky)
