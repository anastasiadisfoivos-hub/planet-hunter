"""TRICERATOPS (Giacalone & Dressing 2020; Giacalone et al. 2021): Bayesian false-positive probabilities.

FPP is the probability that the signal is not a planet transiting the target; NFPP is the probability that it
comes from a resolved nearby star. Giacalone et al. (2021) validate at FPP < 0.015 and NFPP < 0.001, and call
a signal a likely nearby false positive at NFPP > 0.1.

TRICERATOPS reaches the network when a `target` is built: the TIC around the star (MAST), a Gaia DR3 field-star
sample for the background scenarios, and a TESScut FFI cutout per sector (to place every star on the pixels).
Those are recorded once, as exactly the attributes `target.__init__` sets
(`record_inputs`), and a replay rebuilds the target from them without touching the network (`replay_target`).
The SPOC optimal aperture of each 2-min / TESS-SPOC sector is read from the light-curve file's APERTURE
extension (the same mask TRICERATOPS' get_spoc_apertures reads from the target-pixel file; its archive-listing
lookup no longer answers). Sectors with no SPOC aperture (QLP) use TRICERATOPS' own default, a 5x5 box.

calc_probs is Monte Carlo (N draws per scenario) and slow, so it runs in a child process with a wall-clock
budget. Past the budget the child is killed and the result says ran: false with the reason. The seed is fixed
so that a replay reproduces the numbers.
"""

from __future__ import annotations

import contextlib
import io
import multiprocessing as mp
import os
import pickle
import tempfile
import time
import traceback
from importlib.metadata import version

import numpy as np

from . import cache
from .lightcurve import LightCurve

VALIDATED_FPP, VALIDATED_NFPP, LIKELY_NFP_NFPP, LIKELY_FP_FPP = 0.015, 0.001, 0.1, 0.5
DEFAULT_N = 100_000  # TRICERATOPS itself defaults to 1e6; see README (runtime)
DEFAULT_BUDGET_S = 900.0
SEED = 20260926
SEARCH_RADIUS_PIX = 10
BIN_MINUTES = 5.0


def record_inputs(tic: int, sectors: list[int]) -> dict:
    """Everything TRICERATOPS reads from the network for this star and these sectors (cached)."""

    def fetch() -> dict:
        from triceratops.triceratops import target

        _use_certifi()
        with contextlib.redirect_stdout(io.StringIO()):
            t = target(ID=int(tic), sectors=np.array(sectors), search_radius=SEARCH_RADIUS_PIX)
        if not (isinstance(t.trilegal_fname, str) and os.path.exists(t.trilegal_fname)):
            # TRICERATOPS would carry on without its background scenarios; do not record (or cache) that.
            raise ConnectionError("TRICERATOPS' Gaia DR3 field-star query failed (no background population)")
        with open(t.trilegal_fname) as f:
            bg = f.read()
        os.remove(t.trilegal_fname)
        return {"ID": int(tic), "sectors": list(map(int, sectors)), "stars": t.stars.to_dict(orient="list"),
                "TESS_images": t.TESS_images, "col0s": t.col0s, "row0s": t.row0s, "pix_coords": t.pix_coords,
                "background_csv": bg, "triceratops_version": version("triceratops")}

    return cache.cached("triceratops", f"{int(tic)}:{','.join(map(str, sectors))}", fetch, fmt="pickle")


def _use_certifi() -> None:
    """astroquery's Gaia client verifies TLS with Python's default context, which on a python.org build has no CA
    bundle unless "Install Certificates" was run. Point it at certifi's bundle (verification stays on)."""
    if not os.environ.get("SSL_CERT_FILE"):
        import certifi

        os.environ["SSL_CERT_FILE"] = certifi.where()


