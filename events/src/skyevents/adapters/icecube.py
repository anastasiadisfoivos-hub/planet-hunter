"""IceCube high-energy neutrino alerts (Gold and Bronze tracks), from NASA GCN Classic.

Page: https://gcn.gsfc.nasa.gov/amon_icecube_gold_bronze_events.html (public, no login). One
row per Notice; an event can have several revisions (the position is refined), and the newest
revision wins. Errors in the table are arcmin (90% containment radius), energy in TeV.

Confidence = IceCube's "signalness" (probability the neutrino is astrophysical rather than from
the atmosphere): the event itself is an official detection, but whether it's cosmic is a
statistical estimate, so the basis is machine_guess.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta

from ..models import Event
from ..util import as_utc, make_event, num, sky
from ._http import FRESH, client

NAME = "icecube"
LIVE_WITHIN = timedelta(days=30)  # roughly one Gold/Bronze alert a week
TABLE = "https://gcn.gsfc.nasa.gov/amon_icecube_gold_bronze_events.html"
NOTICE_BASE = "https://gcn.gsfc.nasa.gov/"

COLUMNS = ["run_event", "rev", "date", "time", "notice_type", "ra", "dec", "err90_arcmin",
           "err50_arcmin", "energy_tev", "signalness", "far_per_yr", "comments"]


def fetch(since: datetime, until: datetime) -> list[Event]:
    return [e for e in current() if since <= as_utc(e["observed_at"]) <= until]


def last_event_at(now: datetime) -> datetime | None:
    return max((as_utc(e["observed_at"]) for e in current()), default=None)


def current() -> list[Event]:
    rows = parse_table(client().request_text("GET", TABLE, ttl=FRESH))
    newest: dict[str, dict] = {}
    for r in rows:
        if r["run_event"] not in newest or r["rev"] > newest[r["run_event"]]["rev"]:
            newest[r["run_event"]] = r
    return [to_event(r) for r in newest.values()]


def parse_table(page: str) -> list[dict]:
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.DOTALL | re.IGNORECASE):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.DOTALL | re.IGNORECASE)]
        if len(cells) < len(COLUMNS) or not re.fullmatch(r"\d+_\d+", cells[0]):
            continue
        r = dict(zip(COLUMNS, cells, strict=False))
        link = re.search(r"href=([^\s>]+)", tr)
        r["notice_url"] = NOTICE_BASE + link[1].strip("\"'") if link else TABLE
        r["rev"] = int(r["rev"]) if r["rev"].isdigit() else 0
        yy, mm, dd = r["date"].split("/")
        r["when"] = as_utc(f"20{yy}-{mm}-{dd}T{r['time']}")
        if num(r["ra"]) is None or num(r["dec"]) is None:
            continue
        out.append(r)
    return out


def to_event(r: dict) -> Event:
    when: datetime = r["when"]
    err = num(r["err90_arcmin"])
    energy, signal, far = num(r["energy_tev"]), num(r["signalness"]), num(r["far_per_yr"])
    kind = r["notice_type"].strip().upper() or "track"
    return make_event(
        source=NAME,
        source_id=r["run_event"],
        type="neutrino",
        title=f"{kind.title()} high-energy neutrino (IceCube run {r['run_event']})",
        summary=(
            "The IceCube detector at the South Pole caught a high-energy neutrino"
            + (f" (most likely about {energy:.0f} TeV)" if energy else "")
            + " coming from this part of the sky."
            + (f" IceCube estimates a {signal * 100:.0f}% chance it came from space rather than Earth's atmosphere."
               if signal is not None else "")
        ),
        source_url=r["notice_url"],
        observed_at=when,
        reported_at=when,
        location=sky(float(r["ra"]), float(r["dec"]), round((err or 60.0) / 60.0, 4)),
        confidence=signal if signal is not None else 0.5,
        confidence_basis="machine_guess",
        raw={
            "notice_type": kind,
            "revision": r["rev"],
            "energy_tev": energy,
            "signalness": signal,
            "far_per_yr": far,
            "error50_deg": round(num(r["err50_arcmin"]) / 60.0, 4) if num(r["err50_arcmin"]) else None,
            "reported_at_known": False,
        },
    )
