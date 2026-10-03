"""Difference-image centroid analysis: where on the sky did the light go missing?

Per sector
  1. Put the target and every Gaia DR3 star on the pixel grid (proper motion propagated to the sector epoch,
     sector WCS), then fit the out-of-transit image with that scene to correct the WCS by a small shift and
     learn the PSF shape.
  2. Fit one PSF to the difference image → centroid (x, y) with covariance, and ΔF, the flux lost in transit.
  3. Offset = centroid − calibrated target position, converted to (east, north) arcsec.
Across sectors
  4. Inverse-covariance-weighted mean offset; offset_sigma = √(oᵀ C⁻¹ o) (Mahalanobis distance).
  5. Each neighbour: the eclipse depth it would need, depth_on_target × 10^(0.4 (T_nb − T_target)), and whether
     the centroid excludes it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .catalog import GAIA_EPOCH, btjd_to_jyear, propagate, sky_offset_arcsec
from .psf import DiffFit, SceneFit, fit_difference, fit_scene
from .reduce import SectorImages

DETECT_SNR = 5.0  # difference-image PSF fit must see the dip at ≥ 5σ in a sector to use its centroid
SECTOR_FLOOR_PX = 0.05  # per-sector systematic centroid error (PSF-model mismatch, jitter), per axis
PROB_FLOOR_PX = 0.10  # extra floor used only by the probability heuristic, so 0.3 px ≈ 3σ
OFF_TARGET_SIGMA = 3.0
OFF_TARGET_MIN_PX = 0.3
NEIGHBOUR_RADIUS_ARCSEC = 150.0  # "every Gaia DR3 neighbour within ~2.5′"
SCENE_DMAG = 5.0  # stars up to 5 mag fainter than the target (≥1% of its flux) are modelled in the scene fit
SCENE_MAX_STARS = 60  # ... the brightest 60 of them; fainter ones blend into the fitted background
W_NEIGHBOUR_EASY = 0.25  # prior weight for a neighbour that needs ≤ 50% eclipse depth
W_NEIGHBOUR_HARD = 0.05  # ... that needs 50–100%
W_TARGET = 1.0
W_ELSEWHERE = 1.0  # an uncatalogued source / systematics, with a fixed likelihood of exp(-4.5) (a 3σ miss)
HEURISTIC = (
    "P(on target) = L_t / (L_t + Σ_i w_i·L_i + e^(-4.5)),  L = exp(-½ d²),  d = Mahalanobis distance of the "
    "combined difference-image centroid from that star, using the combined covariance plus a (0.1 px)² floor; "
    "i runs over Gaia neighbours able to make the dip (needed depth ≤ 100%) with w_i = 0.25 (needed ≤ 50%) or "
    "0.05 (50–100%); the e^(-4.5) term is 'somewhere else' (uncatalogued source or systematics). A centroid "
    "exactly on the target gives ≈ 0.99; 3σ off with no neighbour gives ≈ 0.5."
)


@dataclass
class Star:
    gaia_id: str | None
    ra_deg: float  # epoch 2016.0
    dec_deg: float
    pmra_masyr: float | None
    pmdec_masyr: float | None
    gmag: float | None
    tmag: float

    def at(self, jyear: float) -> tuple[float, float]:
        return propagate(self.ra_deg, self.dec_deg, self.pmra_masyr, self.pmdec_masyr, GAIA_EPOCH, jyear)


@dataclass
class SectorResult:
    images: SectorImages
    detected: bool
    target_xy: tuple[float, float]  # calibrated pixel position of the target
    star_xy: np.ndarray  # calibrated pixel positions of the neighbours ...
    star_ids: list  # ... and their Gaia ids
    scene: SceneFit | None
    diff: DiffFit | None
    offset_en: np.ndarray | None  # (east, north) arcsec, centroid − target
    cov_en: np.ndarray | None
    jac: np.ndarray  # (east, north) arcsec per (x, y) pixel
    depth: float | None
    depth_err: float | None
    reason: str

    @property
    def pixel_scale(self) -> float:
        return float(math.sqrt(abs(np.linalg.det(self.jac))))

    def to_dict(self) -> dict:
        img = self.images
        d = {
            "sector": img.sector,
            "kind": img.kind,
            "n_transits": img.n_transits,
            "n_in_transit_frames": img.n_in,
            "n_out_of_transit_frames": img.n_out,
            "detected": self.detected,
            "reason": self.reason,
            "diff_snr": _r(self.diff.snr, 2) if self.diff else None,
            "depth_on_target": _r(self.depth, 6),
            "depth_on_target_err": _r(self.depth_err, 6),
            "target_px": [_r(self.target_xy[0], 3), _r(self.target_xy[1], 3)],
            "centroid_px": [_r(self.diff.x, 3), _r(self.diff.y, 3)] if self.diff else None,
            "centroid_offset_arcsec": _r(float(np.hypot(*self.offset_en)), 2) if self.offset_en is not None else None,
            "offset_east_north_arcsec": [_r(v, 2) for v in self.offset_en] if self.offset_en is not None else None,
            "offset_sigma": _r(_mahal(self.offset_en, self.cov_en), 2) if self.offset_en is not None else None,
            "pixel_scale_arcsec": _r(self.pixel_scale, 3),
            "wcs_shift_px": [_r(self.scene.dx, 3), _r(self.scene.dy, 3)] if self.scene else None,
            "psf_sigma_px": [_r(self.scene.shape.sx, 3), _r(self.scene.shape.sy, 3)] if self.scene else None,
            "notes": list(img.notes),
        }
        return d


def _r(x, nd):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def _mahal(v: np.ndarray, cov: np.ndarray) -> float:
    return float(np.sqrt(v @ np.linalg.solve(cov, v)))


def _jacobian(wcs, x: float, y: float, ra0: float, dec0: float) -> np.ndarray:
    """Numerical d(east, north)/d(x, y) in arcsec per pixel at (x, y)."""
    cols = []
    for dx, dy in ((1.0, 0.0), (0.0, 1.0)):
        ra1, dec1 = wcs.all_pix2world([[x + dx, y + dy]], 0)[0]
        ra_c, dec_c = wcs.all_pix2world([[x, y]], 0)[0]
        e1, n1 = sky_offset_arcsec(ra0, dec0, ra1, dec1)
        ec, nc = sky_offset_arcsec(ra0, dec0, ra_c, dec_c)
        cols.append([e1 - ec, n1 - nc])
    return np.array(cols).T


def analyze_sector(img: SectorImages, target: Star, neighbours: list[Star]) -> SectorResult:
    wcs = img.wcs()
    year = btjd_to_jyear(img.epoch_btjd)
    ra_t, dec_t = target.at(year)
    tx, ty = (float(v) for v in wcs.all_world2pix([[ra_t, dec_t]], 0)[0])
    nb_radec = np.array([s.at(year) for s in neighbours]).reshape(-1, 2)
    nb_xy = wcs.all_world2pix(nb_radec, 0) if len(neighbours) else np.zeros((0, 2))
    jac = _jacobian(wcs, tx, ty, ra_t, dec_t)

    ny, nx = img.oot.shape
    in_scene = [
        i for i, s in enumerate(neighbours)
        if s.tmag < target.tmag + SCENE_DMAG and -4 <= nb_xy[i, 0] <= nx + 3 and -4 <= nb_xy[i, 1] <= ny + 3
    ]
    in_scene = sorted(in_scene, key=lambda i: neighbours[i].tmag)[:SCENE_MAX_STARS]
    flux_rel = np.array([10 ** (-0.4 * (neighbours[i].tmag - target.tmag)) for i in in_scene])
    scene_xy = nb_xy[in_scene] if in_scene else np.zeros((0, 2))
    scene = fit_scene(img.oot, img.frame_var, (tx, ty), scene_xy, flux_rel)
    txc, tyc = tx + scene.dx, ty + scene.dy
    star_xy = nb_xy + np.array([scene.dx, scene.dy]) if len(neighbours) else nb_xy

    starts = [(txc, tyc)] + [tuple(star_xy[i]) for i in in_scene[:6]]
    diff = fit_difference(img.diff, img.diff_var, scene.shape, starts)
    depth = diff.flux / scene.target_flux if scene.target_flux > 0 else None
    depth_err = diff.flux_err / scene.target_flux if scene.target_flux > 0 else None

    empty = dict(images=img, target_xy=(txc, tyc), star_xy=star_xy, star_ids=[s.gaia_id for s in neighbours], scene=scene, diff=diff, jac=jac, depth=depth,
                 depth_err=depth_err)
    if not (diff.flux > 0 and diff.snr >= DETECT_SNR and depth_err):
        return SectorResult(detected=False, offset_en=None, cov_en=None,
                            reason=f"dip not seen in the pixels (difference-image SNR {diff.snr:.1f} < {DETECT_SNR:g})",
                            **empty)
    if not (0 <= diff.x <= nx - 1 and 0 <= diff.y <= ny - 1):
        return SectorResult(detected=False, offset_en=None, cov_en=None,
                            reason="difference-image centroid fell outside the cutout", **empty)

    off_px = np.array([diff.x - txc, diff.y - tyc])
    cov_px = diff.cov + scene.cov_dxdy + np.eye(2) * SECTOR_FLOOR_PX**2
    return SectorResult(detected=True, offset_en=jac @ off_px, cov_en=jac @ cov_px @ jac.T,
                        reason=f"dip seen at SNR {diff.snr:.1f}", **empty)


@dataclass
class Combined:
    offset_en: np.ndarray
    cov_en: np.ndarray
    offset_arcsec: float
    offset_sigma: float
    depth: float
    depth_err: float
    pixel_scale: float
    chi2_red: float


def combine(results: list[SectorResult]) -> Combined | None:
    used = [r for r in results if r.detected]
    if not used:
        return None
    inv = [np.linalg.inv(r.cov_en) for r in used]
    cov = np.linalg.inv(sum(inv))
    off = cov @ sum(i @ r.offset_en for i, r in zip(inv, used))
    chi2_red = 1.0
    if len(used) > 1:
        chi2 = sum(float((r.offset_en - off) @ i @ (r.offset_en - off)) for i, r in zip(inv, used))
        chi2_red = chi2 / (2 * (len(used) - 1))
        if chi2_red > 1.0:  # sectors disagree more than their errors allow: widen the combined error
            cov = cov * chi2_red
    w = np.array([1 / r.depth_err**2 for r in used])
    depth = float(np.sum(w * np.array([r.depth for r in used])) / w.sum())
    return Combined(off, cov, float(np.hypot(*off)), _mahal(off, cov), depth, float(1 / np.sqrt(w.sum())),
                    float(np.mean([r.pixel_scale for r in used])), float(chi2_red))


def excluded(delta_en: np.ndarray, cov: np.ndarray, pixel_scale: float) -> bool:
    """A position is excluded when the centroid is > 3σ from it AND more than 0.3 px away."""
    return _mahal(delta_en, cov) > OFF_TARGET_SIGMA and float(np.hypot(*delta_en)) > OFF_TARGET_MIN_PX * pixel_scale


def neighbour_table(target: Star, neighbours: list[Star], comb: Combined | None, jyear: float) -> list[dict]:
    """Every Gaia neighbour within 2.5′ with the depth it would need and its distance from the centroid."""
    ra_t, dec_t = target.at(jyear)
    rows = []
    for s in neighbours:
        ra, dec = s.at(jyear)
        pos = np.array(sky_offset_arcsec(ra_t, dec_t, ra, dec))
        sep = float(np.hypot(*pos))
        if sep > NEIGHBOUR_RADIUS_ARCSEC:
            continue
        row = {
            "gaia_id": s.gaia_id,
            "sep_arcsec": round(sep, 2),
            "east_north_arcsec": [round(float(pos[0]), 2), round(float(pos[1]), 2)],
            "gmag": _r(s.gmag, 3),
            "tmag": _r(s.tmag, 3),
            "flux_ratio": _r(10 ** (-0.4 * (s.tmag - target.tmag)), 6),
            "needed_depth": None,
            "centroid_distance_sigma": None,
            "excluded_by_centroid": None,
            "suspect": False,
        }
        if comb is not None:
            needed = comb.depth * 10 ** (0.4 * (s.tmag - target.tmag))
            delta = comb.offset_en - pos
            row["needed_depth"] = _r(needed, 5)
            row["centroid_distance_sigma"] = _r(_mahal(delta, comb.cov_en), 2)
            row["excluded_by_centroid"] = excluded(delta, comb.cov_en, comb.pixel_scale)
            row["suspect"] = bool(needed <= 1.0 and not row["excluded_by_centroid"])
        rows.append(row)
    return sorted(rows, key=lambda r: r["sep_arcsec"])


def on_target_probability(comb: Combined, rows: list[dict]) -> float:
    cov = comb.cov_en + np.eye(2) * (PROB_FLOOR_PX * comb.pixel_scale) ** 2
    lt = math.exp(-0.5 * _mahal(comb.offset_en, cov) ** 2)
    total = W_TARGET * lt + W_ELSEWHERE * math.exp(-4.5)
    for r in rows:
        nd = r["needed_depth"]
        if nd is None or nd > 1.0:
            continue
        w = W_NEIGHBOUR_EASY if nd <= 0.5 else W_NEIGHBOUR_HARD
        d = _mahal(comb.offset_en - np.array(r["east_north_arcsec"]), cov)
        total += w * math.exp(-0.5 * d * d)
    return W_TARGET * lt / total


def _name(r: dict) -> str:
    return f"Gaia DR3 {r['gaia_id']} (G={r['gmag']:.1f}, {r['sep_arcsec']:.0f}″ away)"


def verdict(comb: Combined | None, rows: list[dict], results: list[SectorResult]) -> tuple[str, str]:
    if comb is None:
        best = max((r.diff.snr for r in results if r.diff), default=0.0)
        if not results:
            return "inconclusive", "no usable TESS pixel data around the transits for this star"
        return ("inconclusive",
                f"the dip is not visible in the pixels (best difference-image SNR {best:.1f} < {DETECT_SNR:g} over "
                f"{len(results)} sector(s)), so its source cannot be located")
    off_px = comb.offset_arcsec / comb.pixel_scale
    suspects = [r for r in rows if r["suspect"]]
    if excluded(comb.offset_en, comb.cov_en, comb.pixel_scale):
        msg = (f"the light lost in transit comes from {comb.offset_arcsec:.1f}″ ({off_px:.2f} px) away from the "
               f"target, {comb.offset_sigma:.1f}σ off")
        if suspects:
            best = min(suspects, key=lambda r: r["centroid_distance_sigma"])
            msg += (f"; it matches {_name(best)}, which would need a {100 * best['needed_depth']:.1f}% eclipse "
                    f"(centroid {best['centroid_distance_sigma']:.1f}σ from it)")
        else:
            msg += "; no catalogued neighbour at that spot is bright enough to cause it"
        return "off target", msg
    if suspects:
        names = "; ".join(f"{_name(r)} would need a {100 * r['needed_depth']:.1f}% eclipse" for r in suspects[:3])
        more = f" (+{len(suspects) - 3} more)" if len(suspects) > 3 else ""
        return ("possible neighbour",
                f"the centroid is consistent with the target ({comb.offset_sigma:.1f}σ, {comb.offset_arcsec:.1f}″) "
                f"but cannot rule out neighbours close enough to share it: {names}{more}")
    return ("on target",
            f"the light lost in transit comes from the target (offset {comb.offset_arcsec:.1f}″ = {off_px:.2f} px, "
            f"{comb.offset_sigma:.1f}σ) and every Gaia neighbour able to mimic the dip is excluded by the centroid")
