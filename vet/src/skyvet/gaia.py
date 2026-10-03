"""Gaia DR3 around the target: RUWE, non-single-star flag, neighbours that could host the signal, variability.

One ADQL query to the ESA Gaia archive (free, public TAP), cached. It returns every Gaia DR3 source within
NEIGHBOUR_RADIUS of the target with its astrometric quality, joined to the DR3 variability classifier
(vari_classifier_result) and eclipsing-binary (vari_eclipsing_binary) tables.

- Target: the source with the TIC's Gaia DR2 id (DR2 and DR3 ids agree for almost all stars), else the nearest
  source within 3" of the TIC position propagated to epoch 2016.0 whose G is within 1 mag of the TIC's.
- binary_hint: RUWE > 1.4 (Lindegren et al. 2021: a poor single-star astrometric fit, often an unresolved
  companion) or a DR3 non-single-star solution (non_single_star > 0: bit 1 astrometric, 2 spectroscopic,
  4 eclipsing). A two-body orbit is fetched from gaiadr3.nss_two_body_orbit. For a spectroscopic (SB1) orbit
  the mass function gives the companion's minimum mass (sin i = 1, host mass from the TIC). An orbit at the
  candidate's period (1%, x2, x1/2) needing >= 0.075 Msun is the dip's eclipsing binary; one needing < 13 M_Jup
  is the transiting planet itself (e.g. WASP-18 b), which is not a binary hint.
- Neighbours: every other source within 3 TESS pixels (63"). A neighbour could produce the dip if eclipsing
  all of its light would be enough: required depth = depth x 10^(0.4 dG) <= 1, where dG = G_nb - G_target
  (the aperture is assumed to hold both stars' light in full, which is the conservative case).
"""

from __future__ import annotations

import math

import requests

from . import cache

TAP_URL = "https://gea.esac.esa.int/tap-server/tap/sync"
NEIGHBOUR_RADIUS_ARCSEC = 63.0  # 3 TESS pixels
RUWE_LIMIT = 1.4
STELLAR_MIN_MSUN = 0.075  # hydrogen-burning limit
PLANET_MAX_MJUP = 13.0  # deuterium-burning limit
MJUP_PER_MSUN = 1047.57
NSS_BITS = {1: "astrometric", 2: "spectroscopic", 4: "eclipsing"}
MAX_NEIGHBOURS_LISTED = 25


def tap(query: str) -> list[dict]:
    r = requests.post(TAP_URL, data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": query},
                      timeout=120)
    r.raise_for_status()
    d = r.json()
    names = [c["name"] for c in d["metadata"]]
    return [dict(zip(names, row, strict=True)) for row in d["data"]]


def field(ra: float, dec: float, radius_arcsec: float = NEIGHBOUR_RADIUS_ARCSEC) -> list[dict]:
    q = f"""
SELECT g.source_id, g.ra, g.dec, g.phot_g_mean_mag, g.bp_rp, g.parallax, g.ruwe, g.non_single_star,
       g.ipd_frac_multi_peak, g.phot_variable_flag,
       v.best_class_name, v.best_class_score, e.frequency AS eb_frequency,
       DISTANCE(POINT('ICRS', g.ra, g.dec), POINT('ICRS', {ra:.7f}, {dec:.7f})) * 3600 AS sep_arcsec
FROM gaiadr3.gaia_source AS g
LEFT OUTER JOIN gaiadr3.vari_classifier_result AS v ON v.source_id = g.source_id
LEFT OUTER JOIN gaiadr3.vari_eclipsing_binary AS e ON e.source_id = g.source_id
WHERE 1 = CONTAINS(POINT('ICRS', g.ra, g.dec), CIRCLE('ICRS', {ra:.7f}, {dec:.7f}, {radius_arcsec / 3600:.6f}))
ORDER BY sep_arcsec"""
    key = f"{ra:.6f}:{dec:.6f}:{radius_arcsec}"
    return cache.cached("gaia-field", key, lambda: tap(q))


def epoch2016(tic_row: dict) -> tuple[float, float]:
    """TIC positions are at J2000; move them to Gaia DR3's J2016.0 with the TIC proper motion."""
    ra, dec = tic_row["ra"], tic_row["dec"]
    pmra, pmdec = tic_row.get("pmRA") or 0.0, tic_row.get("pmDEC") or 0.0
    dt = 16.0
    return (ra + pmra * dt / 3.6e6 / math.cos(math.radians(dec)), dec + pmdec * dt / 3.6e6)


