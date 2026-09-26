"""Target lists for the sweep.

List A ("new"): stars with a 2-min (SPOC) or FFI (QLP) light curve in the most recent public sector(s),
Tmag <= 13, not a TOI, CTOI, confirmed-planet host or catalogued eclipsing binary.
List B ("siblings"): hosts of confirmed transiting planets observed in the same sectors, Tmag <= 13; their
known planets are masked and the residuals searched for more.

Both lists are ranked: M dwarfs first, then small stars, then other dwarfs, then everything else; inside a
tier smaller stars first (a given planet makes a deeper dip), then brighter stars (less noise).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from hunter.cache import retry

from . import catalogs, stars
from .cache import DAY, cached_json, download
from .stars import Star

MAX_TMAG = 13.0
QLP_TARGET_LIST = "https://archive.stsci.edu/hlsps/qlp/target_lists/s{sector:04d}.csv"
SECTOR1_START = date(2018, 7, 25)
SMALL_STAR_RSUN = 0.8

TIERS = {0: "M dwarf (Teff < 4000 K)", 1: f"small star (R < {SMALL_STAR_RSUN} R_sun)",
         2: "dwarf star", 3: "other (giant, subgiant or no class in the TIC)"}


def _count(**criteria) -> int:
    from astroquery.mast import Observations

    return int(retry(lambda: Observations.query_criteria_count(**criteria)))


def _criteria(kind: str, sector: int) -> dict:
    if kind == "2min":
        return {"obs_collection": "TESS", "dataproduct_type": "timeseries", "sequence_number": sector}
    return {"obs_collection": "HLSP", "provenance_name": "QLP", "sequence_number": sector}


def latest_sectors(kind: str, n: int = 1, today: date | None = None) -> list[int]:
    """The newest n sectors with public light curves of this kind ("2min" = SPOC, "ffi" = QLP)."""
    today = today or datetime.now(UTC).date()
    guess = int((today - SECTOR1_START).days / 27.3) + 3

    def compute() -> list[int]:
        found = []
        for s in range(guess, 0, -1):
            if _count(**_criteria(kind, s)) > 0:
                found.append(s)
                if len(found) == n:
                    break
        return found
    return cached_json(f"sectors/{kind}-{n}-{today.isoformat()}", 0.25 * DAY, compute)


def _spoc_rows(sector: int) -> list[tuple[int, float, float]]:
    from astroquery.mast import Observations

    def compute() -> list:
        t = retry(lambda: Observations.query_criteria(**_criteria("2min", sector)))
        rows = {}
        for r in t:
            name = str(r["target_name"]).lstrip("0")
            if name.isdigit() and int(r["t_exptime"]) == 120:
                rows[int(name)] = (int(name), float(r["s_ra"]), float(r["s_dec"]))
        return list(rows.values())
    return [tuple(x) for x in cached_json(f"sector-lists/spoc-s{sector:04d}", 30 * DAY, compute)]


def _qlp_rows(sector: int) -> list[tuple[int, float, float]]:
    path = download(QLP_TARGET_LIST.format(sector=sector), f"sector-lists/qlp-s{sector:04d}.csv", 30 * DAY)
    rows = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            tic, ra, dec = line.strip().split(",")[:3]
            rows.append((int(tic), float(ra), float(dec)))
    return rows


def tier(s: Star) -> int:
    dwarf = (s.lumclass or "DWARF") == "DWARF" and (s.logg is None or s.logg >= 3.8)
    if s.teff is not None and s.teff < 4000 and dwarf and s.lumclass == "DWARF":
        return 0
    if s.rad is not None and s.rad < SMALL_STAR_RSUN and dwarf:
        return 1
    if s.lumclass == "DWARF" and s.rad is not None:
        return 2
    return 3


def rank_key(s: Star) -> tuple:
    return (tier(s), s.rad if s.rad is not None else 99.0, s.tmag if s.tmag is not None else 99.0)


def reason(s: Star, where: dict[str, list[int]], known: list[str] | None = None) -> str:
    bits = [TIERS[tier(s)]]
    if s.teff is not None:
        bits.append(f"Teff {s.teff:.0f} K")
    if s.rad is not None:
        bits.append(f"R {s.rad:.2f} R_sun")
    bits.append(f"Tmag {s.tmag:.2f}")
    bits.append(", ".join(f"{k} in S{','.join(map(str, v))}" for k, v in where.items() if v))
    if known:
        bits.append("known: " + ", ".join(known))
    return "; ".join(bits)


@dataclass
class TargetRow:
    rank: int
    list: str  # "A" new-star search | "B" sibling search on a known host
    star: Star
    tier: int
    observed: dict[str, list[int]]
    known: list[str]
    reason: str

    def to_csv(self) -> dict:
        return {"rank": self.rank, "list": self.list, **self.star.to_row(), "tier": self.tier,
                "sectors_2min": " ".join(map(str, self.observed.get("2min", []))),
                "sectors_ffi": " ".join(map(str, self.observed.get("ffi", []))),
                "known": "; ".join(self.known), "reason": self.reason}


CSV_FIELDS = ["rank", "list", "tic", "ra", "dec", "tmag", "teff", "logg", "rad", "rad_err", "mass", "rho", "lumclass",
              "contratio", "tier", "sectors_2min", "sectors_ffi", "known", "reason"]


def build(n_sectors: int = 1, max_tmag: float = MAX_TMAG, refresh: bool = False, log=print) -> dict:
    cat = catalogs.load(refresh)
    sectors = {"2min": latest_sectors("2min", n_sectors), "ffi": latest_sectors("ffi", n_sectors)}
    log(f"latest public sectors: {sectors}")

    observed: dict[int, dict[str, list[int]]] = {}
    positions: dict[int, tuple[int, float, float]] = {}
    raw_counts = {}
    for kind, secs in sectors.items():
        for s in secs:
            rows = _spoc_rows(s) if kind == "2min" else _qlp_rows(s)
            raw_counts[f"{kind}_s{s}"] = len(rows)
            log(f"{kind} S{s}: {len(rows)} light curves")
            for tic, ra, dec in rows:
                observed.setdefault(tic, {"2min": [], "ffi": []})[kind].append(s)
                positions[tic] = (tic, ra, dec)

    log(f"{len(positions)} distinct stars; fetching TIC parameters (CDS xMatch)")
    bright = stars.bulk(sorted(positions.values()), max_tmag, label="targets")
    bright = {s.tic: s for s in bright}

    known_any = cat.tics
    hosts = cat.tics_of("confirmed")
    transiting_hosts = {e.tic for e in cat.entries if e.kind == "confirmed" and e.disposition == "transiting"}

    list_a = sorted((s for tic, s in bright.items() if tic not in known_any), key=rank_key)
    list_b = sorted((s for tic, s in bright.items() if tic in transiting_hosts), key=rank_key)

    def rows_for(lst: str, ss: list[Star]) -> list[TargetRow]:
        out = []
        for i, s in enumerate(ss, start=1):
            known = [e.name for e in cat.on_star(s.tic)] if lst == "B" else []
            out.append(TargetRow(i, lst, s, tier(s), observed[s.tic], known, reason(s, observed[s.tic], known)))
        return out

    a_rows, b_rows = rows_for("A", list_a), rows_for("B", list_b)
    kind_sets = {k: cat.tics_of(k) for k in ("toi", "ctoi", "confirmed", "eb")}
    excluded = {k: len(kind_sets[k] & bright.keys()) for k in kind_sets}
    summary = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sectors": sectors,
        "light_curves_per_sector": raw_counts,
        "distinct_stars": len(positions),
        "tmag_le_13": len(bright),
        "on_known_lists_by_list": excluded,
        "on_any_known_list": len(known_any & bright.keys()),
        "confirmed_hosts_any": len(hosts & bright.keys()),
        "list_a": len(a_rows),
        "list_a_by_tier": {TIERS[k]: sum(1 for r in a_rows if r.tier == k) for k in TIERS},
        "list_b": len(b_rows),
        "list_b_by_tier": {TIERS[k]: sum(1 for r in b_rows if r.tier == k) for k in TIERS},
        "catalogue_fetched_at": cat.fetched_at,
    }
    return {"summary": summary, "A": a_rows, "B": b_rows}


def write(result: dict, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key, name in (("A", "targets_new.csv"), ("B", "targets_siblings.csv")):
        paths[key] = out_dir / name
        with open(paths[key], "w", newline="") as fh:
            w = csv.DictWriter(fh, CSV_FIELDS)
            w.writeheader()
            for r in result[key]:
                w.writerow(r.to_csv())
    paths["summary"] = out_dir / "targets_summary.json"
    paths["summary"].write_text(json.dumps(result["summary"], indent=2))
    return paths


def read(path: Path) -> list[dict]:
    """Rows of a targets CSV, or of a plain file with one TIC number per line."""
    text = Path(path).read_text()
    first = text.lstrip().split("\n", 1)[0]
    if "tic" in first.split(","):
        return list(csv.DictReader(text.splitlines()))
    rows = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip().replace("TIC", "").strip()
        if line:
            rows.append({"tic": line, "list": "A"})
    return rows
