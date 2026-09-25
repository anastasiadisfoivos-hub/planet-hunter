"""Rubin Observatory (LSST) alert-stream objects, via the Fink LSST broker (through skysources).

- Live or paused: skysources.stream_status() (newest LSST alert at the brokers; live = within
  72 h). The Rubin alert stream has been quiet since 2026-07-14.
- Window: [since, until] while live. While paused, skysources.latest_observed_window(n) for the
  same number of nights, so the feed still shows Rubin's most recent real events, with their
  true dates, each marked raw.from_latest_observed_window = true.
- Which objects: Fink's all-sky tags (https://api.lsst.fink-portal.org/api/v1/tags) that pick
  likely extragalactic transients. One Event per diaObject (its newest alert in the window),
  converted by skysources.alerts.fink_row_to_discovery, so the type rules and Fink columns are
  the same ones the rest of planet-hunter uses (see sources/README.md, "Class -> CatchType").
- Images: the Fink cutout URLs of that alert (template / science / difference), passed through.

Known solar-system objects Rubin re-observes are not events here; new moving objects Rubin
reports reach the feed through the MPC NEO Confirmation Page (temporary designations "LS...").
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from skysources import latest_observed_window, stream_status
from skysources.alerts import fink_row_to_discovery
from skysources.fink import CONE_COLUMNS, FINK_API

from ..models import Event, Image
from ..util import as_utc, iso, make_event, num, sky
from ._http import FRESH, UpstreamError, client

log = logging.getLogger(__name__)

NAME = "rubin"
LIVE_WITHIN = timedelta(hours=72)  # same rule as stream_status()
TAGS = [
    "in_tns",
    "most_likely_sn",
    "sn_near_galaxy_candidate",
    "extragalactic_new_candidate",
    "extragalactic_lt20mag_candidate",
    "hostless_candidate",
]
PER_TAG = 300
POSITION_ERROR_DEG = 0.1 / 3600
CREDIT = "NSF–DOE Vera C. Rubin Observatory, via the Fink broker"
LICENSE = "Rubin public alert data; no licence stated by the source"

TYPE_MAP = {
    "supernova": "supernova",
    "tidal_disruption_event": "tidal_disruption_event",
    "kilonova": "kilonova",
    "microlensing": "microlensing",
    "variable_star": "variable_star",
    "eclipsing_binary": "variable_star",
    "flare": "stellar_flare",
    "active_galaxy": "active_galaxy_flare",
    "asteroid": "asteroid",
    "near_earth_object": "near_earth_object",
    "trans_neptunian_object": "asteroid",
    "comet": "comet",
    "interstellar_object": "interstellar_object",
}
BASIS = {"tns": "official_report", "simbad": "catalogue_match", "vsx": "catalogue_match", "cats": "machine_guess"}


def window(since: datetime, until: datetime) -> tuple[datetime, datetime, dict]:
    """The window actually queried, and the stream status behind that choice."""
    status = stream_status()
    if status.get("is_live"):
        return since, until, status
    nights = max(1, math.ceil((until - since) / timedelta(days=1)))
    start, end = latest_observed_window(nights)
    return start, end, status


def fetch(since: datetime, until: datetime) -> list[Event]:
    start, end, status = window(since, until)
    from_latest = not status.get("is_live")
    rows: dict[int, dict] = {}
    tags: dict[int, set[str]] = {}
    for tag in TAGS:
        try:
            batch = tag_rows(tag, start, end)
        except UpstreamError as exc:
            log.warning("Fink tag %s failed: %s", tag, exc)
            continue
        for row in batch:
            oid = int(row["r:diaObjectId"])
            tags.setdefault(oid, set()).add(tag)
            if oid not in rows or row["r:midpointMjdTai"] > rows[oid]["r:midpointMjdTai"]:
                rows[oid] = row
    events = [to_event(row, sorted(tags[oid])) for oid, row in rows.items()]
    for e in events:
        # True when the stream is paused and these are Rubin's latest nights, not the requested
        # window: a UI can keep them out of "recent" and offer them as their own toggle.
        e["raw"]["from_latest_observed_window"] = from_latest
    return events


def last_event_at(now: datetime) -> datetime | None:
    t = stream_status().get("last_alert_at")
    return as_utc(t) if t else None


def status_extra(since: datetime, until: datetime) -> dict:
    """Rubin's line in status.json: live flag from stream_status(), and the window used."""
    start, end, status = window(since, until)
    return {
        "live": bool(status.get("is_live")),
        "last_event_at": _iso_or_none(status.get("last_alert_at")),
        "last_scheduled_visit_at": _iso_or_none(status.get("last_scheduled_visit_at")),
        "window": {"start": iso(start), "end": iso(end)},
        "note": None if status.get("is_live") else (
            "Rubin's alert stream is paused; showing its latest nights with alerts, at their real dates."
        ),
    }


