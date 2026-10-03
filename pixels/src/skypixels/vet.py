"""vet_pixels(): is the dip on the target star or on a neighbour?"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import analyze as an
from .catalog import BTJD_OFFSET, GAIA_EPOCH, btjd_to_jyear, gaia_cone, gaia_to_tmag, match_target, propagate, tic_row
from .reduce import SectorImages, make_images

GAIA_RADIUS_ARCSEC = 240.0  # covers the corners of a 15×15 cutout
GAIA_DMAG = 10.0  # a star 10 mag fainter can still mimic a 0.01% dip with a total eclipse
DEFAULT_MAX_SECTORS = 3


@dataclass
class Ephemeris:
    period_d: float
    t0_btjd: float
    duration_h: float

    @property
    def duration_d(self) -> float:
        return self.duration_h / 24.0


@dataclass
class VetInputs:
    """Everything the analysis needs; small enough to record as an offline test fixture."""

    tic: dict
    gaia: list[dict]
    ephemeris: Ephemeris
    sectors: list[SectorImages]
    products: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        meta = {"tic": self.tic, "gaia": self.gaia, "ephemeris": asdict(self.ephemeris), "products": self.products,
                "skipped": self.skipped, "sectors": [s.sector for s in self.sectors]}
        (folder / "inputs.json").write_text(json.dumps(meta, indent=1))
        for s in self.sectors:
            s.to_npz(folder / f"s{s.sector:04d}.npz")

    @classmethod
    def load(cls, folder: Path) -> "VetInputs":
        meta = json.loads((folder / "inputs.json").read_text())
        sectors = [SectorImages.from_npz(folder / f"s{s:04d}.npz") for s in meta["sectors"]]
        return cls(meta["tic"], meta["gaia"], Ephemeris(**meta["ephemeris"]), sectors, meta["products"],
                   meta["skipped"])


@dataclass
class PixelVet:
    tic_id: int
    ephemeris: dict
    verdict: str  # "on target" | "possible neighbour" | "off target" | "inconclusive"
    reason: str
    on_target_probability: float | None
    centroid_offset_arcsec: float | None
    centroid_offset_px: float | None
    offset_sigma: float | None
    offset_east_north_arcsec: list[float] | None
    depth_on_target: float | None
    depth_on_target_err: float | None
    depth_upper_limit_3sigma: float | None  # only when the dip is not seen in the pixels
    tic_contamination_ratio: float | None
    target_tmag: float | None
    suspect_neighbours: list[dict]
    neighbours: list[dict]
    per_sector: list[dict]
    heuristic: str
    data: list[dict]
    warnings: list[str]
    timings_s: dict[str, float] = field(default_factory=dict)
    files: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _stars(tic: dict, gaia: list[dict]) -> tuple[an.Star, list[an.Star]]:
    match = match_target(tic, gaia)
    if match is not None:
        tmag = tic["tmag"] if tic.get("tmag") is not None else gaia_to_tmag(match["gmag"], match["bp_rp"])
        target = an.Star(match["gaia_id"], match["ra_deg"], match["dec_deg"], match["pmra_masyr"],
                         match["pmdec_masyr"], match["gmag"], tmag)
    else:
        ra, dec = propagate(tic["ra_deg"], tic["dec_deg"], tic.get("pmra_masyr"), tic.get("pmdec_masyr"), 2000.0,
                            GAIA_EPOCH)
        target = an.Star(None, ra, dec, tic.get("pmra_masyr"), tic.get("pmdec_masyr"), tic.get("gmag"), tic["tmag"])
    others = [
        an.Star(g["gaia_id"], g["ra_deg"], g["dec_deg"], g["pmra_masyr"], g["pmdec_masyr"], g["gmag"],
                gaia_to_tmag(g["gmag"], g["bp_rp"]))
        for g in gaia
        if match is None or g["gaia_id"] != match["gaia_id"]
    ]
    return target, others


SATURATION_TMAG = 6.8  # TESS saturates around T ≈ 6.8 in 2-s exposures


def _warnings(inputs: VetInputs, target: an.Star, results: list, comb) -> list[str]:
    out = []
    if target.gaia_id is None:
        out.append("target not matched in Gaia DR3; TIC position used")
    if target.tmag is not None and target.tmag < SATURATION_TMAG:
        out.append(f"target is saturated (T={target.tmag:.1f}); bleed columns make centroids less reliable")
    if comb is not None and comb.chi2_red > 4:
        out.append(f"sectors disagree about the centroid (χ²/dof = {comb.chi2_red:.1f}); errors widened to match")
    if comb is not None and sum(r.detected for r in results) == 1:
        out.append("centroid from a single sector")
    if inputs.skipped:
        out.append(f"{len(inputs.skipped)} sector(s) skipped (see per_sector)")
    return out


def normalise_t0(t0: float) -> float:
    """Accept BTJD, or a full BJD (> 2 400 000) which is converted to BTJD."""
    return t0 - BTJD_OFFSET if t0 > 2_400_000 else t0


def gather(tic_id: int, period_d: float, t0_btjd: float, duration_h: float, sectors: list[int] | None = None,
           max_sectors: int = DEFAULT_MAX_SECTORS, refresh: bool = False,
           timings: dict[str, float] | None = None) -> VetInputs:
    """Catalogues + pixel data → reduced per-sector images (network, cached)."""
    from . import fetch

    timings = timings if timings is not None else {}
    eph = Ephemeris(float(period_d), normalise_t0(float(t0_btjd)), float(duration_h))
    t = time.perf_counter()
    tic = tic_row(tic_id, refresh)
    gmax = min((tic.get("gmag") or tic["tmag"] + 0.5) + GAIA_DMAG, 20.5)
    gaia = gaia_cone(tic["ra_deg"], tic["dec_deg"], GAIA_RADIUS_ARCSEC, gmax, refresh)
    timings["catalogues"] = round(time.perf_counter() - t, 2)

    t = time.perf_counter()
    rows = fetch.list_products(int(tic_id), tic["ra_deg"], tic["dec_deg"], refresh)
    chosen = fetch.choose_products(rows, sectors, max_sectors)
    timings["search"] = round(time.perf_counter() - t, 2)
    if not chosen:  # nothing to look at: the analysis will say "inconclusive"
        return VetInputs(tic, gaia, eph, [], [], [])

    images, skipped = [], []
    t_dl = t_red = 0.0
    for row in chosen:
        t = time.perf_counter()
        try:
            series = fetch.read(fetch.download(row, tic["ra_deg"], tic["dec_deg"]), row)
        except Exception as exc:  # one broken sector should not sink the others
            skipped.append({"sector": row["sector"], "kind": row["kind"], "why": f"download/read failed: {exc}"})
            t_dl += time.perf_counter() - t
            continue
        t_dl += time.perf_counter() - t
        t = time.perf_counter()
        img = make_images(series.sector, series.kind, series.time, series.flux, series.quality,
                          series.wcs.to_header_string(relax=True), eph.period_d, eph.t0_btjd, eph.duration_d,
                          series.aperture)
        t_red += time.perf_counter() - t
        if img is None:
            skipped.append({"sector": row["sector"], "kind": row["kind"],
                            "why": "no transit with in-transit frames and out-of-transit frames on both sides"})
        else:
            images.append(img)
    timings["download"] = round(t_dl, 2)
    timings["reduce"] = round(t_red, 2)
    products = [{"sector": r["sector"], "kind": r["kind"], "filename": r["filename"]} for r in chosen]
    return VetInputs(tic, gaia, eph, images, products, skipped)


def analyze_inputs(inputs: VetInputs, timings: dict[str, float] | None = None) -> tuple[PixelVet, list]:
    """Pure analysis (no network) → PixelVet and the per-sector results (for rendering)."""
    timings = timings if timings is not None else {}
    t = time.perf_counter()
    target, others = _stars(inputs.tic, inputs.gaia)
    results = [an.analyze_sector(img, target, others) for img in inputs.sectors]
    comb = an.combine(results)
    used = [r for r in results if r.detected] or results
    jyear = float(np.mean([btjd_to_jyear(r.images.epoch_btjd) for r in used])) if used else 2020.0
    rows = an.neighbour_table(target, others, comb, jyear)
    verdict, reason = an.verdict(comb, rows, results)
    prob = an.on_target_probability(comb, rows) if comb is not None else None
    timings["analyze"] = round(time.perf_counter() - t, 2)
    upper = None
    if comb is None:
        fits_ = [r for r in results if r.depth is not None and r.depth_err]
        if fits_:
            w = np.array([1 / r.depth_err**2 for r in fits_])
            mean = float(np.sum(w * np.array([r.depth for r in fits_])) / w.sum())
            upper = round(max(mean, 0.0) + 3 / float(np.sqrt(w.sum())), 6)
    warnings = _warnings(inputs, target, results, comb)
    suspects = [
        {k: r[k] for k in ("gaia_id", "sep_arcsec", "gmag", "tmag", "needed_depth", "centroid_distance_sigma")}
        for r in rows if r["suspect"]
    ]
    per_sector = [r.to_dict() for r in results] + [
        {"sector": s["sector"], "kind": s["kind"], "detected": False, "reason": s["why"]} for s in inputs.skipped
    ]
    vet = PixelVet(
        tic_id=int(inputs.tic["tic_id"]),
        ephemeris=asdict(inputs.ephemeris),
        verdict=verdict,
        reason=reason,
        on_target_probability=None if prob is None else round(prob, 3),
        centroid_offset_arcsec=None if comb is None else round(comb.offset_arcsec, 2),
        centroid_offset_px=None if comb is None else round(comb.offset_arcsec / comb.pixel_scale, 3),
        offset_sigma=None if comb is None else round(comb.offset_sigma, 2),
        offset_east_north_arcsec=None if comb is None else [round(float(v), 2) for v in comb.offset_en],
        depth_on_target=None if comb is None else round(comb.depth, 6),
        depth_on_target_err=None if comb is None else round(comb.depth_err, 6),
        depth_upper_limit_3sigma=upper,
        tic_contamination_ratio=inputs.tic.get("contratio"),
        target_tmag=target.tmag,
        suspect_neighbours=suspects,
        neighbours=rows,
        per_sector=sorted(per_sector, key=lambda d: d["sector"]),
        heuristic=an.HEURISTIC,
        data=inputs.products,
        warnings=warnings,
        timings_s=timings,
    )
    return vet, results


def vet_pixels(tic: int, period_d: float, t0_btjd: float, duration_h: float, sectors: list[int] | None = None,
               out_dir: str | Path | None = None, max_sectors: int = DEFAULT_MAX_SECTORS,
               refresh: bool = False) -> PixelVet:
    """Difference-image vetting of one transit signal. Writes PNGs + JSON to out_dir when given."""
    t_start = time.perf_counter()
    timings: dict[str, float] = {}
    inputs = gather(int(tic), period_d, t0_btjd, duration_h, sectors, max_sectors, refresh, timings)
    vet, results = analyze_inputs(inputs, timings)
    if out_dir is not None:
        from .render import write_outputs

        t = time.perf_counter()
        vet.files = write_outputs(vet, results, Path(out_dir))
        timings["render"] = round(time.perf_counter() - t, 2)
    timings["total"] = round(time.perf_counter() - t_start, 2)
    if out_dir is not None:
        (Path(out_dir) / "pixel_vet.json").write_text(json.dumps(vet.to_dict(), indent=1))
    return vet
