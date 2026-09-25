import json

from skyspectra import net
from skyspectra.gaia_xp import WAVELENGTH_NM, build_xp, parse_xp
from skyspectra.hosts import read_tic_file, select_hosts
from skyspectra.hypatia import build_abundances

WASP121 = 22529346
HD189733 = 256364928


def test_read_tic_file_formats(tmp_path):
    hosts = tmp_path / "hosts.json"
    hosts.write_text(json.dumps({"source": "x", "tic": [22529346, 256364928], "name": ["a", "b"]}))
    assert read_tic_file(hosts) == [22529346, 256364928]
    lst = tmp_path / "list.json"
    lst.write_text(json.dumps(["TIC 5", 6, {"tic": 7}, 5]))
    assert read_tic_file(lst) == [5, 6, 7]
    txt = tmp_path / "tics.txt"
    txt.write_text("# map hosts\nTIC 22529346\n256364928  # HD 189733\n\n")
    assert read_tic_file(txt) == [22529346, 256364928]


def test_select_hosts_real_archive(replay):
    hosts, missing = select_hosts(net.Net(), [WASP121, HD189733, 1])
    assert missing == [1]
    by = {h.tic: h for h in hosts}
    assert by[WASP121].name == "WASP-121" and by[WASP121].planets == ["WASP-121 b"]
    assert by[WASP121].gaia_dr3 == 5565050255701441664  # the DR3 id, not the '3' in 'Gaia DR3'
    assert by[HD189733].gaia_dr3 == 1827242816201846144


def test_abundances_real_hypatia(replay):
    hosts, _ = select_hosts(net.Net(), [WASP121, HD189733])
    docs = build_abundances(net.Net(), hosts)
    assert set(docs) == {WASP121, HD189733}
    w = docs[WASP121]
    assert w["tic"] == WASP121 and w["name"] == "WASP-121"
    assert w["source"] and w["credit"] and w["licence"]
    fe = next(e for e in w["elements"] if e["symbol"] == "Fe")
    assert fe["x_h_dex"] == 0.23 and fe["err_dex"] == 0.04  # metal-rich host
    for e in w["elements"]:
        assert set(e) >= {"symbol", "x_h_dex", "err_dex"}
        assert -3 < e["x_h_dex"] < 2


def test_parse_xp_rejects_wrong_grid():
    import pytest

    with pytest.raises(ValueError):
        parse_xp('source_id,solution_id,ra,dec,flux,flux_error\n1,2,3,4,"(1.0, 2.0)","(0.1, 0.1)"\n')


def test_gaia_xp_real(replay):
    hosts, _ = select_hosts(net.Net(), [WASP121, HD189733])
    docs = build_xp(net.Net(), hosts)
    assert set(docs) == {WASP121, HD189733}
    d = docs[WASP121]
    assert d["wavelength_nm"] == WAVELENGTH_NM and (WAVELENGTH_NM[0], WAVELENGTH_NM[-1]) == (336.0, 1020.0)
    assert len(d["flux"]) == len(d["flux_error"]) == 343
    assert d["gaia_dr3_source_id"] == "5565050255701441664"
    assert "CC BY-SA 3.0 IGO" in d["licence"] and d["source"] and d["credit"]
    # an F6 star (~6,500 K): brighter in the blue-green than in the near-IR
    assert max(d["flux"]) > 3 * d["flux"][-1] > 0
