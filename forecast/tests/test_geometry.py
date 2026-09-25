import math

import numpy as np
import pytest

from skyforecast import RUBIN_FOV_DEG2, RUBIN_FOV_RADIUS_DEG, Sphere
from skyforecast.geometry import (
    cap_area_deg2,
    cap_grid,
    fraction_within,
    parse_grid,
    separation_deg,
    xyz_to_radec,
)


def test_fov_is_equal_area_circle_of_9_6_deg2():
    assert RUBIN_FOV_DEG2 == 9.6
    assert cap_area_deg2(RUBIN_FOV_RADIUS_DEG) == pytest.approx(9.6, rel=2e-4)
    assert RUBIN_FOV_RADIUS_DEG == pytest.approx(1.748, abs=1e-3)


def test_cap_area_whole_sky():
    assert cap_area_deg2(180) == pytest.approx(41252.96, rel=1e-6)


@pytest.mark.parametrize("ra,dec,r", [(0, 0, 0.05), (359.9, 89.5, 10), (120, -60, 3)])
def test_grid_points_lie_inside_the_cap(ra, dec, r):
    pts = cap_grid(Sphere(ra, dec, r), 2000)
    pra, pdec = xyz_to_radec(pts)
    assert np.all(separation_deg(pra, pdec, ra, dec) <= r + 1e-9)
    assert np.allclose(np.linalg.norm(pts, axis=1), 1)


def test_fraction_full_none_and_half():
    s = Sphere(40, -20, 1.0)
    pts = cap_grid(s)
    assert fraction_within(pts, 40, -20, 1.748) == 1.0
    assert fraction_within(pts, 50, -20, 1.748) == 0.0
    # A huge footprint centred 90 deg away covers exactly half (great-circle boundary).
    eq = cap_grid(Sphere(40, 0, 1.0))
    assert fraction_within(eq, 130, 0, 90) == pytest.approx(0.5, abs=0.01)


def test_fraction_matches_analytic_lens_small_angle():
    # Two equal flat circles, radius R, centres d apart: lens area formula.
    R, d = 1.0, 1.2
    s = Sphere(10, 0, R)
    f = fraction_within(cap_grid(s, 20000), 10 + d, 0, R)
    lens = 2 * R**2 * math.acos(d / (2 * R)) - d / 2 * math.sqrt(4 * R**2 - d**2)
    assert f == pytest.approx(lens / (math.pi * R**2), abs=0.01)


def test_parse_grid_ordering():
    assert parse_grid("healpix nside=64").order == "ring"
    assert parse_grid("healpix nside=64 nested").order == "nested"
    with pytest.raises(ValueError):
        parse_grid("hexgrid 5")
