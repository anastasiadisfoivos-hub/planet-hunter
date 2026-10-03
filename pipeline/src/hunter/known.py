"""Is this signal already on a list? Confirmed planets, TOIs, CTOIs, and the TESS eclipsing-binary catalogue."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import requests

from .cache import DAY, cached_json, retry

ARCHIVE_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
CTOI_URL = "https://exofop.ipac.caltech.edu/tess/download_ctoi.php?sort=ctoi&output=pipe"
VIZIER_ASU = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
EB_CATALOGUE = "J/ApJS/258/16/tess-ebs"  # Prsa et al. 2022, ApJS 258, 16
TTL = 7 * DAY
TIMEOUT = 60
ALIASES = {1.0: "same period", 2.0: "our period is twice the listed one", 3.0: "our period is 3x the listed one",
           0.5: "our period is half the listed one", 1 / 3: "our period is 1/3 of the listed one"}


@dataclass
class CatalogueEntry:
    name: str
    period: float | None
    list_name: str
    extra: dict = field(default_factory=dict)


@dataclass
class KnownResult:
    status: str  # "known" | "not_on_lists" | "unchecked"
    name: str | None
    list_name: str | None
    listed_period: float | None
    alias: str | None
    extra: dict
    errors: list[str]


def _get(url: str, params: dict | None = None) -> str:
    def call() -> str:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text
    return retry(call)


def _tap(query: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(_get(ARCHIVE_TAP, {"query": query, "format": "csv"}))))


def _float(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def confirmed_planets(tic_id: int) -> list[dict]:
    rows = cached_json("archive-ps", str(tic_id), TTL, lambda: _tap(
        "select pl_name,pl_orbper,pl_trandep,pl_radj from pscomppars "
        f"where tic_id = 'TIC {int(tic_id)}'"))
    return [{"name": r["pl_name"], "period": _float(r["pl_orbper"]), "list": "NASA Exoplanet Archive (confirmed)",
             "extra": {"archive_depth_pct": _float(r["pl_trandep"]), "archive_radius_rjup": _float(r["pl_radj"])}}
            for r in rows]


def tois(tic_id: int) -> list[dict]:
    rows = cached_json("archive-toi", str(tic_id), TTL, lambda: _tap(
        f"select toi,pl_orbper,tfopwg_disp from toi where tid = {int(tic_id)}"))
    return [{"name": f"TOI-{r['toi']}", "period": _float(r["pl_orbper"]), "list": "TESS Objects of Interest",
             "extra": {"tfopwg_disposition": r["tfopwg_disp"] or None}} for r in rows]


def _ctoi_table() -> list[dict]:
    reader = csv.DictReader(io.StringIO(_get(CTOI_URL)), delimiter="|")
    return [{"tic": r["TIC ID"], "ctoi": r["CTOI"], "period": r["Period (days)"],
             "disp": r["TFOPWG Disposition"] or r["User Disposition"]} for r in reader]


def ctois(tic_id: int) -> list[dict]:
    table = cached_json("exofop-ctoi", "all", TTL, _ctoi_table)
    return [{"name": f"CTOI {r['ctoi']}", "period": _float(r["period"]), "list": "ExoFOP community TOIs",
             "extra": {"disposition": r["disp"] or None}} for r in table if r["tic"] == str(int(tic_id))]


def _eb_rows(tic_id: int) -> list[dict]:
    text = _get(VIZIER_ASU, {"-source": EB_CATALOGUE, "TIC": str(int(tic_id)), "-out": "TIC,Per,Morph"})
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    # header, units, dashes, then data
    return [dict(zip(("tic", "period", "morph"), (c.strip() for c in ln.split("\t")))) for ln in lines[3:]]


def eclipsing_binaries(tic_id: int) -> list[dict]:
    rows = cached_json("tess-ebs", str(tic_id), TTL, lambda: _eb_rows(tic_id))
    return [{"name": f"TIC {int(tic_id)} (TESS EB catalogue)", "period": _float(r["period"]),
             "list": "TESS Eclipsing Binary catalogue (Prsa et al. 2022)",
             "extra": {"morphology": _float(r["morph"])}} for r in rows]


def match_period(found: float, listed: float | None, tol: float = 0.01) -> str | None:
    if not listed:
        return None
    ratio = found / listed
    for k, label in ALIASES.items():
        if abs(ratio - k) / k < tol:
            return label
    return None


def check(tic_id: int, period: float, include_eb_catalogue: bool = False) -> KnownResult:
    sources = [confirmed_planets, tois, ctois]
    if include_eb_catalogue:
        sources = [eclipsing_binaries, *sources]
    errors: list[str] = []
    best = None
    for source in sources:
        try:
            entries = source(tic_id)
        except Exception as exc:
            errors.append(f"{source.__name__}: {type(exc).__name__}: {exc}"[:300])
            continue
        for e in entries:
            alias = match_period(period, e["period"])
            if alias is None:
                continue
            rank = 0 if alias == "same period" else 1
            if best is None or rank < best[0]:
                best = (rank, e, alias)
        if best is not None and best[0] == 0:
            break
    if best is not None:
        _, e, alias = best
        return KnownResult("known", e["name"], e["list"], e["period"], alias, e["extra"], errors)
    return KnownResult("unchecked" if errors else "not_on_lists", None, None, None, None, {}, errors)
