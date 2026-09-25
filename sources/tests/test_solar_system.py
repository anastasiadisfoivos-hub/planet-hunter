from collections import Counter

from fixtures import scenarios as sc

from skysources.classes import skybot_class_to_catch_type
from skysources.solar_system import known_solar_system, parse_skybot_votable
from skysources.util import sep_deg


def test_known_objects_from_recorded_skybot(replay):
    replay("skybot")
    objs = known_solar_system(sc.SKYBOT_SPHERE, sc.SKYBOT_TIME)
    assert len(objs) == 56
    types = Counter(o["type"] for o in objs)
    assert types["asteroid"] == 53 and types["trans_neptunian_object"] == 3
    first = next(o for o in objs if o["name"] == "2007 HG81")
    assert first["number"] == "388540" and first["skybot_class"] == "MB>Inner"
    for o in objs:
        assert sep_deg(10.0, 5.0, o["ra_deg"], o["dec_deg"]) <= 0.5 + 1e-3
        assert set(o) >= {"name", "type", "ra_deg", "dec_deg"}


def test_empty_votable_means_no_objects():
    raw = b'<?xml version="1.0"?><vot:VOTABLE><vot:INFO name="QUERY_STATUS" value="OK"/></vot:VOTABLE>'
    assert parse_skybot_votable(raw) == []


def test_skybot_classes():
    assert skybot_class_to_catch_type("NEA>Apollo") == "near_earth_object"
    assert skybot_class_to_catch_type("KBO>Resonant>3:2") == "trans_neptunian_object"
    assert skybot_class_to_catch_type("MB>Hilda") == "asteroid"
    assert skybot_class_to_catch_type("Comet", "C/2025 N1") == "comet"
    assert skybot_class_to_catch_type("Hyperbolic", "3I/ATLAS") == "interstellar_object"
