"""schedule(sphere, start, end): Rubin visits touching a sphere, from the ObsLocTAP service.

Service: https://usdf-rsp.slac.stanford.edu/obsloctap/  (docs https://obsloctap.lsst.io,
code https://github.com/lsst-dm/obsloctap). No login. It is an IVOA ObsLocTAP *table* served over
a small REST API (`/schedule`), not a full TAP/ADQL endpoint.

The table holds both the scheduler's forecast (execution_status Planned/Scheduled) and what
actually happened (Performed/Aborted), so one call covers future and past windows.

Query strategy: `time=0` switches off the service's window on `t_planning` (the time the plan
was *made*), and our own predicate filters on `t_min` (exposure start) plus an RA/Dec box.
The exact cone test (visit centre within sphere radius + camera half-FOV) is done locally.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from astropy.time import Time

from .http import HOST_MIN_INTERVAL, get_client
from .models import Sphere, Visit, validate_sphere
from .util import as_utc, sep_deg

OBSLOCTAP_URL = "https://usdf-rsp.slac.stanford.edu/obsloctap/schedule"
HOST_MIN_INTERVAL.setdefault("usdf-rsp.slac.stanford.edu", 1.0)

ROW_LIMIT = 1000  # the service's obsplanLimit when time=0
LSSTCAM_FOV_DEG = 3.5  # s_fov in the table (diameter)

# em_min/em_max (metres) -> band, copied from obsloctap/models.py `spectral_ranges`.
BANDS = {
    (3.3e-07, 4e-07): "u",
    (4.02e-07, 5.52e-07): "g",
    (5.52e-07, 6.91e-07): "r",
    (6.91e-07, 8.18e-07): "i",
    (8.18e-07, 9.22e-07): "z",
    (9.22e-07, 1.06e-06): "y",
}

STATUS = {
    "Performed": "performed",
    "Aborted": "aborted",
    "Planned": "planned",
    "Scheduled": "planned",
    "Unscheduled": "planned",
}


def schedule(
    sphere: Sphere,
    start: datetime | str,
    end: datetime | str,
    *,
    include_aborted: bool = False,
) -> list[Visit]:
    """Planned and completed Rubin visits whose field of view overlaps `sphere` in [start, end].

    Sorted by time. Aborted visits are dropped unless `include_aborted`.
    """
    sphere = validate_sphere(sphere)
    t0, t1 = Time(as_utc(start)).mjd, Time(as_utc(end)).mjd
    if t1 <= t0:
        raise ValueError("end must be after start")
    reach = sphere["radius_deg"] + LSSTCAM_FOV_DEG / 2
    rows = _fetch_rows(t0, t1, _box_predicate(sphere, reach))

    seen: set[tuple] = set()
    visits: list[Visit] = []
    for row in rows:
        if sep_deg(sphere["ra_deg"], sphere["dec_deg"], row["s_ra"], row["s_dec"]) > reach:
            continue
        visit = row_to_visit(row)
        if visit["status"] == "aborted" and not include_aborted:
            continue
        # One exposure can appear more than once (re-planned rows); obs_id is per-block, not
        # per-visit, so key on time + pointing.
        key = (round(row["t_min"] * 86400), round(row["s_ra"], 3), round(row["s_dec"], 3))
        if key in seen:
            continue
        seen.add(key)
        visits.append(visit)
    visits.sort(key=lambda v: v["time"])
    return visits


def row_to_visit(row: dict) -> Visit:
    return {
        "time": Time(row["t_min"], format="mjd").to_datetime(UTC).isoformat(timespec="seconds"),
        "band": band_from_em(row.get("em_min"), row.get("em_max")),
        "status": STATUS.get(row.get("execution_status", ""), "unknown"),  # type: ignore[typeddict-item]
        "ra_deg": round(float(row["s_ra"]), 6),
        "dec_deg": round(float(row["s_dec"]), 6),
        "obs_id": row.get("obs_id") or None,
        "exposure_s": row.get("t_exptime"),
    }


def band_from_em(em_min: float | None, em_max: float | None) -> str | None:
    if em_min is None or em_max is None:
        return None
    for (lo, hi), band in BANDS.items():
        if math.isclose(em_min, lo, rel_tol=1e-3) and math.isclose(em_max, hi, rel_tol=1e-3):
            return band
    return None


def _fetch_rows(t0: float, t1: float, box: str, depth: int = 0) -> list[dict]:
    predicate = f"t_min >= {t0:.6f} AND t_min <= {t1:.6f}"
    if box:
        predicate += f" AND {box}"
    rows = get_client().get_json(
        OBSLOCTAP_URL,
        params={"time": 0, "RESPONSEFORMAT": "json", "predicate": predicate},
        ttl=_ttl_for(t1),
    )
    if len(rows) >= ROW_LIMIT and depth < 12:
        mid = (t0 + t1) / 2  # truncated by the service's row cap: split the window
        return _fetch_rows(t0, mid, box, depth + 1) + _fetch_rows(mid, t1, box, depth + 1)
    return rows


def _box_predicate(sphere: Sphere, reach: float) -> str:
    """A coarse RA/Dec box around the cone. RA is omitted near the poles or when the box wraps."""
    dec, ra = sphere["dec_deg"], sphere["ra_deg"]
    dmin, dmax = max(-90.0, dec - reach), min(90.0, dec + reach)
    parts = [f"s_dec >= {dmin:.4f}", f"s_dec <= {dmax:.4f}"]
    max_abs_dec = max(abs(dmin), abs(dmax))
    if max_abs_dec < 89.0:
        dra = reach / math.cos(math.radians(max_abs_dec))
        lo, hi = ra - dra, ra + dra
        if dra < 180 and lo >= 0 and hi < 360:
            parts += [f"s_ra >= {lo:.4f}", f"s_ra <= {hi:.4f}"]
    return " AND ".join(parts)


def _ttl_for(t1_mjd: float) -> float:
    # Past windows barely change; the forecast is refreshed often.
    return 6 * 3600.0 if t1_mjd < Time.now().mjd - 1 else 600.0
