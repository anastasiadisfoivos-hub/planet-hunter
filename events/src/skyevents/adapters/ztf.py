"""ZTF transients (northern sky), classified by the ALeRCE broker. No login.

API: https://api.alerce.online/ztf/v1/objects/ (docs https://api.alerce.online/ztf/v1/docs).
Fink's ZTF API (https://api.fink-portal.org) did not answer within 75 s when checked on
2026-09-25, so ALeRCE is the ZTF path.

Two kinds of rows, both ALeRCE machine classifications (confidence = its probability,
basis machine_guess):
- Light-curve classifier (lc_classifier_BHRF_forced_phot), objects seen in the window whose top
  class is a supernova type, TDE or microlensing, plus CV/Nova when the object is new
  (first seen within NEW_DAYS; an old CV/Nova object is an ordinary variable star).
- Stamp classifier: brand-new objects (first seen in the window) whose first image already looks
  like a supernova, before a light curve exists.
id: ztf:<ZTF object id>, the same id TNS lists as the internal name, which is how the
de-duplicator joins the two.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..models import Event
from ..util import dt_to_mjd_utc, make_event, mjd_utc_to_dt, num, sky
from ._http import FRESH, client

NAME = "ztf"
LIVE_WITHIN = timedelta(days=3)
API = "https://api.alerce.online/ztf/v1/objects/"
EXPLORER = "https://alerce.online/object/{}"
LC = "lc_classifier_BHRF_forced_phot"
STAMP = "stamp_classifier"
MIN_PROB = 0.5
MIN_STAMP_PROB = 0.7
NEW_DAYS = 30
PAGE_SIZE = 200
MAX_PAGES = 3

LC_CLASSES: dict[str, tuple[str, str]] = {
    "SNIa": ("supernova", "a type Ia supernova"),
    "SESN": ("supernova", "a stripped-envelope supernova"),
    "SNII": ("supernova", "a type II supernova"),
    "SNIIn": ("supernova", "a type IIn supernova"),
    "SLSN": ("supernova", "a superluminous supernova"),
    "TDE": ("tidal_disruption_event", "a star being torn apart by a black hole (tidal disruption event)"),
    "Microlensing": ("microlensing", "a microlensing event"),
    "CV/Nova": ("variable_star", "a nova or cataclysmic-variable outburst"),
}


def fetch(since: datetime, until: datetime) -> list[Event]:
    m0, m1 = dt_to_mjd_utc(since), dt_to_mjd_utc(until)
    out: dict[str, Event] = {}
    for cls, (kind, words) in LC_CLASSES.items():
        for r in objects(LC, cls, MIN_PROB, [("lastmjd", f"{m0:.4f}"), ("lastmjd", f"{m1:.4f}")]):
            if cls == "CV/Nova" and r["firstmjd"] < m1 - NEW_DAYS:
                continue
            out[r["oid"]] = to_event(r, kind, words, "light-curve")
    for r in objects(STAMP, "SN", MIN_STAMP_PROB, [("firstmjd", f"{m0:.4f}"), ("firstmjd", f"{m1:.4f}")]):
        out.setdefault(r["oid"], to_event(r, "supernova", "a supernova", "first-image"))
    return list(out.values())


def last_event_at(now: datetime) -> datetime | None:
    doc = client().get_json(
        API, params=[("order_by", "lastmjd"), ("order_mode", "DESC"), ("page_size", 1)], ttl=FRESH
    )
    items = doc.get("items") or []
    return mjd_utc_to_dt(items[0]["lastmjd"]) if items else None


def objects(classifier: str, cls: str, min_prob: float, ranges: list[tuple[str, str]]) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        params = [
            ("classifier", classifier), ("class", cls), ("ranking", 1), ("probability", min_prob),
            *ranges, ("order_by", "lastmjd"), ("order_mode", "DESC"), ("page_size", PAGE_SIZE), ("page", page),
        ]
        items = client().get_json(API, params=params, ttl=FRESH).get("items") or []
        rows += items
        if len(items) < PAGE_SIZE:
            break
    return rows


def to_event(r: dict, kind: str, words: str, how: str) -> Event:
    oid = r["oid"]
    first, last = mjd_utc_to_dt(r["firstmjd"]), mjd_utc_to_dt(r["lastmjd"])
    n = int(r.get("ndet") or 0)
    prob = float(r.get("probability") or 0.0)
    err_arcsec = max(num(r.get("sigmara")) or 0.0, num(r.get("sigmadec")) or 0.0, 0.5)
    return make_event(
        source=NAME,
        source_id=oid,
        type=kind,
        title=f"{kind.replace('_', ' ').capitalize()} candidate {oid}",
        summary=(
            f"ZTF has detected {oid} {n} time{'s' if n != 1 else ''} since {first:%d %b %Y}. ALeRCE's {how} "
            f"classifier's best guess is {words} (probability {prob:.2f}); this is a machine guess, not a "
            f"confirmed type."
        ),
        source_url=EXPLORER.format(oid),
        observed_at=last,
        reported_at=last,
        location=sky(float(r["meanra"]), float(r["meandec"]), round(err_arcsec / 3600, 6)),
        confidence=prob,
        confidence_basis="machine_guess",
        raw={
            "names": [oid],
            "classifier": r.get("classifier"),
            "class": r.get("class"),
            "detections": n,
            "first_detected_at": first.isoformat(timespec="seconds"),
            "broker": "alerce",
        },
    )
