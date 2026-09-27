"""The faint-star target list: TIC 8.2 M dwarfs with Tmag 13-16 that TGLC covers, ranked.

Selection (tic.sky): Tmag 13-16, Teff < 4000 K, luminosity class DWARF, object type STAR, not SPLIT / DUPLICATE /
ARTIFACT in the TIC.

Dropped (counted in the summary, never listed):
  known        a TOI (any disposition), CTOI, confirmed-planet host or TESS EB catalogue star
  no_tglc      no TGLC sector (1-55) covers the position
  crowded      TIC contamination ratio > 1: neighbours put more flux in the star's aperture than the star
               (TGLC's PSF fit removes known Gaia neighbours, but its residuals then dominate)
  no_radius    no TIC radius: the planet size cannot be judged

Tiers (every listed star is in exactly one):
  1  R <= 0.4 R_sun (mid/late M dwarf), >= 3 TGLC sectors, contamination <= 0.1
  2  R <= 0.6 R_sun, >= 2 TGLC sectors, contamination <= 0.3
  3  everything else that was not dropped (one sector, larger or more crowded stars), and every star with TIC
     Tmag > 15.7: TGLC stops at its own Gaia-fitted T = 16, and 6 of 11 such stars in the noise sample had no file
Inside a tier stars are ordered by the predicted smallest planet detectable at SNR 10 at P = 5 d (noise.py, with
the Tmag noise model and 22.5 days of data per sector), smallest first. That one number combines radius,
brightness and number of sectors. Every row carries a plain `reason`.

Coverage here is the vectorised footprint (coverage.sector_mask, a few percent approximate at field edges); the
loader confirms every file.
"""

from __future__ import annotations

import csv
import gzip
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import coverage, known, noise, tic

DAYS_PER_SECTOR = 22.5  # median days with data per TGLC sector after quality masking (results/noise_sample.json)
TIER_NAMES = {1: "tier 1: R <= 0.4 R_sun, >= 3 sectors, contamination <= 0.1",
              2: "tier 2: R <= 0.6 R_sun, >= 2 sectors, contamination <= 0.3",
              3: "tier 3: the rest (1 sector, larger or more crowded)"}
DROP_NAMES = {"known": "on a known list (TOI, CTOI, confirmed host, TESS EB)", "no_tglc": "no TGLC sector (1-55)",
              "crowded": "TIC contamination ratio > 1", "no_radius": "no TIC radius"}
CSV_FIELDS = ["rank", "tier", "tic", "ra", "dec", "tmag", "teff", "logg", "rad", "rad_err", "mass", "rho",
              "lumclass", "contratio", "gaia_dr2", "n_sectors", "sectors", "pred_cdpp_1h_ppm",
              "pred_rmin_p1_rearth", "pred_rmin_p5_rearth", "pred_rmin_p10_rearth", "reason"]
MAX_CONTRATIO = 1.0
NEAR_LIMIT_TMAG = 15.7


def tier(rad: float, n_sectors: int, contratio: float, tmag: float = 14.0) -> int:
    c = contratio if contratio is not None else 0.0
    if tmag > NEAR_LIMIT_TMAG:
        return 3
    if rad <= 0.4 and n_sectors >= 3 and c <= 0.1:
        return 1
    if rad <= 0.6 and n_sectors >= 2 and c <= 0.3:
        return 2
    return 3


def _crowding_word(c: float | None) -> str:
    if c is None:
        return "contamination unknown"
    return f"contamination {c:.2f} ({'low' if c <= 0.1 else 'moderate' if c <= 0.3 else 'high'})"


def reason(r: dict) -> str:
    kind = "late M dwarf" if r["rad"] <= 0.3 else "M dwarf"
    secs = r["sectors"]
    sec_txt = f"S{secs[0]}" if len(secs) == 1 else f"S{secs[0]}-S{secs[-1]}"
    return (f"{kind}, R {r['rad']:.2f} R_sun, Teff {r['teff']:.0f} K, Tmag {r['tmag']:.2f}; "
            f"{len(secs)} TGLC sector{'s' if len(secs) != 1 else ''} ({sec_txt}); {_crowding_word(r['contratio'])}; "
            f"not a TOI, CTOI, confirmed host or known EB; a {r['pred_rmin_p5_rearth']:.1f} R_earth planet at P = 5 d "
            f"should reach SNR 10 (predicted)"
            + ("; near TGLC's T = 16 limit, may have no file" if r["tmag"] > NEAR_LIMIT_TMAG else ""))


