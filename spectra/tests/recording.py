"""Record real answers once, replay them offline in tests.

All network access in skyspectra goes through Net._fetch, so patching it covers everything.
Recordings are real responses; a few big ones are trimmed to what the tests use (see `trim`).
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from skyspectra import net

FIXTURES = Path(__file__).parent / "fixtures"
HTTP_DIR = FIXTURES / "http"

# Kurucz atlas windows kept in the recording (the whole file is 24 MB).
ATLAS_WINDOWS = [(392.0, 398.0), (585.0, 592.0), (655.0, 658.0)]


def _trim_atlas(text: str) -> str:
    out = []
    for line in text.splitlines():
        parts = line.split()
        try:
            w = float(parts[0]) if len(parts) == 2 else None
        except ValueError:
            w = None
        if w is None or any(a <= w <= b for a, b in ATLAS_WINDOWS):
            out.append(line)
    return "\n".join(out)


def _trim_csv(text: str, column: str, keep: set[str]) -> str:
    rows = list(csv.reader(io.StringIO(text)))
    i = rows[0].index(column)
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_NONNUMERIC).writerows([rows[0]] + [r for r in rows[1:] if r[i] in keep])
    return buf.getvalue()


def trim(url: str, params, text: str, keep: dict) -> str:
    if url.endswith("solarfluxintwl.asc"):
        return _trim_atlas(text)
    if url.endswith("/TAP/sync") and params and "pscomppars" in params.get("query", ""):
        return _trim_csv(text, "hostname", keep["hostnames"])
    if url.endswith("/TAP/sync") and params and "from spectra" in params.get("query", ""):
        return _trim_csv(text, "pl_name", keep["planets"])
    if "nph-firefly" in url:  # the viewer page: only the workspace path matters
        return re.search(r"FF_InitPage \([^)]*\)", text).group()
    return text


@contextmanager
def recording(name: str, keep: dict):
    """Run live, bypassing the cache, saving every answer under fixtures/http/<name>.json.gz."""
    answers: dict[str, dict] = {}
    orig = net.Net._fetch

    def fetch(self, method, url, params, data):
        status, text = orig(self, method, url, params, data)
        answers[net.key(method, url, params, data)] = {
            "method": method, "url": url, "params": params, "data": data, "status": status,
            "text": trim(url, params, text, keep)}
        return status, text

    net.Net._fetch = fetch
    old_cache = os.environ.get("SKYSPECTRA_CACHE")
    tmp = tempfile.TemporaryDirectory()
    os.environ["SKYSPECTRA_CACHE"] = tmp.name  # an empty cache: every answer really comes from the network
    try:
        yield
    finally:
        net.Net._fetch = orig
        if old_cache is None:
            os.environ.pop("SKYSPECTRA_CACHE")
        else:
            os.environ["SKYSPECTRA_CACHE"] = old_cache
        tmp.cleanup()
        HTTP_DIR.mkdir(parents=True, exist_ok=True)
        doc = {"recorded_at": datetime.now(UTC).isoformat(timespec="seconds"), "answers": answers}
        with gzip.open(HTTP_DIR / f"{name}.json.gz", "wt") as f:
            json.dump(doc, f, sort_keys=True)


def load(name: str) -> dict:
    with gzip.open(HTTP_DIR / f"{name}.json.gz", "rt") as f:
        return json.load(f)


def install_replay(monkeypatch, *names: str) -> None:
    answers = {}
    for name in names:
        answers.update(load(name)["answers"])

    def fetch(self, method, url, params, data):
        k = net.key(method, url, params, data)
        if k not in answers:
            raise AssertionError(f"no recorded answer for {method} {url} {params} {data}")
        a = answers[k]
        return a["status"], a["text"]

    monkeypatch.setattr(net.Net, "_fetch", fetch)
