from __future__ import annotations

import base64
import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from api.contract import Discovery
from api.deps import Player, ServicesDep
from api.models import DiscoveryPage

router = APIRouter(tags=["discoveries"])


def encode_cursor(caught_at: str, discovery_id: str) -> str:
    raw = json.dumps([caught_at, discovery_id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        caught_at, discovery_id = json.loads(raw)
        if not isinstance(caught_at, str) or not isinstance(discovery_id, str):
            raise ValueError
        return caught_at, discovery_id
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid cursor.") from None


@router.get("/discoveries", response_model=DiscoveryPage)
def list_discoveries(
    pid: Player,
    svc: ServicesDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> DiscoveryPage:
    """The player's catches, most recently caught first."""
    before = decode_cursor(cursor) if cursor else None
    rows = svc.storage.list_catches(pid, limit + 1, before)
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last, caught_at = rows[-1]
        next_cursor = encode_cursor(caught_at, last.id)
    return DiscoveryPage(items=[d for d, _ in rows], next_cursor=next_cursor)


@router.get("/discoveries/{discovery_id}", response_model=Discovery)
def get_discovery(discovery_id: str, pid: Player, svc: ServicesDep) -> Discovery:
    if not svc.storage.has_catch(pid, discovery_id):
        raise HTTPException(404, "Not in your catches.")
    d = svc.storage.get_discovery(discovery_id)
    if d is None:
        raise HTTPException(404, "Not in your catches.")
    return d
