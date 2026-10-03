"""Known variability of the target and its neighbours: AAVSO VSX and Gaia DR3.

- VSX (Watson et al. 2006, the AAVSO International Variable Star Index, via VizieR B/vsx/vsx): every entry
  within 2 TESS pixels (42"). `vsx_match` is the nearest one, with its type, period and whether that period is
  the candidate's (within 1%, or x2 / x1/2: an eclipsing binary's period is often twice the dip period).
- Gaia DR3 (Eyer et al. 2023): the target's phot_variable_flag and vari_classifier_result class, and every
  source within 63" in vari_eclipsing_binary, with its period (1 / frequency) and the same period match.
"""

from __future__ import annotations

from . import cache
from .gaia import sep_to

VSX_RADIUS_ARCSEC = 42.0
PERIOD_TOL = 0.01
ECLIPSING_VSX = ("E", "EA", "EB", "EW", "ELL")  # VSX type prefixes for eclipsing / ellipsoidal binaries


def period_match(p_cand: float, p_other: float | None) -> str | None:
    if not p_other or p_other <= 0:
        return None
    for label, k in (("same", 1.0), ("x2", 2.0), ("x1/2", 0.5)):
        if abs(p_other / (k * p_cand) - 1) < PERIOD_TOL:
            return label
    return None


def vsx(ra: float, dec: float) -> list[dict]:
    def fetch() -> list[dict]:
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        from astroquery.vizier import Vizier

        v = Vizier(columns=["Name", "Type", "Period", "max", "min", "RAJ2000", "DEJ2000", "OID"], row_limit=-1)
        res = v.query_region(SkyCoord(ra, dec, unit="deg"), radius=VSX_RADIUS_ARCSEC * u.arcsec,
                             catalog="B/vsx/vsx")
        out = []
        if len(res):
            for r in res[0]:
                out.append({"name": str(r["Name"]), "type": str(r["Type"]),
                            "period_d": _f(r["Period"]), "max": _f(r["max"]), "min": _f(r["min"]),
                            "ra": float(r["RAJ2000"]), "dec": float(r["DEJ2000"]), "oid": int(r["OID"])})
        return out

    return cache.cached("vsx", f"{ra:.6f}:{dec:.6f}:{VSX_RADIUS_ARCSEC}", fetch)


def run(cand: dict, ra: float, dec: float, gaia_rows: list[dict] | None, target: dict | None) -> dict:
    """Both sources are tried; each says whether it ran (vsx_ran, gaia_ran). ran = both did."""
    p = cand["period_d"]
    out: dict = {"ran": False, "vsx_ran": False, "gaia_ran": False, "vsx_match": None, "gaia_variable": None}
    problems = []
    try:
        entries = vsx(ra, dec)
        for e in entries:
            e["sep_arcsec"] = round(sep_to(e, ra, dec), 2)
            e["period_match"] = period_match(p, e["period_d"])
            e["eclipsing"] = e["type"].split("/")[0].split("+")[0].rstrip(":") in ECLIPSING_VSX
        entries.sort(key=lambda e: e["sep_arcsec"])
        out.update(vsx_ran=True, vsx_match=entries[0] if entries else None, vsx_all=entries)
    except cache.OfflineMiss:
        raise
    except Exception as e:  # noqa: BLE001
        problems.append(f"VSX query failed: {type(e).__name__}: {e}")
    if gaia_rows is None or target is None:
        problems.append("Gaia DR3 variability not available (see the gaia block)")
    else:
        ebs = []
        for r in gaia_rows:
            if r.get("eb_frequency"):
                per = 1.0 / float(r["eb_frequency"])
                ebs.append({"source_id": str(r["source_id"]), "is_target": r["source_id"] == target["source_id"],
                            "sep_arcsec": round(sep_to(r, target["ra"], target["dec"]), 2),
                            "gmag": r["phot_g_mean_mag"], "period_d": round(per, 6),
                            "period_match": period_match(p, per)})
        out["gaia_ran"] = True
        out["gaia_variable"] = {
            "phot_variable_flag": target.get("phot_variable_flag"),
            "class": target.get("best_class_name"), "class_score": target.get("best_class_score"),
            "eclipsing_binaries_within_63arcsec": ebs,
        }
    out["ran"] = out["vsx_ran"] and out["gaia_ran"]
    if problems:
        out["reason"] = "; ".join(problems)
    return out


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v
