"""Join the same object reported by several sources into ONE Event.

Two events from different sources are the same object if either:

1. Name: they share a name (raw.names, normalised: case, spaces and the "SN "/"AT "/"TDE "
   prefix ignored). E.g. TNS "SN 2026acow" lists internal name "ZTF26abwpgne" = ztf:ZTF26abwpgne;
   Rubin's TNS cross-match "AT 2026ema" = tns:2026ema; "GRB 260920B" and "EP260920b".
2. Position + time, sky frame only, and only within the same category, with compatible types
   (equal, or one is "unknown"):
   - transients: separation <= max(2 arcsec, error_a + error_b), observed within 60 days
     (TNS gives the first detection, the brokers the latest one);
   - high energy: separation <= error_a + error_b (both 90% radii), observed within 1 hour.
   Solar-system, Sun and Earth events join by name only: their positions move, or aren't points.

Matches are transitive (union-find). The merged Event keeps the id, type, title, summary and
confidence of the best member: official_report > catalogue_match > machine_guess, then source
priority (SOURCE_PRIORITY), then earliest report. It takes the tightest position, the earliest
reported_at, the latest observed_at (raw.first_observed_at keeps the earliest), every image, and
lists every member in raw.sources = [{source, id, source_url}], so both links survive.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from datetime import timedelta

from .models import CATEGORY_OF, Event
from .util import as_utc, sep_deg

SOURCE_PRIORITY = ["tns", "gcn", "gracedb", "icecube", "jpl", "mpc", "donki", "cneos", "rubin", "ztf"]
BASIS_RANK = {"official_report": 0, "catalogue_match": 1, "machine_guess": 2}
TRANSIENT_MIN_SEP_DEG = 2.0 / 3600
TRANSIENT_MAX_DT = timedelta(days=60)
HIGH_ENERGY_MAX_DT = timedelta(hours=1)


def norm_name(name: str) -> str:
    n = re.sub(r"\s+", "", name.strip().lower())
    return re.sub(r"^(sn|at|tde)(?=\d{4}[a-z]+$)", "", n)


def names(e: Event) -> set[str]:
    return {norm_name(n) for n in e.get("raw", {}).get("names", []) if n}


def dedup(events: list[Event]) -> list[Event]:
    events = sorted(events, key=lambda e: e["id"])
    parent = list(range(len(events)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        if events[i]["source"] != events[j]["source"] or events[i]["id"] == events[j]["id"]:
            parent[find(i)] = find(j)

    # 0. the same id twice (a source listing one object in two places) is one event
    for i in range(1, len(events)):
        if events[i]["id"] == events[i - 1]["id"]:
            union(i - 1, i)

    # 1. names
    by_name: dict[str, list[int]] = defaultdict(list)
    for i, e in enumerate(events):
        for n in names(e):
            by_name[n].append(i)
    for idx in by_name.values():
        for j in idx[1:]:
            union(idx[0], j)

    # 2. position + time
    for i, j in _position_pairs(events):
        union(i, j)

    clusters: dict[int, list[Event]] = defaultdict(list)
    for i, e in enumerate(events):
        clusters[find(i)].append(e)
    merged = [merge(c) if len(c) > 1 else _single(c[0]) for c in clusters.values()]
    return sorted(merged, key=lambda e: e["observed_at"], reverse=True)


def _compatible(a: Event, b: Event) -> bool:
    return a["type"] == b["type"] or "unknown" in (a["type"], b["type"])


def _position_pairs(events: list[Event]):
    by_cat: dict[str, list[int]] = defaultdict(list)
    for i, e in enumerate(events):
        if e["location"]["frame"] != "sky":
            continue
        cat = CATEGORY_OF.get(e["type"])
        if cat == "other":  # "unknown" joins its neighbours' category by position
            for c in ("transients", "high_energy"):
                by_cat[c].append(i)
        elif cat in ("transients", "high_energy"):
            by_cat[cat].append(i)

    # transients: bucket by declination so the comparison stays near-linear
    band = 0.05
    buckets: dict[int, list[int]] = defaultdict(list)
    for i in by_cat["transients"]:
        buckets[int(events[i]["location"]["dec_deg"] // band)].append(i)
    for b, idx in buckets.items():
        near = idx + buckets.get(b + 1, [])
        for x, i in enumerate(idx):
            for j in near[x + 1 :]:
                if _match(events[i], events[j], TRANSIENT_MAX_DT, TRANSIENT_MIN_SEP_DEG):
                    yield i, j

    he = by_cat["high_energy"]
    for x, i in enumerate(he):
        for j in he[x + 1 :]:
            if _match(events[i], events[j], HIGH_ENERGY_MAX_DT, 0.0):
                yield i, j


def _match(a: Event, b: Event, max_dt: timedelta, min_sep: float) -> bool:
    if a["source"] == b["source"] or not _compatible(a, b):
        return False
    if abs(as_utc(a["observed_at"]) - as_utc(b["observed_at"])) > max_dt:
        return False
    la, lb = a["location"], b["location"]
    tol = max(min_sep, la["error_deg"] + lb["error_deg"])
    return sep_deg(la["ra_deg"], la["dec_deg"], lb["ra_deg"], lb["dec_deg"]) <= tol


def _rank(e: Event) -> tuple:
    pri = SOURCE_PRIORITY.index(e["source"]) if e["source"] in SOURCE_PRIORITY else len(SOURCE_PRIORITY)
    return (BASIS_RANK.get(e["confidence_basis"], 3), pri, e["reported_at"], e["id"])


def _link(e: Event) -> dict:
    return {"source": e["source"], "id": e["id"], "source_url": e["source_url"]}


def _single(e: Event) -> Event:
    out = copy.deepcopy(e)
    out["raw"]["sources"] = [_link(e)]
    return out


def merge(cluster: list[Event]) -> Event:
    ranked = sorted(cluster, key=_rank)
    best = ranked[0]
    out = copy.deepcopy(best)
    if out["type"] == "unknown":
        out["type"] = next((e["type"] for e in ranked if e["type"] != "unknown"), "unknown")
    sky_locs = [e["location"] for e in ranked if e["location"]["frame"] == "sky"]
    if sky_locs:
        out["location"] = copy.deepcopy(min(sky_locs, key=lambda loc: loc["error_deg"]))
    observed = sorted(e["observed_at"] for e in cluster)
    out["observed_at"] = observed[-1]
    out["reported_at"] = min(e["reported_at"] for e in cluster)
    if out["brightness_mag"] is None:
        out["brightness_mag"] = next((e["brightness_mag"] for e in ranked if e["brightness_mag"] is not None), None)
    seen: set[str] = set()
    out["images"] = []
    for e in ranked:
        for img in e["images"]:
            if img["url"] not in seen:
                seen.add(img["url"])
                out["images"].append(copy.deepcopy(img))
    raw = out["raw"]
    raw["names"] = sorted({n for e in ranked for n in e["raw"].get("names", [])})
    raw["first_observed_at"] = observed[0]
    raw["sources"] = [_link(e) for e in ranked]
    raw["merged_ids"] = [e["id"] for e in ranked[1:]]
    return out
