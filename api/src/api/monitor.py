"""The live monitor: what the sweep is searching right now, or a replay of the last run.

A star is hunt's monitor/<tic>.json (DEEPHUNT):
  {tic, tmag, teff, radius_rsun, ra, dec, sectors, observed_from, observed_to,
   lightcurve: {t, f}, detections: [{t0, duration_h, depth_ppm, period_d|null, kind, outcome,
   reason}], outcome, searched_at}
It is stored as given (honesty rule applied, NaN/inf as null); the columns the monitor counts on
are copied out of it here.

Modes of GET /monitor/now:
- "live": a run is "running" and a shard posted progress within PH_MONITOR_LIVE_TIMEOUT_S. The
  star is the run's most recently searched one (null until a shard posts a star).
- "replay": otherwise. The newest finished run that has stars (else any run with stars) is
  cycled in search order, one star per PH_MONITOR_STEP_S of server time, so every viewer sees
  the same star at the same moment.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

from api import honesty
from api.finder import _scrub
from api.ports import MonitorStar, Storage
from api.timeutil import parse

RUN_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
CANDIDATE_OUTCOME = "candidate"


class InvalidStar(ValueError):
    pass


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _time(value: Any, default: datetime) -> datetime:
    if not isinstance(value, str):
        return default
    try:
        dt = parse(value.replace("Z", "+00:00"))
    except ValueError:
        raise InvalidStar(f"searched_at {value!r} is not an ISO time") from None
    if dt is None:
        return default
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def parse_star(record: Any, now: datetime, tic: int | None = None) -> MonitorStar:
    """Check one monitor record and copy out its columns. `tic`, when given (from the file
    name), must match the record's."""
    if not isinstance(record, dict):
        raise InvalidStar("not a JSON object")
    star_tic = record.get("tic")
    if isinstance(star_tic, bool) or not isinstance(star_tic, int) or star_tic <= 0:
        raise InvalidStar("tic must be a positive integer")
    if tic is not None and star_tic != tic:
        raise InvalidStar(f"tic {star_tic} does not match the file name")
    detections = record.get("detections")
    detections = [] if detections is None else detections
    if not isinstance(detections, list) or not all(isinstance(d, dict) for d in detections):
        raise InvalidStar("detections must be a list of objects")
    sectors = record.get("sectors")
    sectors = [] if sectors is None else sectors
    if not isinstance(sectors, list):
        raise InvalidStar("sectors must be a list")
    searched_at = _time(record.get("searched_at"), now)

    rec = honesty.clean(_scrub(record))
    rec.setdefault("detections", [])
    rec["searched_at"] = searched_at.isoformat()
    candidates = sum(1 for d in detections if d.get("outcome") == CANDIDATE_OUTCOME)
    rejected: dict[str, int] = {}
    for d in rec["detections"]:
        if d.get("outcome") == CANDIDATE_OUTCOME:
            continue
        reason = str(d.get("reason") or d.get("outcome") or "unknown")[:120]
        rejected[reason] = rejected.get(reason, 0) + 1
    outcome = rec.get("outcome")
    return MonitorStar(
        tic=star_tic,
        record=rec,
        searched_at=searched_at,
        outcome=str(outcome)[:60] if outcome is not None else None,
        ra=_num(record.get("ra")),
        dec=_num(record.get("dec")),
        sectors=[int(s) for s in sectors if isinstance(s, int) and not isinstance(s, bool)],
        detections_count=len(detections),
        candidates_count=candidates,
        rejected=rejected,
    )


def _progress(run: dict[str, Any] | None) -> dict[str, int]:
    return {"done": run["done"], "total": run["total"]} if run else {"done": 0, "total": 0}


def now_view(
    storage: Storage, now: datetime, *, live_timeout_s: float, step_s: float
) -> dict[str, Any]:
    running = storage.latest_monitor_run("running")
    if running and (now - running["updated_at"]).total_seconds() <= live_timeout_s:
        return {
            "mode": "live",
            "run_id": running["run_id"],
            "run_started_at": running["started_at"],
            "progress": _progress(running),
            "star": storage.latest_monitor_star(running["run_id"]),
            "next_at": None,
        }
    run = storage.latest_monitor_run("done", with_stars=True) or storage.latest_monitor_run(
        with_stars=True
    )
    if run is None:
        return {"mode": "replay", "run_id": None, "run_started_at": None,
                "progress": _progress(None), "star": None, "next_at": None}  # fmt: skip
    slot = int(now.timestamp() // step_s)
    index = slot % run["stars"]
    return {
        "mode": "replay",
        "run_id": run["run_id"],
        "run_started_at": run["started_at"],
        "progress": _progress(run),
        "star": storage.monitor_star_at(run["run_id"], index),
        "next_at": datetime.fromtimestamp((slot + 1) * step_s, UTC),
    }
