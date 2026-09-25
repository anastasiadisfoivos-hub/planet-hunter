"""Which chemical-fingerprint files exist per star: the SPECTRA data set's index.json.

PH_SPECTRA_INDEX is a path or an http(s) URL (e.g. the web app's /data/spectra/index.json). It is
read at most every PH_SPECTRA_INDEX_TTL_S; when it's unset, missing or unreadable the lab says
no spectra exist (index_available: false) and the last good copy, if any, keeps being used.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from api.models import LabSpectra

log = logging.getLogger(__name__)

TIMEOUT_S = 5.0


class SpectraIndex:
    def __init__(self, source: str | None, ttl_s: float = 3600.0) -> None:
        self.source = source
        self.ttl_s = ttl_s
        self._lock = threading.Lock()
        self._doc: dict[str, Any] | None = None
        self._read_at: float | None = None

    def _read(self) -> dict[str, Any]:
        assert self.source is not None
        if self.source.startswith(("http://", "https://")):
            req = urllib.request.Request(self.source, headers={"User-Agent": "planet-hunter-api"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310 - our own URL
                doc = json.load(r)
        else:
            doc = json.loads(Path(self.source).read_text())
        if not isinstance(doc, dict):
            raise ValueError("index.json is not an object")
        return doc

    def doc(self) -> dict[str, Any] | None:
        if not self.source:
            return None
        with self._lock:
            now = time.monotonic()
            if self._read_at is None or now - self._read_at >= self.ttl_s:
                self._read_at = now  # a failed read also waits a TTL before the next try
                try:
                    self._doc = self._read()
                except Exception as exc:  # noqa: BLE001 - tolerate it missing
                    log.warning("spectra index %s unreadable: %s", self.source, exc)
            return self._doc

    def for_star(self, tic_id: int) -> LabSpectra:
        doc = self.doc()
        if doc is None:
            return LabSpectra(index_available=False)
        star = (doc.get("stars") or {}).get(str(tic_id)) or {}
        planets = doc.get("planets") or {}
        slugs = sorted(
            slug
            for slug, p in planets.items()
            if isinstance(p, dict) and _as_int(p.get("tic")) == tic_id
        )
        return LabSpectra(
            gaia_xp="gaia_xp" in star,
            abundances="abundances" in star,
            planet_atmospheres=slugs,
            index_available=True,
        )

    def star_name(self, tic_id: int) -> str | None:
        doc = self.doc() or {}
        return ((doc.get("stars") or {}).get(str(tic_id)) or {}).get("name")


def _as_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
