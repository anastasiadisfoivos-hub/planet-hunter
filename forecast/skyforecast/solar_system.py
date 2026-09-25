"""Known solar-system objects from SkyBoT: pass-through plus predicted catches.

Per object j, a visit i "covers" it when j is inside both the sphere and visit i's footprint at
the visit epoch, and j is at least as bright as the single-visit depth in that band. Then

    P_j = 1 - prod_{i covering j} (1 - q_i)

and for predictable type t:   mu_t = sum_{j in t} P_j + (1 - kappa_t) * mu_t_base
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .config import ForecastConfig
from .contract import CatchType, KnownSolarSystemObject, Sphere
from .geometry import separation_deg
from .providers import SkybotObject, SkybotProvider


def classify(sso_class: str) -> CatchType:
    """Map a SkyBoT class string to a CatchType."""
    c = sso_class.strip().lower()
    if "interstellar" in c:
        return CatchType.interstellar_object
    if c.startswith("comet"):
        return CatchType.comet
    if c.startswith("nea") or any(k in c for k in ("apollo", "aten", "amor", "atira")):
        return CatchType.near_earth_object
    if c.startswith(("kbo", "tno", "sdo", "centaur")) or "centaur" in c:
        return CatchType.trans_neptunian_object
    return CatchType.asteroid  # MB, Hungaria, Mars-Crosser, Trojan, Hilda, unclassified


@dataclass(frozen=True)
class PlannedVisit:
    time: datetime
    ra_deg: float
    dec_deg: float
    band: str
    q: float


@dataclass
class KnownObjectsResult:
    objects: list[KnownSolarSystemObject]
    expected: dict[CatchType, float]  # sum of P_j per type


def _epochs(visits: list[PlannedVisit], cfg: ForecastConfig) -> list[datetime]:
    """Bucket visit times; cap the number of SkyBoT queries by taking evenly spaced buckets."""
    bucket = timedelta(minutes=cfg.skybot_bucket_minutes)
    starts: list[datetime] = []
    for v in sorted(visits, key=lambda v: v.time):
        if not starts or v.time - starts[-1] >= bucket:
            starts.append(v.time)
    if len(starts) > cfg.skybot_max_queries:
        idx = np.linspace(0, len(starts) - 1, cfg.skybot_max_queries).round().astype(int)
        starts = [starts[i] for i in sorted(set(idx))]
    return starts


def _detectable(obj: SkybotObject, band: str, cfg: ForecastConfig) -> bool:
    if obj.v_mag is None:
        return True
    depth = cfg.single_visit_depth.get(band, max(cfg.single_visit_depth.values()))
    return obj.v_mag <= depth


def known_objects_scheduled(sphere: Sphere, visits: list[PlannedVisit],
                            skybot: SkybotProvider, cfg: ForecastConfig,
                            reference_epoch: datetime) -> KnownObjectsResult:
    """With a schedule: query SkyBoT at visit epochs, accumulate per-object catch probability."""
    epochs = _epochs(visits, cfg)
    by_epoch = {e: skybot.cone(sphere.ra_deg, sphere.dec_deg, sphere.radius_deg, e)
                for e in epochs}

    miss: dict[str, float] = {}          # prod (1 - q_i) over covering visits
    seen: dict[str, tuple[float, SkybotObject]] = {}  # name -> (|dt| to reference, row)
    for e, rows in by_epoch.items():
        dt = abs((e - reference_epoch).total_seconds())
        for o in rows:
            if separation_deg(o.ra_deg, o.dec_deg, sphere.ra_deg,
                              sphere.dec_deg) > sphere.radius_deg:
                continue
            if o.name not in seen or dt < seen[o.name][0]:
                seen[o.name] = (dt, o)
    for v in visits:
        e = min(epochs, key=lambda e: abs((e - v.time).total_seconds()))
        for o in by_epoch[e]:
            in_sphere = separation_deg(o.ra_deg, o.dec_deg, sphere.ra_deg,
                                       sphere.dec_deg) <= sphere.radius_deg
            in_fov = separation_deg(o.ra_deg, o.dec_deg, v.ra_deg, v.dec_deg) <= cfg.fov_radius_deg
            if in_sphere and in_fov and _detectable(o, v.band, cfg):
                miss[o.name] = miss.get(o.name, 1.0) * (1.0 - v.q)

    return _result(seen, {name: 1.0 - m for name, m in miss.items()})


def known_objects_unscheduled(sphere: Sphere, epoch: datetime, skybot: SkybotProvider,
                              p_catch: float, cfg: ForecastConfig) -> KnownObjectsResult:
    """No usable visit list: one query at window mid, and every detectable object gets the same
    catch probability p_catch (1 - exp(-V) for climatological visits V; 0 when nothing visits)."""
    rows = skybot.cone(sphere.ra_deg, sphere.dec_deg, sphere.radius_deg, epoch)
    p = p_catch
    deepest = max(cfg.single_visit_depth.values())
    rows = [o for o in rows if separation_deg(o.ra_deg, o.dec_deg, sphere.ra_deg,
                                              sphere.dec_deg) <= sphere.radius_deg]
    seen = {o.name: (0.0, o) for o in rows}
    probs = {o.name: p for o in rows if o.v_mag is None or o.v_mag <= deepest}
    return _result(seen, probs)


def _result(seen: dict[str, tuple[float, SkybotObject]],
            probs: dict[str, float]) -> KnownObjectsResult:
    objects = []
    expected: dict[CatchType, float] = {}
    for name in sorted(seen):
        o = seen[name][1]
        t = classify(o.sso_class)
        objects.append(KnownSolarSystemObject(o.name, t, o.ra_deg, o.dec_deg))
        expected[t] = expected.get(t, 0.0) + probs.get(name, 0.0)
    return KnownObjectsResult(objects=objects, expected=expected)
