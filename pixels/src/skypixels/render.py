"""PNG figures and small JSON arrays (for the web UI) of each sector's images and star markers."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .analyze import SectorResult


def _round(a: np.ndarray, sig: int = 4) -> list:
    out = []
    for row in np.asarray(a, dtype=float):
        out.append([None if not np.isfinite(v) else float(f"{v:.{sig}g}") for v in row])
    return out


def _compass(res: SectorResult) -> dict:
    """Unit vectors (pixel dx, dy) pointing north and east."""
    inv = np.linalg.inv(res.jac)
    north = inv @ np.array([0.0, 1.0])
    east = inv @ np.array([1.0, 0.0])
    return {"north": (north / np.linalg.norm(north)).round(4).tolist(),
            "east": (east / np.linalg.norm(east)).round(4).tolist()}


def sector_json(vet, res: SectorResult) -> dict:
    img = res.images
    ny, nx = img.oot.shape
    markers = [{"kind": "target", "gaia_id": None, "x": round(res.target_xy[0], 3), "y": round(res.target_xy[1], 3),
                "label": f"TIC {vet.tic_id}"}]
    # vet.neighbours is the ≤ 2.5′ subset of the analysed stars; match pixel positions by Gaia id
    by_id = {row["gaia_id"]: row for row in vet.neighbours}
    for sid, (x, y) in zip(res.star_ids, res.star_xy):
        row = by_id.get(sid)
        if row is None or not (-1 <= x <= nx and -1 <= y <= ny):
            continue
        markers.append({"kind": "suspect" if row["suspect"] else "neighbour", "gaia_id": sid,
                        "x": round(float(x), 3), "y": round(float(y), 3), "gmag": row["gmag"],
                        "needed_depth": row["needed_depth"]})
    centroid = None
    if res.diff is not None:
        centroid = {"x": round(res.diff.x, 3), "y": round(res.diff.y, 3),
                    "cov_px": [[round(float(v), 5) for v in r] for r in res.diff.cov],
                    "used": res.detected}
    return {
        "tic_id": vet.tic_id,
        "sector": img.sector,
        "kind": img.kind,
        "shape": [ny, nx],
        "units": "e-/s; image[row][col], row = y, col = x, pixel centres at integers",
        "pixel_scale_arcsec": round(res.pixel_scale, 3),
        "compass": _compass(res),
        "out_of_transit": _round(img.oot),
        "difference": _round(img.diff),
        "difference_snr": _round(img.diff / np.sqrt(img.diff_var), 3),
        "aperture": img.aperture.astype(int).tolist() if img.aperture is not None else None,
        "markers": markers,
        "centroid": centroid,
    }


def sector_png(vet, res: SectorResult, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse

    img = res.images
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.9), constrained_layout=True)
    oot = np.where(np.isfinite(img.oot), img.oot, np.nan)
    lo = np.nanpercentile(oot, 5)
    axes[0].imshow(np.log10(np.clip(oot - lo, 1, None)), origin="lower", cmap="Greys_r")
    axes[0].set_title(f"Out of transit (log) — sector {img.sector} {img.kind.upper()}")
    lim = np.nanmax(np.abs(img.diff)) or 1.0
    axes[1].imshow(img.diff, origin="lower", cmap="RdBu_r", vmin=-lim, vmax=lim)
    snr = f"SNR {res.diff.snr:.1f}" if res.diff else ""
    axes[1].set_title(f"Difference (out − in): light lost in transit  {snr}")
    ny, nx = img.oot.shape
    by_id = {row["gaia_id"]: row for row in vet.neighbours}
    tmag_t = vet.target_tmag if vet.target_tmag is not None else 10.0
    for ax in axes:
        # Only stars that matter visually: within 5 mag of the target, or able to host the dip (all are in the JSON).
        for sid, (x, y) in zip(res.star_ids, res.star_xy):
            row = by_id.get(sid)
            if row is None or not (-0.5 <= x <= nx - 0.5 and -0.5 <= y <= ny - 0.5):
                continue
            if not row["suspect"] and (row["tmag"] or 99) > tmag_t + 5:
                continue
            size = float(np.clip(22 - (row["gmag"] or 20), 5, 13))  # brighter star, bigger ring
            if row["suspect"]:
                size = max(size, 16.0)  # drawn above the centroid marker so it stays visible
            ax.plot(x, y, "o", mfc="none", mec="orange" if row["suspect"] else "deepskyblue", ms=size, mew=1.3,
                    zorder=7 if row["suspect"] else 2)
        ax.plot(*res.target_xy, "x", color="lime", ms=11, mew=2.2, zorder=5)
        if res.diff is not None and res.detected:
            cov = res.diff.cov
            vals, vecs = np.linalg.eigh(cov)
            ang = np.degrees(np.arctan2(vecs[1, 1], vecs[0, 1]))
            for k in (1, 3):
                ax.add_patch(Ellipse((res.diff.x, res.diff.y), 2 * k * np.sqrt(vals[1]), 2 * k * np.sqrt(vals[0]),
                                     angle=ang, fill=False, color="magenta", lw=1.2, ls="-" if k == 1 else "--"))
            ax.plot(res.diff.x, res.diff.y, "+", color="magenta", ms=12, mew=2, zorder=6)
        if img.aperture is not None:
            ax.contour(img.aperture.astype(float), levels=[0.5], colors="yellow", linewidths=0.8,
                       extent=(-0.5, nx - 0.5, -0.5, ny - 0.5))
        comp = _compass(res)
        base = np.array([nx - 2.2, 2.2])
        for key, col in (("north", "white"), ("east", "khaki")):
            v = np.array(comp[key]) * 1.2
            ax.annotate("", xy=base + v, xytext=base, arrowprops=dict(arrowstyle="->", color=col, lw=1.4))
            ax.text(*(base + v * 1.35), key[0].upper(), color=col, fontsize=9, ha="center", va="center")
        ax.set_xlim(-0.5, nx - 0.5)
        ax.set_ylim(-0.5, ny - 0.5)
        ax.set_xlabel("column (px)")
        ax.set_ylabel("row (px)")
    from matplotlib.lines import Line2D

    handles = [Line2D([], [], ls="", marker="x", color="lime", mew=2, label="target"),
               Line2D([], [], ls="", marker="+", color="magenta", mew=2, label="dip centroid (1σ, 3σ)"),
               Line2D([], [], ls="", marker="o", mfc="none", mec="deepskyblue", label="Gaia neighbour"),
               Line2D([], [], ls="", marker="o", mfc="none", mec="orange", label="could host the dip")]
    axes[1].legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.7)
    fig.suptitle(f"TIC {vet.tic_id} — {vet.verdict}", fontsize=12)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def write_outputs(vet, results: list[SectorResult], out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    files = {"pngs": [], "json": []}
    for res in results:
        stem = f"tic{vet.tic_id}_s{res.images.sector:04d}"
        png = out / f"{stem}_pixels.png"
        js = out / f"{stem}_pixels.json"
        sector_png(vet, res, png)
        js.write_text(json.dumps(sector_json(vet, res), separators=(",", ":")))
        files["pngs"].append(png.name)
        files["json"].append(js.name)
    return files
