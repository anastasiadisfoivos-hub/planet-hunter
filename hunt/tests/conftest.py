from pathlib import Path

import numpy as np
import pytest

from hunt.catalogs import Catalogue
from hunt.lightcurve import StarLC
from hunt.stars import Star

DATA = Path(__file__).parent / "data"
TOI_TIC, EB_TIC, QUIET_TIC = 415739607, 408512382, 175516858


def load_fixture(tic: int) -> tuple[Star, StarLC]:
    """Recorded star and light curve as recorded: native cadence for HUNT's fixtures (as the sweep searches it),
    10-min bins for the two all-sector stars (TOI-813, TOI-2180), stored binned to keep the repository small."""
    lc, meta = StarLC.load(DATA / f"{tic}.npz")
    return Star.from_row(meta["star"]), lc


@pytest.fixture(scope="session")
def catalogue() -> Catalogue:
    return Catalogue.from_json(DATA / "catalogue.json")


def make_lc(n_sectors: int = 2, days: float = 27.0, cadence_min: float = 10.0, noise: float = 5e-4,
            seed: int = 0) -> StarLC:
    """TESS-like synthetic curve: a mid-sector gap, sectors 60 days apart."""
    rng = np.random.default_rng(seed)
    times, groups = [], []
    for s in range(n_sectors):
        t0 = 3000.0 + s * (days + 60)
        t = np.arange(t0, t0 + days, cadence_min / 1440)
        t = t[np.abs(t - (t0 + days / 2)) > 0.5]
        times.append(t)
        groups.append(np.full(len(t), s + 1))
    t = np.concatenate(times)
    f = 1 + rng.normal(0, noise, len(t))
    g = np.concatenate(groups)
    products = [{"sector": s + 1, "author": "SPOC", "exptime": 600.0} for s in range(n_sectors)]
    return StarLC(t, f, np.full(len(t), noise), g, products)


def box(t, period, t0, duration, depth):
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    return np.where(np.abs(phase) < duration / 2, -depth, 0.0)


SUN_LIKE = Star(tic=1, ra=10.0, dec=-20.0, tmag=10.0, teff=5700, logg=4.44, rad=1.0, rad_err=0.05, mass=1.0,
                rho=1.0, lumclass="DWARF")
