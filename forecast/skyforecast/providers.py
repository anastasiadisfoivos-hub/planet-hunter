"""Provider interfaces. Real implementations live elsewhere (sources/); this package only
depends on these Protocols and is tested against fakes.

Every provider is optional. A provider that is None, or that raises, is treated as
unavailable and the forecast degrades (see model.forecast).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from .contract import Window


@dataclass(frozen=True)
class Pointing:
    """One planned Rubin visit. p_exec: probability it actually happens (None -> default)."""

    time: datetime
    ra_deg: float
    dec_deg: float
    band: str
    p_exec: float | None = None


@dataclass(frozen=True)
class Exposure:
    """Rubin visits per HEALPix pixel over the period the heatmap counts cover.

    Uses the same grid string as heatmap.json. Pixels absent from `visits` had zero visits.
    """

    grid: str
    visits: dict[int, float]
    span_days: float


@dataclass(frozen=True)
class SkybotObject:
    """One row of a SkyBoT cone search. sso_class is SkyBoT's class string (e.g. 'MB>Middle',
    'NEA>Apollo', 'KBO>Classical', 'Comet'). v_mag None means unknown brightness."""

    name: str
    sso_class: str
    ra_deg: float
    dec_deg: float
    v_mag: float | None = None


@runtime_checkable
class ScheduleProvider(Protocol):
    def pointings(self, window: Window) -> list[Pointing]: ...


@runtime_checkable
class HeatmapProvider(Protocol):
    def heatmap(self) -> dict[str, Any]:
        """Returns heatmap.json as parsed JSON (shared contract shape)."""
        ...


@runtime_checkable
class ExposureProvider(Protocol):
    def exposure(self) -> Exposure: ...


@runtime_checkable
class SkybotProvider(Protocol):
    def cone(self, ra_deg: float, dec_deg: float, radius_deg: float,
             epoch: datetime) -> list[SkybotObject]: ...


@dataclass
class Providers:
    schedule: ScheduleProvider | None = None
    heatmap: HeatmapProvider | None = None
    exposure: ExposureProvider | None = None
    skybot: SkybotProvider | None = None
