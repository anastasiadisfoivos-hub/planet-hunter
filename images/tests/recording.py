"""Record real answers once, replay them offline in tests.

All network access in skypictures goes through Net.text (listings, JSON) and Net.probe
(image checks), so patching those two covers everything.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from skypictures import net

FIXTURES = Path(__file__).parent / "fixtures"
HTTP_DIR = FIXTURES / "http"


def _text_key(url: str, params) -> str:
    return net._key(url, params)


def _trim(url: str, text: str) -> str:
    """SDO day listings are ~1.5 MB of links; the code only reads the 1024-px ones."""
    if url.startswith("https://sdo.gsfc.nasa.gov/assets/img/browse"):
        return "\n".join(re.findall(r'href="\d{8}_\d{6}_1024_\d{4}\.jpg"', text))
    return text


@contextmanager
def recording(name: str):
    """Run live (bypassing the cache), saving every answer under fixtures/http/<name>.json."""
    texts: dict[str, dict] = {}
    probes: dict[str, dict] = {}
    orig_text, orig_probe = net.Net.text, net.Net.probe

    def text(self, url, params=None, ttl=3600.0):
        body = orig_text(self, url, params, ttl=0)
        texts[_text_key(url, params)] = {"url": url, "params": params, "text": _trim(url, body)}
        return body

    def probe(self, url):
        p = self._probe_uncached(url)
        probes[url] = asdict(p)
        return p

    net.Net.text, net.Net.probe = text, probe
    try:
        yield
    finally:
        net.Net.text, net.Net.probe = orig_text, orig_probe
        HTTP_DIR.mkdir(parents=True, exist_ok=True)
        path = HTTP_DIR / f"{name}.json"
        old = json.loads(path.read_text()) if path.exists() else {"texts": {}, "probes": {}}
        doc = {"recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
               "texts": {**old["texts"], **texts}, "probes": {**old["probes"], **probes}}
        path.write_text(json.dumps(doc, indent=1, sort_keys=True))


def install_replay(monkeypatch, *names: str) -> None:
    """Serve recorded answers; any unrecorded request fails the test."""
    texts: dict[str, str] = {}
    probes: dict[str, dict] = {}
    for n in names:
        doc = json.loads((HTTP_DIR / f"{n}.json").read_text())
        texts.update({k: v["text"] for k, v in doc["texts"].items()})
        probes.update(doc["probes"])

    def text(self, url, params=None, ttl=3600.0):
        key = _text_key(url, params)
        if key not in texts:
            raise AssertionError(f"no recorded response for GET {url} {params}")
        return texts[key]

    def probe(self, url):
        if url not in probes:
            raise AssertionError(f"no recorded probe for {url}")
        return net.Probe(**probes[url])

    monkeypatch.setattr(net.Net, "text", text)
    monkeypatch.setattr(net.Net, "probe", probe)
