"""Planet finder: HUNT's candidate JSON and PIXELS' PixelVet, as the API stores and serves them.

Shapes (from hunt/ and pixels/):
- Candidate (hunt/candidates/<tic>_<n>.json): {tic, period_d, t0_btjd, duration_h, depth_ppm, snr,
  sde, n_transits, sectors, radius_rjup, radius_low, radius_high,
  checks: [{name, value, passed, reason}], score, score_parts, known_lists, folded, unfolded,
  created_at}
- PixelVet: {verdict, reason, on_target_probability, centroid_offset_arcsec, offset_sigma,
  suspect_neighbours[], per_sector[], images: {out_of_transit, difference, markers}}

Always "candidate": the honesty rule (api/honesty.py) is applied to everything stored here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from api import honesty
from api.ports import CandidateRow, KnownMatch
from api.timeutil import parse

CANDIDATE_ID = re.compile(r"^(\d{1,12})_(\d{1,4})$")
REQUIRED = ("tic", "period_d", "t0_btjd", "duration_h")
PIXEL_VERDICTS = ("on target", "possible neighbour", "off target", "inconclusive")
# The fields of a candidate the list endpoint returns (the folded/unfolded curves and the checks
# are only in GET /candidates/{id}).
SUMMARY_FIELDS = (
    "tic", "period_d", "t0_btjd", "duration_h", "depth_ppm", "snr", "sde", "n_transits",
    "sectors", "radius_rjup", "radius_low", "radius_high", "known_lists",
)  # fmt: skip


class InvalidCandidate(ValueError):
    pass


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(record: dict[str, Any]) -> str:
    """Hash of the candidate without created_at, so a nightly re-run that only restamps the file
    doesn't rewrite the row."""
    body = {k: v for k, v in record.items() if k != "created_at"}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def ephemeris_key(record: dict[str, Any]) -> str:
    """What a pixel vet depends on. Rounded, so float noise in HUNT's output doesn't re-vet."""
    eph = [
        round(float(record["period_d"]), 6),
        round(float(record["t0_btjd"]), 4),
        round(float(record["duration_h"]), 3),
        sorted(int(s) for s in record.get("sectors") or []),
    ]
    return hashlib.sha256(canonical(eph).encode()).hexdigest()[:32]


def parse_candidate(candidate_id: str, record: Any) -> dict[str, Any]:
    """Check one candidate JSON against the shape above and apply the honesty rule."""
    m = CANDIDATE_ID.match(candidate_id)
    if not m:
        raise InvalidCandidate(f"{candidate_id!r} is not <tic>_<n>")
    if not isinstance(record, dict):
        raise InvalidCandidate("not a JSON object")
    missing = [k for k in REQUIRED if _num(record.get(k)) is None]
    if missing:
        raise InvalidCandidate(f"missing or non-numeric: {', '.join(missing)}")
    if int(record["tic"]) != int(m.group(1)):
        raise InvalidCandidate(f"tic {record['tic']} does not match the file name")
    if record["period_d"] <= 0 or record["duration_h"] <= 0:
        raise InvalidCandidate("period_d and duration_h must be > 0")
    if not isinstance(record.get("sectors", []), list):
        raise InvalidCandidate("sectors must be a list")
    return honesty.clean(record)


def candidate_row(candidate_id: str, record: dict[str, Any], now: datetime) -> CandidateRow:
    created = now
    if isinstance(record.get("created_at"), str):
        try:
            created = parse(record["created_at"].replace("Z", "+00:00")) or now
        except ValueError:
            pass
        if created.tzinfo is None:
            created = now
    return CandidateRow(
        id=candidate_id,
        tic=int(record["tic"]),
        record=record,
        content_hash=content_hash(record),
        ephemeris_key=ephemeris_key(record),
        score=_num(record.get("score")) or 0.0,
        radius_rjup=_num(record.get("radius_rjup")),
        period_d=float(record["period_d"]),
        created_at=created,
        updated_at=now,
    )


# Known lists ------------------------------------------------------------------------------

_NO_MATCH = {"not_on_lists", "unchecked", "no_match", "none", "clear", "not_found"}


