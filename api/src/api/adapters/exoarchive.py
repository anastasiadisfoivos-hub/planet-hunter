"""The real PlanetArchive: NASA Exoplanet Archive TAP, table pscomppars (free, no key).

One row per confirmed planet, with the archive's preferred self-consistent parameters; the
star's values (mass, radius, Teff, distance, Tmag) come from the same rows.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from api.models import HostStar, HostSystem, KnownPlanet

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
COLUMNS = (
    "pl_name, hostname, pl_orbper, pl_orbsmax, pl_rade, pl_bmasse, pl_bmassprov,"
    " st_mass, st_rad, st_teff, sy_dist, sy_tmag"
)


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _first(rows: list[dict[str, Any]], key: str) -> float | None:
    return next((x for r in rows if (x := _num(r.get(key))) is not None), None)


def host_system(tic_id: int, rows: list[dict[str, Any]], now: datetime) -> HostSystem:
    rows = sorted(rows, key=lambda r: str(r.get("pl_name") or ""))
    return HostSystem(
        tic_id=tic_id,
        host_name=next((r["hostname"] for r in rows if r.get("hostname")), None),
        star=HostStar(
            mass_msun=_first(rows, "st_mass"),
            radius_rsun=_first(rows, "st_rad"),
            teff_k=_first(rows, "st_teff"),
            distance_pc=_first(rows, "sy_dist"),
            tmag=_first(rows, "sy_tmag"),
        ),
        planets=[
            KnownPlanet(
                name=r["pl_name"],
                period_d=_num(r.get("pl_orbper")),
                a_au=_num(r.get("pl_orbsmax")),
                radius=_num(r.get("pl_rade")),
                mass=_num(r.get("pl_bmasse")),
                mass_kind=r.get("pl_bmassprov") or None,
            )
            for r in rows
            if r.get("pl_name")
        ],
        fetched_at=now,
    )


class ExoplanetArchive:
    def __init__(self, timeout_s: float = 20.0) -> None:
        self.timeout_s = timeout_s

    def host_system(self, tic_id: int, now: datetime) -> HostSystem:
        query = f"select {COLUMNS} from pscomppars where tic_id = 'TIC {int(tic_id)}'"
        url = TAP_URL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
        req = urllib.request.Request(url, headers={"User-Agent": "planet-hunter-api"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:  # noqa: S310
            rows = json.load(r)
        if not isinstance(rows, list):
            raise ValueError("unexpected answer from the NASA Exoplanet Archive")
        return host_system(tic_id, rows, now)