def replay_target(rec: dict, workdir: str):
    """A triceratops `target` rebuilt from recorded inputs (no network)."""
    import pandas as pd
    from triceratops.triceratops import target

    t = object.__new__(target)
    t.ID, t.mission, t.sectors = rec["ID"], "TESS", np.array(rec["sectors"])
    t.search_radius, t.N_pix = SEARCH_RADIUS_PIX, 2 * SEARCH_RADIUS_PIX + 2
    t.stars = pd.DataFrame(rec["stars"])
    t.TESS_images, t.col0s, t.row0s, t.pix_coords = rec["TESS_images"], rec["col0s"], rec["row0s"], rec["pix_coords"]
    t.background_population_source, t.trilegal_url = "gaia", None
    t.trilegal_fname = None
    if rec["background_csv"]:
        t.trilegal_fname = os.path.join(workdir, f"{rec['ID']}_gaia_background.csv")
        with open(t.trilegal_fname, "w") as f:
            f.write(rec["background_csv"])
    return t


def apertures(rec: dict, spoc: dict[int, list]) -> list[np.ndarray]:
    """One aperture per recorded sector: SPOC's where the light curve had one, else a 5x5 box."""
    out = []
    for sector, pc in zip(rec["sectors"], rec["pix_coords"], strict=True):
        if spoc.get(sector):
            out.append(np.array(spoc[sector], dtype=float))
            continue
        c, r = np.round(pc[0])  # TRICERATOPS' own default: 5x5 around the target
        out.append(np.array([np.repeat(np.arange(c - 2, c + 3), 5), np.tile(np.arange(r - 2, r + 3), 5)]).T)
    return out


def folded(lc: LightCurve, period: float, t0: float, duration_d: float) -> tuple[np.ndarray, np.ndarray, float, float]:
    """(time from mid-transit [d], flux, flux error, bin width [d]) within ±2 durations, binned to 5 min
    (or the native cadence if longer)."""
    ph = (lc.time - t0 + 0.5 * period) % period - 0.5 * period
    half = max(2 * duration_d, 0.1)
    sel = np.abs(ph) < half
    width = max(BIN_MINUTES / 1440, lc.cadence_days)
    edges = np.arange(-half, half + width, width)
    idx = np.digitize(ph[sel], edges)
    tb, fb = [], []
    for i in np.unique(idx):
        m = idx == i
        if m.sum() >= 1:
            tb.append(ph[sel][m].mean())
            fb.append(lc.flux[sel][m].mean())
    tb, fb = np.array(tb), np.array(fb)
    out = np.abs(tb) > 0.75 * duration_d
    err = float(np.std(fb[out])) if out.sum() > 5 else float(np.median(lc.flux_err) / np.sqrt(width / lc.cadence_days))
    return tb, fb, err, width


def _worker(path_in: str, path_out: str) -> None:
    try:
        if cache.offline():
            cache.forbid_network()
        with open(path_in, "rb") as f:
            job = pickle.load(f)
        np.random.seed(job["seed"])
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            t = replay_target(job["rec"], tmp)
            t.calc_depths(tdepth=job["depth"], all_ap_pixels=apertures(job["rec"], job["spoc_apertures"]))
            t.calc_probs(time=job["time"], flux_0=job["flux"], flux_err_0=job["err"], P_orb=job["period"],
                         N=job["N"], exptime=job["exptime"], verbose=0)
        if not hasattr(t, "FPP"):
            raise RuntimeError("calc_probs stopped early: TRICERATOPS needs the target's mass, radius, Teff and "
                               "parallax in the TIC")
        probs = t.probs.sort_values("prob", ascending=False)
        top = [{"scenario": r["scenario"], "tic": str(r["ID"]), "prob": float(f"{r['prob']:.3g}")}
               for _, r in probs.head(5).iterrows()]
        res = {"ok": True, "fpp": float(t.FPP), "nfpp": float(t.NFPP), "top_scenarios": top,
               "n_stars_considered": int((t.stars["tdepth"] > 0).sum())}
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}
    with open(path_out, "wb") as f:
        pickle.dump(res, f)


