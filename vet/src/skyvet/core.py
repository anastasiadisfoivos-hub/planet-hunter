"""vet_candidate: add a "vetting" block to a Planet Finder (HUNT) candidate."""

from __future__ import annotations

import copy
import time
import traceback
from datetime import UTC, datetime
from importlib.metadata import version

from . import cache, gaia, leo, lightcurve, summary, tic, tri, variability

REQUIRED = ("tic", "period_d", "t0_btjd", "duration_h")


def vet_candidate(candidate_json: dict, *, triceratops: bool = True, tri_budget_s: float = tri.DEFAULT_BUDGET_S,
                  tri_n: int = tri.DEFAULT_N, pixel: bool = True, max_sectors: int = 3) -> dict:
    """Return a copy of the candidate with a "vetting" block:

    leo, triceratops, gaia, variability: each says ran: true/false (with the reason when false);
    summary: {verdict: pass | flag | fail, reasons: [...], notes: [...]}; runtime_s per step and in total.
    A tool that cannot run never counts as passing: it is a flag reason.
    """
    missing = [k for k in REQUIRED if candidate_json.get(k) in (None, "")]
    if missing:
        raise ValueError(f"candidate is missing {', '.join(missing)}")
    cand = copy.deepcopy(candidate_json)
    cand["tic"] = int(cand["tic"])
    t_all = time.time()
    runtime: dict[str, float] = {}
    v: dict = {}

    def step(name, fn, default):
        t0 = time.time()
        try:
            return fn()
        except cache.OfflineMiss as e:
            return {**default, "ran": False, "reason": f"offline and not cached: {e}"}
        except Exception as e:  # noqa: BLE001
            return {**default, "ran": False, "reason": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc()[-1200:]}
        finally:
            runtime[name] = round(time.time() - t0, 1)

    row = step("tic", lambda: {"ran": True, "row": tic.row(cand["tic"])}, {})
    tic_row = row.get("row")
    lcres = step("lightcurve", lambda: {"ran": True, "lc": lightcurve.fetch(
        cand["tic"], cand["period_d"], cand["t0_btjd"], cand["duration_h"] / 24,
        sectors=cand.get("sectors"), max_sectors=max_sectors)}, {})
    lc = lcres.get("lc")
    no_lc = f"no light curve: {lcres.get('reason')}" if lc is None else None
    no_tic = f"no TIC row: {row.get('reason')}" if tic_row is None else None

    leo_default = {"passed": None, "flags": [], "version": version("leo-vetter"), "tool": "LEO-vetter"}
    if no_lc or no_tic:
        v["leo"] = {**leo_default, "ran": False, "reason": no_tic or no_lc}
    else:
        v["leo"] = step("leo", lambda: leo.run(cand, tic_row, lc, pixel=pixel), leo_default)

    tri_default = {"fpp": None, "nfpp": None, "version": version("triceratops"), "tool": "TRICERATOPS"}
    if not triceratops:
        v["triceratops"] = {**tri_default, "ran": False, "reason": "skipped (--no-triceratops)"}
    elif no_lc:
        v["triceratops"] = {**tri_default, "ran": False, "reason": no_lc}
    else:
        v["triceratops"] = step("triceratops", lambda: tri.run(cand, lc, budget_s=tri_budget_s, n=tri_n),
                                tri_default)

    gaia_default = {"ruwe": None, "neighbours": [], "binary_hint": None}
    rows = target = None
    if no_tic:
        v["gaia"] = {**gaia_default, "ran": False, "reason": no_tic}
    else:
        def run_gaia():
            nonlocal rows, target
            block, rows, target = gaia.run(cand, tic_row)
            return block
        v["gaia"] = step("gaia", run_gaia, gaia_default)

    var_default = {"vsx_match": None, "gaia_variable": None, "vsx_ran": False, "gaia_ran": False}
    if no_tic:
        v["variability"] = {**var_default, "ran": False, "reason": no_tic}
    else:
        ra, dec = gaia.epoch2016(tic_row)
        v["variability"] = step("variability", lambda: variability.run(cand, ra, dec, rows, target), var_default)

    _pixel_source(v, rows, target)
    v["summary"] = summary.summarise(v, rows, target)
    runtime["total"] = round(time.time() - t_all, 1)
    v["light_curve"] = (None if lc is None else
                        {"products": lc.products, "n_points": int(len(lc.time)),
                         "detrend": "lightkurve flatten (Savitzky-Golay), window max(0.75 d, 3 x duration), transits masked"})
    v["runtime_s"] = runtime
    v["skyvet_version"] = version("skyvet")
    v["vetted_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    v["offline"] = cache.offline()
    cand["vetting"] = v
    return cand


def _pixel_source(v: dict, rows: list[dict] | None, target: dict | None) -> None:
    """Name the star under LEO's difference-image fit: the nearest Gaia DR3 source, with its TIC ID."""
    px = (v.get("leo") or {}).get("pixel") or {}
    if not px.get("ran") or not rows or target is None or px.get("source_ra") is None:
        return
    best = min(rows, key=lambda r: gaia.sep_to(r, px["source_ra"], px["source_dec"]))
    src = {"gaia_dr3": str(best["source_id"]), "gmag": round(best["phot_g_mean_mag"], 3),
           "is_target": best["source_id"] == target["source_id"],
           "sep_from_fit_arcsec": round(gaia.sep_to(best, px["source_ra"], px["source_dec"]), 2),
           "sep_from_target_arcsec": round(gaia.sep_to(best, target["ra"], target["dec"]), 2)}
    if not src["is_target"]:
        try:
            src["tic"] = tic.by_gaia(src["gaia_dr3"])
        except Exception as e:  # noqa: BLE001
            src["tic"], src["tic_error"] = None, f"{type(e).__name__}: {e}"
    px["source"] = src
