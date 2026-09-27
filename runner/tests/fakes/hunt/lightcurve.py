from __future__ import annotations

import os
import time
from dataclasses import dataclass

import numpy as np


@dataclass
class StarLC:
    time: np.ndarray
    flux: np.ndarray
    sector: np.ndarray
    sectors: list


def stitch(tic: int, max_sectors: int = 999) -> StarLC:
    time.sleep(float(os.environ.get("FAKE_HUNT_SLEEP", "0")))
    if tic % 7 == 0:
        raise LookupError(f"no TESS light curve for TIC {tic}")
    n = 3 if max_sectors <= 3 else 6
    t = np.concatenate([np.arange(1500 + 27 * i, 1520 + 27 * i, 2 / 1440) for i in range(n)])
    rng = np.random.default_rng(tic)
    f = 1 + 1e-3 * rng.standard_normal(len(t))
    g = np.concatenate([np.full(len(np.arange(1500 + 27 * i, 1520 + 27 * i, 2 / 1440)), 10 + i) for i in range(n)])
    return StarLC(t, f, g, list(range(10, 10 + n)))
