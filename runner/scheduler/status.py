"""`planet-hunter status`: is it running, how far tonight's run is, the last run, the ledger's totals, disk."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from scheduler.config import Config
from scheduler.ledger import Ledger


def _ago(ts: str | float | None) -> str:
    if ts is None:
        return "never"
    t = datetime.fromisoformat(ts).timestamp() if isinstance(ts, str) else float(ts)
    s = time.time() - t
    return f"{s:.0f} s ago" if s < 120 else f"{s / 60:.0f} min ago" if s < 7200 else f"{s / 3600:.1f} h ago"


def report(cfg: Config) -> dict:
    hb_path = cfg.state_dir / "heartbeat.json"
    hb = json.loads(hb_path.read_text()) if hb_path.exists() else None
    ledger = Ledger(cfg.ledger_path) if cfg.ledger_path.exists() else None
    totals = ledger.counts() if ledger else {}
    last = ledger.last_run() if ledger else None
    vets = ledger.pending_vets() if ledger else 0
    return {"heartbeat": hb, "ledger_totals": totals, "last_run": last, "vets_pending": vets}


def main(cfg: Config, as_json: bool = False) -> int:
    r = report(cfg)
    if as_json:
        print(json.dumps(r, indent=1, default=str))
        return 0
    hb = r["heartbeat"]
    if hb is None:
        print("No heartbeat yet: the runner has not started a run on this machine.")
    else:
        fresh = (time.time() - datetime.fromisoformat(hb["at"]).timestamp()) < 3 * max(cfg.heartbeat_s, 60)
        live = hb["state"] in ("preparing", "searching", "wrapping", "ingesting") and fresh
        print(f"Run {hb['run_id']}: {hb['state']}{' (live)' if live else ''}; heartbeat {_ago(hb['at'])}")
        for q, v in hb.get("queues", {}).items():
            print(f"  {q:5s} {v['done']:>6} done of {v['total']:<6} planned, {v['running']} running")
        print(f"  vets: {hb.get('vets_running', 0)} running, {hb.get('vets_pending', 0)} waiting")
        p = hb.get("poster") or {}
        if p:
            print(f"  monitor posts: {p.get('sent', 0)} sent, {p.get('failed', 0)} failed, "
                  f"{p.get('dropped', 0)} dropped; last OK {_ago(p.get('last_ok_at'))}"
                  + (f"; last error: {p['last_error']}" if p.get("last_error") else ""))
        d = hb.get("disk") or {}
        if d:
            print(f"  disk: {d.get('used_gb')} GB of a {d.get('cap_gb')} GB cap, {d.get('free_gb')} GB free"
                  + (" -- PAUSED (over the cap)" if d.get("paused") else ""))
        off = {k: v["why"] for k, v in (hb.get("capabilities") or {}).items() if not v.get("enabled")}
        if off:
            print("  off: " + "; ".join(f"{k}: {why}" for k, why in off.items()))
    last = r["last_run"]
    if last:
        s = last.get("summary") or {}
        fin = last.get("finished_at")
        print(f"Last run {last['run_id']}: {last['state']}" + (f", finished {_ago(fin)}" if fin else ""))
        for q, v in (s.get("stars_per_hour") or {}).items():
            print(f"  {q:5s} {v['stars']} stars, {v['mean_s_per_star']} s/star per worker, "
                  f"{v['stars_per_hour_all_workers']} stars/h on all workers")
        ing = (s.get("ingest") or {}).get("summary") or {}
        if ing:
            print(f"  ingested: {json.dumps({k: ing[k] for k in list(ing)[:6]}, default=str)[:300]}")
    print("Ledger (all nights): " + ", ".join(
        f"{q} {sum(v.values())} ({', '.join(f'{k} {n}' for k, n in sorted(v.items()))})"
        for q, v in sorted(r["ledger_totals"].items())) if r["ledger_totals"] else "Ledger: empty")
    print(f"Now: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC")
    return 0
