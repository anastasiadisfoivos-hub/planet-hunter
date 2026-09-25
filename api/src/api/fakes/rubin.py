"""Fake Rubin alert source: a deterministic, sky-fixed population of transients.

The sky is split into 1x1 degree cells. Each cell has a fixed set of objects, and each object
fires alerts on some nights. The same object can therefore show up across nights and overlapping
traps, always under one object-level ID.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, time, timedelta

from api.contract import SOLAR_SYSTEM_TYPES, CatchType, Cutouts, Discovery, Link, Sphere
from api.geometry import angular_distance_deg

_TYPES: list[tuple[CatchType, float]] = [
    (CatchType.asteroid, 0.30),
    (CatchType.variable_star, 0.18),
    (CatchType.supernova, 0.14),
    (CatchType.active_galaxy, 0.10),
    (CatchType.near_earth_object, 0.05),
    (CatchType.flare, 0.05),
    (CatchType.trans_neptunian_object, 0.04),
    (CatchType.comet, 0.03),
    (CatchType.eclipsing_binary, 0.03),
    (CatchType.tidal_disruption_event, 0.02),
    (CatchType.microlensing, 0.02),
    (CatchType.kilonova, 0.005),
    (CatchType.interstellar_object, 0.005),
    (CatchType.unknown, 0.03),
]

_WHY = {
    CatchType.asteroid: "a point of light that moved between exposures, like a main-belt asteroid",
    CatchType.near_earth_object: "a fast-moving point, consistent with a near-Earth object",
    CatchType.trans_neptunian_object: "a very slow, faint moving point, like a distant icy body",
    CatchType.comet: "a moving source that looks slightly fuzzy, consistent with a comet",
    CatchType.interstellar_object: "a moving source on an unusual path; this is a long-shot guess",
    CatchType.supernova: "a new brightening next to a galaxy that was not there before",
    CatchType.active_galaxy: "the core of a galaxy flickering in brightness",
    CatchType.tidal_disruption_event: "a flare at the very centre of a galaxy",
    CatchType.microlensing: "a star that brightened smoothly and symmetrically",
    CatchType.kilonova: "a fast-fading red flash; rare, so treat this guess with caution",
    CatchType.variable_star: "a star whose brightness changes from night to night",
    CatchType.flare: "a star that brightened sharply for a short time",
    CatchType.eclipsing_binary: "a star that dims at regular intervals, as when two stars eclipse",
    CatchType.unknown: "a change in brightness that doesn't fit a clear pattern yet",
}


def _pick_type(rng: random.Random) -> CatchType:
    x = rng.random() * sum(w for _, w in _TYPES)
    for t, w in _TYPES:
        x -= w
        if x <= 0:
            return t
    return CatchType.unknown


class FakeAlertSource:
    def __init__(self, objects_per_cell: float = 0.6, active_prob: float = 0.35, seed: int = 0):
        self.objects_per_cell = objects_per_cell
        self.active_prob = active_prob
        self.seed = seed
        self.calls = 0

    def alerts_in_sphere(self, sphere: Sphere, since: datetime, until: datetime) -> list[Discovery]:
        self.calls += 1
        found: dict[str, Discovery] = {}
        for cell in _cells_touching(sphere):
            for obj in self._objects(cell):
                d = self._first_detection(obj, since, until)
                if d is None:
                    continue
                ra, dec = obj["pos"](d)
                if angular_distance_deg(ra, dec, sphere.ra_deg, sphere.dec_deg) > sphere.radius_deg:
                    continue
                found[obj["id"]] = self._discovery(obj, d, ra, dec)
        return sorted(found.values(), key=lambda x: (x.detected_at, x.id), reverse=True)

    def _objects(self, cell: tuple[int, int]) -> list[dict]:
        ra0, dec0 = cell
        rng = random.Random(f"{self.seed}:cell:{ra0}:{dec0}")
        n = sum(1 for _ in range(3) if rng.random() < self.objects_per_cell / 3)
        objs = []
        for k in range(n):
            ctype = _pick_type(rng)
            ra, dec = ra0 + rng.random(), min(89.999, dec0 + rng.random())
            num = (ra0 + 360) * 1_000_000 + (dec0 + 90) * 1_000 + k
            moving = ctype in SOLAR_SYSTEM_TYPES
            drift = (rng.uniform(-0.25, 0.25), rng.uniform(-0.1, 0.1)) if moving else (0.0, 0.0)
            ref = date(2026, 1, 1)

            def pos(dt: datetime, ra=ra, dec=dec, drift=drift, ref=ref) -> tuple[float, float]:
                days = (dt.date() - ref).days % 4 if drift != (0.0, 0.0) else 0
                d = max(-90.0, min(90.0, dec + drift[1] * days))
                return (ra + drift[0] * days) % 360, d

            objs.append(
                {
                    "id": f"rubin:{'ss' if moving else 'obj'}:{num}",
                    "num": num,
                    "type": ctype,
                    "confidence": round(rng.uniform(0.35, 0.95), 2),
                    "known": rng.random() < 0.4,
                    "pos": pos,
                }
            )
        return objs

    def _first_detection(self, obj: dict, since: datetime, until: datetime) -> datetime | None:
        day = since.date()
        while day <= until.date():
            rng = random.Random(f"{self.seed}:night:{obj['num']}:{day.isoformat()}")
            if rng.random() < self.active_prob:
                t = datetime.combine(day, time(), tzinfo=UTC) + timedelta(
                    seconds=rng.randrange(86_400)
                )
                if since <= t < until:
                    return t
            day += timedelta(days=1)
        return None

    def _discovery(self, obj: dict, detected: datetime, ra: float, dec: float) -> Discovery:
        t: CatchType = obj["type"]
        moving = obj["id"].startswith("rubin:ss:")
        name = None
        if obj["known"]:
            name = f"FAKE {'2026 ' if moving else ''}{obj['num'] % 100000}"
        return Discovery(
            id=obj["id"],
            type=t,
            confidence=obj["confidence"],
            source="rubin",
            origin="fake-rubin-alerts",
            ra_deg=round(ra, 6),
            dec_deg=round(dec, 6),
            detected_at=detected,
            name_if_known=name,
            known_status="known" if obj["known"] else "not_on_lists",
            cutouts=Cutouts(),
            light_curve=None,
            explanation=(
                f"Best guess: {t.value.replace('_', ' ')} "
                f"(confidence {obj['confidence']:.2f}). We saw {_WHY[t]}."
            ),
            links=[Link(label="About Rubin alerts", url="https://rubinobservatory.org/")],
            raw={"fake": True, "object_num": obj["num"]},
        )


def _cells_touching(sphere: Sphere) -> list[tuple[int, int]]:
    dec_lo = max(-90.0, sphere.dec_deg - sphere.radius_deg)
    dec_hi = min(90.0, sphere.dec_deg + sphere.radius_deg)
    near_pole = dec_hi >= 89.999 or dec_lo <= -89.999
    worst = max(abs(dec_lo), abs(dec_hi))
    cosd = math.cos(math.radians(min(worst, 89.999)))
    half_ra = 180.0 if near_pole else min(180.0, sphere.radius_deg / max(cosd, 1e-6))
    cells = []
    for dec0 in range(math.floor(dec_lo), min(89, math.floor(dec_hi)) + 1):
        if half_ra >= 180.0:
            ras = range(0, 360)
        else:
            lo = math.floor(sphere.ra_deg - half_ra)
            ras = [r % 360 for r in range(lo, math.floor(sphere.ra_deg + half_ra) + 1)]
        cells.extend((ra0, dec0) for ra0 in sorted(set(ras)))
    return cells
