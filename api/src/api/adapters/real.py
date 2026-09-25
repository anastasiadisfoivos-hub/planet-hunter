"""The real StarAnalyzer: pipeline/ (package `hunter`), turned into the compact Analysis we store.

The pipeline's per-signal light curve is 2000 unfolded points; we keep instead the curve folded on
each signal's period and binned to at most 1000 points, which is what a reader looks at.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from api.analysis import describe
from api.known_systems import NAME_OF
from api.models import (
    Analysis,
    Check,
    Flare,
    FoldedCurve,
    Link,
    Sector,
    Signal,
    StarInfo,
)

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


def _star(info, name: str | None = None) -> StarInfo:
    return StarInfo(
        tic_id=info.tic_id,
        name=name or NAME_OF.get(info.tic_id),
        ra_deg=info.ra_deg,
        dec_deg=info.dec_deg,
        radius_rsun=info.radius_rsun,
        teff_k=info.teff_k,
        tmag=info.tmag,
    )


class PipelineAnalyzer:
    def __init__(self, max_sectors: int = 2):
        self.max_sectors = max_sectors

    def resolve(self, name: str) -> StarInfo:
        from hunter.resolve import resolve

        return _star(resolve(name), name)

    def latest_data_marker(self, tic_id: int) -> str | None:
        from hunter import latest_data_marker

        return latest_data_marker(tic_id)

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

        star = _star(result.star)
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
        )