def run(cand: dict, tic_row: dict) -> tuple[dict, list[dict], dict | None]:
    """(gaia block, the raw field rows, the target row). Raises on network failure; the caller reports it."""
    ra, dec = epoch2016(tic_row)
    rows = field(ra, dec)
    for r in rows:  # separations from the J2016 target position
        r["sep_arcsec"] = float(r["sep_arcsec"])
    target, how = _identify(rows, tic_row)
    if target is None:
        return ({"ran": False, "reason": "no Gaia DR3 source matches the TIC star (id or 3\" + 1 mag)",
                 "ruwe": None, "neighbours": [], "binary_hint": None}, rows, None)
    depth = (cand.get("depth_ppm") or 0) / 1e6
    g0 = target["phot_g_mean_mag"]
    neighbours = []
    for r in rows:
        if r["source_id"] == target["source_id"] or r["phot_g_mean_mag"] is None:
            continue
        sep = _sep(target, r)
        dg = r["phot_g_mean_mag"] - g0
        need = depth * 10 ** (0.4 * dg) if depth > 0 else None
        neighbours.append({"source_id": str(r["source_id"]), "sep_arcsec": round(sep, 2),
                           "gmag": round(r["phot_g_mean_mag"], 3), "delta_g": round(dg, 3),
                           "ra": r["ra"], "dec": r["dec"],
                           "required_depth": None if need is None else round(need, 4),
                           "could_mimic": None if need is None else bool(need <= 1.0)})
    neighbours.sort(key=lambda n: n["sep_arcsec"])
    ruwe = target.get("ruwe")
    nss = target.get("non_single_star") or 0
    reasons = []
    if ruwe is not None and ruwe > RUWE_LIMIT:
        reasons.append(f"RUWE {ruwe:.2f} > {RUWE_LIMIT} (poor single-star astrometric fit; possible unresolved "
                       "companion)")
    orbit = None
    if nss:
        kinds = [v for b, v in NSS_BITS.items() if nss & b]
        orbit = nss_orbit(target["source_id"], cand.get("period_d"), tic_row.get("mass"))
        if orbit and orbit.get("companion") == "planetary":
            pass  # the orbit is the candidate's own planet: evidence for it, not a binary hint
        else:
            what = f"Gaia DR3 non-single-star solution ({' + '.join(kinds)}, non_single_star = {nss})"
            if orbit and orbit.get("period_d"):
                what += f", orbit P = {orbit['period_d']:.4f} d"
                if orbit.get("m2_min_msun") is not None:
                    what += f", companion >= {orbit['m2_min_msun']:.3f} Msun"
            reasons.append(what)
    mimics = [n for n in neighbours if n["could_mimic"]]
    block = {
        "ran": True, "catalogue": "Gaia DR3", "source_id": str(target["source_id"]), "matched_by": how,
        "gmag": round(g0, 3), "ruwe": None if ruwe is None else round(ruwe, 3), "non_single_star": nss,
        "ipd_frac_multi_peak": target.get("ipd_frac_multi_peak"), "nss_orbit": orbit,
        "binary_hint": bool(reasons), "binary_reasons": reasons,
        "radius_arcsec": NEIGHBOUR_RADIUS_ARCSEC, "n_neighbours": len(neighbours),
        "n_could_mimic": len(mimics),
        "neighbours": (mimics + [n for n in neighbours if not n["could_mimic"]])[:MAX_NEIGHBOURS_LISTED],
    }
    return block, rows, target


def nss_orbit(source_id, p_cand: float | None, m1_msun: float | None) -> dict | None:
    q = ("SELECT nss_solution_type, period, period_error, semi_amplitude_primary, semi_amplitude_primary_error, "
         f"eccentricity FROM gaiadr3.nss_two_body_orbit WHERE source_id = {int(source_id)}")
    rows = cache.cached("gaia-nss", str(source_id), lambda: tap(q))
    if not rows:
        return None
    r = rows[0]
    out = {"solution_type": r["nss_solution_type"], "period_d": r["period"], "period_error_d": r["period_error"],
           "k1_kms": r["semi_amplitude_primary"], "eccentricity": r["eccentricity"]}
    if p_cand and r["period"]:
        from .variability import period_match

        out["period_match"] = period_match(p_cand, r["period"])
    if r["period"] and r["semi_amplitude_primary"] and m1_msun:
        m2 = min_companion_mass(r["period"], r["semi_amplitude_primary"], r["eccentricity"] or 0.0, m1_msun)
        out["m2_min_msun"] = round(m2, 5)
        out["m2_min_mjup"] = round(m2 * MJUP_PER_MSUN, 2)
        if out.get("period_match"):
            out["companion"] = ("stellar" if m2 >= STELLAR_MIN_MSUN else
                                "planetary" if m2 * MJUP_PER_MSUN < PLANET_MAX_MJUP else "brown dwarf range")
    return out


def min_companion_mass(p_days: float, k_kms: float, ecc: float, m1_msun: float) -> float:
    """Minimum companion mass [Msun] from the SB1 mass function (sin i = 1): solves
    m2^3 / (m1 + m2)^2 = P K^3 (1 - e^2)^1.5 / (2 pi G)."""
    g, msun = 6.674e-11, 1.98892e30
    f = p_days * 86400 * (k_kms * 1e3) ** 3 * (1 - ecc**2) ** 1.5 / (2 * math.pi * g) / msun
    lo, hi = 0.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if mid**3 / (m1_msun + mid) ** 2 < f:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _identify(rows: list[dict], tic_row: dict) -> tuple[dict | None, str]:
    dr2 = str(tic_row.get("GAIA") or "")
    for r in rows:
        if dr2 and str(r["source_id"]) == dr2:
            return r, "TIC Gaia DR2 id"
    gt = tic_row.get("GAIAmag")
    near = [r for r in rows if r["sep_arcsec"] <= 3.0 and r["phot_g_mean_mag"] is not None
            and (gt is None or abs(r["phot_g_mean_mag"] - gt) < 1.0)]
    if near:
        return min(near, key=lambda r: r["sep_arcsec"]), "nearest within 3\" and 1 mag of the TIC G"
    return None, ""


def _sep(a: dict, b: dict) -> float:
    ra1, d1, ra2, d2 = map(math.radians, (a["ra"], a["dec"], b["ra"], b["dec"]))
    s = math.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * math.cos(d2) * math.sin((ra2 - ra1) / 2) ** 2
    return math.degrees(2 * math.asin(math.sqrt(s))) * 3600


def sep_to(row: dict, ra: float, dec: float) -> float:
    return _sep(row, {"ra": ra, "dec": dec})
