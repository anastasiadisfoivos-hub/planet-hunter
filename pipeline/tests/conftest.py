import os

import numpy as np
import pytest


def pytest_addoption(parser):
    parser.addoption("--run-network", action="store_true", help="run tests that download real TESS data")


def pytest_configure(config):
    config.addinivalue_line("markers", "network: needs internet (MAST, NASA Exoplanet Archive, ExoFOP, VizieR)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network") or os.environ.get("HUNTER_RUN_NETWORK") == "1":
        return
    skip = pytest.mark.skip(reason="network test: pass --run-network (or HUNTER_RUN_NETWORK=1)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


def make_time(n_sectors: int = 2, days: float = 27.0, cadence_min: float = 2.0, start: float = 2000.0,
              sector_gap: float = 60.0) -> tuple[np.ndarray, np.ndarray]:
    """TESS-like sampling: 2-min cadence, a ~1-day gap mid-sector, sectors separated by sector_gap days."""
    times, groups = [], []
    for s in range(n_sectors):
        t0 = start + s * (days + sector_gap)
        t = np.arange(t0, t0 + days, cadence_min / 1440)
        mid = t0 + days / 2
        t = t[np.abs(t - mid) > 0.5]
        times.append(t)
        groups.append(np.full(len(t), s + 1))
    return np.concatenate(times), np.concatenate(groups)


def box(time, period, t0, duration, depth):
    phase = (time - t0 + 0.5 * period) % period - 0.5 * period
    return np.where(np.abs(phase) < duration / 2, -depth, 0.0)


@pytest.fixture
def rng():
    return np.random.default_rng(42)
