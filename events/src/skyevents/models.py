"""Shapes from the SHARED EVENT CONTRACT (identical in the PICTURES brief). Do not change these
without changing the contract."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

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
EVENT_TYPES: tuple[str, ...] = EventType.__args__  # type: ignore[attr-defined]

ImageKind = Literal[
    "cutout_reference", "cutout_new", "cutout_difference", "sky_context", "solar", "light_curve"
]
ConfidenceBasis = Literal["official_report", "catalogue_match", "machine_guess"]


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
    kind: ImageKind
    caption: str
    credit: str
    license: str
    width: int | None
    height: int | None


class Event(TypedDict):
    id: str  # "<source>:<source's own id>", stable
    type: EventType
    title: str
    summary: str  # plain English, 1-2 sentences
    source: str
    source_url: str
    observed_at: str  # ISO 8601 UTC
    reported_at: str  # ISO 8601 UTC
    location: Location
    confidence: float  # 0-1
    confidence_basis: ConfidenceBasis
    brightness_mag: float | None
    images: list[Image]
    raw: dict[str, Any]  # small


# Filter categories (query(categories=...)). "other" holds "unknown", which fits none of the five.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "transients": (
        "supernova", "tidal_disruption_event", "kilonova", "nova", "active_galaxy_flare",
        "variable_star", "stellar_flare", "microlensing",
    ),
    "solar_system": ("asteroid", "near_earth_object", "comet", "interstellar_object"),
    "sun_space_weather": ("solar_flare", "coronal_mass_ejection", "geomagnetic_storm"),
    "earth_atmosphere": ("fireball",),
    "high_energy": ("gamma_ray_burst", "neutrino", "gravitational_wave"),
    "other": ("unknown",),
}
CATEGORY_OF: dict[str, str] = {t: c for c, ts in CATEGORIES.items() for t in ts}
