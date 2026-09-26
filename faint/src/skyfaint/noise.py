"""Noise per star: CDPP at 1 h and 2 h, and the smallest planet detectable at SNR 10.

CDPP (combined differential photometric precision), measured here, per sector and combined:
  1. flatten each sector with a 1-day running median (TGLC's calibrated flux is already detrended, this only
     removes what is left), then clip points more than 5 sigma from 1 (flares, residual junk)
  2. average the flux over every run of consecutive points spanning the window (1 h or 2 h; at TGLC's 30-min
     cadence that is 2 or 4 points, at 10 min 6 or 12), skipping runs that cross a gap
  3. CDPP = 1.4826 x MAD of those averages, in ppm
The star's CDPP combines the sectors as 1 / sqrt(mean(1 / CDPP_s^2)): the single noise level that gives the same
total transit SNR over sectors of equal length. Measuring the scatter of the window averages (not sigma / sqrt(n))
keeps the red noise in.

Smallest detectable radius at SNR 10 for P = 1, 5, 10 d:
  T      central-transit duration for the star's density: 13 h x (P / 365 d)^(1/3) x rho^(-1/3) (rho solar;
         from the TIC density, else M/R^3, else M = R for a dwarf)
  sigma(T) = CDPP_1h x (T / 1 h)^alpha, alpha = log2(CDPP_2h / CDPP_1h) (-0.5 for white noise; red noise flattens it)
  N      expected transits = days with data / P
  depth  = 10 x sigma(T) / sqrt(N)
  Rp     = R_star x sqrt(depth) x 109.1 R_earth / R_sun
This is the box-SNR used by hunt's search (depth / error on the depth); it assumes a central transit and no
limb darkening, so real small planets need a little more.

predicted_cdpp_1h(tmag) is an empirical fit (fit_noise_model) to CDPPs measured on TGLC curves of faint M dwarfs,
used to rank targets before anything is downloaded.
"""

from __future__ import annotations

import math

import numpy as np

R_SUN_IN_EARTH = 109.1
PERIODS_D = (1.0, 5.0, 10.0)
SNR_THRESHOLD = 10.0
GAP_D = 0.5

# log10(CDPP_1h / ppm) = a + b (T - 14) + c (T - 14)^2, fit by scripts/fit_noise.py on measured TGLC curves (see
# NOISE_MODEL_NOTE). Replaced after fitting; the fallback is only used until then.
NOISE_MODEL = {"a": 3.60, "b": 0.24, "c": 0.02}
NOISE_MODEL_NOTE = "placeholder"