def run(cand: dict, lc: LightCurve, budget_s: float = DEFAULT_BUDGET_S, n: int = DEFAULT_N) -> dict:
    out = {"ran": False, "fpp": None, "nfpp": None, "version": version("triceratops"), "tool": "TRICERATOPS",
           "N": n, "budget_s": budget_s, "seed": SEED}
    t_start = time.time()
    try:
        rec = record_inputs(cand["tic"], lc.sectors)
    except cache.OfflineMiss:
        raise
    except Exception as e:  # noqa: BLE001
        return {**out, "reason": f"could not gather TRICERATOPS inputs (MAST/Gaia/TESScut): {type(e).__name__}: {e}"}
    if len(rec["TESS_images"]) == 0:
        return {**out, "reason": "TESScut returned no cutout for any sector"}
    dur = cand["duration_h"] / 24
    tb, fb, err, width = folded(lc, cand["period_d"], cand["t0_btjd"], dur)
    depth = (cand.get("depth_ppm") or 0) / 1e6 or float(1 - np.min(fb))
    job = {"rec": rec, "seed": SEED, "depth": depth, "time": tb, "flux": fb, "err": err,
           "period": cand["period_d"], "N": n, "exptime": width, "spoc_apertures": lc.apertures}
    remaining = budget_s - (time.time() - t_start)
    with tempfile.TemporaryDirectory() as tmp:
        pin, pout = os.path.join(tmp, "in.pkl"), os.path.join(tmp, "out.pkl")
        with open(pin, "wb") as f:
            pickle.dump(job, f)
        proc = mp.get_context("spawn").Process(target=_worker, args=(pin, pout), daemon=True)
        proc.start()
        proc.join(max(remaining, 1.0))
        if proc.is_alive():
            proc.kill()
            proc.join()
            return {**out, "reason": f"time budget of {budget_s:.0f} s ran out during calc_probs (N = {n}); "
                                     "raise --tri-budget or lower --tri-n",
                    "runtime_s": round(time.time() - t_start, 1)}
        if not os.path.exists(pout):
            return {**out, "reason": f"calc_probs process died (exit code {proc.exitcode})"}
        with open(pout, "rb") as f:
            res = pickle.load(f)
    if not res["ok"]:
        return {**out, "reason": res["error"], "trace": res["trace"]}
    # FPP = 1 - (planet scenarios); when those sum to 1 it can come out a hair below 0. Report 0, keep the raw.
    fpp_raw, nfpp_raw = res["fpp"], res["nfpp"]
    fpp, nfpp = max(fpp_raw, 0.0), max(nfpp_raw, 0.0)
    if fpp < VALIDATED_FPP and nfpp < VALIDATED_NFPP:
        call = "validated (FPP < 0.015, NFPP < 0.001)"
    elif nfpp > LIKELY_NFP_NFPP:
        call = "likely nearby false positive (NFPP > 0.1)"
    elif fpp > LIKELY_FP_FPP:
        call = "likely false positive (FPP > 0.5)"
    else:
        call = "not validated, not ruled out"
    return {**out, "ran": True, "fpp": float(f"{fpp:.3g}"), "nfpp": float(f"{nfpp:.3g}"), "classification": call,
            "fpp_raw": fpp_raw, "nfpp_raw": nfpp_raw,
            "top_scenarios": res["top_scenarios"], "n_stars_considered": res["n_stars_considered"],
            "sectors": lc.sectors, "depth_used_ppm": round(depth * 1e6, 1), "n_points": len(tb),
            "bin_minutes": round(width * 1440, 2),
            "apertures": {s: "SPOC" if lc.apertures.get(s) else "5x5 default" for s in rec["sectors"]},
            # Without a field-star population TRICERATOPS silently skips DTP/DEB/BTP/BEB (and x2P) scenarios.
            "background_population": bool(rec["background_csv"]),
            "runtime_s": round(time.time() - t_start, 1)}
