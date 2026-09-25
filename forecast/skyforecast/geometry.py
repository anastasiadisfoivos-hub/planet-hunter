"""Sky geometry: spherical caps, a deterministic point grid over a cap, HEALPix lookups."""

from __future__ import annotations

import math
import re
from functools import lru_cache

import astropy.units as u
import numpy as np
from astropy.coordinates import BarycentricMeanEcliptic, Galactic, SkyCoord
from astropy_healpix import HEALPix

from .contract import Sphere

DEG2_PER_SR = (180.0 / math.pi) ** 2
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


def unit_vector(ra_deg, dec_deg) -> np.ndarray:
    ra = np.radians(ra_deg)
    dec = np.radians(dec_deg)
    return np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)], axis=-1)


def separation_deg(ra1, dec1, ra2, dec2) -> np.ndarray:
    """Great-circle separation (Vincenty form, stable at all angles)."""
    ra1, dec1, ra2, dec2 = map(np.radians, (ra1, dec1, ra2, dec2))
    dra = ra2 - ra1
    num = np.hypot(np.cos(dec2) * np.sin(dra),
                   np.cos(dec1) * np.sin(dec2) - np.sin(dec1) * np.cos(dec2) * np.cos(dra))
    den = np.sin(dec1) * np.sin(dec2) + np.cos(dec1) * np.cos(dec2) * np.cos(dra)
    return np.degrees(np.arctan2(num, den))


def cap_area_deg2(radius_deg: float) -> float:
    """Area of a spherical cap: 2*pi*(1 - cos r) sr, in deg^2."""
    return 2.0 * math.pi * (1.0 - math.cos(math.radians(radius_deg))) * DEG2_PER_SR


@lru_cache(maxsize=64)
def _cap_grid(ra_deg: float, dec_deg: float, radius_deg: float, n: int) -> np.ndarray:
    # Equal-area Fibonacci spiral in the cap's local frame: cos(theta) uniform in [cos r, 1].
    i = np.arange(n) + 0.5
    cos_t = 1.0 - (i / n) * (1.0 - math.cos(math.radians(radius_deg)))
    sin_t = np.sqrt(np.clip(1.0 - cos_t**2, 0.0, None))
    phi = np.arange(n) * GOLDEN_ANGLE
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    centre = np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])
    east = np.array([-math.sin(ra), math.cos(ra), 0.0])
    north = np.cross(centre, east)
    pts = (np.outer(sin_t * np.cos(phi), east) + np.outer(sin_t * np.sin(phi), north)
           + np.outer(cos_t, centre))
    pts.setflags(write=False)
    return pts


def random_cap_points(ra_deg: float, dec_deg: float, radius_deg: float, n: int,
                      rng: np.random.Generator) -> np.ndarray:
    """n unit vectors drawn uniformly at random over a cap."""
    cos_t = 1.0 - rng.random(n) * (1.0 - math.cos(math.radians(radius_deg)))
    sin_t = np.sqrt(np.clip(1.0 - cos_t**2, 0.0, None))
    phi = rng.random(n) * 2 * math.pi
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    centre = np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])
    east = np.array([-math.sin(ra), math.cos(ra), 0.0])
    north = np.cross(centre, east)
    return (np.outer(sin_t * np.cos(phi), east) + np.outer(sin_t * np.sin(phi), north)
            + np.outer(cos_t, centre))


def cap_grid(sphere: Sphere, n: int = 4000) -> np.ndarray:
    """n unit vectors spread uniformly (equal area) over the sphere's cap. Deterministic."""
    return _cap_grid(sphere.ra_deg, sphere.dec_deg, sphere.radius_deg, n)


def xyz_to_radec(xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ra = np.degrees(np.arctan2(xyz[..., 1], xyz[..., 0])) % 360.0
    dec = np.degrees(np.arcsin(np.clip(xyz[..., 2], -1.0, 1.0)))
    return ra, dec


def fraction_within(points: np.ndarray, ra_deg: float, dec_deg: float, radius_deg: float) -> float:
    """Fraction of grid points within radius_deg of (ra, dec)."""
    c = unit_vector(ra_deg, dec_deg)
    return float(np.mean(points @ c >= math.cos(math.radians(radius_deg))))


_GRID_RE = re.compile(r"healpix\s+nside\s*=\s*(\d+)", re.IGNORECASE)


def parse_grid(grid: str) -> HEALPix:
    """'healpix nside=N' -> HEALPix. RING ordering unless the string mentions 'nest'."""
    m = _GRID_RE.search(grid)
    if not m:
        raise ValueError(f"unsupported grid {grid!r}; expected 'healpix nside=N'")
    order = "nested" if "nest" in grid.lower() else "ring"
    return HEALPix(nside=int(m.group(1)), order=order)


def pixels_of(hp: HEALPix, xyz: np.ndarray) -> np.ndarray:
    ra, dec = xyz_to_radec(xyz)
    return np.asarray(hp.lonlat_to_healpix(ra * u.deg, dec * u.deg))


def pixel_area_deg2(hp: HEALPix) -> float:
    return float(hp.pixel_area.to(u.deg**2).value)


def pixel_centres(hp: HEALPix) -> tuple[np.ndarray, np.ndarray]:
    lon, lat = hp.healpix_to_lonlat(np.arange(hp.npix))
    return lon.to_value(u.deg), lat.to_value(u.deg)


def galactic_latitude(ra_deg, dec_deg) -> np.ndarray:
    c = SkyCoord(ra=np.atleast_1d(ra_deg) * u.deg, dec=np.atleast_1d(dec_deg) * u.deg,
                 frame="icrs")
    return c.transform_to(Galactic()).b.to_value(u.deg)


def ecliptic_latitude(ra_deg, dec_deg) -> np.ndarray:
    c = SkyCoord(ra=np.atleast_1d(ra_deg) * u.deg, dec=np.atleast_1d(dec_deg) * u.deg,
                 frame="icrs")
    return c.transform_to(BarycentricMeanEcliptic()).lat.to_value(u.deg)
