import json
from collections import Counter

from contract import assert_discovery
from fixtures import scenarios as sc
from recording import HTTP_DIR

from skysources.alerts import alerts, classify_fink_row, fink_row_to_discovery, light_curve
from skysources.util import sep_deg


def _recorded_cone(name):
    doc = json.loads((HTTP_DIR / f"{name}.json").read_text())
    return next(json.loads(v["text"]) for v in doc["responses"].values() if "conesearch" in v["url"])


def test_ecliptic_field_objects_and_asteroids(replay):
    replay("alerts_ecliptic")
    found = alerts(sc.ECLIPTIC, *sc.ECLIPTIC_WINDOW, max_cutout_lookups=sc.ECLIPTIC_CUTOUT_LOOKUPS)
    for d in found:
        assert_discovery(d)
        assert sep_deg(sc.ECLIPTIC["ra_deg"], sc.ECLIPTIC["dec_deg"], d["ra_deg"], d["dec_deg"]) <= 0.3
    kinds = Counter(d["id"].split(":")[1] for d in found)
    assert kinds["obj"] > 0 and kinds["ss"] > 0
    ids = [d["id"] for d in found]
    assert len(ids) == len(set(ids)), "one Discovery per object"
    assert [d["detected_at"] for d in found] == sorted((d["detected_at"] for d in found), reverse=True)


def test_one_discovery_per_object_uses_latest_alert(replay):
    replay("alerts_deep_field")
    found = alerts(sc.DEEP_FIELD, *sc.DEEP_FIELD_WINDOW)
    rows = _recorded_cone("alerts_deep_field")
    by_id = {d["id"]: d for d in found}
    for r in rows:
        d = by_id[f"rubin:obj:{r['r:diaObjectId']}"]
        assert d["raw"]["alert_count"] == r["r:nDiaSources"]
        assert d["raw"]["latest_diaSourceId"] == str(r["r:diaSourceId"])
        assert f"diaSourceId={r['r:diaSourceId']}&kind=Template" in d["cutouts"]["before"]
        assert "kind=Science" in d["cutouts"]["now"] and "kind=Difference" in d["cutouts"]["difference"]


def test_long_lived_object_is_one_supernova_guess(replay):
    replay("alerts_deep_field")
    found = {d["id"]: d for d in alerts(sc.DEEP_FIELD, *sc.DEEP_FIELD_WINDOW)}
    d = found[f"rubin:obj:{sc.LIGHT_CURVE_OBJECT}"]
    assert d["type"] == "supernova"
    assert d["raw"]["alert_count"] == 100
    assert d["confidence"] > 0.99
    assert "machine guess" in d["explanation"]


def test_catalogue_label_beats_classifier(replay):
    rows = _recorded_cone("alerts_deep_field")
    vsx = next(r for r in rows if r["f:xm_vsx_Type"] == "E")
    catch, conf, basis = classify_fink_row(vsx)
    assert (catch, conf, basis["kind"]) == ("eclipsing_binary", 1.0, "vsx")
    d = fink_row_to_discovery(vsx)
    assert d["known_status"] == "known"


def test_unprocessed_classifier_is_unknown_with_zero_confidence():
    rows = _recorded_cone("alerts_ecliptic")
    r = next(r for r in rows if r["f:clf_cats_class"] == -1 and not r["f:is_cataloged"])
    d = fink_row_to_discovery(r)
    assert (d["type"], d["confidence"], d["known_status"]) == ("unknown", 0.0, "not_on_lists")


def test_asteroid_ids_types_and_cutout_budget(replay):
    replay("alerts_ecliptic")
    found = alerts(sc.ECLIPTIC, *sc.ECLIPTIC_WINDOW, max_cutout_lookups=sc.ECLIPTIC_CUTOUT_LOOKUPS)
    ss = [d for d in found if d["id"].startswith("rubin:ss:")]
    assert all(d["known_status"] == "known" and d["name_if_known"] for d in ss)
    assert sum(1 for d in ss if d["cutouts"]["now"]) <= sc.ECLIPTIC_CUTOUT_LOOKUPS
    assert all(d["type"] in ("asteroid", "near_earth_object", "trans_neptunian_object", "comet") for d in ss)
    # A SkyBoT class was attached where SkyBoT knew the object.
    assert any(d["raw"]["skybot_class"] for d in ss)


def test_asteroid_id_matches_fink_ssObjectId(replay):
    """Fink's /sso answers (recorded) must agree with the ID we compute from the designation."""
    replay("alerts_ecliptic")
    doc = json.loads((HTTP_DIR / "alerts_ecliptic.json").read_text())
    from skysources.sso import ss_object_id

    checked = 0
    for v in doc["responses"].values():
        if v["url"].endswith("/sso"):
            rows = json.loads(v["text"])
            assert ss_object_id(v["json"]["n_or_d"]) == rows[0]["r:ssObjectId"]
            checked += 1
    assert checked >= 1


def test_light_curve(replay):
    replay("alerts_deep_field")
    lc = light_curve(sc.LIGHT_CURVE_OBJECT)
    assert len(lc) == 100
    assert lc == sorted(lc, key=lambda p: p["time"])
    assert set(lc[0]) == {"time", "band", "flux_njy", "flux_err_njy"}