def _robust_sigma(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if len(x) < 5:
        return float("nan")
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def _running_median(t: np.ndarray, f: np.ndarray, window_d: float) -> np.ndarray:
    out = np.empty_like(f)
    lo = np.searchsorted(t, t - window_d / 2)
    hi = np.searchsorted(t, t + window_d / 2)
    for i in range(len(t)):
        out[i] = np.median(f[lo[i]:hi[i]])
    return out


def _window_means(t: np.ndarray, f: np.ndarray, window_d: float) -> np.ndarray:
    """Mean flux of every run of consecutive points starting at each point and spanning `window_d`, skipping runs
    with a gap (> 2 cadences) inside."""
    if len(t) < 3:
        return np.array([])
    cad = float(np.median(np.diff(t)))
    n = max(1, int(round(window_d / cad)))
    if len(t) < n + 1:
        return np.array([])
    cs = np.concatenate([[0.0], np.cumsum(f)])
    means = (cs[n:] - cs[:-n]) / n
    span = t[n - 1:] - t[:len(t) - n + 1]
    ok = span <= (n - 1) * cad + 2 * cad
    return means[ok]


def sector_cdpp(t: np.ndarray, f: np.ndarray, hours: float) -> tuple[float, int]:
    """(CDPP in ppm, number of points used) for one sector."""
    order = np.argsort(t)
    t, f = t[order], f[order]
    ok = np.isfinite(f)
    t, f = t[ok], f[ok]
    if len(t) < 50:
        return float("nan"), 0
    flat = f / _running_median(t, f, 1.0)
    s = _robust_sigma(flat)
    keep = np.abs(flat - 1) < 5 * s
    t, flat = t[keep], flat[keep]
    means = []
    for seg in np.split(np.arange(len(t)), np.flatnonzero(np.diff(t) > GAP_D) + 1):
        means.append(_window_means(t[seg], flat[seg], hours / 24))
    m = np.concatenate(means) if means else np.array([])
    return _robust_sigma(m) * 1e6, int(len(t))


def cdpp(time: np.ndarray, flux: np.ndarray, sector: np.ndarray) -> dict:
    """Per-sector and combined CDPP at 1 h and 2 h (ppm)."""
    per = {}
    for s in np.unique(sector):
        m = sector == s
        c1, n = sector_cdpp(time[m], flux[m], 1.0)
        c2, _ = sector_cdpp(time[m], flux[m], 2.0)
        per[int(s)] = {"cdpp_1h_ppm": _r(c1), "cdpp_2h_ppm": _r(c2), "n_points": n}

    def combine(key: str) -> float | None:
        v = np.array([p[key] for p in per.values() if p[key] is not None], float)
        return _r(1 / math.sqrt(np.mean(1 / v**2))) if len(v) else None
    return {"cdpp_1h_ppm": combine("cdpp_1h_ppm"), "cdpp_2h_ppm": combine("cdpp_2h_ppm"), "per_sector": per}


def _r(x: float) -> float | None:
    return round(float(x), 1) if x is not None and np.isfinite(x) else None


def density(star: dict) -> tuple[float | None, str]:
    rho, rad, mass = star.get("rho"), star.get("rad"), star.get("mass")
    if rho and rho > 0:
        return float(rho), "TIC density"
    if rad and mass and rad > 0 and mass > 0:
        return mass / rad**3, "TIC mass and radius"
    if rad and rad > 0:
        return 1 / rad**2, "TIC radius with M = R assumed"
    return None, "no radius in the TIC"


def duration_h(period_d: float, rho_solar: float) -> float:
    return 13.0 * (period_d / 365.25) ** (1 / 3) * rho_solar ** (-1 / 3)


def days_with_data(time: np.ndarray, step: float = 0.5) -> float:
    return float(len(np.unique(np.floor(np.asarray(time) / step)))) * step if len(time) else 0.0


def detectable_radius(star: dict, cdpp_1h: float, cdpp_2h: float | None, days: float,
                      periods=PERIODS_D, snr: float = SNR_THRESHOLD) -> dict:
    """Smallest planet radius (R_earth) giving SNR `snr` at each period (see module docstring)."""
    rho, rho_note = density(star)
    rad = star.get("rad")
    alpha = math.log2(cdpp_2h / cdpp_1h) if cdpp_2h and cdpp_1h and cdpp_2h > 0 else -0.5
    alpha = min(max(alpha, -0.5), 0.0)
    out = {"snr_threshold": snr, "days_with_data": round(days, 1), "noise_slope_alpha": round(alpha, 3),
           "density_solar": None if rho is None else round(rho, 3), "density_from": rho_note, "by_period": {}}
    for p in periods:
        if rho is None or not rad or not cdpp_1h or days <= 0:
            out["by_period"][f"{p:g}"] = None
            continue
        t = duration_h(p, rho)
        sigma_t = cdpp_1h * (t / 1.0) ** alpha * 1e-6
        n = days / p
        depth = snr * sigma_t / math.sqrt(max(n, 1e-9))
        rp = rad * math.sqrt(depth) * R_SUN_IN_EARTH if depth < 1 else None
        out["by_period"][f"{p:g}"] = {"radius_rearth": None if rp is None else round(rp, 2),
                                      "depth_ppm": round(depth * 1e6), "duration_h": round(t, 2),
                                      "n_transits": round(n, 1)}
    return out


def predicted_cdpp_1h(tmag: float) -> float:
    x = tmag - 14.0
    m = NOISE_MODEL
    return 10 ** (m["a"] + m["b"] * x + m["c"] * x * x)


def star_noise(lc, star: dict) -> dict:
    """CDPP (1 h, 2 h) and detectable radius at P = 1, 5, 10 d for a loaded light curve (FaintLC or StarLC)."""
    c = cdpp(lc.time, lc.flux, lc.sector)
    days = days_with_data(lc.time)
    det = detectable_radius(star, c["cdpp_1h_ppm"], c["cdpp_2h_ppm"], days)
    return {"tic": star.get("tic"), "tmag": star.get("tmag"), "rad_rsun": star.get("rad"), **c,
            "predicted_cdpp_1h_ppm": _r(predicted_cdpp_1h(star["tmag"])) if star.get("tmag") else None,
            "detectable": det}
