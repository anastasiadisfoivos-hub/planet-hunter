"""alerts(sphere, since, until): Rubin alert-stream objects inside a sphere, as Discoveries.

Broker: Fink (https://api.lsst.fink-portal.org), no login. One Discovery per *object*:
  - rubin:obj:<diaObjectId>  for everything Fink's cone search returns (static-sky transients
    and variables); detected_at and cutouts come from the object's latest alert.
  - rubin:ss:<ssObjectId>    for detections Rubin associated to a known solar-system orbit,
    read from Fink's SSO bulk file (see sso.py).

Honesty: types are Fink's best guess (or a catalogue label it cross-matched) with its number.
Nothing here says "discovered".
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from astropy.time import Time

from . import classes, fink, sso
from .http import UpstreamError
from .models import CatchType, Discovery, Sphere, validate_sphere
from .util import as_utc, float_or_none, sep_deg

log = logging.getLogger(__name__)

ORIGIN = "Fink LSST broker"


def alerts(
    sphere: Sphere,
    since: datetime | str,
    until: datetime | str,
    *,
    include_solar_system: bool = True,
    light_curves: bool = False,
    max_cutout_lookups: int = 25,
) -> list[Discovery]:
    """Discoveries for objects with at least one Rubin alert inside `sphere` during [since, until].

    light_curves: also fetch each object's detections (one extra request per object).
    max_cutout_lookups: solar-system cutouts need one Fink /sso call per object; only the most
        recent this-many objects get them, the rest have cutouts set to None.
    """
    sphere = validate_sphere(sphere)
    t0, t1 = as_utc(since), as_utc(until)
    if t1 <= t0:
        raise ValueError("until must be after since")
    m0, m1 = _mjd_tai(t0), _mjd_tai(t1)
    ttl = 900.0 if t1 > datetime.now(UTC) else 6 * 3600.0

    rows: dict[int, dict[str, Any]] = {}
    for ra, dec, rad in fink.cone_tiles(sphere["ra_deg"], sphere["dec_deg"], sphere["radius_deg"]):
        for row in fink.conesearch(ra, dec, rad, m0, m1, ttl=ttl):
            if sep_deg(sphere["ra_deg"], sphere["dec_deg"], row["r:ra"], row["r:dec"]) > sphere["radius_deg"]:
                continue
            oid = int(row["r:diaObjectId"])
            if oid not in rows or row["r:midpointMjdTai"] > rows[oid]["r:midpointMjdTai"]:
                rows[oid] = row

    out = [fink_row_to_discovery(r) for r in rows.values()]
    if light_curves:
        for d in out:
            d["light_curve"] = light_curve(d["raw"]["diaObjectId"])

    if include_solar_system:
        out += _solar_system(sphere, m0, m1, max_cutout_lookups)

    out.sort(key=lambda d: d["detected_at"], reverse=True)
    return out


# ---------------------------------------------------------------- static-sky objects (Fink rows)


def fink_row_to_discovery(row: dict[str, Any]) -> Discovery:
    oid = int(row["r:diaObjectId"])
    src = int(row["r:diaSourceId"])
    catch, confidence, basis = classify_fink_row(row)
    tns_name = classes.present(row.get("f:xm_tns_fullname"))
    gaia_name = classes.present(row.get("f:xm_gaiadr3_DR3Name"))
    catalogued = bool(row.get("f:is_cataloged") or tns_name or classes.present(row.get("f:xm_vsx_Type")))
    n_alerts = int(row.get("r:nDiaSources") or 1)

    links = [{"label": "Fink portal", "url": fink.portal_url(oid)}]
    if tns_name:
        links.append({"label": f"TNS {tns_name}", "url": f"https://www.wis-tns.org/object/{tns_name.split(' ', 1)[-1]}"})

    return {
        "id": f"rubin:obj:{oid}",
        "type": catch,
        "confidence": confidence,
        "source": "rubin",
        "origin": ORIGIN,
        "ra_deg": round(float(row["r:ra"]), 7),
        "dec_deg": round(float(row["r:dec"]), 7),
        "detected_at": _iso(row["r:midpointMjdTai"]),
        "name_if_known": tns_name or (f"Gaia {gaia_name}" if gaia_name and not gaia_name.startswith("Gaia") else gaia_name),
        "known_status": "known" if catalogued else "not_on_lists",
        "cutouts": {
            "before": fink.cutout_url(src, "Template"),
            "now": fink.cutout_url(src, "Science"),
            "difference": fink.cutout_url(src, "Difference"),
        },
        "light_curve": None,
        "explanation": _explain(basis, n_alerts, row),
        "links": links,
        "raw": {
            "broker": "fink",
            "diaObjectId": str(oid),
            "latest_diaSourceId": str(src),
            "alert_count": n_alerts,
            "first_detected_at": _iso(row.get("f:firstDiaSourceMjdTaiFink")),
            "type_basis": basis["kind"],
            "fink": row,
        },
    }


def classify_fink_row(row: dict[str, Any]) -> tuple[CatchType, float, dict[str, str]]:
    """(type, confidence, basis). Order: a TNS classification, then a SIMBAD or VSX catalogue type
    at the same position, then Fink's CATS classifier. Catalogue labels carry confidence 1.0
    ("already catalogued as this"); the classifier carries its own score."""
    if catch := classes.tns_type(row.get("f:xm_tns_type")):
        return catch, 1.0, {"kind": "tns", "label": str(row["f:xm_tns_type"])}
    if catch := classes.simbad_type(row.get("f:xm_simbad_otype")):
        return catch, 1.0, {"kind": "simbad", "label": str(row["f:xm_simbad_otype"])}
    if catch := classes.vsx_type(row.get("f:xm_vsx_Type")):
        return catch, 1.0, {"kind": "vsx", "label": str(row["f:xm_vsx_Type"])}
    label, catch = classes.cats_type(row.get("f:clf_cats_class", row.get("f:main_label_classifier")))
    score = _clamp01(row.get("f:clf_cats_score"))
    if label == "not processed":
        score = 0.0
    return catch, score, {"kind": "cats", "label": label}


def _explain(basis: dict[str, str], n_alerts: int, row: dict[str, Any]) -> str:
    seen = f"Rubin has sent {n_alerts} alert{'s' if n_alerts != 1 else ''} about this object"
    kind, label = basis["kind"], basis["label"]
    if kind == "tns":
        return f"{seen}. It is listed on the Transient Name Server as {label}."
    if kind == "simbad":
        return f"{seen}. Fink matched it to a SIMBAD object of type '{label}' within 1 arcsec."
    if kind == "vsx":
        return f"{seen}. Fink matched it to a known variable star (VSX type '{label}')."
    if label == "not processed":
        return f"{seen}. Fink's classifier has not labelled it yet, so its type is unknown."
    score = _clamp01(row.get("f:clf_cats_score"))
    return (
        f"{seen}. Fink's CATS classifier's best guess is '{label}' "
        f"(score {score:.2f} out of 1). This is a machine guess, not a confirmed type."
    )


def light_curve(dia_object_id: str | int) -> list[dict[str, Any]]:
    pts = [
        {
            "time": _iso(r["r:midpointMjdTai"]),
            "band": r.get("r:band"),
            "flux_njy": r.get("r:psfFlux"),
            "flux_err_njy": r.get("r:psfFluxErr"),
        }
        for r in fink.sources(dia_object_id)
    ]
    return sorted(pts, key=lambda p: p["time"])


# ---------------------------------------------------------------- solar-system objects


def _solar_system(sphere: Sphere, m0: float, m1: float, max_cutout_lookups: int) -> list[Discovery]:
    try:
        seen = sso.sightings(m0, m1, (sphere["ra_deg"], sphere["dec_deg"], sphere["radius_deg"]))
    except UpstreamError as exc:
        log.warning("Fink SSO bulk file unavailable: %s", exc)
        return []
    if not seen:
        return []

    skybot = _skybot_classes(sphere, seen)
    seen.sort(key=lambda s: s.mjd_tai, reverse=True)
    out = []
    for i, s in enumerate(seen):
        src, fink_ss_id = _latest_sso_source(s) if i < max_cutout_lookups else (None, None)
        out.append(sso_to_discovery(s, skybot.get(s.designation), src, fink_ss_id))
    return out


def sso_to_discovery(
    s: sso.SsoSighting,
    skybot_class: str | None,
    dia_source_id: int | None,
    fink_ss_object_id: int | None = None,
) -> Discovery:
    if skybot_class:
        catch = classes.skybot_class_to_catch_type(skybot_class, s.designation)
        basis = f"SkyBoT lists it as '{skybot_class}'"
    else:
        catch = sso.heuristic_type(s.designation, s.helio_au)
        basis = "type from its designation and distance from the Sun" + (
            f" ({s.helio_au:.2f} AU)" if s.helio_au is not None else ""
        )
    ss_id = fink_ss_object_id or sso.ss_object_id(s.designation)
    # ID rule: rubin:ss:<ssObjectId>. When the designation can't be packed (old "A924 EV"
    # style), fall back to the designation itself, which is Fink's own key for the object.
    ident = f"rubin:ss:{ss_id}" if ss_id is not None else f"rubin:ss:{s.designation.replace(' ', '_')}"
    cut = (
        {
            "before": fink.cutout_url(dia_source_id, "Template"),
            "now": fink.cutout_url(dia_source_id, "Science"),
            "difference": fink.cutout_url(dia_source_id, "Difference"),
        }
        if dia_source_id
        else {"before": None, "now": None, "difference": None}
    )
    n = s.n_detections
    return {
        "id": ident,
        "type": catch,
        "confidence": 1.0,
        "source": "rubin",
        "origin": ORIGIN,
        "ra_deg": round(s.ra_deg, 7),
        "dec_deg": round(s.dec_deg, 7),
        "detected_at": _iso(s.mjd_tai),
        "name_if_known": s.designation,
        "known_status": "known",
        "cutouts": cut,
        "light_curve": None,
        "explanation": (
            f"Rubin saw this moving object {n} time{'s' if n != 1 else ''} here and linked it to the "
            f"known orbit of {s.designation}; {basis}."
        ),
        "links": [
            {"label": "JPL Small-Body Database", "url": f"https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={s.designation.replace(' ', '%20')}"},
        ],
        "raw": {
            "broker": "fink",
            "designation": s.designation,
            "ssObjectId": str(ss_id) if ss_id is not None else None,
            "latest_diaSourceId": str(dia_source_id) if dia_source_id else None,
            "alert_count": n,
            "band": s.band,
            "helio_au": s.helio_au,
            "topo_au": s.topo_au,
            "skybot_class": skybot_class,
        },
    }


def _skybot_classes(sphere: Sphere, seen: list[sso.SsoSighting]) -> dict[str, str]:
    """Dynamical classes for the objects we saw, from one SkyBoT cone at the median sighting time.
    Best effort: on failure every object falls back to sso.heuristic_type."""
    from .solar_system import known_solar_system

    times = sorted(s.mjd_tai for s in seen)
    t_mid = Time(times[len(times) // 2], format="mjd", scale="tai").utc.to_datetime(UTC)
    try:
        known = known_solar_system(sphere, t_mid)
    except Exception as exc:  # noqa: BLE001 - SkyBoT is optional context here
        log.warning("SkyBoT unavailable, using heuristic SSO types: %s", exc)
        return {}
    return {k["name"]: k["skybot_class"] for k in known}


def _latest_sso_source(s: sso.SsoSighting) -> tuple[int | None, int | None]:
    """(diaSourceId of the sighting, Fink's ssObjectId) via one /sso call."""
    try:
        rows = fink.sso_rows(s.designation)
    except UpstreamError:
        return None, None
    best = min(rows, key=lambda r: abs(r["r:midpointMjdTai"] - s.mjd_tai), default=None)
    if best is None:
        return None, None
    ss_id = int(best["r:ssObjectId"]) if best.get("r:ssObjectId") else None
    if abs(best["r:midpointMjdTai"] - s.mjd_tai) > 1e-4:  # ~9 s: not the same exposure
        return None, ss_id
    return int(best["r:diaSourceId"]), ss_id


# ---------------------------------------------------------------- helpers


def _mjd_tai(t: datetime) -> float:
    return float(Time(t).tai.mjd)


def _iso(mjd_tai: object) -> str | None:
    if mjd_tai is None:
        return None
    t = Time(float(mjd_tai), format="mjd", scale="tai").utc.to_datetime(UTC)
    return t.isoformat(timespec="seconds")


def _clamp01(v: object) -> float:
    f = float_or_none(v)
    return 0.0 if f is None else round(max(0.0, min(1.0, f)), 4)
