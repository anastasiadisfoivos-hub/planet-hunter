"""Shared-contract data types (see the SHARED CONTRACT in the project brief).

Nothing here adds fields to the contract; pipeline-specific detail goes in ``Discovery.raw``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Literal


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


KnownStatus = Literal["known", "not_on_lists", "unchecked"]


@dataclass(frozen=True)
class StarTarget:
    tic_id: int


@dataclass
class Discovery:
    id: str
    type: CatchType
    confidence: float
    source: Literal["rubin", "tess"]
    origin: str
    ra_deg: float
    dec_deg: float
    detected_at: str
    name_if_known: str | None
    known_status: KnownStatus
    cutouts: dict[str, str | None]
    light_curve: dict[str, list[float]] | None
    explanation: str
    links: list[dict[str, str]]
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = str(self.type)
        return d


def empty_cutouts() -> dict[str, str | None]:
    return {"before": None, "now": None, "difference": None}
