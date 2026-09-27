"""python3 -m scheduler run | status [--json] | update [--force-sync] | janitor | recover"""

from __future__ import annotations

import argparse

from scheduler.config import Config


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="planet-hunter", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run (or resume) today's search, then merge, vet and ingest it")
    s = sub.add_parser("status", help="is it running; tonight's progress; the last run")
    s.add_argument("--json", action="store_true")
    u = sub.add_parser("update", help="pull PH_REPO_REF and refresh changed venvs")
    u.add_argument("--force-sync", action="store_true")
    sub.add_parser("janitor", help="measure disk use and prune caches if over the cap")
    sub.add_parser("recover", help="make stars left 'running' by a crash retryable (run does this itself)")
    a = p.parse_args(argv)
    cfg = Config.from_env()
    if a.cmd == "run":
        from scheduler.run import Runner

        return Runner(cfg).execute()
    if a.cmd == "status":
        from scheduler import status

        return status.main(cfg, a.json)
    if a.cmd == "update":
        from scheduler.update import update

        return update(cfg, force_sync=a.force_sync)
    if a.cmd == "janitor":
        from scheduler.disk import janitor

        print(janitor(cfg.data, cfg.cache_dir, cfg.runs_dir, cfg.disk_cap_gb))
        return 0
    if a.cmd == "recover":
        from scheduler.ledger import Ledger

        print(f"{Ledger(cfg.ledger_path).recover()} star(s) made retryable")
        return 0
    return 2
