"""forecast(sphere, window, providers) -> Forecast.

    A        = 2*pi*(1 - cos r)                       sphere area, deg^2
    f_i      = fraction of the sphere inside pointing i's footprint (r_fov = 1.748 deg)
    q_i      = p_exec of pointing i (default 0.8)
    overlap  = separation(sphere, pointing) < r + r_fov      (exact, not from the grid)
    P_visit  = 1 - prod_{i overlapping} (1 - q_i)
    V        = sum_i q_i * f_i                        expected sphere-equivalent visits
    mu_t     = rho_t * A * V                          rho_t: smoothed rate, per deg^2 per visit

See rates.py for rho_t and solar_system.py for the known-object adjustment. Missing inputs
degrade the forecast and are reported in inputs_used as 'no:<input> - <consequence>'.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from .config import SOLAR_SYSTEM_TYPES, ForecastConfig
from .contract import ALL_TYPES, CatchType, Expected, Forecast, Sphere, Visit, Window
from .geometry import cap_area_deg2, cap_grid, fraction_within, parse_grid, pixels_of
from .providers import Exposure, Providers
from .rates import BaseRates
from .solar_system import (
    KnownObjectsResult,
    PlannedVisit,
    known_objects_scheduled,
    known_objects_unscheduled,
)


def _sig(x: float) -> float:
    return float(f"{x:.4g}")


def _try(fn):
    try:
        return fn(), None
    except Exception as e:  # noqa: BLE001 - any provider failure means "unavailable"
        return None, f"{type(e).__name__}: {e}"


def _missing(name: str, err: str | None, consequence: str) -> str:
    why = "error" if err else "not provided"
    return f"no:{name} ({why}) - {consequence}"


def _climatology_visits_per_day(exposure: Exposure, points) -> float | None:
    if exposure.span_days <= 0:
        return None
    hp = parse_grid(exposure.grid)
    pix = pixels_of(hp, points)
    return sum(exposure.visits.get(int(p), 0.0) for p in pix) / len(pix) / exposure.span_days


_RATES_CACHE: dict[tuple, BaseRates] = {}


def _build_rates(heatmap: dict, exposure: Exposure | None, cfg: ForecastConfig) -> BaseRates:
    """BaseRates, cached per heatmap version (grid + generated_at + size) and exposure."""
    key = (heatmap.get("grid"), heatmap.get("generated_at"), len(heatmap.get("cells", [])),
           None if exposure is None else (exposure.grid, exposure.span_days,
                                          len(exposure.visits), sum(exposure.visits.values())),
           cfg.prior_visits, cfg.assumed_visits_per_pixel)
    if heatmap.get("generated_at") is None or key not in _RATES_CACHE:
        rates = BaseRates.build(heatmap, exposure, cfg)
        if heatmap.get("generated_at") is None:
            return rates
        if len(_RATES_CACHE) >= 4:
            _RATES_CACHE.pop(next(iter(_RATES_CACHE)))
        _RATES_CACHE[key] = rates
    return _RATES_CACHE[key]


def forecast(sphere: Sphere | dict, window: Window | dict, providers: Providers | None = None,
             *, config: ForecastConfig | None = None, now: datetime | None = None) -> Forecast:
    sphere = sphere if isinstance(sphere, Sphere) else Sphere.from_dict(sphere)
    window = window if isinstance(window, Window) else Window.from_dict(window)
    providers = providers or Providers()
    cfg = config or ForecastConfig()
    inputs: list[str] = []

    points = cap_grid(sphere, cfg.grid_points)
    area = cap_area_deg2(sphere.radius_deg)

    # --- exposure history + heatmap -> smoothed base rates ------------------------------------
    exposure, exp_err = (None, None)
    if providers.exposure is not None:
        exposure, exp_err = _try(providers.exposure.exposure)
    rates: BaseRates | None = None
    hm_err = None
    if providers.heatmap is not None:
        heatmap, hm_err = _try(providers.heatmap.heatmap)
        if heatmap is not None:
            rates, hm_err = _try(lambda: _build_rates(heatmap, exposure, cfg))
            if rates is None and exposure is not None:
                # Bad exposure must not take the heatmap down with it.
                rates, hm_err = _try(lambda: _build_rates(heatmap, None, cfg))
                exposure, exp_err = None, "exposure incompatible with heatmap"
            if rates is not None:
                inputs.append(f"heatmap({heatmap['grid']}, generated_at="
                              f"{heatmap.get('generated_at', '?')})")
    if rates is None:
        inputs.append(_missing("heatmap", hm_err, "no base rates; only known solar-system "
                                                  "objects are forecast"))
    if exposure is not None:
        inputs.append(f"exposure(span_days={exposure.span_days:g})")
    elif rates is not None:
        inputs.append(_missing("exposure", exp_err,
                               f"heatmap counts assumed to come from "
                               f"{cfg.assumed_visits_per_pixel:g} visit(s) per pixel"))

    # --- Rubin schedule -> visit probability and expected visits ------------------------------
    pointings, sch_err = (None, None)
    if providers.schedule is not None:
        pointings, sch_err = _try(lambda: providers.schedule.pointings(window))

    planned: list[PlannedVisit] = []
    if pointings is not None:
        reach = sphere.radius_deg + cfg.fov_radius_deg
        V = 0.0
        miss = 1.0
        coverage: list[tuple[float, float]] = []
        for p in pointings:
            if not window.contains(p.time):
                continue
            # Overlap is decided exactly (circles touch); the grid only measures how much.
            if math.degrees(math.acos(max(-1.0, min(1.0, _dot(p, sphere))))) >= reach:
                continue
            f = fraction_within(points, p.ra_deg, p.dec_deg, cfg.fov_radius_deg)
            q = cfg.default_p_exec if p.p_exec is None else p.p_exec
            V += q * f
            coverage.append((q, f))
            miss *= 1.0 - q
            planned.append(PlannedVisit(p.time, p.ra_deg, p.dec_deg, p.band, q))
        planned.sort(key=lambda v: v.time)
        p_visit: float | None = 1.0 - miss
        inputs.append(f"rubin_schedule({len(planned)} of {len(pointings)} pointings overlap)")
    else:
        vpd = None
        coverage = None
        if exposure is not None:
            vpd, _ = _try(lambda: _climatology_visits_per_day(exposure, points))
        if vpd is not None:
            V = vpd * window.days
            p_visit = 1.0 - math.exp(-V)
            inputs.append(_missing("rubin_schedule", sch_err,
                                   "base rates only; visits from exposure climatology "
                                   f"({vpd:.3g}/day)"))
        else:
            V = 1.0
            p_visit = None
            inputs.append(_missing("rubin_schedule", sch_err,
                                   "base rates only; expected counts are PER SINGLE VISIT, "
                                   "not window totals; visit probability unknown"))

    # --- base expectations --------------------------------------------------------------------
    mu = {t: 0.0 for t in ALL_TYPES}
    if rates is not None:
        rho = rates.density(points)
        for t in ALL_TYPES:
            mu[t] = rho[t] * area * V

    # --- known solar-system objects -----------------------------------------------------------
    known: KnownObjectsResult | None = None
    sb_err = None
    if providers.skybot is not None:
        if planned:
            known, sb_err = _try(lambda: known_objects_scheduled(
                sphere, planned, providers.skybot, cfg, window.mid))
        else:
            p_catch = 0.0 if pointings is not None else (
                1.0 - math.exp(-V) if p_visit is not None else 1.0)
            known, sb_err = _try(lambda: known_objects_unscheduled(
                sphere, window.mid, providers.skybot, p_catch, cfg))
    if known is not None:
        inputs.append(f"skybot({len(known.objects)} known objects)")
        for t in SOLAR_SYSTEM_TYPES:
            kappa = cfg.known_fraction.get(t, 0.0)
            mu[t] = known.expected.get(t, 0.0) + (1.0 - kappa) * mu[t]
    else:
        inputs.append(_missing("skybot", sb_err, "no known-object list; asteroid-family "
                                                 "expectations are base rates only"))

    return Forecast(
        sphere=sphere,
        window=window,
        rubin_visit_probability=None if p_visit is None else _sig(p_visit),
        visits=[Visit(v.time, v.band) for v in planned],
        expected=[Expected(CatchType(t), _sig(mu[t])) for t in ALL_TYPES],
        known_solar_system_objects=known.objects if known else [],
        generated_at=(now or datetime.now(UTC)),
        inputs_used=inputs,
        coverage=None if coverage is None else tuple(coverage),
    )


def _dot(p, sphere: Sphere) -> float:
    r1, d1, r2, d2 = map(math.radians, (p.ra_deg, p.dec_deg, sphere.ra_deg, sphere.dec_deg))
    return math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
