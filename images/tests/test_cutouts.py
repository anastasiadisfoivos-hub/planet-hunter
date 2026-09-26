from skypictures import cutouts


def ev(**kw):
    base = {"id": "x", "type": "supernova", "source_url": "", "raw": {},
            "location": {"frame": "sky", "ra_deg": 1.0, "dec_deg": 2.0, "error_deg": 0.0}}
    return {**base, **kw}


def test_rubin_id_from_skysources_raw():
    assert cutouts.rubin_source_id(ev(raw={"latest_diaSourceId": "170666304334200861"})) == "170666304334200861"


def test_rubin_id_from_fink_row_and_nested():
    assert cutouts.rubin_source_id(ev(raw={"r:diaSourceId": 17066630433420086})) == "17066630433420086"
    assert cutouts.rubin_source_id(ev(raw={"alert": {"diaSourceId": 42}})) == "42"


def test_rubin_id_from_cutout_urls():
    url = cutouts.LSST_API + "/cutouts?diaSourceId=123456&kind=Science&output-format=PNG"
    assert cutouts.rubin_source_id(ev(raw={"cutouts": {"now": url}})) == "123456"


def test_missing_and_placeholder_ids_are_ignored():
    assert cutouts.rubin_source_id(ev(raw={"latest_diaSourceId": None, "r:diaSourceId": 0})) is None
    assert cutouts.survey_cutouts(ev()) == []


def test_ztf_ids():
    assert cutouts.ztf_ids(ev(raw={"i:objectId": "ZTF22abegjtx", "i:candid": 3551357696315015003})) == (
        "ZTF22abegjtx", "3551357696315015003")
    assert cutouts.ztf_ids(ev(id="ztf:ZTF20abwtifz")) == ("ZTF20abwtifz", None)
    assert cutouts.ztf_ids(ev(source_url="https://fink-portal.org/ZTF18aaaaljy")) == ("ZTF18aaaaljy", None)
    assert cutouts.ztf_ids(ev(raw={"objectId": "not-ztf"})) is None


def test_rubin_triplet_order_urls_and_captions():
    imgs = cutouts.survey_cutouts(ev(raw={"latest_diaSourceId": "99", "r:band": "i",
                                          "r:midpointMjdTai": 61235.4187436385}))
    assert [i["kind"] for i in imgs] == ["cutout_reference", "cutout_new", "cutout_difference"]
    assert [i["url"].split("kind=")[1].split("&")[0] for i in imgs] == ["Template", "Science", "Difference"]
    assert all(i["url"].startswith(cutouts.LSST_API + "/cutouts?diaSourceId=99&") for i in imgs)
    assert "i band, 2026-07-14 10:02 UTC" in imgs[1]["caption"]
    assert imgs[2]["caption"].startswith("Rubin difference image: the new light only")
    assert all("Rubin Observatory" in i["credit"] and "Fink" in i["credit"] for i in imgs)


def test_rubin_preferred_over_ztf_when_both_present():
    imgs = cutouts.survey_cutouts(ev(raw={"latest_diaSourceId": "99", "objectId": "ZTF22abegjtx"}))
    assert "lsst" in imgs[0]["url"]


def test_ztf_without_candid_says_latest_alert():
    imgs = cutouts.survey_cutouts(ev(id="ztf:ZTF20abwtifz"))
    assert "candid" not in imgs[0]["url"]
    assert "its latest alert" in imgs[1]["caption"]
    assert imgs[2]["caption"].startswith("ZTF difference image: the new light only")
