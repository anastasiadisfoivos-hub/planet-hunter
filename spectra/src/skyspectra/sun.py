"""sun_spectrum.json: the real Sun, from the Kitt Peak Solar Flux Atlas 2005 (Kurucz).

The atlas is residual flux (continuum = 1) every 0.0005 nm from 300 to 1000 nm, air wavelengths,
solar laboratory frame. We average it into bins (<= 5,000 points over 380-750 nm) and label the
classic Fraunhofer lines. Each label's wavelength is the laboratory (NIST, air) value; a label is
only kept if the full-resolution atlas really has an absorption line there (checked, see
`find_line`), and the measured depth is reported with it.
"""

from __future__ import annotations

import math

from . import sources
from .net import DAY, Net

ATLAS_URL = "http://kurucz.harvard.edu/sun/fluxatlas2005/solarfluxintwl.asc"
LOW_NM, HIGH_NM = 380.0, 750.0
BIN_NM = 0.075  # -> 4,934 points over 380-750 nm
MAX_POINTS = 5000

# (air nm, element, label). Laboratory wavelengths from NIST ASD; Fraunhofer letters after
# Fraunhofer (1817). The G band is mostly CH molecule, with the Fe I line at its core.
FRAUNHOFER: list[tuple[float, str, str]] = [
    (393.366, "Ca", "K (Ca II)"),
    (396.847, "Ca", "H (Ca II)"),
    (410.174, "H", "h, H-delta"),
    (422.673, "Ca", "g (Ca I)"),
    (430.790, "Fe", "G band (CH, Fe I)"),
    (434.047, "H", "G', H-gamma"),
    (438.355, "Fe", "d (Fe I)"),
    (486.135, "H", "F, H-beta"),
    (495.761, "Fe", "c (Fe I)"),
    (516.733, "Mg", "b4 (Mg I)"),
    (517.268, "Mg", "b2 (Mg I)"),
    (518.362, "Mg", "b1 (Mg I)"),
    (527.039, "Fe", "E2 (Fe I)"),
    (588.995, "Na", "D2 (Na I)"),
    (589.592, "Na", "D1 (Na I)"),
    (656.281, "H", "C, H-alpha"),
    (686.719, "O", "B (telluric O2)"),
]
MAX_OFFSET_NM = 0.04  # the atlas minimum must sit this close to the lab wavelength
MAX_DEPTH_FLUX = 0.85  # ... and be at least 15% deep


def parse_atlas(text: str, low: float = 0.0, high: float = math.inf) -> tuple[list[float], list[float]]:
    """'  300.0000  0.3595' rows after a free-text header -> (nm, residual flux) in [low, high]."""
    wl: list[float] = []
    fx: list[float] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            w, f = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        if low <= w <= high:
            wl.append(w)
            fx.append(f)
    if not wl:
        raise ValueError("no atlas data in range")
    return wl, fx


def bin_mean(wl: list[float], fx: list[float], low: float, high: float, width: float) -> tuple[list, list]:
    n = round((high - low) / width)
    sums = [0.0] * n
    counts = [0] * n
    for w, f in zip(wl, fx):
        i = int((w - low) / width)
        if 0 <= i < n:
            sums[i] += f
            counts[i] += 1
    out_w, out_f = [], []
    for i in range(n):
        if counts[i]:
            out_w.append(round(low + (i + 0.5) * width, 4))
            out_f.append(round(sums[i] / counts[i], 4))
    return out_w, out_f


def find_line(wl: list[float], fx: list[float], nm: float) -> tuple[float, float] | None:
    """(wavelength, flux) of the deepest atlas point within MAX_OFFSET_NM of nm, if deep enough."""
    best = None
    for w, f in zip(wl, fx):
        if abs(w - nm) <= MAX_OFFSET_NM and (best is None or f < best[1]):
            best = (w, f)
    if best is None or best[1] > MAX_DEPTH_FLUX:
        return None
    return best


def build_sun(net: Net, low: float = LOW_NM, high: float = HIGH_NM, width: float = BIN_NM) -> dict:
    text = net.text(ATLAS_URL, ttl=365 * DAY)
    wl, fx = parse_atlas(text, low, high)
    bw, bf = bin_mean(wl, fx, low, high, width)
    if len(bw) > MAX_POINTS:
        raise ValueError(f"{len(bw)} points > {MAX_POINTS}")
    lines = []
    for nm, element, label in FRAUNHOFER:
        if not low <= nm <= high:
            continue
        hit = find_line(wl, fx, nm)
        if hit is None:
            continue
        lines.append({"nm": nm, "element": element, "label": label,
                      "atlas_min_nm": round(hit[0], 4), "atlas_min_flux": round(hit[1], 4),
                      "telluric": "telluric" in label})
    return {
        "wavelength_nm": bw,
        "flux": bf,
        "lines": lines,
        **sources.meta("kurucz"),
        "flux_kind": "residual flux: continuum-normalised (1.0 = continuum), disk-integrated sunlight",
        "wavelength_medium": "air, solar laboratory frame (gravitational redshift removed)",
        "binning": f"mean of the 0.0005 nm atlas samples in {width} nm bins",
        "line_wavelengths": "laboratory air wavelengths (NIST ASD); atlas_min_* is the measured line core",
    }
