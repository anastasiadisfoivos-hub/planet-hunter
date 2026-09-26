"""The verdict: pass, flag or fail, with every reason in plain words.

fail: published evidence that the dip is not a planet on the target.
  - LEO-vetter raised a false-positive test (FP: off-target, significant secondary, radius too large, V-shaped,
    odd-even differences).
  - TRICERATOPS: NFPP > 0.1 (likely nearby false positive) or FPP > 0.5 (likely false positive).
  - Gaia DR3 has a spectroscopic orbit at the candidate's period (or x2, x1/2) that needs a stellar companion.
  - A catalogued eclipsing binary at the candidate's period (or x2, x1/2): VSX within 42" or Gaia DR3
    vari_eclipsing_binary within 63".
flag: needs a person to look.
  - Any tool or part that did not run, or LEO tests it could not evaluate.
  - LEO-vetter false-alarm (FA) tests. The candidate already passed HUNT's own detection cuts, so LEO doubting
    that the signal is a clean transit is a reason to look, not a disposition.
  - TRICERATOPS not validated (FPP >= 0.015 or NFPP >= 0.001) but not ruled out.
  - Gaia binary hint (RUWE > 1.4, or a non-single-star solution that is not the candidate's own planet).
  - A known variable at the target (VSX within 42" or a Gaia DR3 variability class) that is not the candidate.
  - Gaia neighbours bright enough to host the dip within 2 TESS pixels, when neither TRICERATOPS nor the pixel
    test ran to weigh them.
pass: every tool ran and none of the above applies.
"""

from __future__ import annotations

from .gaia import sep_to

PLANET_TYPES = ("EP",)  # VSX / Gaia class for an exoplanet transit


