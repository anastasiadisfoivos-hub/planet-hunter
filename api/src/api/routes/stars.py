"""Per-star Lab: GET /stars/{tic}/lab and GET /stars/{tic}/lightcurve."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from api import lab
from api.deps import Reader, ServicesDep, SettingsDep
from api.models import MAX_TIC, LabView, LightcurveView
from api.timeutil import utcnow

router = APIRouter(tags=["per-star lab"])

Tic = Annotated[int, Path(gt=0, lt=MAX_TIC)]


@router.get("/stars/{tic_id}/lab", response_model=LabView)
async def star_lab(tic_id: Tic, _: Reader, svc: ServicesDep, cfg: SettingsDep) -> LabView:
    """Everything that exists for this star, for /lab/star/<tic>: its stored analysis (signals,
    light curve), its planets in the NASA Exoplanet Archive and its SPECTRA files. Any TIC gets an
    answer; nothing here starts an analysis (POST /analyze does)."""
    storage, now = svc.storage, utcnow()
    rec, lc = await asyncio.gather(
        asyncio.to_thread(storage.get_star_analysis, tic_id),
        asyncio.to_thread(storage.get_star_lightcurve, tic_id),
    )
    host, fresh = await asyncio.to_thread(
        lab.cached_known_planets, storage, tic_id, now, cfg.known_planets_ttl_s
    )
    note = None
    if not fresh and svc.archive is not None:
        try:
            # On a timeout the thread still finishes and caches the answer for the next visit.
            host = await asyncio.wait_for(
                asyncio.to_thread(lab.fetch_known_planets, storage, svc.archive, tic_id, now),
                cfg.archive_timeout_s,
            )
        except Exception:  # noqa: BLE001 - the lab still answers
            lab.log.warning("known planets for TIC %s unavailable", tic_id, exc_info=True)
            note = lab.NOTE_ARCHIVE_STALE if host is not None else lab.NOTE_ARCHIVE_DOWN
    spectra = svc.spectra
    await asyncio.to_thread(spectra.doc)  # may read a file or URL: off the event loop
    return lab.build(tic_id, rec, lc, host, note, spectra)


@router.get(
    "/stars/{tic_id}/lightcurve",
    response_model=LightcurveView,
    responses={404: {"description": "No light curve stored; `detail` says why"}},
)
def star_lightcurve(tic_id: Tic, _: Reader, svc: ServicesDep) -> LightcurveView:
    """The star's stored light curve: unfolded (binned to <= 3000 points, BTJD) and folded on each
    detected signal's period (<= 1000 points each)."""
    rec = svc.storage.get_star_analysis(tic_id)
    lc = svc.storage.get_star_lightcurve(tic_id)
    if lc is None or lc.status != "stored" or lc.curve is None:
        tmag = rec.analysis.star.tmag if rec is not None else None
        if tmag is None and (host := svc.storage.get_known_planets(tic_id)) is not None:
            tmag = host.star.tmag
        reason = lab.lightcurve_status(rec, lc, tmag).reason_if_not
        raise HTTPException(404, {"reason": reason, "tic_id": tic_id})
    return lab.lightcurve_view(rec, lc)
