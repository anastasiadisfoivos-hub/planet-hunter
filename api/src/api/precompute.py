"""Pre-compute "Analyze a star" results: `python -m api.precompute`.

    python -m api.precompute --known-systems
    python -m api.precompute --tic-file web/public/data/hosts.json --shard 3/20
    python -m api.precompute --stars 100100827,22529346 --force

Idempotent: a star whose stored result matches its current TESS data marker is skipped (so a
re-run, or a run after a crash, only does what's missing or out of date). A skipped star whose
result was stored before light curves were kept gets its light curve re-read (no new search).
A failing star is recorded and the run moves on. Prints a JSON summary; exits 1 if more than
--max-failed-fraction of the stars failed (default: any).

--shard i/N (0 <= i < N) takes every N-th star of the sorted, de-duplicated list, starting at i,
so N parallel runs cover the list exactly once. Uses PH_ADAPTERS (set it to "real") and
PH_DATABASE_URL like the API.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api import analysis
from api.known_systems import KNOWN_SYSTEMS
from api.ports import StarAnalyzer, Storage
from api.timeutil import utcnow

log = logging.getLogger("api.precompute")


def read_tics(path: Path) -> list[int]:
    """TICs from hosts.json (columnar, a "tic" list), a JSON list (ints or objects with tic /
    tic_id), or text with one TIC per line ("TIC " prefix and # comments allowed)."""
    text = path.read_text()
    try:
        doc: Any = json.loads(text)
    except json.JSONDecodeError:
        doc = None
    values: list[Any]
    if isinstance(doc, dict):
        values = doc.get("tic") or doc.get("tics") or doc.get("stars") or []
    elif isinstance(doc, list):
        values = doc
    else:
        values = [line.split("#", 1)[0] for line in text.splitlines()]
    tics = []
    for v in values:
        if isinstance(v, dict):
            v = v.get("tic_id", v.get("tic"))
        if isinstance(v, str):
            v = re.sub(r"(?i)^\s*tic\s*", "", v).strip()
            if not v:
                continue
        if v is None:
            continue
        try:
            tic = int(v)
        except (TypeError, ValueError):
            log.warning("skipping %r: not a TIC", v)
            continue
        if tic > 0:
            tics.append(tic)
    return tics


def parse_shard(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    if not m or not 0 <= int(m[1]) < int(m[2]):
        raise argparse.ArgumentTypeError("--shard must be i/N with 0 <= i < N, e.g. 0/20")
    return int(m[1]), int(m[2])


def shard(tics: list[int], i: int, n: int) -> list[int]:
    return sorted(set(tics))[i::n]


@dataclass
class Summary:
    shard: str
    stars: int = 0
    analyzed: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)  # stored result is current
    lightcurves_reread: list[int] = field(default_factory=list)  # skipped, curve backfilled
    no_data: list[int] = field(default_factory=list)  # no TESS light curve
    failed: list[dict[str, Any]] = field(default_factory=list)
    not_reached: list[int] = field(default_factory=list)  # --time-budget-min ran out
    seconds: float = 0.0


def backfill(storage: Storage, analyzer: StarAnalyzer, tic: int) -> bool:
    """Re-read a current result's light curve if it has none; never fails the star."""
    rec = storage.get_star_analysis(tic)
    if rec is None or not analysis.needs_lightcurve(storage, rec):
        return False
    try:
        analysis.backfill_lightcurve(storage, analyzer, rec, utcnow())
    except Exception as exc:  # noqa: BLE001
        log.warning("TIC %s: light curve re-read failed: %s", tic, exc)
        return False
    return True


def precompute_one(storage: Storage, analyzer: StarAnalyzer, tic: int, force: bool) -> str:
    """'analyzed', 'skipped', 'skipped_reread' (a light curve backfilled) or 'no_data'.
    Raises on failure."""
    rec = storage.get_star_analysis(tic)
    try:
        marker = analyzer.latest_data_marker(tic)
        marker_known = True
    except Exception as exc:  # noqa: BLE001
        log.warning("TIC %s: data marker unavailable: %s", tic, exc)
        marker, marker_known = None, False
    if not force:
        if rec is not None and (not marker_known or marker is None or marker == rec.data_marker):
            if marker_known:
                storage.touch_star_analysis(tic, utcnow())
            return "skipped_reread" if backfill(storage, analyzer, tic) else "skipped"
        if marker_known and marker is None:
            analysis.record_no_data(storage, tic, utcnow())
            return "no_data"
    try:
        analysis.run(
            storage, analyzer, tic, marker, lambda step: log.info("TIC %s: %s", tic, step), utcnow
        )
    except LookupError as exc:  # no light curve (or none with usable points)
        log.info("TIC %s: %s", tic, exc)
        analysis.record_no_data(storage, tic, utcnow())
        return "no_data"
    return "analyzed"


def run(
    storage: Storage,
    analyzer: StarAnalyzer,
    tics: list[int],
    *,
    shard_label: str = "0/1",
    force: bool = False,
    time_budget_s: float | None = None,
) -> Summary:
    started = time.monotonic()
    summary = Summary(shard=shard_label, stars=len(tics))
    for k, tic in enumerate(tics):
        if time_budget_s is not None and time.monotonic() - started > time_budget_s:
            summary.not_reached = tics[k:]
            break
        t0 = time.monotonic()
        try:
            outcome = precompute_one(storage, analyzer, tic, force)
        except Exception as exc:  # noqa: BLE001 - one star must not stop the shard
            log.warning("TIC %s failed: %s", tic, exc)
            summary.failed.append({"tic_id": tic, "error": (str(exc) or type(exc).__name__)[:300]})
            outcome = "failed"
        else:
            if outcome == "skipped_reread":
                summary.lightcurves_reread.append(tic)
                outcome = "skipped"
            getattr(summary, outcome).append(tic)
        print(
            f"[{k + 1}/{len(tics)}] TIC {tic}: {outcome} ({time.monotonic() - t0:.1f} s)",
            file=sys.stderr,
            flush=True,
        )
    summary.seconds = round(time.monotonic() - started, 1)
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m api.precompute", description=__doc__.split("\n\n")[0]
    )
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--tic-file", type=Path, help="hosts.json, a JSON list, or one TIC per line")
    which.add_argument("--known-systems", action="store_true", help=", ".join(KNOWN_SYSTEMS))
    which.add_argument("--stars", help="comma-separated TICs")
    p.add_argument("--shard", type=parse_shard, default=(0, 1), help="i/N, 0-based (default 0/1)")
    p.add_argument("--force", action="store_true", help="re-analyze even if stored")
    p.add_argument("--max-failed-fraction", type=float, default=0.0)
    p.add_argument("--time-budget-min", type=float, help="stop starting new stars after this long")
    p.add_argument("--db", help="SQLite path (default: PH_DATABASE_URL, else PH_DB_PATH)")
    p.add_argument("--database-url", help="Postgres URL (default: PH_DATABASE_URL)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if a.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if a.known_systems:
        tics = list(KNOWN_SYSTEMS.values())
    elif a.stars:
        tics = [int(s) for s in re.split(r"[,\s]+", a.stars.strip()) if s]
    else:
        tics = read_tics(a.tic_file)
    i, n = a.shard
    mine = shard(tics, i, n)

    from api.settings import Settings
    from api.wiring import build_analyzer, storage_from_cli

    storage = storage_from_cli(a.db, a.database_url)
    try:
        summary = run(
            storage,
            build_analyzer(Settings.from_env()),
            mine,
            shard_label=f"{i}/{n}",
            force=a.force,
            time_budget_s=a.time_budget_min * 60 if a.time_budget_min else None,
        )
    finally:
        storage.close()

    out = {
        "shard": summary.shard,
        "stars_in_list": len(set(tics)),
        "stars_in_shard": summary.stars,
        "counts": {
            k: len(getattr(summary, k))
            for k in (
                "analyzed",
                "skipped",
                "lightcurves_reread",
                "no_data",
                "failed",
                "not_reached",
            )
        },  # fmt: skip
        "analyzed": summary.analyzed,
        "lightcurves_reread": summary.lightcurves_reread,
        "no_data": summary.no_data,
        "failed": summary.failed,
        "not_reached": summary.not_reached,
        "seconds": summary.seconds,
    }
    print(json.dumps(out, indent=1))
    done = summary.stars - len(summary.not_reached)
    failed_fraction = len(summary.failed) / done if done else 0.0
    return 1 if failed_fraction > a.max_failed_fraction else 0


if __name__ == "__main__":
    sys.exit(main())
