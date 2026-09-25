"""Nightly checker: `python -m api.nightly [--db PATH] [--dry-run]`.

Sky traps: new Rubin alerts since the trap's last check. Star traps: re-hunt only when new
TESS data exists. Idempotent: each window advances only when its catches are committed, and
IDs plus the one-catch-per-player key absorb any overlap.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime

from api import catalog
from api.settings import Settings
from api.timeutil import iso, utcnow
from api.wiring import Services, build_services

log = logging.getLogger("api.nightly")


@dataclass
class Summary:
    run_until: str
    sky_checked: int = 0
    star_checked: int = 0
    star_rehunted: int = 0
    star_skipped_no_new_data: int = 0
    new_catches: int = 0
    created: int = 0
    updated: int = 0
    rejected: int = 0
    failures: list[dict] = field(default_factory=list)


def _log_step(tic: int):
    return lambda step: log.debug("TIC %s: %s", tic, step)


def run_nightly(services: Services, now: datetime | None = None, dry_run: bool = False) -> Summary:
    run_until = now or utcnow()
    storage = services.storage
    s = Summary(run_until=iso(run_until))

    for trap in storage.iter_traps():
        try:
            if trap.kind == "sky":
                s.sky_checked += 1
                since = trap.last_checked_at or trap.created_at
                if since >= run_until:
                    continue
                found = services.alerts.alerts_in_sphere(trap.sphere, since, run_until)
                if dry_run:
                    s.new_catches += sum(not storage.has_catch(trap.player_id, d.id) for d in found)
                    continue
                with storage.atomic():
                    r = catalog.ingest_rubin(storage, trap.player_id, trap.id, found, run_until)
                    storage.set_trap_checked(trap.id, last_checked_at=run_until)
            else:
                s.star_checked += 1
                tic = trap.star.tic_id
                marker = services.hunter.latest_data_marker(tic)
                if marker is None or marker == trap.last_tess_marker:
                    s.star_skipped_no_new_data += 1
                    continue
                s.star_rehunted += 1
                if dry_run:
                    continue
                found = services.hunter.hunt(tic, _log_step(tic))
                with storage.atomic():
                    r = catalog.ingest_hunt(storage, trap.player_id, trap.id, tic, found, run_until)
                    storage.set_trap_checked(trap.id, last_checked_at=run_until, marker=marker)
            s.new_catches += r.new_catches
            s.created += r.created
            s.updated += r.updated
            s.rejected += len(r.rejected)
        except Exception as e:  # one bad trap must not stop the others
            log.exception("trap %s failed", trap.id)
            s.failures.append({"trap_id": trap.id, "error": str(e) or type(e).__name__})
    return s


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m api.nightly", description=__doc__)
    parser.add_argument("--db", help="SQLite path (default: $PH_DB_PATH or traps.db)")
    parser.add_argument("--dry-run", action="store_true", help="count, but write nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    settings = Settings.from_env()
    if args.db:
        settings = Settings(**{**settings.__dict__, "db_path": args.db})
    summary = run_nightly(build_services(settings), dry_run=args.dry_run)
    print(json.dumps(asdict(summary), indent=2))
    return 1 if summary.failures else 0


if __name__ == "__main__":
    sys.exit(main())
