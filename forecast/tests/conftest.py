from datetime import UTC, datetime

import pytest

from skyforecast import Providers, Window
from skyforecast.fakes import FakeHeatmap, FakeSchedule, FakeSkybot

TONIGHT = Window(datetime(2026, 9, 26, 0, tzinfo=UTC), datetime(2026, 9, 26, 10, tzinfo=UTC))
NOW = datetime(2026, 9, 25, 18, tzinfo=UTC)


@pytest.fixture(scope="session")
def heatmap():
    return FakeHeatmap()


@pytest.fixture(scope="session")
def skybot():
    return FakeSkybot()


@pytest.fixture
def full(heatmap, skybot):
    return Providers(schedule=FakeSchedule(), heatmap=heatmap, exposure=heatmap, skybot=skybot)
