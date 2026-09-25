"""Choose fake or real adapters. Routes, storage and tests only ever see the ports."""

from __future__ import annotations

from dataclasses import dataclass

from api.ports import AlertSource, Forecaster, StarHunter, Storage
from api.settings import Settings
from api.storage.sqlite import SqliteStorage


@dataclass
class Services:
    storage: Storage
    alerts: AlertSource
    hunter: StarHunter
    forecaster: Forecaster


def build_services(settings: Settings) -> Services:
    storage = SqliteStorage(settings.db_path)
    if settings.adapters == "real":
        from api.adapters import real

        return Services(
            storage=storage,
            alerts=real.alert_source(),
            hunter=real.star_hunter(),
            forecaster=real.forecaster(),
        )
    if settings.adapters != "fake":
        raise ValueError(f"PH_ADAPTERS must be 'fake' or 'real', got {settings.adapters!r}")

    from api.fakes.forecast import FakeForecaster
    from api.fakes.rubin import FakeAlertSource
    from api.fakes.tess import FakeStarHunter

    return Services(
        storage=storage,
        alerts=FakeAlertSource(),
        hunter=FakeStarHunter(),
        forecaster=FakeForecaster(),
    )
