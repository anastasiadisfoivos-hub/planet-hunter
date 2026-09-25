"""Catalogue lookups: the target's TIC 8.2 row and Gaia DR3 stars around it, plus epoch/magnitude helpers."""

from __future__ import annotations

import math

import numpy as np

from .cache import DAY, cached_json, retry

TIC_TTL_S = 30 * DAY
GAIA_TTL_S = 30 * DAY
GAIA_EPOCH = 2016.0  # Gaia DR3 reference epoch (Julian year)
BTJD_OFFSET = 2457000.0


def _num(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _query_tic(tic_id: int) -> dict:
    from astroquery.mast import Catalogs

    rows = retry(lambda: Catalogs.query_criteria(catalog="Tic", ID=int(tic_id)))
    if len(rows) == 0:
        raise LookupError(f"TIC {tic_id} not found in TIC 8.2")
    r = rows[0]
    return {
        "tic_id": int(r["ID"]),
        "ra_deg": float(r["ra"]),  # TIC positions are epoch 2000 (Gaia propagated back)
        "dec_deg": float(r["dec"]),
        "pmra_masyr": _num(r["pmRA"]),
        "pmdec_masyr": _num(r["pmDEC"]),
        "tmag": _num(r["Tmag"]),
        "gaia_dr2_id": str(r["GAIA"]) if r["GAIA"] not in (None, "") and str(r["GAIA"]) != "--" else None,
        "gmag": _num(r["GAIAmag"]),
        "contratio": _num(r["contratio"]),
    }


def tic_row(tic_id: int, refresh: bool = False) -> dict:
    return cached_json("tic", str(int(tic_id)), TIC_TTL_S, lambda: _query_tic(tic_id), refresh)


def _query_gaia(ra: float, dec: float, radius_arcsec: float, gmax: float) -> list[dict]:
    from astroquery.gaia import Gaia

    Gaia.ROW_LIMIT = -1
    adql = (
        "SELECT source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, bp_rp FROM gaiadr3.gaia_source "
        f"WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra:.7f}, {dec:.7f}, {radius_arcsec / 3600:.6f})) "
        f"AND phot_g_mean_mag < {gmax:.2f}"
    )
    table = retry(lambda: Gaia.launch_job(adql).get_results())
    stars = []
    for r in table:
        stars.append(
            {
                "gaia_id": str(int(r["source_id"])),
                "ra_deg": float(r["ra"]),
                "dec_deg": float(r["dec"]),
                "pmra_masyr": _num(r["pmra"]),
                "pmdec_masyr": _num(r["pmdec"]),
                "gmag": float(r["phot_g_mean_mag"]),
                "bp_rp": _num(r["bp_rp"]),
            }
        )
    return sorted(stars, key=lambda s: s["gmag"])


def _query_vizier(ra: float, dec: float, radius_arcsec: float, gmax: float) -> list[dict]:
    """Same stars from the CDS VizieR copy of Gaia DR3 (I/355/gaiadr3), used when the ESA archive is down."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.vizier import Vizier

    v = Vizier(columns=["Source", "RA_ICRS", "DE_ICRS", "pmRA", "pmDE", "Gmag", "BP-RP"],
               column_filters={"Gmag": f"<{gmax:.2f}"}, row_limit=-1)
    tables = retry(lambda: v.query_region(SkyCoord(ra, dec, unit="deg"), radius=radius_arcsec * u.arcsec,
                                          catalog="I/355/gaiadr3"))
    stars = []
    for r in tables[0] if len(tables) else []:
        stars.append({"gaia_id": str(int(r["Source"])), "ra_deg": float(r["RA_ICRS"]), "dec_deg": float(r["DE_ICRS"]),
                      "pmra_masyr": _num(r["pmRA"]), "pmdec_masyr": _num(r["pmDE"]), "gmag": float(r["Gmag"]),
                      "bp_rp": _num(r["BP-RP"])})
    return sorted(stars, key=lambda s: s["gmag"])


def gaia_cone(ra: float, dec: float, radius_arcsec: float, gmax: float, refresh: bool = False) -> list[dict]:
    """Gaia DR3 sources (epoch 2016.0) within radius_arcsec, brighter than gmax, brightest first."""
    key = f"{ra:.6f},{dec:.6f},{radius_arcsec:.0f},{gmax:.1f}"

    def compute() -> list[dict]:
        try:
            return _query_gaia(ra, dec, radius_arcsec, gmax)
        except Exception:
            return _query_vizier(ra, dec, radius_arcsec, gmax)

    return cached_json("gaia", key, GAIA_TTL_S, compute, refresh)


def gaia_to_tmag(gmag: float, bp_rp: float | None) -> float:
    """TESS magnitude from Gaia G and BP-RP (Stassun et al. 2019, AJ 158, 138, eq. 1); G-0.43 without a colour."""
    if bp_rp is None or not np.isfinite(bp_rp):
        return gmag - 0.430
    c = float(np.clip(bp_rp, -0.2, 3.5))
    return gmag - 0.00522555 * c**3 + 0.0891337 * c**2 - 0.633923 * c + 0.0324473


def btjd_to_jyear(btjd: float) -> float:
    return 2000.0 + (btjd + BTJD_OFFSET - 2451545.0) / 365.25


def propagate(ra: float, dec: float, pmra: float | None, pmdec: float | None, from_year: float,
              to_year: float) -> tuple[float, float]:
    """Linear proper-motion propagation (pmra already includes cos δ, mas/yr). Missing PMs → no motion."""
    dt = to_year - from_year
    pmra = pmra or 0.0
    pmdec = pmdec or 0.0
    dec_new = dec + pmdec * dt / 3.6e6
    ra_new = ra + pmra * dt / 3.6e6 / max(math.cos(math.radians(dec)), 1e-6)
    return ra_new, dec_new


def sky_offset_arcsec(ra0: float, dec0: float, ra: float, dec: float) -> tuple[float, float]:
    """(east, north) offset of (ra, dec) from (ra0, dec0) in arcsec; small-angle approximation."""
    east = (ra - ra0 + 540.0) % 360.0 - 180.0
    return east * math.cos(math.radians(dec0)) * 3600.0, (dec - dec0) * 3600.0


def match_target(tic: dict, stars: list[dict]) -> dict | None:
    """The Gaia DR3 source that is the TIC target: the DR2 id if it survived into DR3, else the nearest source
    within 3″ (at 2016.0) whose G agrees within 1 mag."""
    if tic.get("gaia_dr2_id"):
        for s in stars:
            if s["gaia_id"] == tic["gaia_dr2_id"]:
                return s
    ra16, dec16 = propagate(tic["ra_deg"], tic["dec_deg"], tic.get("pmra_masyr"), tic.get("pmdec_masyr"), 2000.0,
                            GAIA_EPOCH)
    best, best_d = None, 3.0
    for s in stars:
        e, n = sky_offset_arcsec(ra16, dec16, s["ra_deg"], s["dec_deg"])
        d = math.hypot(e, n)
        if d < best_d and (tic.get("gmag") is None or abs(s["gmag"] - tic["gmag"]) < 1.0):
            best, best_d = s, d
    return best
