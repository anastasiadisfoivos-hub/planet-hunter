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
  the same star at the same moment. With ?after=<tic> the client steps itself: the star after
  <tic> in search order (wrapping around; a tic not in the run gives the first star). Either
  way `next_tic` is the star after the returned one (live: null).
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
KNOWN_OUTCOME = "known"
REJECTED_OUTCOME = "rejected"


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
    known = sum(1 for d in detections if d.get("outcome") == KNOWN_OUTCOME)
    rejected_n = sum(1 for d in detections if d.get("outcome") == REJECTED_OUTCOME)
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
        known_count=known,
        rejected_count=rejected_n,
    )


SPARK_BINS = 180
FUNNEL = (  # GET /monitor/stats funnel: (key, label, the sweep summary's count)
    ("stars", "Stars searched", "stars_searched"),
    ("signals", "Repeating dips found", "signals_found"),
    ("snr", "Strong enough", "after_snr"),
    ("sde", "Stand out from other periods", "after_sde"),
    ("checks", "Passed the checks", "after_checks"),
    ("candidates", "New candidates", "candidates"),
)


def spark(f: list[Any], bins: int = SPARK_BINS) -> list[int]:
    """A row-sized trace of a whole light curve (normalised flux, sectors joined end to end):
    `bins` bins by point index, each keeping its lowest point, as round((f - 1) * 1e6) ppm.
    Non-numbers are dropped; a curve shorter than `bins` gives one bin per point."""
    v = [x for x in (_num(x) for x in f) if x is not None]
    step = len(v) / bins  # the same edges as numpy.linspace(0, len, bins + 1).astype(int)
    edges = [int(i * step) for i in range(bins)] + [len(v)]
    return [round((min(v[a:b]) - 1) * 1e6) for a, b in zip(edges, edges[1:], strict=False) if b > a]


def funnel(summary: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """The stored sweep summary's funnel as [{key, label, count}], or None without one."""
    if not isinstance(summary, dict):
        return None
    counts = summary.get("funnel") if isinstance(summary.get("funnel"), dict) else summary
    steps = [
        {"key": key, "label": label, "count": counts[name]}
        for key, label, name in FUNNEL
        if isinstance(counts.get(name), int) and not isinstance(counts.get(name), bool)
    ]
    return steps or None


def _progress(run: dict[str, Any] | None) -> dict[str, int]:
    return {"done": run["done"], "total": run["total"]} if run else {"done": 0, "total": 0}


def now_view(
    storage: Storage,
    now: datetime,
    *,
    live_timeout_s: float,
    step_s: float,
    after: int | None = None,
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
            "next_tic": None,
        }
    run = storage.latest_monitor_run("done", with_stars=True) or storage.latest_monitor_run(
        with_stars=True
    )
    if run is None:
        return {"mode": "replay", "run_id": None, "run_started_at": None,
                "progress": _progress(None), "star": None, "next_at": None,
                "next_tic": None}  # fmt: skip
    run_id = run["run_id"]
    slot = int(now.timestamp() // step_s)
    if after is None:
        star = storage.monitor_star_at(run_id, slot % run["stars"])
    else:  # the client steps through the run itself
        tic = storage.monitor_next_tic(run_id, after)
        star = storage.get_monitor_star(run_id, tic) if tic is not None else None
    next_tic = storage.monitor_next_tic(run_id, star["tic"]) if star is not None else None
    return {
        "mode": "replay",
        "run_id": run_id,
        "run_started_at": run["started_at"],
        "progress": _progress(run),
        "star": star,
        "next_at": datetime.fromtimestamp((slot + 1) * step_s, UTC),
        "next_tic": next_tic,
    }


def runner_view(storage: Storage, now: datetime, *, stale_s: float) -> dict[str, Any] | None:
    """The search server's last heartbeat for GET /monitor/now. `responding` is false once it has
    been silent longer than `stale_s`, except that an idle server which said when its next run
    starts (it runs only then) is responding until `stale_s` after that time."""
    doc = storage.get_finder_doc("monitor_heartbeat")
    if doc is None:
        return None
    record, seen = doc
    quiet_until = seen
    if record.get("state") == "idle" and isinstance(record.get("next_run_at"), str):
        try:
            next_run = parse(record["next_run_at"].replace("Z", "+00:00"))
        except ValueError:
            next_run = None
        if next_run is not None and next_run.tzinfo is not None:
            quiet_until = max(seen, next_run)
    return {
        "state": record.get("state"),
        "run_id": record.get("run_id"),
        "next_run_at": record.get("next_run_at"),
        "last_seen_at": seen,
        "responding": (now - quiet_until).total_seconds() <= stale_s,
    }
