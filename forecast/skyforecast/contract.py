"""Shared-contract shapes (mirrors the SHARED CONTRACT; do not change field names).

Angles are degrees (ICRS), times are timezone-aware UTC datetimes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

SPHERE_RADIUS_MIN_DEG = 0.05
SPHERE_RADIUS_MAX_DEG = 10.0


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


ALL_TYPES: tuple[CatchType, ...] = tuple(CatchType)


def _utc(t: datetime) -> datetime:
    if t.tzinfo is None:
        raise ValueError(f"datetime must be timezone-aware, got naive {t!r}")
    return t.astimezone(UTC)


def _iso(t: datetime) -> str:
    return _utc(t).isoformat().replace("+00:00", "Z")


def parse_time(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


@dataclass(frozen=True)
class Sphere:
    ra_deg: float
    dec_deg: float
    radius_deg: float

    def __post_init__(self) -> None:
        if not (SPHERE_RADIUS_MIN_DEG <= self.radius_deg <= SPHERE_RADIUS_MAX_DEG):
            raise ValueError(
                f"radius_deg must be in [{SPHERE_RADIUS_MIN_DEG}, {SPHERE_RADIUS_MAX_DEG}], "
                f"got {self.radius_deg}"
            )
        if not (-90.0 <= self.dec_deg <= 90.0):
            raise ValueError(f"dec_deg must be in [-90, 90], got {self.dec_deg}")
        object.__setattr__(self, "ra_deg", self.ra_deg % 360.0)

    def to_dict(self) -> dict[str, float]:
        return {"ra_deg": self.ra_deg, "dec_deg": self.dec_deg, "radius_deg": self.radius_deg}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Sphere:
        return cls(float(d["ra_deg"]), float(d["dec_deg"]), float(d["radius_deg"]))


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _utc(self.start))
        object.__setattr__(self, "end", _utc(self.end))
        if self.end <= self.start:
            raise ValueError("window end must be after start")

    @property
    def days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400.0

    @property
    def mid(self) -> datetime:
        return self.start + (self.end - self.start) / 2

    def contains(self, t: datetime) -> bool:
        return self.start <= t < self.end

    def to_dict(self) -> dict[str, str]:
        return {"start": _iso(self.start), "end": _iso(self.end)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Window:
        return cls(parse_time(d["start"]), parse_time(d["end"]))


@dataclass(frozen=True)
class Visit:
    time: datetime
    band: str

    def to_dict(self) -> dict[str, str]:
        return {"time": _iso(self.time), "band": self.band}


@dataclass(frozen=True)
class Expected:
    type: CatchType
    mean_count: float

    def to_dict(self) -> dict[str, Any]:
        return {"type": str(self.type), "mean_count": self.mean_count}


@dataclass(frozen=True)
class KnownSolarSystemObject:
    name: str
    type: CatchType
    ra_deg: float
    dec_deg: float

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": str(self.type), "ra_deg": self.ra_deg,
                "dec_deg": self.dec_deg}


@dataclass(frozen=True)
class Forecast:
    sphere: Sphere
    window: Window
    # None only when neither a schedule nor exposure history is available (unknowable).
    rubin_visit_probability: float | None
    visits: list[Visit]
    expected: list[Expected]
    known_solar_system_objects: list[KnownSolarSystemObject]
    generated_at: datetime
    inputs_used: list[str] = field(default_factory=list)
    # NOT part of the shared contract (never serialised): (q_i, f_i) for each overlapping
    # planned visit - execution probability and fraction of the sphere covered. Lets
    # probability.py compute exact P(at least one catch) instead of an approximation.
    coverage: tuple[tuple[float, float], ...] | None = field(default=None, compare=False,
                                                             repr=False)

    def mean_count(self, t: CatchType | str) -> float:
        t = CatchType(t)
        for e in self.expected:
            if e.type == t:
                return e.mean_count
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sphere": self.sphere.to_dict(),
            "window": self.window.to_dict(),
            "rubin_visit_probability": self.rubin_visit_probability,
            "visits": [v.to_dict() for v in self.visits],
            "expected": [e.to_dict() for e in self.expected],
            "known_solar_system_objects": [o.to_dict() for o in self.known_solar_system_objects],
            "generated_at": _iso(self.generated_at),
            "inputs_used": list(self.inputs_used),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Forecast:
        return cls(
            sphere=Sphere.from_dict(d["sphere"]),
            window=Window.from_dict(d["window"]),
            rubin_visit_probability=d["rubin_visit_probability"],
            visits=[Visit(parse_time(v["time"]), v["band"]) for v in d["visits"]],
            expected=[Expected(CatchType(e["type"]), float(e["mean_count"]))
                      for e in d["expected"]],
            known_solar_system_objects=[
                KnownSolarSystemObject(o["name"], CatchType(o["type"]), float(o["ra_deg"]),
                                       float(o["dec_deg"]))
                for o in d["known_solar_system_objects"]
            ],
            generated_at=parse_time(d["generated_at"]),
            inputs_used=list(d["inputs_used"]),
        )
