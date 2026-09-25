"""Implied companion size from transit depth: Rp = R_star * sqrt(depth)."""

from __future__ import annotations

import math
from dataclasses import dataclass

RSUN_IN_RJUP = 695700.0 / 71492.0  # IAU nominal solar radius / Jupiter equatorial radius
RSUN_IN_REARTH = 695700.0 / 6378.1


@dataclass
class Size:
    radius_rjup: float | None
    radius_rearth: float | None
    note: str


def implied_radius(depth: float, stellar_radius_rsun: float | None) -> Size:
    if stellar_radius_rsun is None:
        return Size(None, None, "The TESS Input Catalog has no radius for this star, so the size of the "
                                "transiting object cannot be worked out.")
    if depth <= 0:
        return Size(None, None, "The measured dip is not below the baseline, so no size can be worked out.")
    r_rsun = stellar_radius_rsun * math.sqrt(depth)
    return Size(r_rsun * RSUN_IN_RJUP, r_rsun * RSUN_IN_REARTH,
                f"Dip depth {depth * 100:.3f}% on a {stellar_radius_rsun:.2f} R_sun star implies about "
                f"{r_rsun * RSUN_IN_RJUP:.2f} Jupiter radii ({r_rsun * RSUN_IN_REARTH:.1f} Earth radii).")
