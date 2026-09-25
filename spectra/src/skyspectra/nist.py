"""elements.json: the strongest lines of ~20 astronomically important elements, from NIST ASD.

For every element we ask the NIST Atomic Spectra Database for the lines of its neutral (I) and,
where it matters in stars, singly ionised (II) spectrum between 300 and 1100 nm (near-UV,
visible, near-IR), keep the lines NIST gives a relative intensity for, and pick the strongest.

NIST relative intensities are only comparable within one spectrum (one ion), so
`relative_intensity` is scaled to 1.0 for the strongest line of that ion in 300-1100 nm;
`nist_intensity` keeps NIST's own number.
"""

from __future__ import annotations

import csv
import html
import io
import re

from . import sources
from .net import DAY, Net
from .sun import FRAUNHOFER

LINES_URL = "https://physics.nist.gov/cgi-bin/ASD/lines1.pl"
VERSION_URL = "https://physics.nist.gov/PhysRefData/ASD/Html/verhist.shtml"
LOW_NM, HIGH_NM = 300.0, 1100.0
MERGE_NM = 0.05  # fine-structure components closer than this are one line at our resolution
VISIBLE_NM = (380.0, 750.0)  # the LAB's main window; n lines from here, a third as many from outside
KEEP_NM = 0.01  # always keep a NIST line this close to a labelled solar Fraunhofer line

# symbol, name, [(spectrum, how many lines to keep)]
ELEMENTS: list[tuple[str, str, list[tuple[str, int]]]] = [
    ("H", "Hydrogen", [("I", 10)]),
    ("He", "Helium", [("I", 10), ("II", 3)]),
    ("Li", "Lithium", [("I", 6)]),
    ("C", "Carbon", [("I", 10), ("II", 5)]),
    ("N", "Nitrogen", [("I", 10), ("II", 5)]),
    ("O", "Oxygen", [("I", 10), ("II", 5)]),
    ("Na", "Sodium", [("I", 8)]),
    ("Mg", "Magnesium", [("I", 10), ("II", 5)]),
    ("Al", "Aluminium", [("I", 8)]),
    ("Si", "Silicon", [("I", 10), ("II", 5)]),
    ("S", "Sulfur", [("I", 8), ("II", 4)]),
    ("K", "Potassium", [("I", 6)]),
    ("Ca", "Calcium", [("I", 10), ("II", 6)]),
    ("Ti", "Titanium", [("I", 10), ("II", 6)]),
    ("Cr", "Chromium", [("I", 10), ("II", 4)]),
    ("Mn", "Manganese", [("I", 8)]),
    ("Fe", "Iron", [("I", 15), ("II", 8)]),
    ("Ni", "Nickel", [("I", 10)]),
    ("Sr", "Strontium", [("I", 5), ("II", 4)]),
    ("Ba", "Barium", [("I", 5), ("II", 5)]),
]

_NUM = re.compile(r"\d+(?:\.\d+)?")


def query_params(spectrum: str) -> dict:
    """The NIST ASD lines-form fields for a tab-separated line list with intensities."""
    return {
        "spectra": spectrum, "low_w": LOW_NM, "upp_w": HIGH_NM, "unit": 1, "de": 0,
        "I_scale_type": 1, "format": 3, "line_out": 0, "en_unit": 0, "output": 0, "page_size": 15,
        "show_obs_wl": 1, "show_calc_wl": 1, "order_out": 0, "show_av": 2, "tsb_value": 0,
        "A_out": 0, "intens_out": "on", "allowed_out": 1, "forbid_out": 1, "conf_out": "on",
        "term_out": "on", "enrg_out": "on", "J_out": "on", "remove_js": "on", "output_type": 0,
        "plot_out": 0, "submit": "Retrieve Data",
    }


def _clean(v: str | None) -> str:
    return (v or "").strip().strip('"').strip()


def parse_intensity(raw: str) -> float | None:
    """NIST intensities carry flags ('5bl', '(700)', '1000h', '25*'); the number is what counts."""
    m = _NUM.search(raw or "")
    return float(m.group()) if m else None


