"""Fake PlanetArchive: WASP-121 b as the archive lists it; every other star hosts nothing."""

from __future__ import annotations

from datetime import datetime

from api.adapters.exoarchive import host_system
from api.models import HostSystem

WASP_121 = 22529346
ROWS: dict[int, list[dict]] = {
    WASP_121: [
        {
            "pl_name": "WASP-121 b", "hostname": "WASP-121", "pl_orbper": 1.27492504,
            "pl_orbsmax": 0.02571, "pl_rade": 19.52604438, "pl_bmasse": 371.85923619,
            "pl_bmassprov": "Mass", "st_mass": 1.33, "st_rad": 1.461, "st_teff": 6628.0,
            "sy_dist": 269.898, "sy_tmag": 10.056,
        }
    ]
}  # fmt: skip


class FakeArchive:
    """`rows[tic]` sets a star's planets; `down` makes every call raise."""

    def __init__(self) -> None:
        self.rows: dict[int, list[dict]] = {k: list(v) for k, v in ROWS.items()}
        self.down = False
        self.calls: list[int] = []

    def host_system(self, tic_id: int, now: datetime) -> HostSystem:
        self.calls.append(tic_id)
        if self.down:
            raise ConnectionError("NASA Exoplanet Archive did not answer")
        return host_system(tic_id, self.rows.get(tic_id, []), now)
