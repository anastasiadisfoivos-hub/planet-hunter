"""skyforecast: what a planet-hunter trap is likely to catch in a time window."""

from .backtest import BacktestReport, backtest
from .config import RUBIN_FOV_DEG2, RUBIN_FOV_RADIUS_DEG, ForecastConfig
from .contract import CatchType, Expected, Forecast, KnownSolarSystemObject, Sphere, Visit, Window
from .model import forecast
from .probability import chance_of_catch, p_at_least_one
from .providers import (
    Exposure,
    ExposureProvider,
    HeatmapProvider,
    Pointing,
    Providers,
    ScheduleProvider,
    SkybotObject,
    SkybotProvider,
)

__all__ = [
    "BacktestReport", "CatchType", "Expected", "Exposure", "ExposureProvider", "Forecast",
    "ForecastConfig", "HeatmapProvider", "KnownSolarSystemObject", "Pointing", "Providers",
    "RUBIN_FOV_DEG2", "RUBIN_FOV_RADIUS_DEG", "ScheduleProvider", "SkybotObject",
    "SkybotProvider", "Sphere", "Visit", "Window", "backtest", "chance_of_catch", "forecast",
    "p_at_least_one",
]
