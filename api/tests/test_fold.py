"""The real adapter's folded curve (no network)."""

from __future__ import annotations

import numpy as np

from api.adapters.real import MAX_BINS, fold


def test_fold_centres_the_dip_and_caps_bins():
    period, t0 = 2.5, 1000.3
    t = np.linspace(1000, 1054, 40_000)
    phase = ((t - t0) / period + 0.5) % 1 - 0.5
    flux = np.where(np.abs(phase) < 0.02, 0.99, 1.0)
    curve = fold(t, flux, period, t0)
    assert len(curve.phase) == len(curve.flux) == MAX_BINS
    assert curve.phase == sorted(curve.phase) and -0.5 < curve.phase[0] < curve.phase[-1] < 0.5
    dip = curve.flux[int(np.argmin(curve.flux))]
    assert dip == 0.99 and abs(curve.phase[int(np.argmin(curve.flux))]) < 0.02
    assert max(curve.flux) == 1.0


def test_fold_sparse_data_uses_fewer_bins_and_drops_empty_ones():
    t = np.array([0.0, 0.1, 0.2, 5.0])
    curve = fold(t, np.ones(4), 1.0, 0.0)
    assert len(curve.phase) <= 4
