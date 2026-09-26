import math

import pytest

from skysources import classes
from skysources.fink import cone_tiles
from skysources.models import validate_sphere
from skysources.sso import heuristic_type, pack_designation, ss_object_id
from skysources.util import sep_deg


@pytest.mark.parametrize(
    "designation,packed",
    [  # verified against Fink /api/v1/sso r:packed_primary_provisional_designation
        ("2011 BU146", "K11BE6U"),
        ("2156 T-2", "T2S2156"),
        ("9085 P-L", "PLS9085"),
        # MPC packing rules
        ("2020 AB", "K20A00B"),
        ("1998 SQ108", "J98SA8Q"),
        ("2007 TA418", "K07Tf8A"),
    ],
)
def test_pack_designation(designation, packed):
    assert pack_designation(designation) == packed


def test_ss_object_id_is_packed_bytes():
    assert ss_object_id("2011 BU146") == 21164710888289877
    assert ss_object_id("A924 EV") is None


def test_sso_heuristics_are_sufficient_conditions():
    assert heuristic_type("2011 BU146", 2.2) == "asteroid"
    assert heuristic_type("2011 BU146", 1.1) == "near_earth_object"
    assert heuristic_type("2014 UZ224", 38.0) == "trans_neptunian_object"
    assert heuristic_type("C/2025 A1", 3.0) == "comet"
    assert heuristic_type("3I/ATLAS", 3.0) == "interstellar_object"


def test_cats_and_catalogue_maps():
    assert classes.cats_type(11)[1] == "supernova"
    assert classes.cats_type(22)[1] == "active_galaxy"
    assert classes.cats_type(12)[1] == "unknown"
    assert classes.cats_type("junk")[1] == "unknown"
    assert classes.simbad_type("QSO") == "active_galaxy"
    assert classes.simbad_type("G") is None  # host galaxy says nothing about the event
    assert classes.simbad_type("Fail") is None
    assert classes.tns_type("SN Ia") == "supernova"
    assert classes.tns_type("TDE-H") == "tidal_disruption_event"
    assert classes.vsx_type("EW") == "eclipsing_binary"
    assert classes.vsx_type("UV") == "flare"
    assert classes.vsx_type("RRAB") == "variable_star"
    assert classes.vsx_type("nan") is None


@pytest.mark.parametrize("dec", [-80.0, -30.0, 0.0, 45.0])
def test_ten_degree_cone_is_covered_by_fink_tiles(dec):
    tiles = cone_tiles(100.0, dec, 10.0)
    assert len(tiles) == 9 and all(r <= 5.0 for *_, r in tiles)
    for i in range(24):  # sample the disc edge and middle
        for frac in (0.5, 0.99):
            b = math.radians(15 * i)
            # point at distance 10*frac, bearing b
            d = math.radians(10 * frac)
            d0 = math.radians(dec)
            d2 = math.asin(math.sin(d0) * math.cos(d) + math.cos(d0) * math.sin(d) * math.cos(b))
            r2 = math.radians(100) + math.atan2(math.sin(b) * math.sin(d) * math.cos(d0), math.cos(d) - math.sin(d0) * math.sin(d2))
            ra, de = math.degrees(r2) % 360, math.degrees(d2)
            assert min(sep_deg(ra, de, t[0], t[1]) for t in tiles) <= 5.0


def test_sphere_limits():
    validate_sphere({"ra_deg": 10, "dec_deg": 5, "radius_deg": 0.05})
    for bad in ({"ra_deg": 10, "dec_deg": 5, "radius_deg": 10.5}, {"ra_deg": 360, "dec_deg": 0, "radius_deg": 1}):
        with pytest.raises(ValueError):
            validate_sphere(bad)
