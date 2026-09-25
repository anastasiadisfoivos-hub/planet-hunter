"""The per-star Lab (/lab/star/<tic>): what exists for one star, from what is stored, the NASA
Exoplanet Archive (cached per star) and the SPECTRA index. Every star gets an answer."""

from __future__ import annotations

import logging
from datetime import datetime

from api import honesty
from api.known_systems import NAME_OF
from api.models import (
    HostSystem,
    LabFolded,
    LabLightcurve,
    LabSignal,
    LabView,
    LightcurveView,
    StoredAnalysis,
    StoredLightCurve,
)
from api.ports import PlanetArchive, Storage
from api.spectra_index import SpectraIndex

log = logging.getLogger(__name__)

TOO_BRIGHT_TMAG = 4.0  # brighter than this saturates TESS: no usable light curve
NOTE_ARCHIVE_DOWN = "NASA Exoplanet Archive unavailable: known planets not checked"
NOTE_ARCHIVE_STALE = "NASA Exoplanet Archive unavailable: showing its last answer"


def fetch_known_planets(
    storage: Storage, archive: PlanetArchive, tic_id: int, now: datetime
) -> HostSystem:
    """Ask the archive and cache its answer (also an empty one)."""
    rec = HostSystem.model_validate(honesty.clean(archive.host_system(tic_id, now).model_dump()))
    storage.put_known_planets(rec)
    return rec


def cached_known_planets(
    storage: Storage, tic_id: int, now: datetime, ttl_s: float
) -> tuple[HostSystem | None, bool]:
    """(cached answer, is it fresh)."""
    rec = storage.get_known_planets(tic_id)
    return rec, rec is not None and (now - rec.fetched_at).total_seconds() < ttl_s


def lightcurve_status(
    analysis: StoredAnalysis | None, lc: StoredLightCurve | None, tmag: float | None
) -> LabLightcurve:
    if lc is not None and lc.status == "stored" and lc.curve is not None:
        return LabLightcurve(
            available=True, n_points=len(lc.curve.time_btjd), sectors=lc.curve.sectors
        )
    if tmag is not None and tmag < TOO_BRIGHT_TMAG:
        return LabLightcurve(available=False, reason_if_not="too bright for TESS (Tmag < ~4)")
    if lc is not None and lc.status == "no_data":
        return LabLightcurve(available=False, reason_if_not="no TESS data")
    # Never analyzed, or analyzed before light curves were kept (POST /analyze re-reads it).
    return LabLightcurve(available=False, reason_if_not="not analyzed yet")


def _first(*values):
    return next((v for v in values if v is not None), None)


def build(
    tic_id: int,
    analysis: StoredAnalysis | None,
    lc: StoredLightCurve | None,
    host: HostSystem | None,
    host_note: str | None,
    spectra: SpectraIndex,
) -> LabView:
    star = analysis.analysis.star if analysis is not None else None
    hs = host.star if host is not None else None
    # TIC 8.2 (stored with the analysis) first; the archive's values when not analyzed. Mass and
    # distance prefer the archive, whose mass is the one its orbits were solved with (Kepler).
    tmag = _first(star and star.tmag, hs and hs.tmag)
    return LabView(
        tic=tic_id,
        name=_first(
            star and star.name,
            NAME_OF.get(tic_id),
            host and host.host_name,
            spectra.star_name(tic_id),
        ),
        teff=_first(star and star.teff_k, hs and hs.teff_k),
        radius=_first(star and star.radius_rsun, hs and hs.radius_rsun),
        mass=_first(hs and hs.mass_msun, star and star.mass_msun),
        distance=_first(hs and hs.distance_pc, star and star.distance_pc),
        tmag=tmag,
        analyzed_at=analysis.analyzed_at if analysis is not None else None,
        lightcurve=lightcurve_status(analysis, lc, tmag),
        signals=[
            LabSignal(**s.model_dump(include=set(LabSignal.model_fields)))
            for s in (analysis.analysis.signals if analysis is not None else [])
        ],
        known_planets=host.planets if host is not None else [],
        known_planets_note=host_note,
        spectra=spectra.for_star(tic_id),
    )


def lightcurve_view(analysis: StoredAnalysis | None, lc: StoredLightCurve) -> LightcurveView:
    assert lc.curve is not None
    signals = analysis.analysis.signals if analysis is not None else []
    return LightcurveView(
        tic_id=lc.tic_id,
        data_marker=lc.data_marker,
        stored_at=lc.stored_at,
        unfolded=lc.curve,
        folded=[
            LabFolded(
                signal_id=s.id,
                type=s.type,
                period_days=s.period_days,
                t0_btjd=s.t0_btjd,
                duration_hours=s.duration_hours,
                depth_ppm=s.depth_ppm,
                phase=s.folded.phase,
                flux=s.folded.flux,
            )
            for s in signals
        ],
    )
