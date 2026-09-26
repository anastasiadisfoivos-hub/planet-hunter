"""The real StarAnalyzer: pipeline/ (package `hunter`), turned into the compact Analysis we store.

The pipeline's per-signal light curve is 2000 unfolded points; we keep instead the curve folded on
each signal's period and binned to at most 1000 points, which is what a reader looks at, plus the
star's whole unfolded light curve binned to at most 3000 points (stored apart, for the Lab).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable

import numpy as np

from api.analysis import describe
from api.known_systems import NAME_OF
from api.lightcurve import bin_lightcurve
from api.models import (
    Analysis,
    Check,
    Flare,
    FoldedCurve,
    LightCurve,
    Link,
    Sector,
    Signal,
    StarInfo,
)

log = logging.getLogger(__name__)

MAX_BINS = 1000
MAX_FLARES = 50


def fold(
    time: np.ndarray, flux: np.ndarray, period: float, t0: float, max_bins: int = MAX_BINS
) -> FoldedCurve:
    """Mean flux in equal phase bins, phase in [-0.5, 0.5) with the dip at 0; empty bins dropped."""
    phase = ((time - t0) / period + 0.5) % 1.0 - 0.5
    bins = int(min(max_bins, max(50, len(time) // 10)))
    idx = np.clip(((phase + 0.5) * bins).astype(int), 0, bins - 1)
    counts = np.bincount(idx, minlength=bins)
    sums = np.bincount(idx, weights=flux, minlength=bins)
    have = counts > 0
    centres = (np.arange(bins) + 0.5) / bins - 0.5
    return FoldedCurve(
        phase=[round(float(x), 5) for x in centres[have]],
        flux=[round(float(x), 6) for x in sums[have] / counts[have]],
    )


def _star(info, name: str | None = None, extra: dict | None = None) -> StarInfo:
    return StarInfo(
        tic_id=info.tic_id,
        name=name or NAME_OF.get(info.tic_id),
        ra_deg=info.ra_deg,
        dec_deg=info.dec_deg,
        radius_rsun=info.radius_rsun,
        teff_k=info.teff_k,
        tmag=info.tmag,
        **(extra or {}),
    )


def _finite(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _tic_mass_distance(tic_id: int) -> dict:
    """TIC 8.2 mass (Msun) and distance (pc), which pipeline/'s resolve() doesn't keep.
    Cached on disk like the pipeline's own TIC answers; {} if MAST can't be reached."""
    from hunter.cache import DAY, cached_json, retry

    def query() -> dict:
        from astroquery.mast import Catalogs

        table = retry(lambda: Catalogs.query_criteria(catalog="Tic", ID=tic_id))
        if len(table) == 0:
            return {}
        row = table[0]
        return {"mass_msun": _finite(row["mass"]), "distance_pc": _finite(row["d"])}

    try:
        return cached_json("api-tic-mass-d-v1", str(tic_id), 30 * DAY, query)
    except Exception as exc:  # noqa: BLE001 - optional extras
        log.warning("TIC %s: mass/distance unavailable: %s", tic_id, exc)
        return {}


def _curve(lc) -> LightCurve:
    return bin_lightcurve(lc.time, lc.flux, [int(p["sector"]) for p in lc.products])


class PipelineAnalyzer:
    def __init__(self, max_sectors: int = 2):
        self.max_sectors = max_sectors

    def resolve(self, name: str) -> StarInfo:
        from hunter.resolve import resolve

        return _star(resolve(name), name)

    def latest_data_marker(self, tic_id: int) -> str | None:
        from hunter import latest_data_marker

        return latest_data_marker(tic_id)

    def lightcurve(self, tic_id: int) -> LightCurve:
        from hunter.fetch import fetch

        return _curve(fetch(tic_id, max_sectors=self.max_sectors))

    def analyze(self, tic_id: int, progress: Callable[[str], None]) -> Analysis:
        from hunter.core import run
        from hunter.fetch import fetch
        from hunter.resolve import resolve

        progress("looking up the star in the TESS Input Catalog")
        resolve(tic_id)
        progress("downloading TESS light curves")
        fetch(tic_id, max_sectors=self.max_sectors)  # cached on disk; run() reads it back
        progress("searching for repeating dips, vetting them and checking for flares")
        result = run(tic_id, max_sectors=self.max_sectors)
        progress("folding and summarising")

        lc, flat, keep = result.lc, result.flat, result.keep
        signals: list[Signal] = []
        flares: list[Flare] = []
        for d in result.discoveries:
            raw = d.raw
            if ":sig:" in d.id:
                n = int(d.id.rsplit(":", 1)[1])
                sig = result.signal_objs[n - 1]
                signals.append(
                    Signal(
                        id=d.id,
                        type=str(d.type),
                        confidence=d.confidence,
                        period_days=round(float(sig.period), 6),
                        t0_btjd=round(float(sig.t0), 5),
                        duration_hours=round(float(sig.duration) * 24, 3),
                        depth_ppm=round(float(sig.depth) * 1e6, 1),
                        snr=round(float(sig.snr), 1),
                        n_transits=int(sig.n_transits),
                        radius_rjup=raw.get("radius_rjup"),
                        radius_lower_rjup=raw.get("radius_lower_rjup"),
                        radius_upper_rjup=raw.get("radius_upper_rjup"),
                        known_status=d.known_status,
                        name_if_known=d.name_if_known,
                        explanation=d.explanation,
                        checks=[
                            Check(name=v["name"], passed=v.get("passed"), reason=v["reason"])
                            for v in raw.get("vetting", [])
                        ],
                        links=[Link(**link) for link in d.links],
                        folded=fold(lc.time[keep], flat[keep], float(sig.period), float(sig.t0)),
                    )
                )
            elif ":flare:" in d.id and len(flares) < MAX_FLARES:
                flares.append(
                    Flare(
                        id=d.id,
                        peak_btjd=round(float(raw["peak_btjd"]), 5),
                        peak_at=d.detected_at,
                        amplitude=round(float(raw["flare"]["amplitude"]), 6),
                        confidence=d.confidence,
                        explanation=d.explanation,
                    )
                )

        star = _star(result.star, extra=_tic_mass_distance(tic_id))
        sectors = [
            Sector(sector=p["sector"], author=p["author"], exptime=p["exptime"])
            for p in result.products
        ]
        links = [
            Link(
                label="ExoFOP-TESS target page",
                url=f"https://exofop.ipac.caltech.edu/tess/target.php?id={tic_id}",
            ),
            Link(
                label="MAST archive",
                url="https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html"
                f"?searchQuery=TIC%20{tic_id}",
            ),
        ]
        return Analysis(
            star=star,
            sectors=sectors,
            signals=signals,
            flares=flares,
            flares_found=result.flares_found,
            signals_examined=len(result.signals),
            summary=describe(star, sectors, signals, result.flares_found),
            links=links,
            lightcurve=_curve(lc),
        )