def _entry_match(list_name: str | None, entry: Any) -> KnownMatch | None:
    if not isinstance(entry, dict):
        return KnownMatch(list_name or "known", str(entry)) if entry else None
    if entry.get("matched") is False or entry.get("match") is False:
        return None
    if str(entry.get("status", "")).lower() in _NO_MATCH:
        return None
    name = entry.get("name") or entry.get("id") or entry.get("toi") or entry.get("ctoi")
    list_name = (
        entry.get("list") or entry.get("list_name") or entry.get("catalogue") or list_name
        or "known"
    )  # fmt: skip
    note = entry.get("alias") or entry.get("note")
    return KnownMatch(str(list_name), str(name) if name is not None else None,
                      str(note) if note else None)  # fmt: skip


def known_match(known_lists: Any) -> KnownMatch | None:
    """The first TOI/CTOI/confirmed/EB match HUNT recorded in a candidate's `known_lists`.

    Accepted: a list of matches ([{list, name, ...}]; `matched: false` or `status: not_on_lists`
    entries are not matches), one hunter.known.check() result ({status: "known", list_name,
    name, alias}), or {list name: [matches]}. Empty or absent: no match.
    """
    if not known_lists:
        return None
    if isinstance(known_lists, list):
        for entry in known_lists:
            if found := _entry_match(None, entry):
                return found
        return None
    if isinstance(known_lists, dict):
        if "status" in known_lists:
            if str(known_lists["status"]).lower() != "known":
                return None
            return _entry_match(None, known_lists)
        for list_name, entries in known_lists.items():
            for entry in entries if isinstance(entries, list) else [entries]:
                if entry and (found := _entry_match(list_name, entry)):
                    return found
    return None


# Pixel vets -------------------------------------------------------------------------------


def normalize_vet(vet: Any) -> dict[str, Any]:
    """A PixelVet (dataclass, object with to_dict(), or dict) as a JSON-safe dict with every
    documented key present."""
    if hasattr(vet, "to_dict"):
        vet = vet.to_dict()
    elif is_dataclass(vet) and not isinstance(vet, type):
        vet = asdict(vet)
    if not isinstance(vet, dict):
        raise TypeError(f"PixelVet must be a dict, got {type(vet).__name__}")
    out = json.loads(json.dumps(_scrub(vet), default=_json_default, allow_nan=False))
    verdict = out.get("verdict")
    if verdict not in PIXEL_VERDICTS:
        raise ValueError(f"unknown pixel verdict {verdict!r}")
    for key in ("reason", "on_target_probability", "centroid_offset_arcsec", "offset_sigma"):
        out.setdefault(key, None)
    for key in ("suspect_neighbours", "per_sector"):
        out.setdefault(key, [])
    out.setdefault("images", {})
    return honesty.clean(out)


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "tolist"):  # numpy arrays and scalars
        return obj.tolist()
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _scrub(obj: Any) -> Any:
    """NaN/inf become null (JSON has neither)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_scrub(v) for v in obj]
    if hasattr(obj, "tolist"):
        return _scrub(obj.tolist())
    return obj


# Funnel -----------------------------------------------------------------------------------


def sweep_stages(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """[{stage, count}] from HUNT's sweep summary, in the summary's order.

    Read from `funnel` or `stages` ({stage: count} or [{stage|name, count|n}]); failing both, the
    summary's top-level integer fields. Stage names are softened here: honesty.clean() leaves
    dict keys alone, and here keys become text."""
    raw = summary.get("funnel", summary.get("stages"))
    if raw is None:
        raw = {k: v for k, v in summary.items() if isinstance(v, int) and not isinstance(v, bool)}
    stages: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        stages = [{"stage": str(k), "count": v} for k, v in raw.items()]
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                stage = item.get("stage", item.get("name"))
                count = item.get("count", item.get("n"))
                if stage is not None:
                    stages.append({"stage": str(stage), "count": count})
    return [
        {"stage": honesty.soften(s["stage"]), "count": s["count"]}
        for s in stages
        if isinstance(s["count"], int) and not isinstance(s["count"], bool)
    ]


def summary_view(row: dict[str, Any]) -> dict[str, Any]:
    """A stored candidate as one item of GET /candidates."""
    rec = row["record"]
    out = {"id": row["id"], **{k: rec.get(k) for k in SUMMARY_FIELDS}}
    out["tic"] = row["tic"]
    out.update(
        score=row["score"],
        pixel_verdict=row["pixel_verdict"],
        status=row["status"],
        status_reason=row["status_reason"],
        votes=row["votes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
    return out