def summarise(v: dict, gaia_rows: list[dict] | None, target: dict | None) -> dict:
    fail, flag, notes = [], [], []
    leo, tri, gaia, var = v.get("leo") or {}, v.get("triceratops") or {}, v.get("gaia") or {}, v.get("variability") or {}

    # LEO-vetter
    if not leo.get("ran"):
        flag.append(f"LEO-vetter did not run: {leo.get('reason', 'unknown')}")
    else:
        for f in leo["flags"]:
            if f.startswith("FP: off-target") and (leo.get("pixel") or {}).get("ran"):
                fail.append("LEO-vetter " + f + ": " + _offset_text(leo["pixel"], gaia_rows, target))
            elif f.startswith("FP"):
                fail.append(f"LEO-vetter {f}")
            else:
                flag.append(f"LEO-vetter {f}")
        for ne in leo.get("not_evaluated", []):
            flag.append(f"LEO-vetter could not evaluate {ne}")
        px = leo.get("pixel") or {}
        if not px.get("ran"):
            flag.append(f"LEO-vetter pixel-level (off-target) test did not run: {px.get('reason', 'unknown')}")
        elif not any(f.startswith("FP: off-target") for f in leo["flags"]):
            notes.append(f"difference-image source is {px['offset_arcsec']}\" from the target (LEO threshold 15\")")

    # TRICERATOPS
    if not tri.get("ran"):
        flag.append(f"TRICERATOPS did not run: {tri.get('reason', 'unknown')}")
    else:
        fpp, nfpp = tri["fpp"], tri["nfpp"]
        top = "; ".join(f"{s['scenario']} on TIC {s['tic']} {s['prob']:.2f}" for s in tri.get("top_scenarios", [])[:3])
        if nfpp > 0.1:
            fail.append(f"TRICERATOPS NFPP = {nfpp:.3g} > 0.1: likely a nearby false positive (FPP = {fpp:.3g}; "
                        f"most probable: {top})")
        elif fpp > 0.5:
            fail.append(f"TRICERATOPS FPP = {fpp:.3g} > 0.5: likely a false positive (most probable: {top})")
        elif fpp >= 0.015 or nfpp >= 0.001:
            flag.append(f"TRICERATOPS FPP = {fpp:.3g}, NFPP = {nfpp:.3g}: not statistically validated "
                        "(needs FPP < 0.015 and NFPP < 0.001)")
        else:
            notes.append(f"TRICERATOPS FPP = {fpp:.3g}, NFPP = {nfpp:.3g}: meets the validation thresholds")

    # Gaia
    if not gaia.get("ran"):
        flag.append(f"Gaia DR3 check did not run: {gaia.get('reason', 'unknown')}")
    else:
        orbit = gaia.get("nss_orbit") or {}
        if orbit.get("companion") == "stellar":
            fail.append(f"Gaia DR3 {orbit['solution_type']} orbit at P = {orbit['period_d']:.5f} d "
                        f"({orbit['period_match']} the candidate's) needs a companion >= {orbit['m2_min_msun']:.3f}"
                        " Msun: a stellar eclipsing binary")
        elif orbit.get("companion") == "planetary":
            notes.append(f"Gaia DR3 {orbit['solution_type']} orbit at the candidate's period needs only "
                         f">= {orbit['m2_min_mjup']:.1f} M_Jup: the transiting companion's own reflex motion")
        elif gaia.get("binary_hint"):
            flag.extend(f"Gaia binary hint: {r}" for r in gaia["binary_reasons"])
        close = [n for n in gaia.get("neighbours", []) if n.get("could_mimic") and n["sep_arcsec"] <= 42]
        weighed = tri.get("ran") or (leo.get("pixel") or {}).get("ran")
        if close and not weighed:
            flag.append(f"{len(close)} Gaia DR3 neighbour(s) within 42\" are bright enough to cause the dip, and "
                        "neither TRICERATOPS nor the pixel test ran to weigh them")
        elif close:
            notes.append(f"{len(close)} Gaia DR3 neighbour(s) within 42\" could cause the dip "
                         "(weighed by TRICERATOPS / the pixel test)")

    # Variability
    if not var.get("vsx_ran"):
        flag.append(f"VSX check did not run: {var.get('reason', 'unknown')}")
    if not var.get("gaia_ran"):
        flag.append(f"Gaia DR3 variability check did not run: {var.get('reason', 'unknown')}")
    for e in var.get("vsx_all", []):
        if e["eclipsing"] and e["period_match"]:
            fail.append(f"VSX eclipsing binary {e['name']} ({e['type']}, P = {e['period_d']} d, {e['period_match']} "
                        f"the candidate's) {e['sep_arcsec']}\" away")
        elif e["type"].split(":")[0] in PLANET_TYPES and e["period_match"] == "same":
            notes.append(f"VSX lists {e['name']} as a transiting exoplanet at this period")
        elif e["sep_arcsec"] <= 21:
            flag.append(f"VSX variable {e['name']} ({e['type']}) {e['sep_arcsec']}\" from the target")
    gv = var.get("gaia_variable") or {}
    for eb in gv.get("eclipsing_binaries_within_63arcsec", []):
        if eb["period_match"]:
            where = "the target" if eb["is_target"] else f"Gaia DR3 {eb['source_id']}, {eb['sep_arcsec']}\" away"
            fail.append(f"Gaia DR3 eclipsing binary at P = {eb['period_d']} d ({eb['period_match']} the candidate's):"
                        f" {where}")
    if gv.get("class") and gv["class"] not in PLANET_TYPES:
        flag.append(f"Gaia DR3 classifies the target as variable: {gv['class']} (score {gv.get('class_score')})")
    elif gv.get("class") in PLANET_TYPES:
        notes.append("Gaia DR3 classifies the target's variability as an exoplanet transit (EP)")

    verdict = "fail" if fail else "flag" if flag else "pass"
    return {"verdict": verdict, "reasons": fail + flag, "notes": notes}


def _offset_text(px: dict, gaia_rows: list[dict] | None, target: dict | None) -> str:
    txt = f"the difference-image source is {px['offset_arcsec']}\" from the target (threshold 15\")"
    if gaia_rows and px.get("source_ra") is not None:
        best = min(gaia_rows, key=lambda r: sep_to(r, px["source_ra"], px["source_dec"]))
        d_fit = sep_to(best, px["source_ra"], px["source_dec"])
        if target is not None and best["source_id"] == target["source_id"]:
            txt += "; the nearest Gaia source to the fitted position is the target itself"
        else:
            d_t = sep_to(best, target["ra"], target["dec"]) if target else float("nan")
            txt += (f"; nearest Gaia DR3 source to the fitted position: {best['source_id']} "
                    f"(G = {best['phot_g_mean_mag']:.2f}, {d_t:.1f}\" from the target, {d_fit:.1f}\" from the fit)")
    return txt
