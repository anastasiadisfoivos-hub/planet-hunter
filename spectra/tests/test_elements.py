from recording import load

from skyspectra import net, nist
from skyspectra.nist import build_elements, merge, parse_intensity, parse_lines, strongest


def _nist_text(spectrum: str) -> str:
    answers = load("sample")["answers"]
    return answers[net.key("GET", nist.LINES_URL, nist.query_params(spectrum), None)]["text"]


def test_parse_intensity_strips_nist_flags():
    assert parse_intensity("5bl") == 5
    assert parse_intensity("(700)") == 700
    assert parse_intensity("1000h") == 1000
    assert parse_intensity("") is None


def test_parse_lines_real_na_i_has_the_d_doublet():
    lines = parse_lines(_nist_text("Na I"))
    nms = [x["nm"] for x in lines]
    assert any(abs(n - 588.995) < 0.001 for n in nms)
    assert any(abs(n - 589.592) < 0.001 for n in nms)
    assert all(300 <= n <= 1100 for n in nms)


def test_parse_lines_rejects_html_error_page():
    import pytest

    with pytest.raises(ValueError):
        parse_lines("<!DOCTYPE html><html><title>NIST ASD : Input Error</title>")


def test_merge_keeps_brightest_close_component():
    lines = [{"nm": 656.2711, "intensity": 100}, {"nm": 656.2852, "intensity": 180}, {"nm": 486.1, "intensity": 50}]
    merged = merge(lines)
    assert [x["nm"] for x in merged] == [486.1, 656.2852]


def test_strongest_prefers_visible_but_keeps_some_uv_ir():
    lines = [{"nm": 300.0 + i, "intensity": 1000 - i} for i in range(10)]  # bright UV
    lines += [{"nm": 500.0 + i, "intensity": 10 + i} for i in range(10)]  # faint visible
    picked = strongest(lines, 4)
    assert sum(380 <= x["nm"] <= 750 for x in picked) == 4
    assert sum(x["nm"] < 380 for x in picked) == 2


def test_build_elements_real_sample(replay):
    els = build_elements(net.Net(), ["H", "Na", "Ca", "Fe"])
    assert isinstance(els, list) and [e["symbol"] for e in els] == ["H", "Na", "Ca", "Fe"]
    by = {e["symbol"]: e for e in els}
    for e in els:
        assert e["source"] and e["credit"] and e["licence"]
        assert e["version"] == "5.12" and "10.18434/T4W30F" in e["citation"]
        assert all({"nm", "relative_intensity"} <= set(ln) for ln in e["lines"])
        assert all(0 < ln["relative_intensity"] <= 1 for ln in e["lines"])

    def line(sym, nm):
        return next(ln for ln in by[sym]["lines"] if abs(ln["nm"] - nm) < 0.01)

    assert line("H", 656.28)["relative_intensity"] == 1.0  # H-alpha is hydrogen's strongest
    assert line("Na", 588.995)["relative_intensity"] == 1.0
    assert line("Na", 589.592)["relative_intensity"] == 0.5  # NIST: D1 half of D2
    assert line("Ca", 393.366)["species"] == "Ca II"  # the K line
    # every Fraunhofer line the Sun file labels for these elements is in the line list
    for nm, el, _ in nist.FRAUNHOFER:
        if el in by:
            line(el, nm)