def _iso_or_none(t: str | None) -> str | None:
    return iso(as_utc(t)) if t else None


def tag_rows(tag: str, start: datetime, end: datetime) -> list[dict]:
    body = {
        "tag": tag,
        "n": str(PER_TAG),
        "startdate": iso(start).rstrip("Z"),
        "stopdate": iso(end).rstrip("Z"),
        "columns": ",".join(CONE_COLUMNS),
    }
    return client().post_json(f"{FINK_API}/tags", json_body=body, ttl=FRESH) or []


def _mag(flux_njy: object) -> float | None:
    f = num(flux_njy)
    return 31.4 - 2.5 * math.log10(f) if f and f > 0 else None


def to_event(row: dict, tags: list[str]) -> Event:
    d = fink_row_to_discovery(row)
    raw = d["raw"]
    kind = TYPE_MAP.get(d["type"], "unknown")
    basis_kind = raw["type_basis"]
    fink_row = raw["fink"]
    tns = d["name_if_known"] if (d["name_if_known"] or "").startswith(("AT ", "SN ", "TDE ")) else None
    oid = raw["diaObjectId"]
    n = raw["alert_count"]

    label = kind.replace("_", " ").capitalize() if kind != "unknown" else "Transient"
    title = f"{label}{' candidate' if basis_kind == 'cats' else ''} {tns or f'Rubin {oid}'}"
    seen = f"Rubin Observatory has sent {n} alert{'s' if n != 1 else ''} about this object, the latest on {as_utc(d['detected_at']):%d %b %Y}."
    if basis_kind == "tns":
        why = f" It is listed on the Transient Name Server as {fink_row.get('f:xm_tns_type')}."
    elif basis_kind in ("simbad", "vsx"):
        cat = "SIMBAD" if basis_kind == "simbad" else "the VSX variable-star catalogue"
        why = f" Fink matched it to a known object in {cat}, so its type comes from that catalogue."
    elif kind == "unknown":
        why = " Fink's classifier has no confident type for it yet."
    else:
        why = (
            f" Fink's classifier's best guess is '{basis_label(row)}' (score {d['confidence']:.2f}), "
            "a machine guess, not a confirmed type."
        )

    names = [n_ for n_ in (tns, tns.split(" ", 1)[1] if tns else None) if n_]
    cut = d["cutouts"]
    images: list[Image] = [
        {"url": url, "kind": kind_, "caption": cap, "credit": CREDIT, "license": LICENSE, "width": None, "height": None}
        for url, kind_, cap in (
            (cut["before"], "cutout_reference", "Reference (template) image before the change"),
            (cut["now"], "cutout_new", "Rubin image from the latest alert"),
            (cut["difference"], "cutout_difference", "Difference: what changed"),
        )
        if url
    ]
    return make_event(
        source=NAME,
        source_id=oid,
        type=kind,
        title=title,
        summary=seen + why,
        source_url=f"https://lsst.fink-portal.org/{oid}",
        observed_at=d["detected_at"],
        reported_at=d["detected_at"],
        location=sky(d["ra_deg"], d["dec_deg"], POSITION_ERROR_DEG),
        confidence=d["confidence"],
        confidence_basis=BASIS.get(basis_kind, "machine_guess"),
        brightness_mag=_mag(fink_row.get("r:psfFlux")),
        images=images,
        raw={
            "names": names,
            "diaObjectId": oid,
            "latest_diaSourceId": raw["latest_diaSourceId"],
            "alert_count": n,
            "first_detected_at": raw["first_detected_at"],
            "type_basis": basis_kind,
            "fink_tags": tags,
            "band": fink_row.get("r:band"),
            "broker": "fink",
        },
    )


def basis_label(row: dict) -> str:
    from skysources import classes

    label, _ = classes.cats_type(row.get("f:clf_cats_class"))
    return label
