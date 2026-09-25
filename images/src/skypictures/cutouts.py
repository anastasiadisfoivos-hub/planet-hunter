"""Survey cutouts (reference / new / difference) from Fink, for Rubin/LSST and ZTF alerts.

Rubin: https://api.lsst.fink-portal.org/api/v1/cutouts?diaSourceId=...   0.2"/px, 30-60 px seen (a few ")
ZTF:   https://api.ztf.fink-portal.org/api/v1/cutouts?objectId=...&candid=...  1.01"/px, usually 63 px (~1')
Both return PNG usable directly as <img src>. The IDs come from what EVENTS put in the event.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from . import credits
from .models import Event, Image

LSST_API = "https://api.lsst.fink-portal.org/api/v1"
ZTF_API = "https://api.ztf.fink-portal.org/api/v1"

# Fink kind name -> contract kind, in display order: before, after, what changed.
KINDS = [("Template", "cutout_reference"), ("Science", "cutout_new"), ("Difference", "cutout_difference")]

ZTF_ID = re.compile(r"\bZTF\d{2}[a-z]{7}\b")
MJD_UNIX0 = 40587.0


def _walk(obj: Any, depth: int = 0) -> Iterator[tuple[str, Any]]:
    """(key, value) pairs of a nested dict/list, shallow first."""
    if depth > 4:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from _walk(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:50]:
            yield from _walk(v, depth + 1)


def _first(raw: dict, names: set[str]) -> Any:
    for k, v in _walk(raw):
        if k in names and v not in (None, "", 0, "0", "nan", "None"):
            return v
    return None


def rubin_source_id(event: Event) -> str | None:
    """The Rubin diaSourceId whose cutouts show this event, if the event carries one."""
    raw = event.get("raw") or {}
    v = _first(raw, {"latest_diaSourceId", "diaSourceId", "r:diaSourceId", "dia_source_id"})
    if v is not None and str(v).isdigit():
        return str(v)
    for _k, url in _walk(raw):  # skysources puts ready-made Fink cutout URLs in raw.cutouts
        if isinstance(url, str) and url.startswith(LSST_API + "/cutouts"):
            ids = parse_qs(urlsplit(url).query).get("diaSourceId")
            if ids and ids[0].isdigit():
                return ids[0]
    return None


def ztf_ids(event: Event) -> tuple[str, str | None] | None:
    """(objectId, candid or None) for a ZTF alert."""
    raw = event.get("raw") or {}
    oid = _first(raw, {"objectId", "i:objectId", "ztf_object_id", "oid"})
    if not (isinstance(oid, str) and ZTF_ID.fullmatch(oid)):
        m = ZTF_ID.search(" ".join([event.get("id", ""), event.get("source_url", "")]))
        oid = m.group(0) if m else None
    if not oid:
        return None
    candid = _first(raw, {"candid", "i:candid"})
    return oid, (str(candid) if candid is not None and str(candid).isdigit() else None)


def _when(raw: dict) -> str:
    mjd = _first(raw, {"r:midpointMjdTai", "midpointMjdTai"})
    jd = _first(raw, {"i:jd", "jd"})
    try:
        if mjd is not None:
            t = (float(mjd) - MJD_UNIX0) * 86400.0
        elif jd is not None:
            t = (float(jd) - 2400000.5 - MJD_UNIX0) * 86400.0
        else:
            return ""
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _band(raw: dict) -> str:
    band = _first(raw, {"r:band", "band"})
    if isinstance(band, str) and band:
        return f"{band} band"
    fid = _first(raw, {"i:fid", "fid"})
    return {1: "g band", 2: "r band", 3: "i band"}.get(int(fid), "") if str(fid).isdigit() else ""


def rubin_cutouts(event: Event) -> list[Image]:
    src = rubin_source_id(event)
    if not src:
        return []
    raw = event.get("raw") or {}
    detail = ", ".join(x for x in (_band(raw), _when(raw)) if x)
    detail = f" ({detail})" if detail else ""
    captions = {
        "cutout_reference": "Rubin reference image: the few arcseconds of sky around the source before the "
        "event, stacked from earlier Rubin exposures.",
        "cutout_new": f"Rubin science image{detail}: the same patch of sky at the moment of this alert "
        f"(diaSource {src}).",
        "cutout_difference": "Rubin difference image: the new light only (science minus reference). "
        "The spot at the centre is what changed.",
    }
    return [_image(f"{LSST_API}/cutouts", {"diaSourceId": src}, fk, kind, captions[kind], credits.RUBIN)
            for fk, kind in KINDS]


def ztf_cutouts(event: Event) -> list[Image]:
    ids = ztf_ids(event)
    if not ids:
        return []
    oid, candid = ids
    raw = event.get("raw") or {}
    which = f"alert {candid}" if candid else "its latest alert"
    detail = ", ".join(x for x in (_band(raw), _when(raw) if candid else "") if x)
    detail = f" ({detail})" if detail else ""
    captions = {
        "cutout_reference": "ZTF reference image: about 1′ of sky around the source before the event, "
        "stacked from earlier ZTF exposures.",
        "cutout_new": f"ZTF science image{detail}: the same patch of sky in {which} for {oid}.",
        "cutout_difference": "ZTF difference image: the new light only (science minus reference). "
        "The spot at the centre is what changed.",
    }
    base = {"objectId": oid, **({"candid": candid} if candid else {})}
    return [_image(f"{ZTF_API}/cutouts", base, fk, kind, captions[kind], credits.ZTF) for fk, kind in KINDS]


def _image(endpoint: str, ids: dict, fink_kind: str, kind: str, caption: str, c: credits.Credit) -> Image:
    q = urlencode({**ids, "kind": fink_kind, "output-format": "PNG"})
    # Fink cutouts are 30-63 px: already thumbnail-sized, so the thumbnail is the image itself.
    return Image(url=f"{endpoint}?{q}", thumb_url=f"{endpoint}?{q}", kind=kind, caption=caption, credit=c.credit, license=c.license,
                 width=None, height=None)  # type: ignore[typeddict-item]


def survey_cutouts(event: Event) -> list[Image]:
    """Rubin cutouts if the event has a Rubin diaSource, else ZTF ones, else nothing."""
    return rubin_cutouts(event) or ztf_cutouts(event)
