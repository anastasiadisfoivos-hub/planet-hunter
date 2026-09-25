"""Owner-only endpoints, behind `Authorization: Bearer <PH_ADMIN_TOKEN>`. With PH_ADMIN_TOKEN unset
they don't exist (404)."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from api.deps import ServicesDep, SettingsDep, rate_limited
from api.finder import CANDIDATE_ID
from api.finder_export import build_file, file_name
from api.timeutil import utcnow

router = APIRouter(prefix="/finder", tags=["admin"], include_in_schema=False)

OFF_TARGET_REASON = "Dip comes from a neighbour; not exportable"


_limit = rate_limited("admin")


def require_admin(
    request: Request,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.admin_token:
        raise HTTPException(404, "Not Found")
    _limit(request, settings)  # after the 404, so an unset token never shows as a 429
    scheme, _, token = (authorization or "").partition(" ")
    given = token.strip().encode() if scheme.lower() == "bearer" else b""
    if not hmac.compare_digest(given, settings.admin_token.encode()):
        raise HTTPException(403, "Wrong or missing admin token (Authorization: Bearer ...).")


class ExportIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)
    tag: str | None = Field(default=None, max_length=100)
    paper_url: str | None = Field(default=None, max_length=500)


@router.post(
    "/export/ctoi",
    dependencies=[Depends(require_admin)],
    response_class=PlainTextResponse,
)
def export_candidates(body: ExportIn, services: ServicesDep) -> PlainTextResponse:
    """The candidates as an ExoFOP CTOI bulk-upload file; marks them "exported". All or nothing:
    one unknown, dismissed or off-target id refuses the whole request."""
    ids = list(dict.fromkeys(body.ids))
    storage = services.storage
    rows = {i: storage.get_candidate(i) for i in ids if CANDIDATE_ID.match(i)}
    if missing := [i for i in ids if rows.get(i) is None]:
        raise HTTPException(404, {"reason": "unknown candidates", "ids": missing})
    if dismissed := [i for i in ids if rows[i]["status"] == "dismissed"]:
        raise HTTPException(409, {"reason": "dismissed candidates", "ids": dismissed})
    if off := [i for i in ids if rows[i]["pixel_verdict"] == "off target"]:
        raise HTTPException(422, {"reason": OFF_TARGET_REASON, "ids": off})
    now = utcnow()
    text = build_file([rows[i] for i in ids], now, body.tag, body.paper_url)
    storage.mark_exported(ids, now)
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": f'attachment; filename="{file_name(now)}"'},
    )
