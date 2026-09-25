"""Owner-only endpoints, behind X-Admin-Token == PH_ADMIN_TOKEN. With PH_ADMIN_TOKEN unset they
don't exist (404)."""

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

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)


_limit = rate_limited("admin")


def require_admin(
    request: Request,
    settings: SettingsDep,
    x_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.admin_token:
        raise HTTPException(404, "Not Found")
    _limit(request, settings)  # after the 404, so an unset token never shows as a 429
    given = (x_admin_token or "").encode()
    if not hmac.compare_digest(given, settings.admin_token.encode()):
        raise HTTPException(403, "Wrong or missing X-Admin-Token.")


class ExportIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)
    tag: str | None = Field(default=None, max_length=100)
    paper_url: str | None = Field(default=None, max_length=500)


@router.post(
    "/candidates/export",
    dependencies=[Depends(require_admin)],
    response_class=PlainTextResponse,
)
def export_candidates(body: ExportIn, services: ServicesDep) -> PlainTextResponse:
    """The candidates as an ExoFOP CTOI bulk-upload file; marks them "exported"."""
    ids = list(dict.fromkeys(body.ids))
    storage = services.storage
    rows = {i: storage.get_candidate(i) for i in ids if CANDIDATE_ID.match(i)}
    if missing := [i for i in ids if rows.get(i) is None]:
        raise HTTPException(404, {"reason": "unknown candidates", "ids": missing})
    if dismissed := [i for i in ids if rows[i]["status"] == "dismissed"]:
        raise HTTPException(409, {"reason": "dismissed candidates", "ids": dismissed})
    now = utcnow()
    text = build_file([rows[i] for i in ids], now, body.tag, body.paper_url)
    storage.mark_exported(ids, now)
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": f'attachment; filename="{file_name(now)}"'},
    )
