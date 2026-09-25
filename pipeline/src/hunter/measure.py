"""Implied companion size from transit depth: Rp = R_star * sqrt(depth), with a 1-sigma range."""

from __future__ import annotations

import math
from dataclasses import dataclass

RSUN_IN_RJUP = 695700.0 / 71492.0  # IAU nominal solar radius / Jupiter equatorial radius
RSUN_IN_REARTH = 695700.0 / 6378.1
ASSUMED_STELLAR_RADIUS_FRAC_ERR = 0.10  # used when the TIC gives a radius but no radius error


@dataclass
class Size:
    radius_rjup: float | None
    radius_rearth: float | None
    note: str
    lower_rjup: float | None = None  # 1-sigma bounds from the stellar-radius and depth errors
    upper_rjup: float | None = None
    stellar_radius_err_rsun: float | None = None
    stellar_radius_err_assumed: bool = False


def implied_radius(depth: float, stellar_radius_rsun: float | None, depth_err: float = 0.0,
                   stellar_radius_err_rsun: float | None = None) -> Size:
    if stellar_radius_rsun is None:
        return Size(None, None, "The TESS Input Catalog has no radius for this star, so the size of the "
                                "transiting object cannot be worked out.")
    if depth <= 0:
        return Size(None, None, "The measured dip is not below the baseline, so no size can be worked out.")
    assumed = stellar_radius_err_rsun is None or not math.isfinite(stellar_radius_err_rsun)
    r_err = ASSUMED_STELLAR_RADIUS_FRAC_ERR * stellar_radius_rsun if assumed else stellar_radius_err_rsun
    depth_err = depth_err if math.isfinite(depth_err) and depth_err > 0 else 0.0
    # Rp ∝ R* · depth^½, so fractional errors add in quadrature with the depth term halved.
    frac = math.hypot(r_err / stellar_radius_rsun, 0.5 * depth_err / depth)
    r_rjup = stellar_radius_rsun * math.sqrt(depth) * RSUN_IN_RJUP
    lower, upper = r_rjup * max(1 - frac, 0.0), r_rjup * (1 + frac)
    return Size(
        r_rjup, r_rjup / RSUN_IN_RJUP * RSUN_IN_REARTH,
        f"Dip depth {depth * 100:.3f}% on a {stellar_radius_rsun:.2f} R_sun star implies about {r_rjup:.2f} "
        f"Jupiter radii ({r_rjup / RSUN_IN_RJUP * RSUN_IN_REARTH:.1f} Earth radii), likely range "
        f"{lower:.2f}-{upper:.2f}.",
        lower, upper, r_err, assumed,
    )
