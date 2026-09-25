"""Base rates (per deg^2 per visit) from heatmap.json, with empirical-Bayes Gamma-Poisson
smoothing (Clayton & Kaldor 1987).

For pixel c and type t with n_ct catches and exposure E_c = visits_c * pixel_area (deg^2 visits):

    prior      lambda_ct ~ Gamma(alpha, beta)      mean m = alpha/beta, variance v = alpha/beta^2
    posterior  lambda_hat_ct = (n_ct + beta * m) / (E_c + beta)

m and v are estimated per type per stratum s (ecliptic-latitude bands |beta_ecl| 0-10-30-90 for
solar-system types, galactic-latitude bands for galactic and extragalactic types, all-sky for
'unknown') by the method of moments over exposed pixels:

    m = sum(n) / sum(E)
    v = sum_c w_c (n_c/E_c - m)^2  -  m * K / sum(E)      (w_c = E_c / sum(E), K pixels)

i.e. the scatter of observed rates minus the part Poisson noise explains. beta = m / v, floored
at prior_visits * pixel_area (always some smoothing) and capped at 1e4 visits * pixel_area when
v <= 0 (rates indistinguishable: pool fully). Rare types therefore borrow strength heavily;
well-measured, genuinely varying ones follow their own pixel. An empty pixel forecasts its
stratum mean, never zero. A type never seen anywhere gets m = 0.5 / total exposure.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from astropy_healpix import HEALPix

from .config import (
    GALACTIC_STRATIFIED_TYPES,
    SOLAR_SYSTEM_TYPES,
    STRATUM_EDGES_DEG,
    ForecastConfig,
)
from .contract import ALL_TYPES, CatchType
from .geometry import (
    ecliptic_latitude,
    galactic_latitude,
    parse_grid,
    pixel_area_deg2,
    pixel_centres,
    pixels_of,
)
from .providers import Exposure


def _stratum(abs_lat: np.ndarray) -> np.ndarray:
    return np.digitize(abs_lat, STRATUM_EDGES_DEG)


def _moments(n: np.ndarray, E: np.ndarray, fallback: float, beta_min: float,
             beta_max: float) -> tuple[float, float]:
    """Method-of-moments Gamma prior (mean, beta) for one stratum."""
    exposed = E > 0
    Et, nt = E[exposed].sum(), n[exposed].sum()
    if Et <= 0 or nt <= 0:
        return fallback, beta_max
    m = nt / Et
    w = E[exposed] / Et
    scatter = float(np.sum(w * (n[exposed] / E[exposed] - m) ** 2))
    v = scatter - m * exposed.sum() / Et
    beta = m / v if v > 0 else beta_max
    return m, float(np.clip(beta, beta_min, beta_max))


@lru_cache(maxsize=8)
def _strata(nside: int, order: str) -> dict[str, np.ndarray]:
    hp = HEALPix(nside=nside, order=order)
    lon, lat = pixel_centres(hp)
    return {
        "ecl": _stratum(np.abs(ecliptic_latitude(lon, lat))),
        "gal": _stratum(np.abs(galactic_latitude(lon, lat))),
        "all": np.zeros(hp.npix, dtype=int),
    }


@dataclass
class BaseRates:
    hp: HEALPix
    pixel_area: float
    rates: dict[CatchType, np.ndarray]  # per pixel, per deg^2 per visit
    visits: np.ndarray                  # per pixel, over span_days (or assumed)
    span_days: float | None             # None when exposure is assumed, not measured

    @classmethod
    def build(cls, heatmap: dict, exposure: Exposure | None,
              cfg: ForecastConfig) -> BaseRates:
        hp = parse_grid(heatmap["grid"])
        area = pixel_area_deg2(hp)
        counts = {t: np.zeros(hp.npix) for t in ALL_TYPES}
        by_name = {str(t): counts[t] for t in ALL_TYPES}
        for cell in heatmap.get("cells", []):
            pix = int(cell["pix"])
            for key, n in (cell.get("counts") or {}).items():
                arr = by_name.get(key)
                if arr is not None:  # unknown key: ignore rather than fail the forecast
                    arr[pix] += float(n)

        if exposure is not None:
            if parse_grid(exposure.grid).nside != hp.nside:
                raise ValueError("exposure grid does not match heatmap grid")
            visits = np.zeros(hp.npix)
            for pix, v in exposure.visits.items():
                visits[int(pix)] = float(v)
            span_days: float | None = exposure.span_days
        else:
            visits = np.full(hp.npix, cfg.assumed_visits_per_pixel)
            span_days = None

        strata = _strata(hp.nside, hp.order)
        E = visits * area
        beta_min = cfg.prior_visits * area
        beta_max = 1e4 * area
        total_E = E.sum()

        rates: dict[CatchType, np.ndarray] = {}
        for t in ALL_TYPES:
            s = strata["ecl"] if t in SOLAR_SYSTEM_TYPES else (
                strata["gal"] if t in GALACTIC_STRATIFIED_TYPES else strata["all"])
            n = counts[t]
            floor = 0.5 / total_E if total_E > 0 else 0.0
            global_rate = n.sum() / total_E if total_E > 0 and n.sum() > 0 else floor
            m_pix = np.empty(hp.npix)
            b_pix = np.empty(hp.npix)
            for k in np.unique(s):
                sel = s == k
                m, beta = _moments(n[sel], E[sel], global_rate, beta_min, beta_max)
                m_pix[sel], b_pix[sel] = m, beta
            rates[t] = (n + b_pix * m_pix) / (E + b_pix)
        return cls(hp=hp, pixel_area=area, rates=rates, visits=visits, span_days=span_days)

    def density(self, points: np.ndarray) -> dict[CatchType, float]:
        """Area-weighted mean rate over the grid points (per deg^2 per visit)."""
        pix = pixels_of(self.hp, points)
        return {t: float(r[pix].mean()) for t, r in self.rates.items()}

    def visits_per_day(self, points: np.ndarray) -> float | None:
        """Climatological Rubin visits per day at these points (None if exposure unmeasured)."""
        if not self.span_days:
            return None
        pix = pixels_of(self.hp, points)
        return float(self.visits[pix].mean() / self.span_days)
