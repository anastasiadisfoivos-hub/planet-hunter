"""LEO-vetter (Kunimoto et al. 2025, github.com/mkunimoto/LEO-vetter): flux-level and pixel-level vetting.

Flux level: TCELightCurve.compute_flux_metrics on the detrended light curve, then every false-alarm (FA) and
false-positive (FP) test of leo_vetter.thresholds with its default thresholds. Each test that fires becomes a
flag, in LEO's own words ("FP: significant secondary", ...). `passed` means no test fired, LEO's "PC".

Pixel level (the "FP: off-target" test): per sector, a transit difference image from a 21x21 TESS FFI cutout
(Bryson's transitDiffImage, as leo_vetter.pixel does), a PRF fit to it (leo_vetter.pixel.prf_fit), and the
offset between the fitted source and the target. LEO fails the signal when the offset of the best-quality
sector is > 15". The cutouts are cached as the finished difference images, and the TESS PRF model as its
interpolated form, so a replay runs the same PRF fit offline.

A metric LEO cannot compute is NaN, and NaN never trips a threshold. So a test that did not fire because its key
metric is NaN is listed in `not_evaluated` instead of counting as passed, and a pixel stage that produced no usable sector says
ran: false with the reason.
"""

from __future__ import annotations

import contextlib
import io
import math
import os
import pickle
import tempfile
import zipfile
from importlib.metadata import version

import numpy as np

from . import cache
from .lightcurve import LightCurve

FA_TESTS = ("weak", "invalid_transits", "bad_shape", "non_unique", "chases", "dmm", "single_event", "bad_fit",
            "sinusoidal", "unphysical_duration", "asymmetric", "chi", "data_gapped")
FP_TESTS = ("odd_even", "vshaped", "large", "secondary")
# The metric without which each test cannot fire at all. If it is NaN and the test did not fire, the test was
# not evaluated (as opposed to passed). "chases" only applies to <= 5 transits and "single_event" to <= 10.
KEY_INPUT = {
    "weak": "MES", "invalid_transits": "new_MES", "bad_shape": "SHP", "non_unique": "sig_pri",
    "chases": "mean_chases", "dmm": "DMM", "single_event": "max_SES", "bad_fit": "transit_aic",
    "sinusoidal": "sine_sig", "unphysical_duration": "trap_qtran", "asymmetric": "trap_qtran_left", "chi": "CHI",
    "data_gapped": "N_gap_2.0", "odd_even": "sig_dep", "vshaped": "transit_b", "large": "Rp",
    "secondary": "sig_sec", "offset": "offset_qual",
}
APPLIES = {"chases": lambda m: m.get("N_transit", 0) <= 5, "single_event": lambda m: m.get("N_transit", 0) <= 10}
KEEP_METRICS = ("MES", "SES", "N_transit", "new_N_transit", "dep", "Rp", "Rp_err", "transit_b", "transit_RpRs",
                "sig_pri", "sig_sec", "dep_sec", "albedo", "Fred", "SHP", "CHI", "DMM", "sine_sig",
                "odd_dep", "even_dep", "sig_dep", "trap_sig_dep", "transit_sig_dep", "trap_sig_epo", "transit_sig_epo",
                "offset_mean", "offset_qual")
PIXEL_MAX_SECTORS = 3
N_PIX = 21


def star_inputs(tic_row: dict) -> tuple[dict | None, str | None]:
    """LEO's star dict from the TIC row, or (None, why)."""
    from leo_vetter.stellar import quadratic_ldc

    need = {"rad": "rad", "mass": "mass", "Teff": "Teff", "logg": "logg"}
    missing = [k for k, c in need.items() if tic_row.get(c) in (None, 0)]
    if missing:
        return None, "TIC has no " + ", ".join(missing) + " for the star"
    rho = tic_row.get("rho") or tic_row["mass"] / tic_row["rad"] ** 3
    u1, u2 = quadratic_ldc(tic_row["Teff"], tic_row["logg"])
    star = {"tic": int(tic_row["ID"]), "ra": tic_row["ra"], "dec": tic_row["dec"], "rad": tic_row["rad"],
            "mass": tic_row["mass"], "Teff": tic_row["Teff"], "logg": tic_row["logg"], "rho": rho,
            "e_rad": tic_row.get("e_rad") or 0.1 * tic_row["rad"],
            "e_mass": tic_row.get("e_mass") or 0.1 * tic_row["mass"],
            "e_Teff": tic_row.get("e_Teff") or 150.0, "u1": float(u1), "u2": float(u2)}
    return star, None


