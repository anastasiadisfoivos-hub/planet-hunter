"""Pydantic mirror of contracts/CONTRACT.md. Field names and value sets must match it exactly."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class CatchType(StrEnum):
    asteroid = "asteroid"
    near_earth_object = "near_earth_object"
    trans_neptunian_object = "trans_neptunian_object"
    comet = "comet"
    interstellar_object = "interstellar_object"
    supernova = "supernova"
    active_galaxy = "active_galaxy"
    tidal_disruption_event = "tidal_disruption_event"
    microlensing = "microlensing"
    kilonova = "kilonova"
    variable_star = "variable_star"
    flare = "flare"
    eclipsing_binary = "eclipsing_binary"
    planet_candidate = "planet_candidate"
    unknown = "unknown"


SOLAR_SYSTEM_TYPES = frozenset(
    {
        CatchType.asteroid,
        CatchType.near_earth_object,
        CatchType.trans_neptunian_object,
        CatchType.comet,
        CatchType.interstellar_object,
    }
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Sphere(_Model):
    ra_deg: float = Field(ge=0, lt=360)
    dec_deg: float = Field(ge=-90, le=90)
    radius_deg: float = Field(ge=0.05, le=10)


class StarTarget(_Model):
    tic_id: int = Field(gt=0)

    @field_validator("tic_id", mode="before")
    @classmethod
    def _int_or_digit_string(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("tic_id must be an integer")
        if isinstance(v, str):
            if not re.fullmatch(r"\d{1,12}", v.strip()):
                raise ValueError("tic_id must be an integer or a string of digits")
            return int(v.strip())
        if not isinstance(v, int):
            raise ValueError("tic_id must be an integer")
        return v


class Cutouts(_Model):
    before: str | None = None
    now: str | None = None
    difference: str | None = None


class LightCurve(_Model):
    time_btjd: list[float] = Field(max_length=2000)
    flux: list[float] = Field(max_length=2000)

    @model_validator(mode="after")
    def _same_length(self) -> LightCurve:
        if len(self.time_btjd) != len(self.flux):
            raise ValueError("time_btjd and flux must have the same length")
        return self


class Link(_Model):
    label: str
    url: str


class Discovery(_Model):
    id: str
    type: CatchType
    confidence: float = Field(ge=0, le=1)
    source: Literal["rubin", "tess"]
    origin: str
    ra_deg: float = Field(ge=0, lt=360)
    dec_deg: float = Field(ge=-90, le=90)
    detected_at: AwareDatetime
    name_if_known: str | None = None
    known_status: Literal["known", "not_on_lists", "unchecked"]
    cutouts: Cutouts
    light_curve: LightCurve | None = None
    explanation: str
    links: list[Link] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class Window(_Model):
    start: AwareDatetime
    end: AwareDatetime


class Visit(_Model):
    time: AwareDatetime
    band: str


class ExpectedCount(_Model):
    type: CatchType
    mean_count: float = Field(ge=0)


class KnownSolarSystemObject(_Model):
    name: str
    type: CatchType
    ra_deg: float = Field(ge=0, lt=360)
    dec_deg: float = Field(ge=-90, le=90)


class Forecast(_Model):
    sphere: Sphere
    window: Window
    rubin_visit_probability: float = Field(ge=0, le=1)
    visits: list[Visit]
    expected: list[ExpectedCount]
    known_solar_system_objects: list[KnownSolarSystemObject]
    generated_at: AwareDatetime
    inputs_used: list[str]


class HeatmapCell(_Model):
    pix: int = Field(ge=0)
    counts: dict[CatchType, int]


class Heatmap(_Model):
    generated_at: AwareDatetime
    grid: str = Field(pattern=r"^healpix nside=\d+$")
    cells: list[HeatmapCell]
