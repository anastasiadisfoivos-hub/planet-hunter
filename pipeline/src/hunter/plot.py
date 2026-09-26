"""Phase-folded light-curve PNGs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .search import Signal  # noqa: E402


def plot_folded(time: np.ndarray, flux: np.ndarray, sig: Signal, path: Path, title: str) -> Path:
    phase_days = (time - sig.t0 + 0.5 * sig.period) % sig.period - 0.5 * sig.period
    hours = phase_days * 24
    window = np.abs(phase_days) < max(3 * sig.duration, 0.1 * sig.period)
    x, y = hours[window], flux[window]
    order = np.argsort(x)
    x, y = x[order], y[order]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5), gridspec_kw={"width_ratios": [2, 1]})
    ax1.plot(x, y, ".", ms=1.5, color="0.6", alpha=0.5, label="TESS data")
    if len(x) > 20:
        edges = np.linspace(x.min(), x.max(), 80)
        idx = np.digitize(x, edges)
        bx = [x[idx == i].mean() for i in range(1, len(edges)) if np.any(idx == i)]
        by = [np.median(y[idx == i]) for i in range(1, len(edges)) if np.any(idx == i)]
        ax1.plot(bx, by, "o", ms=3.5, color="C0", label="binned")
    half = sig.duration * 12
    ax1.plot([x.min(), -half, -half, half, half, x.max()], [1, 1, 1 - sig.depth, 1 - sig.depth, 1, 1],
             color="C3", lw=1.2, label="box model")
    ax1.set_xlabel("Hours from mid-transit")
    ax1.set_ylabel("Relative brightness")
    ax1.set_title(title, fontsize=10)
    ax1.legend(loc="lower right", fontsize=8)

    full_phase = ((time - sig.t0) / sig.period + 0.25) % 1.0 - 0.25
    ax2.plot(full_phase, flux, ".", ms=1, color="0.6", alpha=0.4)
    ax2.axvline(0.5, color="C1", ls=":", lw=1)
    ax2.set_xlabel("Orbital phase (0 = main dip, 0.5 = halfway)")
    ax2.set_title(f"Full orbit, P = {sig.period:.5f} d", fontsize=10)
    lo, hi = np.percentile(flux, [0.5, 99.9])
    ax2.set_ylim(min(lo, 1 - 1.3 * sig.depth), hi + 0.2 * (hi - lo))
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_raw(time: np.ndarray, flux: np.ndarray, path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(time, flux, ".", ms=1, color="0.5")
    ax.set_xlabel("Time (BTJD)")
    ax.set_ylabel("Relative brightness")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
