"""Shapes from the SHARED CONTRACT. Do not change these without changing the contract."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

CatchType = Literal[
    "asteroid",
    "near_earth_object",
    "trans_neptunian_object",
    "comet",
    "interstellar_object",
    "supernova",
    "active_galaxy",
    "tidal_disruption_event",
    "microlensing",
    "kilonova",
    "variable_star",
    "flare",
    "eclipsing_binary",
    "planet_candidate",
    "unknown",
]

CATCH_TYPES: tuple[str, ...] = CatchType.__args__  # type: ignore[attr-defined]

RADIUS_MIN_DEG = 0.05
RADIUS_MAX_DEG = 10.0


class Sphere(TypedDict):
    ra_deg: float
    dec_deg: float
    radius_deg: float


def validate_sphere(sphere: Sphere) -> Sphere:
    ra, dec, r = float(sphere["ra_deg"]), float(sphere["dec_deg"]), float(sphere["radius_deg"])
    if not 0.0 <= ra < 360.0:
        raise ValueError(f"ra_deg must be in [0, 360): {ra}")
    if not -90.0 <= dec <= 90.0:
        raise ValueError(f"dec_deg must be in [-90, 90]: {dec}")
    if not RADIUS_MIN_DEG <= r <= RADIUS_MAX_DEG:
        raise ValueError(f"radius_deg must be in [{RADIUS_MIN_DEG}, {RADIUS_MAX_DEG}]: {r}")
    return {"ra_deg": ra, "dec_deg": dec, "radius_deg": r}


class Link(TypedDict):
    label: str
    url: str


class Cutouts(TypedDict):
    before: str | None  # template
    now: str | None  # science
    difference: str | None


class Discovery(TypedDict):
    id: str
    type: CatchType
    confidence: float  # 0-1, the broker's own number
    source: Literal["rubin", "tess"]
    origin: str  # which broker / pipeline produced it
    ra_deg: float
    dec_deg: float
    detected_at: str  # ISO 8601 UTC
    name_if_known: str | None
    known_status: Literal["known", "not_on_lists", "unchecked"]
    cutouts: Cutouts
    light_curve: NotRequired[list[dict[str, Any]] | None]
    explanation: str
    links: list[Link]
    raw: dict[str, Any]


class Visit(TypedDict):
    """One entry of Forecast.visits ({time, band}) plus extra context from ObsLocTAP."""

    time: str  # ISO 8601 UTC, start of exposure
    band: str | None
    status: Literal["planned", "performed", "aborted", "unknown"]
    ra_deg: float
    dec_deg: float
    obs_id: str | None
    exposure_s: float | None


class KnownSolarSystemObject(TypedDict):
    """Forecast.known_solar_system_objects entry ({name, type, ra_deg, dec_deg}) plus extras."""

    name: str
    type: CatchType
    ra_deg: float
    dec_deg: float
    number: str | None
    skybot_class: str
    v_mag: float | None
    position_error_arcsec: float | None
