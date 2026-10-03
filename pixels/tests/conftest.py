import json
import os
from pathlib import Path

import numpy as np
import pytest

DATA = Path(__file__).parent / "data"
CASES = json.loads((DATA / "cases.json").read_text())


def pytest_addoption(parser):
    parser.addoption("--run-network", action="store_true", help="run tests that download real TESS data")


def pytest_configure(config):
    config.addinivalue_line("markers", "network: needs internet (MAST, TESScut, Gaia archive)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network") or os.environ.get("SKYPIXELS_RUN_NETWORK") == "1":
        return
    skip = pytest.mark.skip(reason="network test: pass --run-network (or SKYPIXELS_RUN_NETWORK=1)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


def simple_wcs_header(ra: float, dec: float, crpix=(6.0, 6.0), scale_arcsec: float = 21.0,
                      rot_deg: float = 30.0) -> str:
    """A TAN WCS with TESS-like 21″ pixels, rotated; CRPIX is 1-based (FITS)."""
    from astropy.wcs import WCS

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = list(crpix)
    s = scale_arcsec / 3600
    r = np.radians(rot_deg)
    w.wcs.cd = np.array([[-s * np.cos(r), s * np.sin(r)], [s * np.sin(r), s * np.cos(r)]])
    return w.to_header_string()


@pytest.fixture
def rng():
    return np.random.default_rng(7)