def parse_lines(tsv: str) -> list[dict]:
    """NIST tab-separated output -> [{nm, intensity, aki, type}] (air wavelengths, nm)."""
    if "<html" in tsv[:500].lower():
        raise ValueError("NIST answered with an HTML page (query error)")
    rows = csv.reader(io.StringIO(tsv), delimiter="\t")
    header = [h.strip() for h in next(rows, [])]
    idx = {h: i for i, h in enumerate(header)}
    obs = next((i for h, i in idx.items() if h.startswith("obs_wl")), None)
    ritz = next((i for h, i in idx.items() if h.startswith("ritz_wl")), None)
    if obs is None and ritz is None:
        raise ValueError(f"no wavelength column in NIST header {header}")
    def cell(row: list[str], i: int | None) -> str:
        return _clean(row[i]) if i is not None and i < len(row) else ""

    out = []
    for row in rows:
        wl = cell(row, obs) or cell(row, ritz)
        m = _NUM.search(wl)
        inten = parse_intensity(cell(row, idx.get("intens")))
        if not m or inten is None or inten <= 0:
            continue
        aki = cell(row, idx.get("Aki(s^-1)"))
        out.append({"nm": float(m.group()), "intensity": inten,
                    "aki": float(aki) if aki and _NUM.match(aki) else None,
                    "type": cell(row, idx.get("Type")) or "E1"})
    return out


def merge(lines: list[dict]) -> list[dict]:
    """Merge components closer than MERGE_NM, keeping the brightest."""
    merged: list[dict] = []
    for line in sorted(lines, key=lambda x: x["nm"]):
        if merged and line["nm"] - merged[-1]["nm"] < MERGE_NM:
            if line["intensity"] > merged[-1]["intensity"]:
                merged[-1] = line
            continue
        merged.append(line)
    return merged


def strongest(lines: list[dict], n: int, keep_nm: list[float] = ()) -> list[dict]:
    """The n brightest visible lines, n//3 (at least 2) brightest near-UV/IR ones, and any line
    within KEEP_NM of a wavelength in keep_nm."""
    merged = merge(lines)
    by_brightness = sorted(merged, key=lambda x: -x["intensity"])
    visible = [x for x in by_brightness if VISIBLE_NM[0] <= x["nm"] <= VISIBLE_NM[1]][:n]
    outside = [x for x in by_brightness if not VISIBLE_NM[0] <= x["nm"] <= VISIBLE_NM[1]][:max(2, n // 3)]
    kept = [x for x in merged if any(abs(x["nm"] - k) <= KEEP_NM for k in keep_nm)]
    chosen = {id(x): x for x in visible + outside + kept}
    return sorted(chosen.values(), key=lambda x: x["nm"])


def nist_version(net: Net) -> dict:
    """The current ASD version and NIST's own suggested citation."""
    raw = re.sub(r"<[^>]+>", " ", net.text(VERSION_URL, ttl=30 * DAY))
    text = re.sub(r"\s+", " ", html.unescape(raw).replace("\xa0", " "))
    m = re.search(r"(Kramida, A\..*?DOI: https://doi\.org/[\w./]+)", text)
    v = re.search(r"version (\d+\.\d+(?:\.\d+)?)", text)
    return {"version": v.group(1) if v else None, "citation": m.group(1) if m else None}


def element_entry(net: Net, symbol: str, name: str, spectra: list[tuple[str, int]]) -> dict:
    lines = []
    for ion, n in spectra:
        parsed = parse_lines(net.text(LINES_URL, query_params(f"{symbol} {ion}"), ttl=90 * DAY))
        best = strongest(parsed, n, [nm for nm, el, _ in FRAUNHOFER if el == symbol])
        if not best:
            continue
        top = max(x["intensity"] for x in merge(parsed))
        for x in best:
            line = {"nm": round(x["nm"], 4), "relative_intensity": round(x["intensity"] / top, 4),
                    "ion": ion, "species": f"{symbol} {ion}", "nist_intensity": x["intensity"]}
            if x["aki"] is not None:
                line["aki_per_s"] = x["aki"]
            if x["type"] != "E1":
                line["transition"] = x["type"]  # forbidden (M1/E2...) lines
            lines.append(line)
    lines.sort(key=lambda x: x["nm"])
    return {"symbol": symbol, "name": name, "lines": lines}


def build_elements(net: Net, symbols: list[str] | None = None) -> list[dict]:
    """elements.json is a list (the LAB contract); each element carries its own provenance."""
    ver = nist_version(net)
    meta = {
        **sources.meta("nist", version=ver["version"], citation=ver["citation"]),
        "wavelength_medium": "air",
        "window_nm": [LOW_NM, HIGH_NM],
        "intensity_note": ("relative_intensity is NIST's relative intensity scaled to 1.0 for the strongest "
                           "line of that species in the window; only comparable within one species."),
    }
    todo = [e for e in ELEMENTS if symbols is None or e[0] in symbols]
    return [{**element_entry(net, *e), **meta} for e in todo]
