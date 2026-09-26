"""Planet finder (/finder on the web): candidates, their pixel check, votes, funnel, sensitivity.

No accounts: a voter is a random id the browser makes once and sends as X-Voter-Key. Only its
SHA-256 is stored. Votes are limited per IP as well (PH_RATE_VOTE_PER_MIN).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import Reader, ServicesDep, SettingsDep, Voter
from api.finder import CANDIDATE_ID, PIXEL_VERDICTS, summary_view, sweep_stages
from api.ports import CandidateQuery, CandidateSort, Vote
from api.timeutil import iso, parse, utcnow

router = APIRouter(prefix="/finder", tags=["finder"])

MAX_LIMIT = 200
STATUSES = ("new", "under review", "dismissed", "exported")
VOTER_KEY = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
CHIP = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
MAX_CHIPS = 8


def voter_hash(key: str | None, *, required: bool) -> str | None:
    if key is None:
        if required:
            raise HTTPException(400, "Send X-Voter-Key: a random id your browser keeps.")
        return None
    if not VOTER_KEY.match(key):
        raise HTTPException(422, "X-Voter-Key must be 16-128 letters, digits, '-' or '_'.")
    return hashlib.sha256(key.encode()).hexdigest()


def _list(values: list[str] | None, allowed: tuple[str, ...], what: str) -> list[str]:
    """Repeated or comma-separated; `on_target` is accepted for `on target`."""
    out = [v.strip().replace("_", " ") for raw in values or [] for v in raw.split(",") if v.strip()]
    if bad := sorted(set(out) - set(allowed)):
        raise HTTPException(422, f"Unknown {what}: {', '.join(bad)}. Known: {', '.join(allowed)}.")
    return sorted(set(out))


def encode_cursor(sort: str, value: Any, candidate_id: str) -> str:
    raw = json.dumps([sort, iso(value) if sort == "newest" else value, candidate_id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, sort: str) -> tuple[Any, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        cursor_sort, value, candidate_id = json.loads(raw)
        if cursor_sort != sort or not isinstance(candidate_id, str):
            raise ValueError
        if sort == "newest":
            value = parse(value)
            if value is None or value.tzinfo is None:
                raise ValueError
        elif isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError
        return value, candidate_id
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid cursor (or it belongs to another sort).") from None


@router.get("/candidates")
def list_candidates(
    _: Reader,
    services: ServicesDep,
    settings: SettingsDep,
    min_radius: Annotated[float | None, Query(ge=0, description="Jupiter radii")] = None,
    max_radius: Annotated[float | None, Query(ge=0, description="Jupiter radii")] = None,
    min_period: Annotated[float | None, Query(gt=0, description="days")] = None,
    max_period: Annotated[float | None, Query(gt=0, description="days")] = None,
    pixel_verdict: Annotated[
        list[str] | None,
        Query(description="on target, possible neighbour, off target, inconclusive, unvetted"),
    ] = None,
    status: Annotated[
        list[str] | None,
        Query(description="new, under review, dismissed, exported (default: all but dismissed)"),
    ] = None,
    needs_votes: Annotated[
        bool, Query(description="only open candidates with fewer than PH_FINDER_VOTES_NEEDED")
    ] = False,
    sort: CandidateSort = "score",
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> dict:
    q = CandidateQuery(
        min_radius=min_radius,
        max_radius=max_radius,
        min_period=min_period,
        max_period=max_period,
        pixel_verdicts=_list(pixel_verdict, (*PIXEL_VERDICTS, "unvetted"), "pixel_verdict"),
        statuses=_list(status, STATUSES, "status"),
        needs_votes=settings.finder_votes_needed if needs_votes else None,
        sort=sort,
        after=decode_cursor(cursor, sort) if cursor else None,
        limit=limit + 1,
    )
    rows = services.storage.query_candidates(q)
    items = [summary_view(r) for r in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        value = {"score": last["score"], "newest": last["created_at"],
                 "votes": last["votes"]["total"]}[sort]  # fmt: skip
        next_cursor = encode_cursor(sort, value, last["id"])
    return {"items": items, "next_cursor": next_cursor}


def _get(services, candidate_id: str) -> dict:
    row = services.storage.get_candidate(candidate_id) if CANDIDATE_ID.match(candidate_id) else None
    if row is None:
        raise HTTPException(404, f"No candidate {candidate_id!r}.")
    return row


@router.get("/candidates/{candidate_id}")
def get_candidate(
    candidate_id: str,
    _: Reader,
    services: ServicesDep,
    x_voter_key: Annotated[str | None, Header()] = None,
) -> dict:
    row = _get(services, candidate_id)
    storage = services.storage
    vet = storage.get_pixel_vet(candidate_id)
    key = voter_hash(x_voter_key, required=False)
    return {
        "candidate": {
            **row["record"],
            "id": row["id"],
            "tic": row["tic"],
            "score": row["score"],
            "status": row["status"],
            "status_reason": row["status_reason"],
            "vetting": row["vetting"],
            "exported_at": row["exported_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
        "pixel_vet": {**vet["record"], "vetted_at": vet["vetted_at"], "current": vet["current"]}
        if vet
        else None,
        "votes": {**row["votes"], "reasons": storage.vote_reasons(candidate_id)},
        "my_vote": storage.get_vote(candidate_id, key) if key else None,
    }


class VoteIn(BaseModel):
    vote: Vote | None  # null withdraws the sender's vote
    reason_chips: list[str] = Field(default_factory=list, max_length=MAX_CHIPS)

    @field_validator("reason_chips")
    @classmethod
    def _chips(cls, chips: list[str]) -> list[str]:
        out: list[str] = []
        for chip in chips:
            chip = chip.strip().lower()
            if not CHIP.match(chip):
                raise ValueError("a reason chip is 1-40 of a-z, 0-9, '-', '_'")
            if chip not in out:
                out.append(chip)
        return out


@router.post("/candidates/{candidate_id}/vote")
def vote(
    candidate_id: str,
    body: VoteIn,
    _: Voter,
    services: ServicesDep,
    x_voter_key: Annotated[str | None, Header()] = None,
) -> dict:
    """Cast or change a vote; `"vote": null` withdraws it (reason_chips are then ignored)."""
    key = voter_hash(x_voter_key, required=True)
    if not CANDIDATE_ID.match(candidate_id):
        raise HTTPException(404, f"No candidate {candidate_id!r}.")
    chips = body.reason_chips if body.vote is not None else []
    try:
        previous = services.storage.put_vote(candidate_id, key, body.vote, chips, utcnow())
    except KeyError:
        raise HTTPException(404, f"No candidate {candidate_id!r}.") from None
    except PermissionError:
        raise HTTPException(409, "This candidate was dismissed; votes are closed.") from None
    row = services.storage.get_candidate(candidate_id)
    return {
        "id": candidate_id,
        "vote": body.vote,
        "reason_chips": chips,
        "previous_vote": previous,
        "status": row["status"],
        "votes": row["votes"],
    }


@router.get("/funnel")
def funnel(_: Reader, services: ServicesDep) -> dict:
    """The latest sweep's stages (from HUNT's summary), then what happened in the finder."""
    storage = services.storage
    doc = storage.get_finder_doc("finder_sweep")
    counts = storage.finder_counts()
    by_status = {s: counts["status"].get(s, 0) for s in STATUSES}
    by_verdict = {v: counts["pixel_verdict"].get(v, 0) for v in PIXEL_VERDICTS}
    stages = [{**s, "source": "sweep"} for s in sweep_stages(doc[0])] if doc else []
    total = sum(by_status.values())
    stages += [
        {"stage": "candidates in the finder", "count": total, "source": "finder"},
        {"stage": "pixel checked", "count": sum(by_verdict.values()), "source": "finder"},
        {"stage": "on target", "count": by_verdict["on target"], "source": "finder"},
        {"stage": "under review", "count": by_status["under review"], "source": "finder"},
        {"stage": "exported", "count": by_status["exported"], "source": "finder"},
    ]
    return {
        "sweep_at": doc[1] if doc else None,
        "stages": stages,
        "by_status": by_status,
        "by_pixel_verdict": by_verdict,
    }


@router.get("/sensitivity")
def sensitivity(_: Reader, services: ServicesDep) -> dict:
    doc = services.storage.get_finder_doc("sensitivity")
    if doc is None:
        raise HTTPException(404, "No sensitivity map stored yet.")
    return {"updated_at": doc[1], "sensitivity": doc[0]}
