"""Give sky events a real distance, and Solar-System objects a real 3D position.

Runs after de-duplication, on the merged events. Which path an event takes depends on its type:

| type | location gets | from | basis |
|---|---|---|---|
| comet, interstellar object (JPL) | ephemeris | Horizons vectors at observed_at | - |
| asteroid seen once (ZTF) | ephemeris | IMCCE SkyBoT names it, then Horizons vectors | - |
| NEOCP / PCCP objects (MPC) | ephemeris | Scout sampled orbits, Kepler to observed_at | - |
| supernova, TDE, kilonova, AGN flare, unknown (small error) | distance | the transient's TNS redshift; else TNS host redshift, else a SIMBAD galaxy/AGN/QSO with a redshift within HOST_RADIUS | redshift / catalogue |
| nova | distance | as above, else Gaia parallax | redshift / catalogue / parallax |
| variable star, stellar flare, microlensing | distance | nearest Gaia DR3 source within GAIA_RADIUS, if parallax/error > MIN_PARALLAX_SNR | parallax |
| gamma-ray burst (and Einstein Probe transients) | distance | redshift reported in a GCN Circular | redshift |
| gravitational wave | distance | GraceDB sky-map DISTMEAN ± DISTSTD | gw_estimate |
| neutrino, anything else | distance | none | unknown |

Redshift -> distance: luminosity distance in astropy's Planck18 cosmology (the kind a GW sky map
gives, so the two compare directly). Parallax -> distance: 1000 / parallax(mas), bounds from
parallax ± its error; Gaia's small parallax zero-point is not corrected.
Every lookup is fail-soft: a failing service leaves its events at basis "unknown" and is named in
status["distances"]["lookups"].
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

from . import catalogues, ephemeris
from .models import CATEGORIES, Distance, Event
from .util import as_utc

log = logging.getLogger(__name__)

HOST_RADIUS_DEG = 2.0 / 3600
GAIA_RADIUS_DEG = 1.5 / 3600
MIN_PARALLAX_SNR = 5.0
MAX_CONE_ERROR_DEG = 2.0 / 3600  # only well-localised events get catalogue cross-matches
COSMOLOGY = "Planck18 (astropy), luminosity distance"

SOLAR_SYSTEM = set(CATEGORIES["solar_system"])
EXTRAGALACTIC = {"supernova", "tidal_disruption_event", "kilonova", "active_galaxy_flare"}
GALACTIC = {"variable_star", "stellar_flare", "microlensing"}


# ------------------------------------------------------------------ conversions


def _sig(x: float, digits: int = 5) -> float:
    return float(f"{x:.{digits}g}")


@lru_cache(maxsize=4096)
def luminosity_distance_pc(z: float) -> float:
    from astropy.cosmology import Planck18

    return float(Planck18.luminosity_distance(z).to("pc").value)


def unknown() -> Distance:
    return {"pc": None, "pc_low": None, "pc_high": None, "redshift": None, "basis": "unknown"}


def from_redshift(z: float, basis: str = "redshift") -> Distance:
    return {"pc": _sig(luminosity_distance_pc(round(z, 6))), "pc_low": None, "pc_high": None,
            "redshift": z, "basis": basis}  # type: ignore[typeddict-item]


def from_parallax(plx_mas: float, err_mas: float) -> Distance | None:
    if not (plx_mas and err_mas and plx_mas > 0 and plx_mas / err_mas > MIN_PARALLAX_SNR):
        return None
    return {"pc": _sig(1000 / plx_mas), "pc_low": _sig(1000 / (plx_mas + err_mas)),
            "pc_high": _sig(1000 / (plx_mas - err_mas)), "redshift": None, "basis": "parallax"}


def from_gw(mean_mpc: float, std_mpc: float | None) -> Distance:
    lo = hi = None
    if std_mpc is not None:
        lo, hi = _sig(max(0.0, mean_mpc - std_mpc) * 1e6), _sig((mean_mpc + std_mpc) * 1e6)
    return {"pc": _sig(mean_mpc * 1e6), "pc_low": lo, "pc_high": hi, "redshift": None, "basis": "gw_estimate"}


def has_distance(e: Event) -> bool:
    loc = e["location"]
    return loc["frame"] == "sky" and ("ephemeris" in loc or (loc.get("distance") or {}).get("pc") is not None)


# ------------------------------------------------------------------ planning


def plan(e: Event) -> str:
    """Which distance path an event takes (see the module table)."""
    if e["location"]["frame"] != "sky":
        return "none"
    t, raw = e["type"], e["raw"]
    if t in SOLAR_SYSTEM:
        if raw.get("pdes"):
            return "horizons"
        if raw.get("temp_designation"):
            return "scout"
        return "identify" if t == "asteroid" else "unknown"
    if t == "gravitational_wave":
        return "gw"
    if t == "gamma_ray_burst" or "redshift_circulars" in raw:
        return "gcn"
    small = e["location"]["error_deg"] <= MAX_CONE_ERROR_DEG
    if t == "nova":
        return "nova" if small or raw.get("redshift") else "unknown"
    if t in EXTRAGALACTIC or t == "unknown":
        return "extragalactic" if small or raw.get("redshift") else "unknown"
    if t in GALACTIC:
        return "galactic" if small else "unknown"
    return "unknown"


# ------------------------------------------------------------------ enrichment


def enrich(events: list[Event]) -> dict[str, Any]:
    """Add location.distance / location.ephemeris to every sky event, in place. Returns the
    status["distances"] block."""
    plans = [plan(e) for e in events]
    by_plan: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(plans):
        by_plan[p].append(i)

    needs_z = [i for i in by_plan["extragalactic"] + by_plan["nova"] if not events[i]["raw"].get("redshift")]
    stars = by_plan["galactic"] + by_plan["nova"]

    def points(idx: list[int]) -> list[tuple[float, float]]:
        return [(events[i]["location"]["ra_deg"], events[i]["location"]["dec_deg"]) for i in idx]

    jobs: dict[str, Callable[[], Any]] = {}
    if needs_z:
        earliest = min(as_utc(events[i]["raw"].get("first_observed_at") or events[i]["observed_at"]) for i in needs_z)
        jobs["tns"] = lambda: catalogues.tns_redshifts(earliest)
        jobs["simbad"] = lambda: catalogues.simbad_galaxies(points(needs_z), HOST_RADIUS_DEG)
    if stars:
        jobs["gaia"] = lambda: catalogues.gaia_sources(points(stars), GAIA_RADIUS_DEG)
    if by_plan["horizons"]:
        jobs["horizons"] = lambda: _each(events, by_plan["horizons"], lambda e: ephemeris.designated(
            e["raw"]["pdes"], as_utc(e["observed_at"])))
    if by_plan["scout"]:
        jobs["scout"] = lambda: _each(events, by_plan["scout"], lambda e: ephemeris.unconfirmed(
            e["raw"]["temp_designation"], as_utc(e["observed_at"])))
    if by_plan["identify"]:
        jobs["identify"] = lambda: _each(events, by_plan["identify"], lambda e: ephemeris.one_off(
            e["location"]["ra_deg"], e["location"]["dec_deg"], as_utc(e["observed_at"]), e["source"]))
    if by_plan["gcn"]:
        jobs["gcn"] = lambda: _each(events, by_plan["gcn"], lambda e: catalogues.gcn_redshift(
            e["raw"].get("redshift_circulars") or []))

    results: dict[str, Any] = {}
    lookups: dict[str, dict] = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {name: pool.submit(fn) for name, fn in jobs.items()}
        for name, fut in futures.items():
            try:
                results[name] = fut.result()
                lookups[name] = {"ok": True, "error": None}
            except Exception as exc:  # noqa: BLE001 - one broken lookup must not stop the feed
                log.warning("distance lookup %s failed: %s", name, exc)
                lookups[name] = {"ok": False, "error": str(exc)[:300]}
    for name in ("horizons", "scout", "identify", "gcn"):
        if name in results:
            errs = [err for _, err in results[name].values() if err]
            lookups[name]["failed_objects"] = len(errs)
            if errs:
                lookups[name]["error"] = errs[0][:300]
    if "tns" in results:
        lookups["tns"].update(rows=len(results["tns"].rows), since=results["tns"].start,
                              truncated=results["tns"].truncated)

    simbad = dict(zip(needs_z, results.get("simbad") or [None] * len(needs_z), strict=True))
    gaia = dict(zip(stars, results.get("gaia") or [None] * len(stars), strict=True))
    tns = results.get("tns")

    for i, (e, p) in enumerate(zip(events, plans, strict=True)):
        if p == "none":
            continue
        loc, raw = e["location"], e["raw"]
        if p in ("horizons", "scout", "identify"):
            got, err = (results.get(p) or {}).get(i, (None, None))
            if got:
                loc["ephemeris"] = got[0]
                raw["distance_from"] = got[1]
                if p == "scout":
                    raw["ephemeris_spread"] = got[2]
                if p == "identify":
                    raw.update(got[2])
                    raw["names"] = sorted({*raw.get("names", []), got[2]["identified_as"]})
            else:
                loc["distance"] = unknown()
                if p == "identify" and p in results:
                    raw["distance_note"] = (f"lookup failed: {err.split(': ', 1)[-1][:120]}" if err else
                                            "no known asteroid within 5 arcsec at that time (IMCCE SkyBoT)")
            continue
        dist, why = _choose(e, p, i, tns, simbad, gaia, results)
        loc["distance"] = dist or unknown()
        if dist:
            raw["distance_from"] = why
    return {"cosmology": COSMOLOGY, "lookups": lookups, "by_type": coverage_by_type(events)}


def _each(events: list[Event], idx: list[int], fn: Callable[[Event], Any]) -> dict[int, tuple[Any, str | None]]:
    """Per-object lookups: one object's failure is recorded, the rest go on."""
    out = {}
    for i in idx:
        try:
            out[i] = (fn(events[i]), None)
        except Exception as exc:  # noqa: BLE001
            log.warning("distance lookup for %s failed: %s", events[i]["id"], exc)
            out[i] = (None, f"{events[i]['id']}: {exc}")
    return out


