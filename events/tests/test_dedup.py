from __future__ import annotations

from skyevents.dedup import dedup, norm_name
from skyevents.util import make_event, sky


def ev(source, sid, type="supernova", ra=10.0, dec=20.0, err=1 / 3600, t="2026-09-20T00:00:00Z",
       basis="machine_guess", names=(), images=(), reported=None):
    return make_event(
        source=source, source_id=sid, type=type, title=f"{source} {sid}", summary="x.",
        source_url=f"https://example.org/{source}/{sid}", observed_at=t, reported_at=reported or t,
        location=sky(ra, dec, err), confidence=0.5, confidence_basis=basis,
        images=[{"url": u, "kind": "cutout_new", "caption": "", "credit": "", "license": "", "width": None, "height": None}
                for u in images],
        raw={"names": list(names)},
    )


def test_norm_name():
    assert norm_name("SN 2026acow") == norm_name("AT 2026acow") == norm_name("2026acow") == "2026acow"
    assert norm_name("ZTF26abwpgne") == "ztf26abwpgne"
    assert norm_name("GRB 260920B") == "grb260920b"


def test_name_match_joins_across_sources_and_keeps_both_links():
    a = ev("tns", "2026acow", basis="official_report", names=["SN 2026acow", "ZTF26abwpgne"], t="2026-09-20T00:00:00Z")
    b = ev("ztf", "ZTF26abwpgne", ra=50, dec=-10, names=["ZTF26abwpgne"], t="2026-09-25T00:00:00Z", images=["https://i/1"])
    [m] = dedup([a, b])
    assert m["id"] == "tns:2026acow"  # official report wins
    assert {s["id"] for s in m["raw"]["sources"]} == {"tns:2026acow", "ztf:ZTF26abwpgne"}
    assert m["raw"]["merged_ids"] == ["ztf:ZTF26abwpgne"]
    assert m["observed_at"] == "2026-09-25T00:00:00Z" and m["raw"]["first_observed_at"] == "2026-09-20T00:00:00Z"
    assert m["reported_at"] == "2026-09-20T00:00:00Z"
    assert [i["url"] for i in m["images"]] == ["https://i/1"]


def test_position_and_time_match_for_transients():
    a = ev("rubin", "1", ra=10.0, dec=20.0, err=0.1 / 3600)
    b = ev("ztf", "Z", ra=10.0 + 1.0 / 3600, dec=20.0, err=0.5 / 3600, t="2026-10-15T00:00:00Z")
    [m] = dedup([a, b])
    assert m["location"]["error_deg"] == round(0.1 / 3600, 8)  # tightest position kept


def test_no_match_when_far_apart_in_space_or_time():
    a = ev("rubin", "1")
    assert len(dedup([a, ev("ztf", "far", ra=10.0 + 10 / 3600)])) == 2
    assert len(dedup([a, ev("ztf", "late", t="2027-01-01T00:00:00Z")])) == 2


def test_incompatible_types_do_not_merge_but_unknown_does():
    a = ev("rubin", "1", type="variable_star")
    assert len(dedup([a, ev("ztf", "Z", type="supernova")])) == 2
    [m] = dedup([ev("rubin", "1", type="unknown"), ev("ztf", "Z", type="supernova")])
    assert m["type"] == "supernova"


def test_same_source_never_merges_by_position():
    assert len(dedup([ev("rubin", "1"), ev("rubin", "2")])) == 2


def test_same_id_twice_becomes_one():
    assert len(dedup([ev("mpc", "X1", type="comet"), ev("mpc", "X1", type="comet")])) == 1


def test_high_energy_needs_overlapping_errors_and_the_same_hour():
    grb = ev("gcn", "GRB_1", type="gamma_ray_burst", err=0.05, t="2026-09-25T07:13:02Z", basis="official_report")
    near = ev("icecube", "n1", type="gamma_ray_burst", ra=10.03, err=0.05, t="2026-09-25T07:30:00Z")
    later = ev("icecube", "n2", type="gamma_ray_burst", ra=10.03, err=0.05, t="2026-09-25T09:30:00Z")
    assert len(dedup([grb, near])) == 1
    assert len(dedup([grb, later])) == 2
    nu = ev("icecube", "n3", type="neutrino", err=1.0, t="2026-09-25T07:13:05Z")
    assert len(dedup([grb, nu])) == 2  # a neutrino is not the burst, however close


def test_solar_system_joins_by_name_only():
    a = ev("mpc", "P1", type="comet", names=["P1"])
    b = ev("jpl", "C/2026_S1", type="comet", names=["C/2026 S1"])
    assert len(dedup([a, b])) == 2
    b["raw"]["names"] = ["P1"]
    assert len(dedup([a, b])) == 1


def test_transitive_clusters():
    a = ev("tns", "2026x", basis="official_report", names=["2026x", "ZTF1"])
    b = ev("ztf", "ZTF1", names=["ZTF1"])
    c = ev("rubin", "9", names=["AT 2026x"], ra=40, dec=40)
    [m] = dedup([a, b, c])
    assert len(m["raw"]["sources"]) == 3
