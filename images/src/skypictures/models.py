"""SHARED EVENT CONTRACT (identical in the EVENTS brief). Do not change here alone."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

EventType = Literal[
    "supernova",
    "tidal_disruption_event",
    "kilonova",
    "nova",
    "active_galaxy_flare",
    "variable_star",
    "stellar_flare",
    "microlensing",
    "asteroid",
    "near_earth_object",
    "comet",
    "interstellar_object",
    "gamma_ray_burst",
    "neutrino",
    "gravitational_wave",
    "fireball",
    "solar_flare",
    "coronal_mass_ejection",
    "geomagnetic_storm",
    "unknown",
]

ImageKind = Literal[
    "cutout_reference", "cutout_new", "cutout_difference", "sky_context", "solar", "light_curve",
    "forecast_map",
]
IMAGE_KINDS: tuple[str, ...] = ImageKind.__args__  # type: ignore[attr-defined]
EVENT_TYPES: tuple[str, ...] = EventType.__args__  # type: ignore[attr-defined]


class SkyLocation(TypedDict):
    frame: Literal["sky"]
    ra_deg: float
    dec_deg: float
    error_deg: float


class SunLocation(TypedDict):
    frame: Literal["sun"]


class EarthLocation(TypedDict):
    frame: Literal["earth"]
    lat_deg: float
    lon_deg: float
    alt_km: float | None


Location = SkyLocation | SunLocation | EarthLocation


class Image(TypedDict):
    url: str
    thumb_url: str | None
    kind: ImageKind
    caption: str
    credit: str
    license: str
    width: int | None
    height: int | None


class Event(TypedDict):
    id: str
    type: EventType
    title: str
    summary: str
    source: str
    source_url: str
    observed_at: str
    reported_at: str
    location: Location
    confidence: float
    confidence_basis: str
    brightness_mag: float | None
    images: list[Image]
    raw: NotRequired[dict[str, Any]]
