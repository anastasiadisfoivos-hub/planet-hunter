from skyspectra import net
from skyspectra.atmospheres import build_atmospheres, parse_ipac, slug, to_depth
from skyspectra.hosts import select_hosts

IPAC = """\\PL_NAME = WASP-121 b
\\REFERENCE = Evans et al. 2016
|CENTRALWAVELNG|BANDWIDTH|PL_TRANDEP|PL_TRANDEPERR1|PL_TRANDEPERR2|PL_TRANDEPLIM|PL_TRANDEP_AUTHORS|
|        double|   double|    double|        double|        double|         long|              char|
|       microns|  microns|         %|              |              |             |                  |
|          null|     null|      null|          null|          null|         null|              null|
        0.43650   0.08900    1.53141        0.01513       -0.01703             0  Evans et al. 2016
        0.61250   0.11500       null           null           null          null              null
"""


def test_slug():
    assert slug("WASP-121 b") == "wasp-121-b"
    assert slug("HD 189733 b") == "hd-189733-b"


def test_parse_ipac_fixed_width_with_spaces_and_nulls():
    kw, rows = parse_ipac(IPAC)
    assert kw["PL_NAME"] == "WASP-121 b"
    assert rows[0]["CENTRALWAVELNG"] == "0.43650" and rows[0]["PL_TRANDEP_AUTHORS"] == "Evans et al. 2016"
    assert rows[1]["PL_TRANDEP"] is None


def test_to_depth_percent_to_ppm_and_ratio_fallback():
    spec, how = to_depth([
        {"CENTRALWAVELNG": "1.2", "PL_TRANDEP": "1.5", "PL_TRANDEPERR1": "0.01", "PL_TRANDEPERR2": "-0.03"},
        {"CENTRALWAVELNG": "0.8", "PL_RATROR": "0.1", "PL_RATRORERR1": "0.001", "PL_RATRORERR2": "-0.001"},
        {"CENTRALWAVELNG": "2.0", "PL_TRANDEP": "1.0", "PL_TRANDEPLIM": "1"},  # an upper limit: skipped
    ])
    assert spec["wavelength_um"] == [0.8, 1.2]
    assert spec["depth_ppm"] == [10000.0, 15000.0]
    assert spec["err_ppm"] == [200.0, 200.0]
    assert how == "(Rp/Rs)^2 and transit depth"


def test_atmospheres_real_archive(replay):
    n = net.Net()
    hosts, _ = select_hosts(n, [22529346, 256364928])
    docs = build_atmospheres(n, hosts, ["WASP-121 b", "HD 189733 b"])
    assert set(docs) == {"wasp-121-b", "hd-189733-b"}
    w = docs["wasp-121-b"]
    assert w["planet"] == "WASP-121 b" and w["tic"] == 22529346
    assert w["detections"] == [] and w["detections_note"]
    assert w["source"] and w["credit"] and w["licence"]
    sp = w["spectrum"]
    assert len(sp["wavelength_um"]) == len(sp["depth_ppm"]) == len(sp["err_ppm"]) == sp["num_datapoints"]
    # the kept spectrum is the one with the most points
    assert sp["num_datapoints"] == max(s["num_datapoints"] for s in w["spectra_available"])
    assert sp["wavelength_um"] == sorted(sp["wavelength_um"])
    # WASP-121 b blocks ~1.5% of its star: depths are ~10,000-20,000 ppm
    med = sorted(sp["depth_ppm"])[len(sp["depth_ppm"]) // 2]
    assert 10_000 < med < 20_000
    assert len(w["spectra_available"]) > 5


def test_viewer_change_degrades_to_null_spectrum(replay, monkeypatch):
    from skyspectra import atmospheres

    def no_workspace(self):
        raise ValueError("archive atmospheres viewer page has no workspace path")

    monkeypatch.setattr(atmospheres.SpectrumFiles, "workspace", no_workspace)
    n = net.Net()
    hosts, _ = select_hosts(n, [22529346])
    docs = build_atmospheres(n, hosts, ["WASP-121 b"])
    assert docs["wasp-121-b"]["spectrum"] is None
    assert docs["wasp-121-b"]["spectra_available"]
