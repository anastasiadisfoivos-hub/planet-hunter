"""Fake providers returning contract-shaped, deterministic SYNTHETIC data.

Used by tests and worked examples until the real clients in sources/ exist. The rate laws below
are shaped like the real sky (asteroids hug the ecliptic, stars the galactic plane,
extragalactic transients avoid it) but the numbers are invented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import astropy.units as u
import numpy as np
from astropy.coordinates import BarycentricMeanEcliptic, SkyCoord

from .contract import CatchType, Window
from .geometry import (
    ecliptic_latitude,
    galactic_latitude,
    parse_grid,
    pixel_area_deg2,
    pixel_centres,
    separation_deg,
)
from .providers import Exposure, Pointing, SkybotObject


def synthetic_rate(t: CatchType, ecl_lat, gal_lat):
    """Synthetic truth: catches per deg^2 per visit."""
    be, b = np.abs(ecl_lat), np.abs(gal_lat)
    disk = np.exp(-((b / 15.0) ** 2)) + 0.1
    dust = 1.0 - 0.9 * np.exp(-((b / 10.0) ** 2))
    law = {
        CatchType.asteroid: 20.0 * np.exp(-((be / 10.0) ** 2)) + 0.05,
        CatchType.near_earth_object: 0.05 * np.exp(-((be / 25.0) ** 2)) + 0.005,
        CatchType.trans_neptunian_object: 0.02 * np.exp(-((be / 10.0) ** 2)) + 0.001,
        CatchType.comet: 0.002 + 0 * be,
        CatchType.interstellar_object: 1e-6 + 0 * be,
        CatchType.supernova: 0.05 * dust,
        CatchType.active_galaxy: 0.2 * dust,
        CatchType.tidal_disruption_event: 0.001 * dust,
        CatchType.kilonova: 1e-5 * dust,
        CatchType.microlensing: 0.01 * np.exp(-((b / 5.0) ** 2)) + 1e-5,
        CatchType.variable_star: 2.0 * disk,
        CatchType.flare: 0.3 * disk,
        CatchType.eclipsing_binary: 0.5 * disk,
        CatchType.planet_candidate: 0.001 + 0 * b,
        CatchType.unknown: 0.01 + 0 * b,
    }
    return law[t]


def synthetic_visits(dec_deg) -> np.ndarray:
    """Rubin-like exposure over a year: ~180 visits in the south, tapering to 0 above +33."""
    dec = np.asarray(dec_deg)
    return np.where(dec < 33.0, 180.0 * np.clip((33.0 - dec) / 40.0, 0.15, 1.0), 0.0)


@dataclass
class FakeHeatmap:
    nside: int = 32
    seed: int = 1
    span_days: float = 365.0
    generated_at: str = "2026-09-24T12:00:00Z"
    _cache: tuple[dict, Exposure] | None = field(default=None, repr=False)

    def _build(self) -> tuple[dict, Exposure]:
        if self._cache is None:
            grid = f"healpix nside={self.nside}"
            hp = parse_grid(grid)
            area = pixel_area_deg2(hp)
            ra, dec = pixel_centres(hp)
            be, b = ecliptic_latitude(ra, dec), galactic_latitude(ra, dec)
            visits = synthetic_visits(dec)
            rng = np.random.default_rng(self.seed)
            per_type = {t: rng.poisson(synthetic_rate(t, be, b) * area * visits)
                        for t in CatchType}
            cells = []
            for pix in range(hp.npix):
                counts = {str(t): int(c[pix]) for t, c in per_type.items() if c[pix] > 0}
                if counts:
                    cells.append({"pix": pix, "counts": counts})
            heatmap = {"generated_at": self.generated_at, "grid": grid, "cells": cells}
            exposure = Exposure(grid=grid, span_days=self.span_days,
                                visits={i: float(v) for i, v in enumerate(visits) if v > 0})
            self._cache = (heatmap, exposure)
        return self._cache

    def heatmap(self) -> dict:
        return self._build()[0]

    def exposure(self) -> Exposure:
        return self._build()[1]


@dataclass
class FakeSchedule:
    """Tonight's fake plan: fields tiled on a ~3 deg grid over the given RA/Dec boxes, each
    visited twice ~33 min apart (Rubin takes visit pairs for asteroid linking)."""

    night_start: datetime = datetime(2026, 9, 26, 0, 0, tzinfo=UTC)
    boxes: tuple[tuple[float, float, float, float], ...] = (
        (-40.0, 40.0, -15.0, 18.0),    # ecliptic band around opposition (RA ~0h in late Sep)
        (-5.0, 35.0, -40.0, -15.0),    # south galactic cap
    )
    spacing_deg: float = 3.0
    bands: tuple[str, ...] = ("g", "r", "i", "z")
    p_exec: float | None = None

    def all_pointings(self) -> list[Pointing]:
        fields = []
        for ra0, ra1, d0, d1 in self.boxes:
            dec = d0
            while dec <= d1 + 1e-9:
                step = self.spacing_deg / max(math.cos(math.radians(dec)), 0.1)
                ra = ra0
                while ra <= ra1 + 1e-9:
                    fields.append((ra % 360.0, dec))
                    ra += step
                dec += self.spacing_deg
        out = []
        slot = timedelta(seconds=40)  # 30 s exposure + overheads
        for k, (ra, dec) in enumerate(fields):
            t1 = self.night_start + k * slot
            band = self.bands[k % len(self.bands)]
            out.append(Pointing(t1, ra, dec, band, self.p_exec))
            out.append(Pointing(t1 + timedelta(minutes=33), ra, dec, band, self.p_exec))
        return out

    def pointings(self, window: Window) -> list[Pointing]:
        return [p for p in self.all_pointings() if window.contains(p.time)]


@dataclass
class FakeSkybot:
    """A synthetic asteroid belt around the ecliptic, drifting retrograde at opposition."""

    n_objects: int = 60000
    seed: int = 7
    epoch0: datetime = datetime(2026, 9, 26, 0, 0, tzinfo=UTC)
    _pop: dict | None = field(default=None, repr=False)

    def _population(self) -> dict:
        if self._pop is None:
            rng = np.random.default_rng(self.seed)
            n = self.n_objects
            lon = rng.uniform(-60.0, 60.0, n) % 360.0
            kind = rng.choice(["MB>Middle", "NEA>Apollo", "KBO>Classical", "Comet>JFc"],
                              size=n, p=[0.955, 0.02, 0.02, 0.005])
            width = np.where(kind == "MB>Middle", 8.0, np.where(kind == "NEA>Apollo", 25.0, 5.0))
            lat = np.clip(rng.normal(0.0, width), -89.0, 89.0)
            c = SkyCoord(lon=lon * u.deg, lat=lat * u.deg,
                         frame=BarycentricMeanEcliptic()).icrs
            rate = np.where(kind == "NEA>Apollo", -2.0, np.where(kind == "KBO>Classical",
                                                                 -0.02, -0.25))  # deg/day
            self._pop = {
                "name": np.array([f"{k.split('>')[0]}-{i:06d}" for i, k in enumerate(kind)]),
                "kind": kind,
                "ra": c.ra.deg,
                "dec": c.dec.deg,
                "rate": rate,
                "v": rng.uniform(17.0, 26.0, n),
            }
        return self._pop

    def cone(self, ra_deg: float, dec_deg: float, radius_deg: float,
             epoch: datetime) -> list[SkybotObject]:
        p = self._population()
        days = (epoch - self.epoch0).total_seconds() / 86400.0
        ra = (p["ra"] + p["rate"] * days) % 360.0
        m = separation_deg(ra, p["dec"], ra_deg, dec_deg) <= radius_deg
        return [SkybotObject(str(p["name"][i]), str(p["kind"][i]), float(ra[i]),
                             float(p["dec"][i]), float(p["v"][i])) for i in np.flatnonzero(m)]


class Broken:
    """A provider that always fails (any method)."""

    def __getattr__(self, name):
        def fail(*_a, **_k):
            raise ConnectionError("fake outage")
        return fail


@dataclass
class TruthSky:
    """The synthetic truth rates on a fine HEALPix map, for fast lookups while simulating."""

    nside: int = 128
    _maps: dict | None = field(default=None, repr=False)

    def maps(self) -> tuple[object, dict]:
        if self._maps is None:
            hp = parse_grid(f"healpix nside={self.nside}")
            ra, dec = pixel_centres(hp)
            be, b = ecliptic_latitude(ra, dec), galactic_latitude(ra, dec)
            self._maps = {"hp": hp, "rates": {t: synthetic_rate(t, be, b) for t in CatchType}}
        return self._maps["hp"], self._maps["rates"]


def simulate_night(schedule: FakeSchedule, window: Window, rng, truth: TruthSky | None = None,
                   cfg=None, types=tuple(CatchType)) -> tuple[list[dict], list[dict]]:
    """Play out one night against the synthetic truth, once for the whole sky: each planned
    pointing executes with its p_exec; each executed visit yields, per type,
    Poisson(integral of truth rate over its footprint) catches placed where the rate is.
    Returns (discoveries, executed visits). Score many spheres against the same night."""
    from .config import ForecastConfig
    from .contract import Sphere
    from .geometry import cap_area_deg2, cap_grid, pixels_of, random_cap_points, xyz_to_radec

    cfg = cfg or ForecastConfig()
    truth = truth or TruthSky()
    hp, rates = truth.maps()
    n_pts = 2000
    cell = cap_area_deg2(cfg.fov_radius_deg) / n_pts
    field_cache: dict[tuple[float, float], tuple] = {}
    discoveries, executed = [], []
    for p in schedule.pointings(window):
        q = cfg.default_p_exec if p.p_exec is None else p.p_exec
        if rng.random() >= q:
            continue
        executed.append({"time": p.time.isoformat(), "ra_deg": p.ra_deg, "dec_deg": p.dec_deg})
        key = (round(p.ra_deg, 6), round(p.dec_deg, 6))
        if key not in field_cache:
            pts = cap_grid(Sphere(p.ra_deg, p.dec_deg, cfg.fov_radius_deg), n_pts)
            pix = pixels_of(hp, pts)
            field_cache[key] = (*xyz_to_radec(pts), pix)
        _, _, pix = field_cache[key]
        for t in types:
            w = rates[t][pix]
            k = rng.poisson(w.sum() * cell)
            # Thinning: uniform random positions in the footprint, kept with prob rate/max.
            wmax = w.max()
            got_ra, got_dec = [], []
            while len(got_ra) < k:
                pts = random_cap_points(p.ra_deg, p.dec_deg, cfg.fov_radius_deg,
                                        max(2 * (k - len(got_ra)), 16), rng)
                keep = rng.random(len(pts)) * wmax < rates[t][pixels_of(hp, pts)]
                r_, d_ = xyz_to_radec(pts[keep])
                got_ra += r_.tolist()
                got_dec += d_.tolist()
            for j in range(k):
                discoveries.append({"type": t.value, "ra_deg": got_ra[j], "dec_deg": got_dec[j],
                                    "detected_at": p.time.isoformat()})
    return discoveries, executed
