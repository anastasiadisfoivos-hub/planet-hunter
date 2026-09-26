"""Store HUNT's candidates, re-check them against the known lists, and pixel-check them.

    python -m api.finder_ingest --dir hunt/candidates [--sensitivity FILE] [--summary FILE]

Steps:
1. Upsert every <tic>_<n>.json in --dir. A candidate whose content (without created_at) is
   unchanged is not rewritten; status and votes always survive.
2. Dismiss an open candidate ("new"/"under review") that is now on a TOI, CTOI, confirmed-planet
   or eclipsing-binary list: first from HUNT's own `known_lists`, then by re-checking up to
   --recheck-limit open candidates (longest-unchecked first) through the KnownLists adapter.
   Exported candidates are never dismissed (once submitted they are on the CTOI list).
3. Store the sweep summary (--summary, else summary.json / sweep_summary.json next to the
   candidates or one folder up) for GET /finder/funnel, and --sensitivity for
   GET /finder/sensitivity.
4. Pixel-check up to --pixel-limit open candidates without a current vet (never-vetted first,
   then by score), stopping when --time-budget-min runs out. A failure is stored and retried on
   later runs, at most --max-vet-attempts times per ephemeris.

Prints a JSON summary. Exits 1 when a candidate file is invalid (the rest are still stored).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from api import honesty
from api.finder import (
    CANDIDATE_ID,
    InvalidCandidate,
    candidate_row,
    known_match,
    normalize_vet,
    parse_candidate,
)
from api.ports import KnownLists, PixelVetter, Storage
from api.settings import Settings
from api.timeutil import utcnow
from api.wiring import build_known_lists, build_pixel_vetter, storage_from_cli

log = logging.getLogger("api.finder_ingest")
SUMMARY_NAMES = ("summary.json", "sweep_summary.json")


def find_summary(folder: Path) -> Path | None:
    for base in (folder, folder.parent):
        for name in SUMMARY_NAMES:
            if (base / name).is_file():
                return base / name
    return None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ingest(
    storage: Storage,
    folder: Path,
    *,
    vetter: PixelVetter | None,
    known: KnownLists | None,
    sensitivity: Path | None = None,
    summary: Path | None = None,
    pixel_limit: int = 20,
    recheck_limit: int = 50,
    max_vet_attempts: int = 3,
    time_budget_s: float = 30 * 60,
    clock=time.monotonic,
) -> dict[str, Any]:
    deadline = clock() + time_budget_s
    out: dict[str, Any] = {
        "candidates": {"created": 0, "updated": 0, "unchanged": 0},
        "invalid": [],
        "dismissed": [],
        "recheck": {"checked": 0, "errors": 0},
        "pixels": {"vetted": 0, "failed": 0, "skipped_for_time": 0},
        "summary_stored": False,
        "sensitivity_stored": False,
    }

    # 1. candidates
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("*.json")):
        if not CANDIDATE_ID.match(path.stem):
            continue
        try:
            records[path.stem] = parse_candidate(path.stem, _load_json(path))
        except (InvalidCandidate, ValueError, OSError) as exc:
            out["invalid"].append({"file": path.name, "error": str(exc)[:300]})
    now = utcnow()
    hashes = storage.candidate_hashes(list(records))
    for cid, rec in records.items():
        row = candidate_row(cid, rec, now)
        same = hashes.get(cid) == row.content_hash
        out["candidates"]["unchanged" if same else storage.upsert_candidate(row)] += 1

    # 2. known lists
    def dismiss(cid: str, reason: str) -> None:
        if storage.dismiss_candidate(cid, honesty.soften(reason), utcnow()):
            out["dismissed"].append({"id": cid, "reason": reason})

    for cid, rec in records.items():
        if match := known_match(rec.get("known_lists")):
            dismiss(cid, match.reason())
    if known is not None and recheck_limit > 0:
        for cid, tic, period in storage.candidates_to_recheck(recheck_limit):
            if clock() >= deadline:
                break
            try:
                match = known.match(tic, period)
            except Exception as exc:  # lists down: leave it open, try again next run
                out["recheck"]["errors"] += 1
                log.warning("known-list re-check failed for %s: %s", cid, exc)
                continue
            out["recheck"]["checked"] += 1
            if match:
                dismiss(cid, match.reason())
            else:
                storage.mark_known_checked(cid, utcnow())

    # 3. summary, sensitivity
    summary = summary or find_summary(folder)
    if summary is not None:
        storage.put_finder_doc("finder_sweep", honesty.clean(_load_json(summary)), utcnow())
        out["summary_stored"] = True
    if sensitivity is not None:
        storage.put_finder_doc("sensitivity", honesty.clean(_load_json(sensitivity)), utcnow())
        out["sensitivity_stored"] = True

    # 4. pixel vets
    if vetter is not None and pixel_limit > 0:
        todo = storage.candidates_to_vet(pixel_limit, max_vet_attempts)
        for i, item in enumerate(todo):
            if clock() >= deadline:
                out["pixels"]["skipped_for_time"] = len(todo) - i
                break
            try:
                vet = normalize_vet(vetter.vet(item.record))
            except Exception as exc:
                storage.put_pixel_vet(
                    item.id, item.ephemeris_key, None, f"{type(exc).__name__}: {exc}"[:500],
                    utcnow(),
                )  # fmt: skip
                out["pixels"]["failed"] += 1
                log.warning("pixel vet failed for %s: %s", item.id, exc)
                continue
            storage.put_pixel_vet(item.id, item.ephemeris_key, vet, None, utcnow())
            out["pixels"]["vetted"] += 1
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m api.finder_ingest", description=__doc__.split("\n")[0]
    )
    p.add_argument("--dir", required=True, type=Path, help="HUNT's candidates folder")
    p.add_argument("--sensitivity", type=Path, help="HUNT's sensitivity JSON")
    p.add_argument("--summary", type=Path, help="HUNT's sweep summary JSON (default: found)")
    p.add_argument("--pixel-limit", type=int, default=20, help="pixel vets per run")
    p.add_argument("--recheck-limit", type=int, default=50, help="known-list re-checks per run")
    p.add_argument("--max-vet-attempts", type=int, default=3)
    p.add_argument("--time-budget-min", type=float, default=30.0)
    p.add_argument("--no-pixels", action="store_true")
    p.add_argument("--no-recheck", action="store_true")
    p.add_argument("--db", help="SQLite file (default: PH_DB_PATH)")
    p.add_argument("--database-url", help="Postgres URL (default: PH_DATABASE_URL)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.dir.is_dir():
        p.error(f"--dir {args.dir} is not a folder")
    settings = Settings.from_env()
    vetter, known, unavailable = None, None, None
    if not args.no_pixels:
        try:
            vetter = build_pixel_vetter(settings)
        except ImportError as exc:  # pixels/ not installed yet: store the rest, vet next time
            unavailable = f"pixels not installed: {exc}"
            log.warning("%s; skipping pixel vets", unavailable)
    if not args.no_recheck:
        known = build_known_lists(settings)
    storage = storage_from_cli(args.db, args.database_url)
    try:
        result = ingest(
            storage,
            args.dir,
            vetter=vetter,
            known=known,
            sensitivity=args.sensitivity,
            summary=args.summary,
            pixel_limit=args.pixel_limit,
            recheck_limit=args.recheck_limit,
            max_vet_attempts=args.max_vet_attempts,
            time_budget_s=args.time_budget_min * 60,
        )
    finally:
        storage.close()
    if unavailable:
        result["pixels"]["unavailable"] = unavailable
    print(json.dumps(result, indent=1))
    return 1 if result["invalid"] else 0


if __name__ == "__main__":
    sys.exit(main())
