"""Turn one sector of pixels into the two images difference imaging needs.

For every transit that has in-transit frames and out-of-transit frames on *both* sides, the local difference
image is  ½(mean before + mean after) − mean in-transit.  Averaging the two sides cancels any linear drift in
the pixels (pointing, scattered light) across the transit.  The sector's difference image is the mean of the
per-transit images; a positive pixel lost light during the transit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# lightkurve's TessQualityFlags.DEFAULT_BITMASK (attitude tweak, safe mode, coarse/earth point, desat,
# manual exclude, impulsive outlier, scattered light, ...), copied to avoid importing lightkurve here.
DEFAULT_BITMASK = 1 | 2 | 4 | 8 | 32 | 128 | 1024 | 2048 | 4096 | 16384 | 65536 | 131072
IN_FRAC = 0.4  # in-transit frames: |t - tc| < 0.4 D (the flat-ish bottom of the transit)
OOT_INNER = 0.75  # out-of-transit windows start 0.75 D from mid-transit ...
OOT_WIDTH_MIN_D = 0.05  # ... and are max(D, 1.2 h) wide on each side


@dataclass
class SectorImages:
    sector: int
    kind: str
    oot: np.ndarray  # median out-of-transit image, e⁻/s
    diff: np.ndarray  # mean (out-of-transit − in-transit), e⁻/s
    diff_var: np.ndarray  # variance of diff per pixel
    frame_var: np.ndarray  # single-frame variance per pixel (white noise)
    wcs_header: str
    epoch_btjd: float  # mean time of the frames used
    n_transits: int
    n_in: int
    n_out: int
    aperture: np.ndarray | None = None
    notes: list[str] = field(default_factory=list)

    def wcs(self):
        from astropy.io import fits
        from astropy.wcs import WCS

        return WCS(fits.Header.fromstring(self.wcs_header))

    # --- (de)serialisation for the offline test fixtures -----------------------------------------------
    def to_npz(self, path) -> None:
        np.savez_compressed(
            path, sector=self.sector, kind=self.kind, oot=self.oot, diff=self.diff, diff_var=self.diff_var,
            frame_var=self.frame_var, wcs_header=self.wcs_header, epoch_btjd=self.epoch_btjd,
            n_transits=self.n_transits, n_in=self.n_in, n_out=self.n_out,
            aperture=self.aperture if self.aperture is not None else np.zeros((0, 0), bool),
            notes=np.array(self.notes, dtype=str),
        )

    @classmethod
    def from_npz(cls, path) -> "SectorImages":
        d = np.load(path, allow_pickle=False)
        ap = d["aperture"]
        return cls(int(d["sector"]), str(d["kind"]), d["oot"], d["diff"], d["diff_var"], d["frame_var"],
                   str(d["wcs_header"]), float(d["epoch_btjd"]), int(d["n_transits"]), int(d["n_in"]),
                   int(d["n_out"]), ap if ap.size else None, [str(n) for n in d["notes"]])


def _good_frames(time: np.ndarray, flux: np.ndarray, quality: np.ndarray) -> np.ndarray:
    finite = np.isfinite(time) & (np.isfinite(flux).sum(axis=(1, 2)) > 0.5 * flux[0].size)
    return finite & ((quality & DEFAULT_BITMASK) == 0)


def frame_noise(cube: np.ndarray) -> np.ndarray:
    """Per-pixel single-frame white noise: robust σ of successive-frame differences / √2."""
    d = np.diff(cube, axis=0)
    mad = np.nanmedian(np.abs(d - np.nanmedian(d, axis=0)), axis=0)
    return (1.4826 * mad / np.sqrt(2.0)) ** 2


def make_images(sector: int, kind: str, time: np.ndarray, flux: np.ndarray, quality: np.ndarray, wcs_header: str,
                period_d: float, t0_btjd: float, duration_d: float,
                aperture: np.ndarray | None = None) -> SectorImages | None:
    """Out-of-transit and difference images for one sector; None if no transit has usable frames."""
    good = _good_frames(time, flux, quality)
    t, cube = time[good], flux[good].astype(float)
    notes: list[str] = []
    if len(t) < 50:
        return None

    phase = (t - t0_btjd + 0.5 * period_d) % period_d - 0.5 * period_d  # days from nearest mid-transit
    epoch = np.round((t - t0_btjd) / period_d).astype(int)
    frame_var = frame_noise(cube[np.abs(phase) > duration_d])

    outer = OOT_INNER * duration_d + max(duration_d, OOT_WIDTH_MIN_D)
    outer = min(outer, 0.5 * period_d)
    inner = OOT_INNER * duration_d
    if outer <= inner:
        return None

    diffs, variances, used_times = [], [], []
    n_in_total = n_out_total = 0
    for e in np.unique(epoch):
        sel = epoch == e
        ph = phase[sel]
        c = cube[sel]
        it = np.abs(ph) < IN_FRAC * duration_d
        before = (ph <= -inner) & (ph >= -outer)
        after = (ph >= inner) & (ph <= outer)
        if it.sum() < 1 or before.sum() < 1 or after.sum() < 1:
            continue
        m_it = np.nanmean(c[it], axis=0)
        m_b = np.nanmean(c[before], axis=0)
        m_a = np.nanmean(c[after], axis=0)
        diffs.append(0.5 * (m_b + m_a) - m_it)
        variances.append(frame_var * (1.0 / it.sum() + 0.25 / before.sum() + 0.25 / after.sum()))
        used_times.append(t[sel][it | before | after])
        n_in_total += int(it.sum())
        n_out_total += int(before.sum() + after.sum())

    if not diffs:
        return None
    k = len(diffs)
    stack = np.array(diffs)
    diff = np.nanmean(stack, axis=0)
    diff_var = np.nansum(np.array(variances), axis=0) / k**2
    if k >= 6:
        # Transit-to-transit scatter also contains red noise (jitter, momentum dumps); trust it when it is larger.
        emp = np.nanvar(stack, axis=0, ddof=1) / k
        ratio = np.nanmedian(emp / diff_var)
        if ratio > 1.0:
            diff_var = diff_var * ratio
            notes.append(f"difference-image noise scaled ×{np.sqrt(ratio):.2f} to match transit-to-transit scatter")

    oot = np.nanmedian(cube[np.abs(phase) > duration_d], axis=0)
    return SectorImages(
        sector=sector, kind=kind, oot=oot, diff=diff, diff_var=diff_var, frame_var=frame_var,
        wcs_header=wcs_header, epoch_btjd=float(np.mean(np.concatenate(used_times))), n_transits=k,
        n_in=n_in_total, n_out=n_out_total, aperture=aperture, notes=notes,
    )
