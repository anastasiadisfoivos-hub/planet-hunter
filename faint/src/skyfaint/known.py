"""Stars already on a known list, as TIC-id sets: TOIs (any disposition), community TOIs, confirmed-planet hosts
(any kind) and the TESS eclipsing-binary catalogue (Prsa et al. 2022). The same sources hunt/ uses, downloaded in
bulk and cached a day (the EB catalogue a month)."""

from __future__ import annotations

import csv
import io

import requests

from .cache import DAY, cached_json, retry

ARCHIVE_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
CTOI_URL = "https://exofop.ipac.caltech.edu/tess/download_ctoi.php?sort=ctoi&output=pipe"
VIZIER_ASU = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
LISTS = {"toi": "TOI", "ctoi": "CTOI", "confirmed": "confirmed-planet host", "eb": "TESS EB catalogue"}


def _get(url: str, params: dict | None = None) -> str:
    def call() -> str:
        r = requests.get(url, params=params, timeout=600)
        r.raise_for_status()
        return r.text
    return retry(call)


def _tois() -> list[int]:
    rows = csv.DictReader(io.StringIO(_get(ARCHIVE_TAP, {"query": "select tid from toi", "format": "csv"})))
    return sorted({int(r["tid"]) for r in rows if r["tid"].strip().isdigit()})


def _confirmed() -> list[int]:
    q = "select tic_id from pscomppars where tic_id is not null"
    rows = csv.DictReader(io.StringIO(_get(ARCHIVE_TAP, {"query": q, "format": "csv"})))
    out = set()
    for r in rows:
        t = r["tic_id"].replace("TIC", "").strip()
        if t.isdigit():
            out.add(int(t))
    return sorted(out)


def _ctois() -> list[int]:
    rows = csv.DictReader(io.StringIO(_get(CTOI_URL)), delimiter="|")
    return sorted({int(r["TIC ID"]) for r in rows if r["TIC ID"].strip().isdigit()})


def _ebs() -> list[int]:
    text = _get(VIZIER_ASU, {"-source": "J/ApJS/258/16/tess-ebs", "-out.max": "unlimited", "-out": "TIC"})
    out = set()
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.isdigit():
            out.add(int(ln))
    return sorted(out)


def load(refresh: bool = False) -> dict[str, set[int]]:
    """{list: set of TIC ids}. A list that cannot be fetched raises: a target list must not silently include
    known stars."""
    fns = {"toi": (_tois, DAY), "ctoi": (_ctois, DAY), "confirmed": (_confirmed, DAY), "eb": (_ebs, 30 * DAY)}
    return {k: set(cached_json(f"known/{k}", ttl, fn, refresh)) for k, (fn, ttl) in fns.items()}


def on_lists(tic: int, lists: dict[str, set[int]]) -> list[str]:
    return [LISTS[k] for k, s in lists.items() if int(tic) in s]