def _choose(e: Event, p: str, i: int, tns, simbad: dict, gaia: dict, results: dict) -> tuple[Distance | None, str]:
    raw = e["raw"]
    if p == "gw":
        d = raw.get("distance_mpc")
        if d and d.get("mean"):
            return from_gw(d["mean"], d.get("std")), f"GraceDB sky map of {e['id'].split(':', 1)[1]} (DISTMEAN ± DISTSTD)"
        return None, ""
    if p == "gcn":
        got, _ = (results.get("gcn") or {}).get(i, (None, None))
        if got:
            z, cid, subject = got
            return from_redshift(z), f"GCN Circular {cid}: {subject}"[:200]
        return None, ""
    if p in ("extragalactic", "nova"):
        z = raw.get("redshift")
        if z and z > 0:
            names = raw.get("names") or [e["id"]]
            name = next((n for n in names if n.startswith(("SN ", "AT ", "TDE "))), names[0])
            return from_redshift(float(z)), f"TNS redshift of {name}"
        loc = e["location"]
        if tns and (r := tns.match(raw.get("names") or [], loc["ra_deg"], loc["dec_deg"], HOST_RADIUS_DEG)):
            if r["redshift"] and r["redshift"] > 0:
                return from_redshift(r["redshift"]), f"TNS redshift of {r['name']}"
            if r["host_redshift"] and r["host_redshift"] > 0:
                host = f" ({r['host']})" if r["host"] else ""
                return from_redshift(r["host_redshift"], "catalogue"), f"TNS host-galaxy redshift of {r['name']}{host}"
        if s := simbad.get(i):
            return from_redshift(float(s["rvz_redshift"]), "catalogue"), (
                f"SIMBAD {s['main_id'].strip()} ({s['otype'].strip()}) within 2 arcsec"
            )
    if p in ("galactic", "nova") and (g := gaia.get(i)):
        plx, err = g["parallax"], g["parallax_error"]
        if plx is not None and err and (d := from_parallax(plx, err)):
            return d, f"Gaia DR3 {g['source_id']} parallax {plx:.3f} ± {err:.3f} mas"
        # A counterpart whose parallax is too uncertain: say so rather than guess a distance.
        snr = f"parallax/error {plx / err:.1f} < {MIN_PARALLAX_SNR:g}" if plx is not None and err else "no parallax"
        raw["distance_note"] = f"Gaia DR3 {g['source_id']} within {GAIA_RADIUS_DEG * 3600:g} arcsec, {snr}"
    return None, ""


# ------------------------------------------------------------------ coverage


def coverage_by_type(events: list[Event]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for t in sorted({e["type"] for e in events if e["location"]["frame"] == "sky"}):
        sky = [e for e in events if e["type"] == t and e["location"]["frame"] == "sky"]
        k = sum(has_distance(e) for e in sky)
        bases = Counter("ephemeris" if "ephemeris" in e["location"] else e["location"]["distance"]["basis"]
                        for e in sky if "ephemeris" in e["location"] or "distance" in e["location"])
        out[t] = {"events": len(sky), "with_distance": k, "share": round(k / len(sky), 3), "basis": dict(bases)}
    return out


def coverage_by_source(events: list[Event], sources: list[str]) -> dict[str, dict]:
    """Per source: its sky events (a merged event counts for every member) and the share with a
    distance or an ephemeris."""
    out = {}
    for name in sources:
        sky = [e for e in events if e["location"]["frame"] == "sky"
               and any(s["source"] == name for s in e["raw"].get("sources", [{"source": e["source"]}]))]
        k = sum(has_distance(e) for e in sky)
        out[name] = {"sky_events": len(sky), "with_distance": k,
                     "share": round(k / len(sky), 3) if sky else None}
    return out