def run(cand: dict, tic_row: dict, lc: LightCurve, pixel: bool = True) -> dict:
    out = {"ran": False, "passed": None, "flags": [], "version": version("leo-vetter"), "tool": "LEO-vetter"}
    star, why = star_inputs(tic_row)
    if star is None:
        return {**out, "reason": why}
    from leo_vetter import thresholds as th
    from leo_vetter.main import TCELightCurve

    per, epo, dur = cand["period_d"], cand["t0_btjd"], cand["duration_h"] / 24
    tlc = TCELightCurve(cand["tic"], lc.time, lc.raw, lc.flux, lc.flux_err, per, epo, dur)
    with contextlib.redirect_stdout(io.StringIO()):
        tlc.compute_flux_metrics(star, verbose=False)
    out["pixel"] = run_pixel(cand, star, lc, tlc) if pixel else {"ran": False, "reason": "disabled (--no-pixel)"}
    m = tlc.metrics
    tests = [("FA", n) for n in FA_TESTS] + [("FP", n) for n in FP_TESTS]
    if "offset_qual" in m:
        tests.append(("FP", "offset"))
    flags, not_evaluated = [], []
    for kind, name in tests:
        fired, message = getattr(th, name)(m, th._default_thresholds)
        if bool(fired):
            flags.append(message)
        elif APPLIES.get(name, lambda _: True)(m) and _nan(m.get(KEY_INPUT[name])):
            # NaN never trips a threshold: this test did not pass, it could not be evaluated.
            not_evaluated.append(f"{kind}: {name} ({KEY_INPUT[name]} is NaN)")
    # Our per-test loop must agree with LEO's own verdict.
    leo_fa, leo_fp = bool(th.check_thresholds(m, "FA")), bool(th.check_thresholds(m, "FP"))
    assert leo_fa == any(f.startswith("FA") for f in flags) and leo_fp == any(f.startswith("FP") for f in flags)
    disposition = "FP" if leo_fp else "FA" if leo_fa else "PC"
    return {**out, "ran": True, "passed": not flags, "flags": flags, "disposition": disposition,
            "not_evaluated": not_evaluated, "thresholds": "leo_vetter.thresholds defaults",
            "metrics": {k: _num(m.get(k)) for k in KEEP_METRICS if k in m},
            "stellar": {k: star[k] for k in ("rad", "mass", "Teff", "logg", "rho", "u1", "u2")},
            "sectors": lc.sectors}


def run_pixel(cand: dict, star: dict, lc: LightCurve, tlc) -> dict:
    """Difference-image centroid offsets per sector; sets offset_mean / offset_qual on tlc.metrics like
    leo_vetter.pixel.pixel_vetting does."""
    from leo_vetter.pixel import planet_dict_from_metrics, prf_fit

    planet = planet_dict_from_metrics(tlc.metrics)
    try:
        cams = _cameras(star)
    except Exception as e:  # noqa: BLE001
        return {"ran": False, "reason": f"tess-point failed: {e}"}
    sectors = [s for s in reversed(lc.sectors) if s in cams][:PIXEL_MAX_SECTORS]
    per_sector, problems = [], []
    for sector in sectors:
        cam, ccd = cams[sector]
        try:
            img = difference_image(star, planet, sector, cam, ccd)
        except cache.OfflineMiss:
            raise
        except Exception as e:  # noqa: BLE001
            problems.append(f"sector {sector}: {type(e).__name__}: {e}")
            continue
        if img.get("error"):
            problems.append(f"sector {sector}: {img['error']}")
            continue
        with _prf_cache(), contextlib.redirect_stdout(io.StringIO()):
            c = prf_fit(sector, cam, ccd, img["images"], img["catalogue"])
        from transitDiffImage.tessDiffImage import pix_to_ra_dec

        fit_ra, fit_dec = pix_to_ra_dec(sector, cam, ccd, c["fit_col"], c["fit_row"])
        per_sector.append({"sector": sector, "cam": cam, "ccd": ccd, "offset_arcsec": _num(c["offset_arc"]),
                           "offset_pix": _num(c["offset_pix"]), "quality": _num(c["quality"]),
                           "fit_ra": _num(fit_ra), "fit_dec": _num(fit_dec)})
    if not per_sector:
        tlc.metrics["offset_mean"] = tlc.metrics["offset_qual"] = np.nan
        return {"ran": False, "reason": "no usable difference image: " + ("; ".join(problems) or "no sectors"),
                "sectors_tried": sectors}
    off = np.array([p["offset_arcsec"] for p in per_sector], dtype=float)
    q = np.array([p["quality"] for p in per_sector], dtype=float)
    tlc.metrics["offset_mean"] = float(np.nansum(off * q) / np.nansum(q))
    tlc.metrics["offset_qual"] = float(off[int(np.nanargmax(q))])
    best = per_sector[int(np.nanargmax(q))]
    return {"ran": True, "tool": "transitDiffImage " + version("transit-diffimage") + " + leo_vetter.pixel.prf_fit",
            "offset_arcsec": round(tlc.metrics["offset_qual"], 2),
            "source_ra": best["fit_ra"], "source_dec": best["fit_dec"],
            "offset_mean_arcsec": round(tlc.metrics["offset_mean"], 2), "threshold_arcsec": 15.0,
            "sectors": per_sector, "problems": problems}


