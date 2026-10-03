"""A simple pixel-integrated elliptical-Gaussian PSF and the two fits built on it.

The TESS PSF is not Gaussian (it has broad wings and changes shape across the camera), but both images are
fitted with the *same* model, so shape errors mostly cancel when the difference-image centroid is compared with
star positions calibrated on the out-of-transit image.  What does not cancel is covered by a systematic floor
(see analyze.SYS_FLOOR_PX).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

OVERSAMPLE = 5


@dataclass
class Shape:
    sx: float = 0.8  # pixels
    sy: float = 0.8
    theta: float = 0.0  # radians


def prf_sum(shape_hw: tuple[int, int], xs, ys, fluxes, s: Shape) -> np.ndarray:
    """Σ flux_i × pixel-integrated elliptical Gaussian (unit total flux) centred at column xs[i], row ys[i].

    Pixel centres are at integer (0-based) coordinates.
    """
    ny, nx = shape_hw
    xs = np.atleast_1d(np.asarray(xs, float))
    ys = np.atleast_1d(np.asarray(ys, float))
    fluxes = np.atleast_1d(np.asarray(fluxes, float))
    sub = (np.arange(OVERSAMPLE) + 0.5) / OVERSAMPLE - 0.5
    gx = (np.arange(nx)[:, None] + sub[None, :]).ravel()
    gy = (np.arange(ny)[:, None] + sub[None, :]).ravel()
    X = gx[None, None, :] - xs[:, None, None]  # (n, 1, nx·os)
    Y = gy[None, :, None] - ys[:, None, None]  # (n, ny·os, 1)
    c, sn = np.cos(s.theta), np.sin(s.theta)
    u = (c * X + sn * Y) / s.sx
    v = (-sn * X + c * Y) / s.sy
    g = np.exp(-0.5 * (u * u + v * v))
    g = np.tensordot(fluxes, g, axes=1) / (2 * np.pi * s.sx * s.sy) / OVERSAMPLE**2
    return g.reshape(ny, OVERSAMPLE, nx, OVERSAMPLE).sum(axis=(1, 3))


def prf(shape_hw: tuple[int, int], x0: float, y0: float, s: Shape) -> np.ndarray:
    """Pixel-integrated elliptical Gaussian of unit total flux centred at column x0, row y0."""
    return prf_sum(shape_hw, [x0], [y0], [1.0], s)


@dataclass
class SceneFit:
    dx: float  # WCS correction: true pixel position = WCS position + (dx, dy)
    dy: float
    shape: Shape
    target_flux: float  # e⁻/s, total PSF flux of the target
    background: float
    cov_dxdy: np.ndarray
    chi2_red: float


def fit_scene(image: np.ndarray, var: np.ndarray, target_xy: tuple[float, float], star_xy: np.ndarray,
              star_flux: np.ndarray) -> SceneFit:
    """Fit the out-of-transit image as F_t × (target + Σ r_i × neighbour_i) + flat background.

    r_i are catalogue flux ratios (star_flux, relative to the target).  Free: a common shift (dx, dy) of all
    catalogue positions, the PSF shape, F_t and the background (the last two solved linearly at each step).
    Tying the neighbours to the target keeps the fit well posed when a neighbour sits inside the target's PSF.
    """
    ok = np.isfinite(image) & np.isfinite(var) & (var > 0)
    w = np.where(ok, 1.0 / np.sqrt(np.where(ok, var, 1.0) + (0.02 * np.abs(np.nan_to_num(image))) ** 2), 0.0)
    img = np.nan_to_num(image)
    hw = image.shape

    def templates(p):
        dx, dy, lsx, lsy, th = p
        s = Shape(np.exp(lsx), np.exp(lsy), th)
        t = prf(hw, target_xy[0] + dx, target_xy[1] + dy, s)
        o = prf_sum(hw, star_xy[:, 0] + dx, star_xy[:, 1] + dy, star_flux, s) if len(star_flux) else np.zeros(hw)
        return s, t, o

    def solve(p):
        _, t, o = templates(p)
        A = np.stack([(t + o).ravel(), np.ones(t.size)], axis=1) * w.ravel()[:, None]
        coef, *_ = np.linalg.lstsq(A, img.ravel() * w.ravel(), rcond=None)
        return coef, A

    def resid(p):
        coef, A = solve(p)
        return A @ coef - img.ravel() * w.ravel()

    best = None
    for s0 in (0.7, 1.1):
        p0 = np.array([0.0, 0.0, np.log(s0), np.log(s0), 0.0])
        r = least_squares(resid, p0, bounds=([-1.5, -1.5, np.log(0.3), np.log(0.3), -np.pi / 2],
                                             [1.5, 1.5, np.log(3.0), np.log(3.0), np.pi / 2]), x_scale=0.1)
        if best is None or r.cost < best.cost:
            best = r
    p = best.x
    coef, _ = solve(p)
    dof = max(int(ok.sum()) - 8, 1)
    chi2_red = float(2 * best.cost / dof)
    try:
        cov = np.linalg.inv(best.jac.T @ best.jac)[:2, :2] * max(chi2_red, 1.0)
    except np.linalg.LinAlgError:
        cov = np.eye(2) * 0.25
    s, _, _ = templates(p)
    return SceneFit(float(p[0]), float(p[1]), s, float(coef[0]), float(coef[1]), cov, chi2_red)


@dataclass
class DiffFit:
    x: float
    y: float
    cov: np.ndarray  # 2×2 covariance of (x, y), pixels²
    flux: float  # total flux lost in transit, e⁻/s (PSF-integrated)
    flux_err: float
    background: float
    chi2_red: float

    @property
    def snr(self) -> float:
        return self.flux / self.flux_err if self.flux_err > 0 else 0.0


def fit_difference(diff: np.ndarray, var: np.ndarray, shape: Shape, starts: list[tuple[float, float]]) -> DiffFit:
    """Fit one point source (fixed PSF shape) + flat background to the difference image."""
    ok = np.isfinite(diff) & np.isfinite(var) & (var > 0)
    w = np.where(ok, 1.0 / np.sqrt(np.where(ok, var, 1.0)), 0.0).ravel()
    d = np.nan_to_num(diff).ravel()
    ny, nx = diff.shape

    def model(p):
        return p[2] * prf(diff.shape, p[0], p[1], shape).ravel() + p[3]

    def resid(p):
        return (model(p) - d) * w

    # Seeds: every requested start, plus the brightest smoothed difference pixel.
    seeds = [(x, y) for x, y in starts if 0 <= x <= nx - 1 and 0 <= y <= ny - 1]
    sm = np.nan_to_num(diff) / np.sqrt(np.where(ok, var, np.inf))
    iy, ix = np.unravel_index(np.argmax(sm), sm.shape)
    seeds.append((float(ix), float(iy)))
    total = float(np.nansum(np.where(ok, diff, 0.0)))
    best = None
    for x0, y0 in seeds:
        p0 = [x0, y0, max(total, 1e-3), 0.0]
        r = least_squares(resid, p0, bounds=([-2, -2, -np.inf, -np.inf], [nx + 1, ny + 1, np.inf, np.inf]))
        if best is None or r.cost < best.cost:
            best = r
    dof = max(int(ok.sum()) - 4, 1)
    chi2_red = float(2 * best.cost / dof)
    try:
        full = np.linalg.inv(best.jac.T @ best.jac) * max(chi2_red, 1.0)
    except np.linalg.LinAlgError:
        full = np.diag([1e6, 1e6, 1e12, 1e12])
    return DiffFit(float(best.x[0]), float(best.x[1]), full[:2, :2], float(best.x[2]), float(np.sqrt(full[2, 2])),
                   float(best.x[3]), chi2_red)
