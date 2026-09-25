"""Model constants and tunable assumptions, with sources."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .contract import CatchType

# LSSTCam field of view: 9.6 deg^2, ~3.5 deg diameter.
# Ivezic et al. 2019, ApJ 873, 111 ("LSST: From Science Drivers to Reference Design"), Sec. 2.2.
RUBIN_FOV_DEG2 = 9.6
# Footprint modelled as the equal-area circle: r = sqrt(9.6 / pi) = 1.748 deg.
RUBIN_FOV_RADIUS_DEG = math.sqrt(RUBIN_FOV_DEG2 / math.pi)

# Single-visit 5-sigma point-source depths (AB mag), Ivezic et al. 2019, Table 1.
RUBIN_SINGLE_VISIT_DEPTH = {"u": 23.9, "g": 25.0, "r": 24.7, "i": 24.0, "z": 23.3, "y": 22.1}

SOLAR_SYSTEM_TYPES = (
    CatchType.asteroid,
    CatchType.near_earth_object,
    CatchType.trans_neptunian_object,
    CatchType.comet,
    CatchType.interstellar_object,
)
GALACTIC_STRATIFIED_TYPES = (
    CatchType.microlensing,
    CatchType.variable_star,
    CatchType.flare,
    CatchType.eclipsing_binary,
    CatchType.planet_candidate,
    # Extragalactic transients: dust extinction makes their rate depend on |b| too.
    CatchType.supernova,
    CatchType.active_galaxy,
    CatchType.tidal_disruption_event,
    CatchType.kilonova,
)
# Latitude band edges (deg) for pooling the smoothing prior.
STRATUM_EDGES_DEG = (10.0, 30.0)


@dataclass(frozen=True)
class ForecastConfig:
    fov_radius_deg: float = RUBIN_FOV_RADIUS_DEG
    # Probability a planned pointing is actually executed, when the schedule doesn't say.
    default_p_exec: float = 0.8
    # Minimum smoothing-prior strength, in visit-equivalents of one pixel. The actual strength
    # is estimated from the data (empirical Bayes, rates.py); this is only a floor.
    prior_visits: float = 1.0
    # Visits per pixel assumed when no exposure history is supplied.
    assumed_visits_per_pixel: float = 1.0
    # Share of historical catches of a type that were already-known objects (removed from the
    # base rate when SkyBoT supplies the known ones explicitly, to avoid double counting).
    known_fraction: dict[CatchType, float] = field(default_factory=lambda: {
        CatchType.asteroid: 0.5,
        CatchType.near_earth_object: 0.5,
        CatchType.trans_neptunian_object: 0.5,
        CatchType.comet: 0.5,
        CatchType.interstellar_object: 0.0,
    })
    single_visit_depth: dict[str, float] = field(
        default_factory=lambda: dict(RUBIN_SINGLE_VISIT_DEPTH))
    # Points laid over the sphere for area integrals.
    grid_points: int = 4000
    # SkyBoT epochs: visits grouped into buckets of this many minutes, at most this many queries.
    skybot_bucket_minutes: float = 10.0
    skybot_max_queries: int = 24