def _cameras(star: dict) -> dict[int, tuple[int, int]]:
    def fetch():
        from tess_stars2px import tess_stars2px_function_entry as ts2px

        _, _, _, sec, cam, ccd, _, _, _ = ts2px(int(star["tic"]), star["ra"], star["dec"])
        return {int(s): [int(c), int(d)] for s, c, d in zip(sec, cam, ccd, strict=True)}

    # tess-point is local computation; cached only so the record of which camera saw the star is fixed.
    return {int(k): tuple(v) for k, v in cache.cached("tess-point", str(star["tic"]), fetch).items()}


def difference_image(star: dict, planet: dict, sector: int, cam: int, ccd: int) -> dict:
    key = f"{star['tic']}:s{sector}:P{planet['period']:.6f}:E{planet['epoch']:.5f}:D{planet['durationHours']:.4f}"

    def fetch() -> dict:
        from leo_vetter.pixel import star_dict
        from transitDiffImage import tessDiffImage

        # The raw ~100 MB cutout is kept in the work directory (not the cache) for re-runs.
        work = cache.work_root() / "tesscut" / f"s{sector}"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            _link_cutout(work, tmp, star["tic"], sector)
            sd = star_dict(star["tic"], star["ra"], star["dec"])
            sd["planetData"] = [dict(planet)]
            sd.update(sector=sector, cam=cam, ccd=ccd)
            tdi = tessDiffImage.tessDiffImage(sd, nPixOnSide=N_PIX, outputDir=tmp, cleanFiles=False)
            with _quiet_fds():  # it shells out to curl and unzip, which write progress to the terminal
                tdi.make_ffi_difference_image(thisPlanet=0, allowedBadCadences=0)
            _keep_cutout(work, tmp, star["tic"], sector)
            f = os.path.join(tmp, f"tic{star['tic']}", f"imageData_{planet['planetID']}_sector{sector}.pickle")
            if not os.path.exists(f):
                return {"error": "difference image not produced (TESScut returned no usable cutout)"}
            with open(f, "rb") as fh:
                data = pickle.load(fh)
        images, catalogue = data[0], data[1]
        if "diffImage" not in images or np.isnan(np.sum(images["diffImage"])):
            return {"error": "difference image empty or NaN (too few clean in/out-of-transit cadences)"}
        # Keep only what the PRF fit reads; the per-cadence pixel data is ~100x larger.
        return {"images": {k: v for k, v in images.items() if isinstance(v, np.ndarray) and v.ndim == 2},
                "catalogue": catalogue, "n_transits_used": len(data[5]) if len(data) > 5 else None}

    return cache.cached("diffimage", key, fetch, fmt="pickle")


@contextlib.contextmanager
def _quiet_fds():
    """Silence file descriptors 1 and 2 (child processes included), restoring them afterwards."""
    import sys

    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (*saved, devnull):
            os.close(fd)


def _link_cutout(work, tmp: str, tic: int, sector: int) -> None:
    """Re-use a kept cutout. transitDiffImage creates tic<N>/ before checking whether to unzip an existing zip,
    so it never unzips one; extract it here."""
    zipped = work / f"tic{tic}_s{sector}.zip"
    if zipped.exists():
        os.symlink(zipped, os.path.join(tmp, zipped.name))
        with zipfile.ZipFile(zipped) as z:
            z.extractall(os.path.join(tmp, f"tic{tic}"))


def _keep_cutout(work, tmp: str, tic: int, sector: int) -> None:
    src = os.path.join(tmp, f"tic{tic}_s{sector}.zip")
    if os.path.exists(src) and not os.path.islink(src):
        os.replace(src, work / f"tic{tic}_s{sector}.zip")


@contextlib.contextmanager
def _prf_cache():
    """Cache SimpleTessPRF's interpolated PRF (it otherwise downloads 25 PRF model files per camera/CCD)."""
    from transitDiffImage import tessprfmodel

    cls = tessprfmodel.SimpleTessPRF
    original = cls._prepare_prf

    def prepare(self):
        key = f"s{'1' if self.sector < 4 else '4'}:c{self.camera}:d{self.ccd}:{self.column}:{self.row}:{self.shape}"
        return tuple(cache.cached("prf", key, lambda: original(self), fmt="pickle"))

    cls._prepare_prf = prepare
    try:
        yield
    finally:
        cls._prepare_prf = original


def _nan(x) -> bool:
    try:
        return x is None or math.isnan(float(x))
    except (TypeError, ValueError):
        return False


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, 6) if math.isfinite(v) else None