def _predict(rows: list[dict]) -> None:
    for r in rows:
        c1 = noise.predicted_cdpp_1h(r["tmag"])
        days = DAYS_PER_SECTOR * len(r["sectors"])
        det = noise.detectable_radius(r, c1, c1 * 2 ** noise.TYPICAL_ALPHA, days)
        r["pred_cdpp_1h_ppm"] = round(c1)
        for p in (1, 5, 10):
            d = det["by_period"][str(p)]
            r[f"pred_rmin_p{p}_rearth"] = d["radius_rearth"] if d and d["radius_rearth"] is not None else 99.0


def build(log: Callable[[str], None] = print, workers: int = 6, step_deg: float = 1.0) -> dict:
    stars = tic.sky(step_deg=step_deg, workers=workers, log=log)
    log(f"{len(stars)} TIC M dwarfs with Tmag 13-16; footprint of TGLC sectors 1-55")
    lists = known.load()
    known_any = set().union(*lists.values())
    ra = np.array([s["ra"] for s in stars])
    dec = np.array([s["dec"] for s in stars])
    bits = np.zeros(len(stars), np.int64)
    for i in range(0, len(stars), 200_000):
        bits[i:i + 200_000] = coverage.sector_mask(ra[i:i + 200_000], dec[i:i + 200_000])
    dropped = {k: 0 for k in DROP_NAMES}
    known_by_list = {k: 0 for k in lists}
    kept = []
    for s, b in zip(stars, bits):
        if s["tic"] in known_any:
            dropped["known"] += 1
            for k, v in lists.items():
                known_by_list[k] += s["tic"] in v
            continue
        secs = coverage.sectors_of(b)
        if not secs:
            dropped["no_tglc"] += 1
            continue
        if s["contratio"] is not None and s["contratio"] > MAX_CONTRATIO:
            dropped["crowded"] += 1
            continue
        if not s["rad"]:
            dropped["no_radius"] += 1
            continue
        kept.append({**s, "sectors": secs, "n_sectors": len(secs)})
    _predict(kept)
    for r in kept:
        r["tier"] = tier(r["rad"], r["n_sectors"], r["contratio"], r["tmag"])
    kept.sort(key=lambda r: (r["tier"], r["pred_rmin_p5_rearth"], r["tmag"]))
    for i, r in enumerate(kept, start=1):
        r["rank"] = i
        r["reason"] = reason(r)
    by_tier = {TIER_NAMES[t]: sum(1 for r in kept if r["tier"] == t) for t in TIER_NAMES}
    nsec = np.array([r["n_sectors"] for r in kept]) if kept else np.array([0])
    summary = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "selection": "TIC 8.2: Tmag 13-16, Teff < 4000 K, DWARF, STAR, not SPLIT/DUPLICATE/ARTIFACT",
        "tic_stars": len(stars),
        "dropped": {DROP_NAMES[k]: v for k, v in dropped.items()},
        "known_by_list": {known.LISTS[k]: v for k, v in known_by_list.items()},
        "listed": len(kept),
        "by_tier": by_tier,
        "sectors_per_star": {"median": float(np.median(nsec)), "p90": float(np.percentile(nsec, 90)),
                             "max": int(nsec.max())},
        "tier1_median_pred_rmin_p5_rearth": _median([r["pred_rmin_p5_rearth"] for r in kept if r["tier"] == 1]),
        "noise_model": {**noise.NOISE_MODEL, "note": noise.NOISE_MODEL_NOTE},
        "coverage": "TGLC sectors 1-55, vectorised footprint (coverage.sector_mask)",
        "known_lists_sizes": {known.LISTS[k]: len(v) for k, v in lists.items()},
    }
    return {"summary": summary, "rows": kept}


def _median(v: list[float]) -> float | None:
    return round(float(np.median(v)), 2) if v else None


def _csv_row(r: dict) -> dict:
    out = {k: r.get(k) for k in CSV_FIELDS}
    out["sectors"] = " ".join(map(str, r["sectors"]))
    return out


def write(result: dict, out_dir: Path, top: int = 5000) -> dict[str, Path]:
    """targets_faint.csv.gz (every listed star), targets_faint_top.csv (the first `top` rows) and
    targets_faint_summary.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"all": out_dir / "targets_faint.csv.gz", "top": out_dir / "targets_faint_top.csv",
             "summary": out_dir / "targets_faint_summary.json"}
    with gzip.open(paths["all"], "wt", newline="") as fh:
        w = csv.DictWriter(fh, CSV_FIELDS)
        w.writeheader()
        for r in result["rows"]:
            w.writerow(_csv_row(r))
    with open(paths["top"], "w", newline="") as fh:
        w = csv.DictWriter(fh, CSV_FIELDS)
        w.writeheader()
        for r in result["rows"][:top]:
            w.writerow(_csv_row(r))
    paths["summary"].write_text(json.dumps(result["summary"], indent=2))
    return paths


def read(path: Path) -> list[dict]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
        return list(csv.DictReader(fh))
